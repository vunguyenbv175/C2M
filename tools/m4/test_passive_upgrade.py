#!/usr/bin/env python3
"""Offline synthetic integration: bounded HTTP Upgrade + contiguous WS only."""
import base64
import hashlib
import json
import unittest

from test_decode_passive_records import (
    CAM, EPH, PEER, cli_record, libflow_blob, record, srv_record, ws_encode,
)
from decode_passive_records import decode_capture_text

KEY = b"c3ludGhldGljLWtleS0xNg=="  # synthetic sixteen bytes, never a device key
ACCEPT = base64.b64encode(hashlib.sha1(KEY + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
REQUEST = (b"GET /synthetic-private-path HTTP/1.1\r\nHost: synthetic-secret-host\r\n"
           b"Connection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\n"
           b"Sec-WebSocket-Key: " + KEY + b"\r\n\r\n")
RESPONSE = (b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n"
            b"Upgrade: websocket\r\nSec-WebSocket-Accept: " + ACCEPT + b"\r\n\r\n")
WS = ws_encode(2, libflow_blob(), masked=False)


def capture(req=REQUEST, res=RESPONSE, data=WS):
    return "\n".join((cli_record(1, req, 100, dport=26012),
                      srv_record(2, res + data, 200, sport=26012)))


class PassiveUpgradeTests(unittest.TestCase):
    def test_pair_and_no_raw_headers(self):
        rep = decode_capture_text(capture())
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["complete_messages"], 1)
        for flow in rep["flows"]:
            self.assertEqual(flow["http_upgrade"]["status"], "matched_passive_upgrade")
            self.assertEqual(flow["start_boundary"], "matched_passive_upgrade")
        blob = json.dumps(rep)
        for secret in (KEY.decode(), ACCEPT.decode(), "synthetic-secret-host", "synthetic-private-path"):
            self.assertNotIn(secret, blob)

    def test_fragmented_headers_then_fragmented_frame(self):
        lines = []
        pkt = 0
        for server, payload, base in ((False, REQUEST, 100), (True, RESPONSE + WS, 200)):
            off = 0
            for chunk in (payload[:1], payload[1:8], payload[8:80], payload[80:-3], payload[-3:]):
                pkt += 1
                if server:
                    lines.append(srv_record(pkt, chunk, base + off, sport=26012))
                else:
                    lines.append(cli_record(pkt, chunk, base + off, dport=26012))
                off += len(chunk)
        rep = decode_capture_text("\n".join(lines))
        self.assertEqual(rep["complete_messages"], 1)
        self.assertTrue(all(f["http_upgrade"]["status"] == "matched_passive_upgrade" for f in rep["flows"]))
        server = next(f for f in rep["flows"] if f["server_sender"])
        self.assertEqual(server["frames"][0]["stream_offset"], len(RESPONSE))
        self.assertEqual(server["run_bytes_pending"], 0)

    def test_wrong_accept_clears_previously_parsed_frames(self):
        wrong = base64.b64encode(b"x" * 20)
        rep = decode_capture_text(capture(res=RESPONSE.replace(ACCEPT, wrong)))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertTrue(all(f["http_upgrade"]["status"] == "accept_mismatch" for f in rep["flows"]))
        self.assertTrue(all(f["suspended"] == "http_upgrade_accept_mismatch" for f in rep["flows"]))

    def test_response_only_is_not_matched_handshake(self):
        rep = decode_capture_text(srv_record(1, RESPONSE + WS, 200, sport=26012))
        flow = rep["flows"][0]
        self.assertEqual(rep["complete_messages"], 1)
        self.assertEqual(flow["http_upgrade"]["status"], "valid_response_only")
        self.assertNotEqual(flow["start_boundary"], "matched_passive_upgrade")

    def test_request_only_has_no_application_messages(self):
        rep = decode_capture_text(cli_record(1, REQUEST, 100, dport=26012))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["http_upgrade"]["status"], "valid_request_only")

    def test_gap_in_http_never_decodes_later_frame(self):
        rep = decode_capture_text("\n".join((srv_record(1, RESPONSE[:20], 200, sport=26012),
                                             srv_record(2, WS, 500, sport=26012))))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["suspended"], "http_upgrade_gap")

    def test_truncated_http_never_salvages_frame(self):
        rep = decode_capture_text("\n".join((srv_record(1, RESPONSE[:20], 200, sport=26012),
                                             srv_record(2, RESPONSE[20:40], 220, sport=26012,
                                                        truncated=True, advertised=50),
                                             srv_record(3, WS, 270, sport=26012))))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["suspended"], "http_upgrade_gap")

    def test_no_http_search_after_unknown_or_gap(self):
        for payload in (b"junk" + RESPONSE + WS, b"\x00" + RESPONSE + WS):
            rep = decode_capture_text(srv_record(1, payload, 200, sport=26012))
            self.assertEqual(rep["complete_messages"], 0)
        rep = decode_capture_text("\n".join((srv_record(1, WS, 100, sport=26012),
                                             srv_record(2, RESPONSE + WS, 9000, sport=26012))))
        self.assertEqual(rep["complete_messages"], 1)
        self.assertEqual(rep["flows"][0]["http_upgrade"]["status"], "not_observed")

    def test_retransmitted_header_deduplicated(self):
        rep = decode_capture_text("\n".join((srv_record(1, RESPONSE, 200, sport=26012),
                                             srv_record(2, RESPONSE, 200, sport=26012),
                                             srv_record(3, WS, 200 + len(RESPONSE), sport=26012))))
        self.assertEqual(rep["complete_messages"], 1)
        self.assertEqual(rep["flows"][0]["retrans_dedup"], 1)

    def test_wrong_peer_cannot_pair(self):
        a = record(1, REQUEST, 100, sport=EPH, dport=26012, src="c0a82082", dst=CAM)
        rep = decode_capture_text(a + "\n" + srv_record(2, RESPONSE + WS, 200, sport=26012))
        self.assertEqual(rep["input"]["skipped_unknown_endpoint"], 1)
        self.assertEqual(rep["flows"][0]["http_upgrade"]["status"], "valid_response_only")

    def test_ped_warning_native_dict_types_and_no_values(self):
        for body, good in (({"ped_on": True, "pcw_on": False}, True),
                           ({"ped_on": 1, "pcw_on": False}, False),
                           ([{"ped_on": True, "pcw_on": False}], False),
                           ({"ped_on": True}, False),
                           ({"ped_on": True, "pcw_on": False, "private_extra": True}, False),
                           ({"ped_on": True, "pcw_on": False, 7: True}, False)):
            ws = ws_encode(2, libflow_blob(topic="ped", key="pedWarning", body=body), masked=False)
            rep = decode_capture_text(capture(data=ws))
            frame = next(f for f in rep["flows"] if f["server_sender"])["frames"][0]
            self.assertEqual(rep["complete_messages"], 1)
            self.assertEqual(frame["msgpack"]["schema_ok"], good)
            self.assertEqual(frame["recognized"], good)
            self.assertNotIn("private_extra", json.dumps(rep))

    def test_invalid_header_does_not_resume(self):
        invalid = RESPONSE.replace(b"Connection: Upgrade", b"Connection: close")
        rep = decode_capture_text("\n".join((srv_record(1, invalid, 200, sport=26012),
                                             srv_record(2, WS, 200 + len(invalid), sport=26012))))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["suspended"], "invalid_http_upgrade")


if __name__ == "__main__":
    unittest.main()
