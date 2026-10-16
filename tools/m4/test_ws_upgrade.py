#!/usr/bin/env python3
"""Offline tests for tools/m4/ws_upgrade.py. In-memory only, no I/O."""
import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ws_upgrade as wu

KEY = b"dGhlIHNhbXBsZSBub25jZQ=="  # 16 bytes: 'the sample nonce'
ACC = b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo="  # RFC6455 accept for KEY
WRONG_ACC = b"s3pPLMBiTxaQ9kYGzzhZRbK+xOp="  # valid b64 20B, mismatched


def req(raw_key: bytes = KEY, extra: bytes = b"", **kw) -> bytes:
    lines = [b"GET /chat HTTP/1.1",
             b"Host: example.com",
             b"Upgrade: websocket",
             b"Connection: Upgrade",
             b"Sec-WebSocket-Key: " + raw_key,
             b"Sec-WebSocket-Version: 13"]
    if extra:
        lines.append(extra)
    return b"\r\n".join(lines) + b"\r\n\r\n"


def resp(raw_acc: bytes = ACC, extra: bytes = b"") -> bytes:
    lines = [b"HTTP/1.1 101 Switching Protocols",
             b"Upgrade: websocket",
             b"Connection: Upgrade",
             b"Sec-WebSocket-Accept: " + raw_acc]
    if extra:
        lines.append(extra)
    return b"\r\n".join(lines) + b"\r\n\r\n"


def safe_dump(d: dict) -> str:
    # safe_metadata + status/reason only; never private values
    m = d.get("safe_metadata", {})
    return json.dumps({"status": d.get("status"), "reason": d.get("reason"),
                       "meta": m})


