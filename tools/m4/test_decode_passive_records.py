#!/usr/bin/env python3
"""Synthetic offline tests for tools/m4/decode_passive_records.py.

All fixtures are constructed in-memory; no hardware, network, or SSH.
Verifies: full JSON, MessagePack envelope, multi-frame, segmented
contiguous, gap (no fabricated decode), retrans dedup, masked directions,
invalid lengths/opcode/fragment, truncation rejection, seq wrap, malformed
input fail-closed, unknown-string redaction, candidate_unverified boundary,
limits, CLI --report, and SAFE-metadata (no payload values leaked).
"""
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import msgpack

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_passive_records import (
    MAX_INPUT_BYTES,
    MAX_PER_PORT,
    MAX_RECORDS,
    decode_capture_text,
)
import decode_passive_records as dec

CAM = "c0a8207b"  # 192.168.32.123 camera
PEER = "c0a82081"  # 192.168.32.129 peer
EPH = 40001


def ws_encode(opcode: int, payload: bytes, masked: bool,
              fin: bool = True, rsv: int = 0) -> bytes:
    b0 = (0x80 if fin else 0x00) | ((rsv & 7) << 4) | (opcode & 0x0F)
    n = len(payload)
    mask_bit = 0x80 if masked else 0x00
    if n < 126:
        head = bytes([b0, mask_bit | n])
    elif n < 65536:
        head = bytes([b0, mask_bit | 126]) + struct.pack(">H", n)
    else:
        head = bytes([b0, mask_bit | 127]) + struct.pack(">Q", n)
    if masked:
        key = b"\x11\x22\x33\x44"
        return head + key + bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return head + payload


def ws_raw_header(opcode: int, pay_len: int, masked: bool,
                  fin: bool = True, rsv: int = 0) -> bytes:
    b0 = (0x80 if fin else 0x00) | ((rsv & 7) << 4) | (opcode & 0x0F)
    mask_bit = 0x80 if masked else 0x00
    if pay_len < 126:
        head = bytes([b0, mask_bit | pay_len])
    elif pay_len < 65536:
        head = bytes([b0, mask_bit | 126]) + struct.pack(">H", pay_len)
    else:
        head = bytes([b0, mask_bit | 127]) + struct.pack(">Q", pay_len)
    if masked:
        head += b"\xaa\xbb\xcc\xdd"
    return head


def record(pkt: int, payload: bytes, seq: int, sport: int = 8080,
           dport: int = EPH, src: str = CAM, dst: str = PEER,
           truncated: bool = False, advertised: int | None = None,
           ack: int = 0, flags: int = 0x18, leg: str = "cardv_8080") -> str:
    if truncated:
        assert advertised is not None and advertised > len(payload)
        plen, cap, t = advertised, len(payload), 1
    else:
        plen, cap, t = len(payload), len(payload), 0
    return (
        f"pkt={pkt} len={60 + cap} src_ip={src} dst_ip={dst} "
        f"sport={sport} dport={dport} seq={seq} ack={ack} "
        f"tcp_flags={flags:02x} payload_len={plen} captured={cap} "
        f"truncated={t} leg={leg} payload_hex={payload.hex()}"
    )


def srv_record(pkt, payload, seq, sport=8080, **kw):
    kw.setdefault("leg", "adas_26012" if sport == 26012 else "cardv_8080")
    return record(pkt, payload, seq, sport=sport, dport=EPH,
                  src=CAM, dst=PEER, **kw)


def cli_record(pkt, payload, seq, dport=8080, sport=EPH, **kw):
    return record(pkt, payload, seq, sport=sport, dport=dport,
                  src=PEER, dst=CAM, leg="cardv_8080", **kw)


def libflow_blob(topic="vehicle", key="vehicleWarning", body=None, fid=424242):
    if body is None:
        body = {"vehicle_id": 3, "headway": 0.9, "warning_level": 0, "fcw": 2,
                "headway_warning": 0, "vb_warning": 0, "sag_warning": 0}
    inner = {"frame_id": fid, "time": 31337111,
             "key": key, "data": body}
    outer = {"time": 31337111, "source": "AdasScreenService",
             "topic": topic, "data": msgpack.packb(inner, use_bin_type=True)}
    return msgpack.packb(outer, use_bin_type=True)