class UpgradeTests(unittest.TestCase):
    def test_prefix_pending(self):
        for p in (b"G", b"GE", b"GET", b"H", b"HT", b"HTTP/1.1 ",
                  b"HTTP/1.1 1", b"HTTP/1.1 10", b"HTTP/1.1 101",
                  b"GET /chat HTTP/1.1\r\nHost: x"):
            r = wu.parse_upgrade_prefix(p, False)
            self.assertEqual(r["status"], "pending", p)
            r2 = wu.parse_upgrade_prefix(p, True)
            self.assertEqual(r2["status"], "pending", p)
        self.assertEqual(wu.parse_upgrade_prefix(b"", False)["status"], "pending")

    def test_not_http(self):
        for p in (b"\x81\x05hello", b"\x00\x01", b" ", b"X", b"  GET /x HTTP/1.1\r\n\r\n"):
            r = wu.parse_upgrade_prefix(p, False)
            self.assertEqual(r["status"], "not_http", p)
        # no header search: WS bytes first, HTTP later still not_http
        evil = b"\x81\x05hello" + req()
        self.assertEqual(wu.parse_upgrade_prefix(evil, False)["status"], "not_http")
        lead = b" " + req()
        self.assertEqual(wu.parse_upgrade_prefix(lead, False)["status"], "not_http")

    def test_valid_request_response(self):
        r = wu.parse_upgrade_prefix(req(), False)
        self.assertEqual(r["status"], "valid")
        self.assertEqual(r["consumed"], len(req()))
        self.assertEqual(r["private_headers"], {"sec_websocket_key": KEY})
        self.assertTrue(r["safe_metadata"]["valid_http_upgrade"])
        self.assertEqual(r["safe_metadata"]["role"], "client")
        s = wu.parse_upgrade_prefix(resp(), True)
        self.assertEqual(s["status"], "valid")
        self.assertEqual(s["private_headers"], {"sec_websocket_accept": ACC})

    def test_match_ok_wrong(self):
        rq = wu.parse_upgrade_prefix(req(), False)
        rs = wu.parse_upgrade_prefix(resp(), True)
        self.assertTrue(wu.match_upgrade(rq, rs))
        rs2 = wu.parse_upgrade_prefix(resp(WRONG_ACC), True)
        self.assertEqual(rs2["status"], "valid")
        self.assertFalse(wu.match_upgrade(rq, rs2))
        # swapped roles fail
        self.assertFalse(wu.match_upgrade(rs, rq))
        bad = wu.parse_upgrade_prefix(req(), True)  # wrong direction
        self.assertEqual(bad["status"], "invalid")
        self.assertFalse(wu.match_upgrade(bad, rs))
        # rfc vector cross-check
        exp = base64.b64encode(hashlib.sha1(KEY + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
        self.assertEqual(exp, ACC)

    def test_bad_b64_key_accept(self):
        badk = wu.parse_upgrade_prefix(req(b"!!!"), False)
        self.assertEqual(badk["status"], "invalid")
        short = base64.b64encode(b"short--8B")  # 8 bytes
        badk2 = wu.parse_upgrade_prefix(req(short), False)
        self.assertEqual(badk2["status"], "invalid")
        bada = wu.parse_upgrade_prefix(resp(b"!!!"), True)
        self.assertEqual(bada["status"], "invalid")
        short20 = base64.b64encode(b"0123456789")  # 10 bytes
        self.assertEqual(wu.parse_upgrade_prefix(resp(short20), True)["status"], "invalid")

    def test_token_case(self):
        q = (b"GET /c HTTP/1.1\r\nHost: h\r\nUpgrade: WebSocket\r\n"
             b"Connection: keep-alive, Upgrade\r\nSec-WebSocket-Key: " + KEY +
             b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(q, False)["status"], "valid")
        q2 = (b"GET /c HTTP/1.1\r\nHost: h\r\nUpgrade: WEBSOCKET\r\n"
              b"Connection: UPGRADE\r\nSec-WebSocket-Key: " + KEY +
              b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(q2, False)["status"], "valid")
        bad = (b"GET /c HTTP/1.1\r\nHost: h\r\nUpgrade: h2c\r\nConnection: Upgrade\r\n"
               b"Sec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(bad, False)["status"], "invalid")
        bad2 = (b"GET /c HTTP/1.1\r\nHost: h\r\nUpgrade: websocket\r\nConnection: keep-alive\r\n"
                b"Sec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(bad2, False)["status"], "invalid")

    def test_duplicate_reject(self):
        d = (b"GET /c HTTP/1.1\r\nHost: a\r\nHost: b\r\nUpgrade: websocket\r\n"
             b"Connection: Upgrade\r\nSec-WebSocket-Key: " + KEY +
             b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(d, False)["reason"], "duplicate_header")
        d2 = (b"GET /c HTTP/1.1\r\nHost: a\r\nHOST: b\r\nUpgrade: websocket\r\n"
              b"Connection: Upgrade\r\nSec-WebSocket-Key: " + KEY +
              b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(d2, False)["status"], "invalid")

    def test_malformed_crlf(self):
        lone_n = req().replace(b"\r\n", b"\n", 1)
        self.assertEqual(wu.parse_upgrade_prefix(lone_n, False)["status"], "invalid")
        lone_r = req().replace(b"\r\n", b"\r", 1)
        self.assertEqual(wu.parse_upgrade_prefix(lone_r, False)["status"], "invalid")
        fold = req().replace(b"\r\nHost:", b"\r\n Host:")
        self.assertEqual(wu.parse_upgrade_prefix(fold, False)["reason"], "obs_fold")
        no_colon = req().replace(b"Host: example.com", b"Host example.com")
        self.assertEqual(wu.parse_upgrade_prefix(no_colon, False)["status"], "invalid")

    def test_method_version_status(self):
        bad_m = b"GETX /c HTTP/1.1\r\nHost: h\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n"
        self.assertEqual(wu.parse_upgrade_prefix(bad_m, False)["status"], "invalid")
        bad_v = req().replace(b"HTTP/1.1", b"HTTP/1.0")
        self.assertEqual(wu.parse_upgrade_prefix(bad_v, False)["status"], "invalid")
        bad_s = resp().replace(b"101", b"200", 1)
        self.assertEqual(wu.parse_upgrade_prefix(bad_s, True)["status"], "invalid")
        bad_t = b"GET  HTTP/1.1\r\nHost: h\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n"
        self.assertEqual(wu.parse_upgrade_prefix(bad_t, False)["status"], "invalid")
        bad_wsv = req().replace(b"13", b"12")
        self.assertEqual(wu.parse_upgrade_prefix(bad_wsv, False)["status"], "invalid")
        no_host = req().replace(b"Host: example.com\r\n", b"")
        self.assertEqual(wu.parse_upgrade_prefix(no_host, False)["status"], "invalid")

    def test_size_bounds(self):
        big_val = b"A" * 2000
        q = (b"GET /c HTTP/1.1\r\nHost: h\r\nX-Pad: " + big_val + b"\r\nUpgrade: websocket\r\n"
             b"Connection: Upgrade\r\nSec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.assertEqual(wu.parse_upgrade_prefix(q, False)["status"], "invalid")
        many = b"GET /c HTTP/1.1\r\nHost: h\r\n" + b"".join(b"X-%d: v\r\n" % i for i in range(33)) + \
            b"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + KEY + b"\r\nSec-WebSocket-Version: 13\r\n\r\n"
        self.assertEqual(wu.parse_upgrade_prefix(many, False)["reason"], "too_many_headers")
        huge = b"GET /c HTTP/1.1\r\nHost: h\r\n" + b"A" * 5000
        self.assertEqual(wu.parse_upgrade_prefix(huge, False)["status"], "invalid")
        self.assertIn(wu.parse_upgrade_prefix(huge, False)["reason"], ("too_large", "need_more_data"))

    def test_body_forbidden_residual(self):
        with_body = req().replace(b"Sec-WebSocket-Version: 13",
                                  b"Sec-WebSocket-Version: 13\r\nContent-Length: 5")
        self.assertEqual(wu.parse_upgrade_prefix(with_body, False)["reason"], "body_forbidden")
        zero_ok = req().replace(b"Sec-WebSocket-Version: 13",
                                b"Sec-WebSocket-Version: 13\r\nContent-Length: 0")
        self.assertEqual(wu.parse_upgrade_prefix(zero_ok, False)["status"], "valid")
        te = req().replace(b"Sec-WebSocket-Version: 13",
                           b"Sec-WebSocket-Version: 13\r\nTransfer-Encoding: chunked")
        self.assertEqual(wu.parse_upgrade_prefix(te, False)["status"], "invalid")
        ws_tail = b"\x81\x05hello"
        full = req() + ws_tail
        r = wu.parse_upgrade_prefix(full, False)
        self.assertEqual(r["status"], "valid")
        self.assertEqual(r["consumed"], len(req()))
        self.assertEqual(full[r["consumed"]:], ws_tail)
        full2 = resp() + ws_tail
        r2 = wu.parse_upgrade_prefix(full2, True)
        self.assertEqual(r2["consumed"], len(resp()))

    def test_extensions_subprotocol(self):
        e = req(extra=b"Sec-WebSocket-Extensions: permessage-deflate")
        self.assertEqual(wu.parse_upgrade_prefix(e, False)["reason"], "extensions_unsupported")
        p = req(extra=b"Sec-WebSocket-Protocol: chat")
        self.assertEqual(wu.parse_upgrade_prefix(p, False)["reason"], "subprotocol_unsupported")
        e2 = resp(extra=b"Sec-WebSocket-Extensions: x")
        self.assertEqual(wu.parse_upgrade_prefix(e2, True)["status"], "invalid")

    def test_privacy(self):
        evil_val = "s3cr3t-t0ken-xyz-999"
        q = req().replace(b"example.com", evil_val.encode())
        r = wu.parse_upgrade_prefix(q, False)
        # valid host with evil value still valid but metadata must not leak
        t = safe_dump(r)
        self.assertNotIn(evil_val, t)
        self.assertNotIn("example.com", t)
        rq = wu.parse_upgrade_prefix(req(), False)
        self.assertEqual(set(rq["safe_metadata"].keys()),
                         {"role", "message", "header_bytes", "valid_http_upgrade"})
        self.assertEqual(set(rq["private_headers"].keys()), {"sec_websocket_key"})
        # utf8 / control rejected without echo
        utf = req() + "é".encode("utf-8")
        utf = req().replace(b"/chat", "/ch\xc3\xa9t".encode("latin1"))
        ri = wu.parse_upgrade_prefix(utf, False)
        self.assertEqual(ri["status"], "invalid")
        self.assertNotIn("é", ri.get("reason", ""))
        ctl = req().replace(b"example.com", b"exa\x00mple")
        rc = wu.parse_upgrade_prefix(ctl, False)
        self.assertEqual(rc["status"], "invalid")
        # unknown header names never in safe metadata
        unk = req(extra=b"X-Evil-Header: 1")
        ru = wu.parse_upgrade_prefix(unk, False)
        self.assertEqual(ru["status"], "valid")
        self.assertNotIn("X-Evil-Header", json.dumps(ru["safe_metadata"]))
        self.assertNotIn("evil", json.dumps(ru["safe_metadata"]).lower())
        # reasons are fixed enum, no raw values
        for d in (rq, ru, ri, rc):
            self.assertNotIn(evil_val, d.get("reason", ""))
        bad_m = wu.parse_upgrade_prefix(b"GETX /c HTTP/1.1\r\n\r\n", False)
        self.assertNotIn(evil_val, bad_m.get("reason", ""))

    def test_direction(self):
        self.assertEqual(wu.parse_upgrade_prefix(req(), True)["reason"], "unexpected_direction")
        self.assertEqual(wu.parse_upgrade_prefix(resp(), False)["reason"], "unexpected_direction")

    def test_no_cli_no_network(self):
        src = Path(__file__).resolve().parent.joinpath("ws_upgrade.py").read_text(encoding="utf-8")
        for pat in ("import socket", "from socket", "import urllib", "import requests",
                    "import paramiko", "import subprocess", "create_connection",
                    "argparse", "print("):
            self.assertNotIn(pat, src, pat)


if __name__ == "__main__":
    unittest.main()