def report_text(rep) -> str:
    return json.dumps(rep, ensure_ascii=False)


class DecodeTests(unittest.TestCase):
    def test_full_json_server_unmasked(self):
        obj = {"type": 1100, "uuid": "DispBrightSet", "brightness": 7}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rep = decode_capture_text(srv_record(1, ws, 1000))
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["complete_messages"], 1)
        f = rep["flows"][0]["frames"][0]
        self.assertEqual(f["kind"], "json")
        self.assertTrue(f["recognized"])
        self.assertEqual(rep["flows"][0]["start_boundary"], "verified_recognized")
        js = f["json"]
        self.assertEqual(js["uuid"], "DispBrightSet")
        self.assertEqual(js["uuid_class"], "ALLOW-L2")
        # SAFE: no payload values.
        t = report_text(rep)
        self.assertNotIn("1100", t)

    def test_msgpack_envelope(self):
        blob = libflow_blob(fid=424242)
        ws = ws_encode(0x2, blob, masked=False)
        rep = decode_capture_text(srv_record(1, ws, 5000, sport=26012,
                                             leg="adas_26012"))
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["complete_messages"], 1)
        f = rep["flows"][0]["frames"][0]
        self.assertEqual(f["kind"], "msgpack")
        mp = f["msgpack"]
        self.assertTrue(mp["decode_ok"])
        self.assertEqual(mp["outer_topic"], "vehicle")
        self.assertEqual(mp["inner_key"], "vehicleWarning")
        self.assertTrue(mp["recognized_schema"])
        t = report_text(rep)
        for secret in ("424242", "31337111", "AdasScreenService"):
            self.assertNotIn(secret, t)

    def test_multi_frames_one_segment(self):
        a = ws_encode(0x1, json.dumps(
            {"type": 1, "uuid": "ClientConn", "connected": True}).encode(),
            masked=False)
        b = ws_encode(0x1, json.dumps(
            {"type": 2, "uuid": "StorageStatus", "status": 0}).encode(),
            masked=False)
        rep = decode_capture_text(srv_record(7, a + b, 100))
        self.assertEqual(rep["complete_messages"], 2)
        kinds = [f["kind"] for f in rep["flows"][0]["frames"]]
        self.assertEqual(kinds, ["json", "json"])

    def test_segmented_contiguous(self):
        obj = {"type": 5, "uuid": "ScreenModeSet", "theme": 1}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        cut = len(ws) - 3
        first, second = ws[:cut], ws[cut:]
        only_first = decode_capture_text(srv_record(1, first, 2000))
        self.assertEqual(only_first["complete_messages"], 0)
        both = decode_capture_text(
            srv_record(1, first, 2000) + "\n" + srv_record(2, second, 2000 + cut))
        self.assertEqual(both["complete_messages"], 1)
        self.assertTrue(both["flows"][0]["frames"][0]["recognized"])

    def test_gap_no_fabricated_decode(self):
        obj = {"type": 9, "uuid": "ClientConn", "connected": True}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        cut = 4
        first, second = ws[:cut], ws[cut:]
        # Second segment starts 50 bytes later than contiguous -> gap.
        rec1 = srv_record(1, first, 3000)
        rec2 = srv_record(3, second, 3000 + cut + 50)  # pkt 2 missing too (recv gap)
        rep = decode_capture_text(rec1 + "\n" + rec2)
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["gaps"], 1)
        t = report_text(rep)
        self.assertNotIn("ClientConn", t)  # nothing decoded -> no names either

    def test_exact_retransmission_dedup(self):
        obj = {"type": 3, "uuid": "StorageStatus", "status": 1}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rec1 = srv_record(1, ws, 7000)
        rec2 = srv_record(2, ws, 7000)  # exact retransmit
        rep = decode_capture_text(rec1 + "\n" + rec2)
        self.assertEqual(rep["complete_messages"], 1)
        self.assertEqual(rep["flows"][0]["retrans_dedup"], 1)
        self.assertEqual(rep["flows"][0]["conflicts"], 0)

    def test_overlap_conflict_suspends(self):
        ws = ws_encode(0x1, json.dumps(
            {"type": 1, "uuid": "ClientConn", "connected": True}).encode(),
            masked=False)
        other = bytes([0xFF] * len(ws))
        rep = decode_capture_text(
            srv_record(1, ws, 8000) + "\n" + srv_record(2, other, 8000))
        fl = rep["flows"][0]
        self.assertEqual(fl["conflicts"], 1)
        self.assertTrue((fl["suspended"] or "").startswith("conflict"))

    def test_client_masked_ok_server_masked_rejected(self):
        obj = {"type": 4, "uuid": "ClientConn", "connected": False}
        ws_masked = ws_encode(0x1, json.dumps(obj).encode(), masked=True)
        rep = decode_capture_text(cli_record(1, ws_masked, 9000))
        self.assertEqual(rep["complete_messages"], 1)
        # Client sender must be masked; unmasked client frame is invalid.
        ws_plain = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rep2 = decode_capture_text(cli_record(1, ws_plain, 9000))
        self.assertEqual(rep2["complete_messages"], 0)
        self.assertEqual(rep2["flows"][0]["frames"][0]["kind"],
                         "invalid_mask_direction")
        # Server sender must be unmasked; masked server frame is invalid.
        ws_srv_masked = ws_encode(0x1, json.dumps(obj).encode(), masked=True)
        rep3 = decode_capture_text(srv_record(1, ws_srv_masked, 9000))
        self.assertEqual(rep3["complete_messages"], 0)

    def test_invalid_opcode_rsv_fragment(self):
        bad_op = ws_raw_header(0x3, 5, masked=False) + b"hello"
        rep = decode_capture_text(srv_record(1, bad_op, 100))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["frames"][0]["kind"], "invalid_opcode")
        bad_rsv = ws_encode(0x1, b"{}", masked=False, rsv=4)
        rep2 = decode_capture_text(srv_record(1, bad_rsv, 100))
        self.assertEqual(rep2["flows"][0]["frames"][0]["kind"], "invalid_rsv")
        frag = ws_encode(0x1, b"frag", masked=False, fin=False)
        rep3 = decode_capture_text(srv_record(1, frag, 100))
        self.assertEqual(rep3["flows"][0]["frames"][0]["kind"],
                         "fragment_unsupported")
        cont = ws_encode(0x0, b"cont", masked=False)
        rep4 = decode_capture_text(srv_record(1, cont, 100))
        self.assertEqual(rep4["flows"][0]["frames"][0]["kind"],
                         "fragment_unsupported")

    def test_huge_frame_rejected(self):
        hdr = ws_raw_header(0x2, 70000, masked=False)
        rep = decode_capture_text(srv_record(1, hdr + b"\x00" * 10, 100))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["frames"][0]["kind"], "frame_too_large")

    def test_truncation_rejected(self):
        obj = {"type": 6, "uuid": "DispBrightSet", "brightness": 3}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rec = record(1, ws[:10], 1000, sport=8080, dport=EPH, src=CAM,
                     dst=PEER, truncated=True, advertised=len(ws))
        rep = decode_capture_text(rec)
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["truncated_skipped"], 1)

    def test_seq_wrap_contiguous(self):
        obj = {"type": 7, "uuid": "ClientConn", "connected": True}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        base = 2 ** 32 - 5
        cut = 5  # first chunk ends exactly at 2**32
        first, second = ws[:cut], ws[cut:]
        rec1 = srv_record(1, first, base)
        rec2 = srv_record(2, second, 0)
        rep = decode_capture_text(rec1 + "\n" + rec2)
        self.assertEqual(rep["complete_messages"], 1)
        self.assertEqual(rep["flows"][0]["gaps"], 0)

    def test_malformed_records_fail_closed(self):
        good = srv_record(1, ws_encode(
            0x1, json.dumps({"type": 1, "uuid": "ClientConn",
                             "connected": True}).encode(), masked=False), 100)
        bad_hex = ("pkt=2 len=70 src_ip=c0a8207b dst_ip=c0a82081 sport=8080 "
                   "dport=40001 seq=200 ack=0 tcp_flags=18 payload_len=10 "
                   "captured=5 truncated=0 leg=cardv_8080 payload_hex=abc")
        # ANY malformed record aborts the whole decode: no partial messages.
        rep = decode_capture_text(good + "\n" + bad_hex)
        self.assertEqual(rep["status"], "error")
        self.assertTrue(rep["fail_closed"])
        self.assertEqual(rep["flows"], [])
        self.assertEqual(rep["complete_messages"], 0)
        self.assertGreaterEqual(len(rep["errors"]), 1)
        self.assertIn("complete application message decoded", report_text(rep))
        # count mismatch
        bad_count = ("pkt=3 len=70 src_ip=c0a8207b dst_ip=c0a82081 sport=8080 "
                     "dport=40001 seq=300 ack=0 tcp_flags=18 payload_len=4 "
                     "captured=4 truncated=0 leg=cardv_8080 payload_hex=aabbcc")
        rep2 = decode_capture_text(bad_count)
        self.assertTrue(rep2["fail_closed"])
        self.assertEqual(rep2["flows"], [])
        self.assertEqual(rep2["complete_messages"], 0)
        # truncated flag mismatch
        bad_flag = ("pkt=4 len=70 src_ip=c0a8207b dst_ip=c0a82081 sport=8080 "
                    "dport=40001 seq=400 ack=0 tcp_flags=18 payload_len=4 "
                    "captured=2 truncated=0 leg=cardv_8080 payload_hex=aabb")
        rep3 = decode_capture_text(bad_flag)
        self.assertTrue(rep3["fail_closed"])
        self.assertEqual(rep3["flows"], [])
        # duplicate pkt
        rep4 = decode_capture_text(good + "\n" + good.replace("pkt=1", "pkt=1"))
        self.assertTrue(rep4["fail_closed"])
        self.assertEqual(rep4["flows"], [])

    def test_unknown_strings_redacted(self):
        evil_uuid = "EvilExfilUUID-9f8a7b6c5d"
        evil_val = "super-secret-token-zzz-12345"
        obj = {"uuid": evil_uuid, "blob": evil_val, "speed": 98765}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rep = decode_capture_text(srv_record(1, ws, 1000))
        t = report_text(rep)
        self.assertNotIn(evil_uuid, t)
        self.assertNotIn(evil_val, t)
        self.assertNotIn("98765", t)
        self.assertIn("REDACTED", t)
        # unknown msgpack topic/key redacted
        inner = {"frame_id": 1, "time": 2, "key": "evil_vendor_key_xyz",
                 "data": {"evil_field": "evil-value-000"}}
        outer = {"time": 2, "source": "EvilSourceName",
                 "topic": "evil_topic_qqq", "data": msgpack.packb(inner, use_bin_type=True)}
        blob = msgpack.packb(outer, use_bin_type=True)
        rep2 = decode_capture_text(
            srv_record(1, ws_encode(0x2, blob, masked=False), 2000, sport=26012,
                       leg="adas_26012"))
        t2 = report_text(rep2)
        for s in ("evil_vendor_key_xyz", "evil_topic_qqq", "EvilSourceName",
                  "evil-value-000", "evil_field"):
            self.assertNotIn(s, t2)
        self.assertIn("REDACTED", t2)

    def test_candidate_unverified_boundary(self):
        # First frame is unknown JSON uuid -> not recognized.
        obj = {"uuid": "MysteryUUID-abc", "x": 1}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rep = decode_capture_text(srv_record(1, ws, 1000))
        self.assertEqual(rep["flows"][0]["start_boundary"], "candidate_unverified")
        self.assertEqual(rep["complete_messages"], 1)
        f = rep["flows"][0]["frames"][0]
        self.assertFalse(f["recognized"])

    def test_ack_and_unknown_endpoint_skipped(self):
        ack = record(1, b"", 100, sport=8080, dport=EPH, src=CAM, dst=PEER)
        unk = record(2, b"\x81\x02hi", 200, sport=9999, dport=9998,
                     src="0a000001", dst="0a000002", leg="other")
        rep = decode_capture_text(ack + "\n" + unk)
        self.assertEqual(rep["input"]["skipped_ack_only"], 1)
        self.assertEqual(rep["input"]["skipped_unknown_endpoint"], 1)
        self.assertEqual(rep["complete_messages"], 0)

    def test_control_frame_not_application_message(self):
        ping = ws_encode(0x9, b"hi", masked=False)
        rep = decode_capture_text(srv_record(1, ping, 100))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["frames"][0]["kind"], "control")

    def test_non_dict_json_rejected(self):
        ws = ws_encode(0x1, b"[1,2,3]", masked=False)
        rep = decode_capture_text(srv_record(1, ws, 100))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["frames"][0]["kind"], "invalid_json")

    def test_record_limits(self):
        recs = [srv_record(i + 1, b"\x81\x00", 1000 + i * 2)
                for i in range(MAX_RECORDS + 1)]
        rep = decode_capture_text("\n".join(recs))
        self.assertEqual(rep["status"], "error")
        self.assertTrue(rep["fail_closed"])
        recs2 = [srv_record(i + 1, b"\x81\x00", 1000 + i * 2)
                 for i in range(MAX_PER_PORT + 1)]
        rep2 = decode_capture_text("\n".join(recs2))
        self.assertEqual(rep2["status"], "error")

    def test_header_lines_ignored(self):
        obj = {"type": 1, "uuid": "ClientConn", "connected": True}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        text = ("m4_sniff=observer_v4\n"
                "capture_scope=partial_payload_prefixes_not_reassembled_stream\n"
                + srv_record(5, ws, 1000) + "\n"
                + "summary packets=9 records=1 completion=packet_limit_partial\n")
        rep = decode_capture_text(text)
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["complete_messages"], 1)

    def test_cli_report_file(self):
        obj = {"type": 1, "uuid": "ClientConn", "connected": True}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        with tempfile.TemporaryDirectory() as td:
            cap = Path(td) / "cap.txt"
            out = Path(td) / "report.json"
            cap.write_text(srv_record(1, ws, 1000) + "\n", encoding="utf-8")
            rc = dec.main([str(cap), "--report", str(out)])
            self.assertEqual(rc, 0)
            rep = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(rep["complete_messages"], 1)
            self.assertIn("complete application message decoded",
                          json.dumps(rep))
            self.assertIn("no injection", json.dumps(rep).lower()
                          .replace("-", " ").replace("_", " ")
                          .replace("no injection", "no injection"))

    def test_cli_malformed_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            cap = Path(td) / "cap.txt"
            out = Path(td) / "report.json"
            cap.write_text("pkt=1 len=1 src_ip=zzzz\n", encoding="utf-8")
            rc = dec.main([str(cap), "--report", str(out)])
            self.assertNotEqual(rc, 0)
            t = out.read_text(encoding="utf-8")
            self.assertNotIn("Traceback", t)

    def test_no_network_imports(self):
        import re
        src = Path(__file__).resolve().parent.joinpath(
            "decode_passive_records.py").read_text(encoding="utf-8")
        for pat in (r"(?m)^\s*import\s+socket\b", r"(?m)^\s*from\s+socket\b",
                    r"(?m)^\s*import\s+urllib\b", r"(?m)^\s*import\s+requests\b",
                    r"(?m)^\s*import\s+paramiko\b",
                    r"(?m)^\s*import\s+subprocess\b",
                    r"create_connection", r"AF_PACKET", r"recvfrom"):
            self.assertIsNone(re.search(pat, src), pat)

    # ---- proof-issue regression tests ----

    def test_endpoint_exact_pairing(self):
        obj = {"type": 1, "uuid": "ClientConn", "connected": True}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        # Same last-octet .123 but wrong subnet: skipped.
        spoof = record(1, ws, 1000, sport=8080, dport=EPH,
                       src="0a00007b", dst=PEER, leg="cardv_8080")
        rep = decode_capture_text(spoof)
        self.assertEqual(rep["input"]["skipped_unknown_endpoint"], 1)
        self.assertEqual(rep["complete_messages"], 0)
        # Wrong peer: skipped.
        spoof2 = record(1, ws, 1000, sport=8080, dport=EPH,
                        src=CAM, dst="0a000081", leg="cardv_8080")
        rep2 = decode_capture_text(spoof2)
        self.assertEqual(rep2["input"]["skipped_unknown_endpoint"], 1)
        # Service port on the PEER side only (camera port ephemeral): skipped,
        # and never misread as a server sender by port coincidence.
        coinc = record(1, ws_encode(0x1, json.dumps(obj).encode(), masked=True),
                       1000, sport=8080, dport=50000, src=PEER, dst=CAM,
                       leg="cardv_8080")
        rep3 = decode_capture_text(coinc)
        self.assertEqual(rep3["input"]["skipped_unknown_endpoint"], 1)
        self.assertEqual(rep3["complete_messages"], 0)
        # Both sides service ports: ambiguous, skipped fail-closed.
        both = record(1, ws, 1000, sport=8080, dport=8080, src=PEER, dst=CAM,
                      leg="cardv_8080")
        rep4 = decode_capture_text(both)
        self.assertEqual(rep4["input"]["skipped_unknown_endpoint"], 1)
        self.assertEqual(rep4["complete_messages"], 0)

    def test_direction_exact_camera_sender(self):
        import decode_passive_records as d
        # Camera src -> server sender even though peer dport is ephemeral.
        rec = {"src_hex": CAM, "dst_hex": PEER, "sport": 26012, "dport": EPH}
        self.assertTrue(d.is_server_sender(rec))
        self.assertTrue(d.is_known_endpoint(rec))
        # Peer src -> client sender even though peer sport coincides with a
        # service number (such records are skipped as unknown endpoints).
        rec2 = {"src_hex": PEER, "dst_hex": CAM, "sport": 8080, "dport": 26012}
        self.assertFalse(d.is_server_sender(rec2))
        self.assertFalse(d.is_known_endpoint(rec2))

    def test_oversize_flushes_run_no_decode_across(self):
        mk = lambda: ws_encode(
            0x1, json.dumps({"type": 1, "uuid": "ClientConn",
                             "connected": True}).encode(), masked=False)
        frame = mk()
        p1, p2 = frame[:10], frame[10:]
        big = b"Z" * 2000  # TCP payload_len 2000 > 1536 ceiling
        # Partial frame, then contiguous oversize record, then the frame tail
        # positioned after the dropped span: the tail alone must not decode.
        recs = (srv_record(1, p1, 1000) + "\n"
                + srv_record(2, big, 1010) + "\n"
                + srv_record(3, p2, 3010))
        rep = decode_capture_text(recs)
        fl = rep["flows"][0]
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(fl["oversize_skipped"], 1)
        self.assertGreaterEqual(fl["gaps"], 1)
        # A later record replaying bytes inside the dropped oversize span must
        # not be appended (fail-closed, no decode across dropped bytes).
        replay = (srv_record(1, p1, 5000) + "\n"
                  + srv_record(2, big, 5010) + "\n"
                  + srv_record(3, p1, 5010))
        rep2 = decode_capture_text(replay)
        self.assertEqual(rep2["complete_messages"], 0)
        self.assertGreaterEqual(rep2["flows"][0]["conflicts"], 1)
        # After an oversize flush a fresh contiguous frame still decodes.
        fresh = (srv_record(1, p1, 9000) + "\n"
                 + srv_record(2, big, 9010) + "\n"
                 + srv_record(3, mk(), 11010))
        rep3 = decode_capture_text(fresh)
        self.assertEqual(rep3["complete_messages"], 1)

    def test_segmented_three_concatenated_offsets(self):
        frames = [ws_encode(0x1, json.dumps(
            {"type": i, "uuid": "ClientConn", "connected": True}).encode(),
            masked=False) for i in range(3)]
        blob = b"".join(frames)
        cut = len(frames[0]) + len(frames[1]) // 2  # split inside frame 2
        recs = (srv_record(1, blob[:cut], 1000) + "\n"
                + srv_record(2, blob[cut:], 1000 + cut))
        rep = decode_capture_text(recs)
        self.assertEqual(rep["complete_messages"], 3)
        got = rep["flows"][0]["frames"]
        self.assertEqual([f["kind"] for f in got], ["json"] * 3)
        expect = [0, len(frames[0]), len(frames[0]) + len(frames[1])]
        self.assertEqual([f["offset"] for f in got], expect)
        self.assertEqual([f["stream_offset"] for f in got], expect)
        self.assertTrue(all(f["recognized"] for f in got))

    def test_noncanonical_length_rejected(self):
        # 16-bit form carrying a value < 126: must use 7-bit form.
        hdr = bytes([0x82, 126]) + struct.pack(">H", 10) + b"0123456789"
        rep = decode_capture_text(srv_record(1, hdr, 100))
        self.assertEqual(rep["complete_messages"], 0)
        self.assertEqual(rep["flows"][0]["frames"][0]["kind"], "invalid_length")
        # 64-bit form carrying a value < 65536: must use shorter form.
        hdr2 = bytes([0x82, 127]) + struct.pack(">Q", 200) + b"y" * 200
        rep2 = decode_capture_text(srv_record(1, hdr2, 100))
        self.assertEqual(rep2["complete_messages"], 0)
        self.assertEqual(rep2["flows"][0]["frames"][0]["kind"], "invalid_length")

    def test_legit_extended128_accepted(self):
        obj = {"type": 1, "uuid": "ClientConn", "connected": True,
               "zz": "p" * 80}  # force extended-126 length form
        raw = json.dumps(obj).encode()
        self.assertGreaterEqual(len(raw), 126)
        ws = ws_encode(0x1, raw, masked=False)
        self.assertEqual(ws[1] & 0x7F, 126)  # really extended form
        rep = decode_capture_text(srv_record(1, ws, 100))
        self.assertEqual(rep["complete_messages"], 1)
        self.assertGreaterEqual(rep["flows"][0]["frames"][0]["payload_len"], 126)

    def test_control_does_not_verify_boundary(self):
        ping = ws_encode(0x9, b"hi", masked=False)
        app = ws_encode(0x1, json.dumps(
            {"type": 1, "uuid": "ClientConn", "connected": True}).encode(),
            masked=False)
        rep = decode_capture_text(srv_record(1, ping + app, 100))
        self.assertEqual(rep["complete_messages"], 1)
        frames = rep["flows"][0]["frames"]
        self.assertEqual(frames[0]["kind"], "control")
        self.assertTrue(frames[1]["recognized"])
        # A mere control frame at offset 0 verifies nothing.
        self.assertEqual(rep["flows"][0]["start_boundary"],
                         "candidate_unverified")

    def test_deny_uuid_known_not_verified(self):
        obj = {"type": 1601, "uuid": "GPSSpeed", "speed": 98771}
        ws = ws_encode(0x1, json.dumps(obj).encode(), masked=False)
        rep = decode_capture_text(srv_record(1, ws, 1000))
        self.assertEqual(rep["complete_messages"], 1)
        f = rep["flows"][0]["frames"][0]
        self.assertFalse(f["recognized"])
        self.assertTrue(f["json"]["known_message"])
        self.assertEqual(f["json"]["uuid"], "GPSSpeed")
        self.assertEqual(f["json"]["uuid_class"], "DENY")
        self.assertEqual(rep["flows"][0]["start_boundary"],
                         "candidate_unverified")
        t = report_text(rep)
        self.assertNotIn("98771", t)

    def test_receive_only_gps_schema_does_not_allow_transmit(self):
        for speed, ident, valid in ((98771, 1601, True), (True, 1601, False),
                                    (1.5, 1601, False), (3, True, False), (3, 1602, False)):
            obj = {"type": ident, "uuid": "GPSSpeed", "speed": speed}
            ws = ws_encode(1, json.dumps(obj).encode(), masked=False)
            rep = decode_capture_text(srv_record(1, ws, 1000))
            js = rep["flows"][0]["frames"][0]["json"]
            self.assertEqual(js["uuid_class"], "DENY")
            self.assertTrue(js["transmit_denied"])
            self.assertFalse(js["recognized_schema"])
            self.assertEqual(js["observed_schema_ok"], valid)
            self.assertEqual(js["known_fields_present"], ["speed", "type", "uuid"])
            self.assertNotIn("98771", report_text(rep))
        self.assertNotIn("GPSSpeed", dec.ALLOW_JSON_UUIDS)

    def test_msgpack_undecoded_not_complete(self):
        # Valid WS binary frame, garbage MessagePack payload.
        ws = ws_encode(0x2, b"\xff\xff\xff", masked=False)
        rep = decode_capture_text(
            srv_record(1, ws, 1000, sport=26012, leg="adas_26012"))
        self.assertEqual(rep["complete_messages"], 0)
        f = rep["flows"][0]["frames"][0]
        self.assertEqual(f["kind"], "msgpack")
        self.assertFalse(f["app_complete"])
        self.assertFalse(f["msgpack"]["decode_ok"])
        # Valid MessagePack but not a dict envelope.
        ws2 = ws_encode(0x2, msgpack.packb([1, 2, 3]), masked=False)
        rep2 = decode_capture_text(
            srv_record(1, ws2, 2000, sport=26012, leg="adas_26012"))
        self.assertEqual(rep2["complete_messages"], 0)
        # Outer dict without inner envelope: not a complete message.
        outer_only = msgpack.packb({"topic": "vehicle", "note": 1})
        ws3 = ws_encode(0x2, outer_only, masked=False)
        rep3 = decode_capture_text(
            srv_record(1, ws3, 3000, sport=26012, leg="adas_26012"))
        self.assertEqual(rep3["complete_messages"], 0)

    def test_tsr_known_not_recognized(self):
        blob = libflow_blob(topic="tsr", key="tsr_warning",
                            body={"opaque": True}, fid=11)
        ws = ws_encode(0x2, blob, masked=False)
        rep = decode_capture_text(
            srv_record(1, ws, 1000, sport=26012, leg="adas_26012"))
        self.assertEqual(rep["complete_messages"], 1)
        mp = rep["flows"][0]["frames"][0]["msgpack"]
        self.assertTrue(mp["decode_ok"])
        self.assertTrue(mp["known_message"])
        self.assertFalse(mp["recognized_schema"])  # runtime-unverified
        self.assertEqual(rep["flows"][0]["start_boundary"],
                         "candidate_unverified")

    def test_empty_vector_body_recognized(self):
        blob = libflow_blob(topic="vehicle", key="vehicleMeasure", body=[],
                            fid=12)
        ws = ws_encode(0x2, blob, masked=False)
        rep = decode_capture_text(
            srv_record(1, ws, 1000, sport=26012, leg="adas_26012"))
        self.assertEqual(rep["complete_messages"], 1)
        mp = rep["flows"][0]["frames"][0]["msgpack"]
        self.assertTrue(mp["schema_ok"])
        self.assertTrue(mp["recognized_schema"])
        self.assertEqual(rep["flows"][0]["start_boundary"],
                         "verified_recognized")

    def test_api_input_size_limit(self):
        rep = decode_capture_text("A" * (MAX_INPUT_BYTES + 1))
        self.assertEqual(rep["status"], "error")
        self.assertTrue(rep["fail_closed"])
        self.assertEqual(rep["complete_messages"], 0)

    def test_frame_cap_before_growth(self):
        parts = []
        for i in range(140):
            obj = {"uuid": f"Mystery-{i:04d}", "x": i}
            parts.append(ws_encode(0x1, json.dumps(obj).encode(), masked=False))
        blob = b"".join(parts)
        recs, pkt, seq = [], 1, 1000
        while blob:
            chunk, blob = blob[:1500], blob[1500:]
            recs.append(srv_record(pkt, chunk, seq))
            pkt += 1
            seq += len(chunk)
        rep = decode_capture_text("\n".join(recs))
        fl = rep["flows"][0]
        self.assertLessEqual(len(fl["frames"]), 128)
        self.assertEqual(fl["suspended"], "frame_cap_exceeded")
        t = report_text(rep)
        self.assertNotIn("Mystery-0007", t)

    def test_boundary_handshake_disclaimer(self):
        rep = decode_capture_text(
            srv_record(1, ws_encode(0x1, json.dumps(
                {"type": 1, "uuid": "ClientConn",
                 "connected": True}).encode(), masked=False), 100))
        t = report_text(rep)
        self.assertIn("handshake", t)


if __name__ == "__main__":
    unittest.main()
