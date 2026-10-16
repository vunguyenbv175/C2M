#!/usr/bin/env python3
"""Offline HTTP->WS upgrade prefix parser (passive only).

Small pure bounded parser for the initial HTTP/1.1 GET request and
101 response at offset 0. Integrated by parent into
decode_passive_records.FlowState; this module never reassembles records.

A matched passive handshake only means the bytes paired per RFC 6455;
it is NOT an authenticated device and NOT proof of support/rendering.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re

MAX_UPGRADE_BYTES = 4096
MAX_HEADERS = 32
MAX_LINE = 1024

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_TOKEN_RE = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _meta(server_sender: bool, valid: bool, hb: int) -> dict:
    return {
        "role": "server" if server_sender else "client",
        "message": "response" if server_sender else "request",
        "header_bytes": int(hb),
        "valid_http_upgrade": bool(valid),
    }


def _res(status: str, reason: str, consumed: int, priv: dict,
         server_sender: bool, valid: bool, hb: int) -> dict:
    return {
        "status": status,
        "reason": reason,
        "consumed": int(consumed),
        "private_headers": dict(priv),
        "safe_metadata": _meta(server_sender, valid, hb),
    }


def _has_token(val: bytes, want: bytes) -> bool:
    for part in val.split(b","):
        if part.strip(b" \t").lower() == want:
            return True
    return False


def _b64_ok(val: bytes, expect: int) -> bool:
    try:
        if not val or len(val) > 128:
            return False
        return len(base64.b64decode(val, validate=True)) == expect
    except Exception:
        return False


def parse_upgrade_prefix(data: bytes, server_sender: bool) -> dict:
    """Parse HTTP upgrade prefix at offset 0. Never searches past offset 0."""
    ss = bool(server_sender)
    if not isinstance(data, (bytes, bytearray)):
        return _res("invalid", "bad_request_line", 0, {}, ss, False, 0)
    buf = bytes(data)
    if len(buf) == 0:
        return _res("pending", "need_more_data", 0, {}, ss, False, 0)
    f = buf[0]
    if f not in (0x47, 0x48):
        return _res("not_http", "not_http_prefix", 0, {}, ss, False, 0)
    if f == 0x47:
        if len(buf) < 4:
            if b"GET "[:len(buf)] == buf:
                return _res("pending", "need_more_data", 0, {}, ss, False, 0)
            return _res("invalid", "bad_method", 0, {}, ss, False, 0)
        if not buf.startswith(b"GET "):
            return _res("invalid", "bad_method", 0, {}, ss, False, 0)
    else:
        hp = b"HTTP/1.1 "
        if len(buf) < len(hp):
            if hp.startswith(buf):
                return _res("pending", "need_more_data", 0, {}, ss, False, 0)
            return _res("invalid", "bad_status_line", 0, {}, ss, False, 0)
        if not buf.startswith(hp):
            return _res("invalid", "bad_status_line", 0, {}, ss, False, 0)
        after = buf[len(hp):]
        if len(after) < 3:
            if b"101".startswith(after):
                return _res("pending", "need_more_data", 0, {}, ss, False, 0)
            return _res("invalid", "bad_status", 0, {}, ss, False, 0)
        if not after.startswith(b"101"):
            return _res("invalid", "bad_status", 0, {}, ss, False, 0)
        if len(after) == 3:
            return _res("pending", "need_more_data", 0, {}, ss, False, 0)
        if after[3:4] not in (b" ", b"\r"):
            return _res("invalid", "bad_status_line", 0, {}, ss, False, 0)
    idx = buf.find(b"\r\n\r\n")
    if idx == -1:
        if len(buf) >= MAX_UPGRADE_BYTES:
            return _res("invalid", "too_large", 0, {}, ss, False, 0)
        return _res("pending", "need_more_data", 0, {}, ss, False, 0)
    hb = idx + 4
    if hb > MAX_UPGRADE_BYTES:
        return _res("invalid", "too_large", 0, {}, ss, False, 0)
    hdr = buf[:hb]
    if any(b > 127 for b in hdr):
        return _res("invalid", "non_ascii", 0, {}, ss, False, 0)
    tmp = hdr.replace(b"\r\n", b"")
    if b"\r" in tmp or b"\n" in tmp:
        return _res("invalid", "lone_cr_lf", 0, {}, ss, False, 0)
    lines = hdr.split(b"\r\n")
    if lines[-2:] != [b"", b""]:
        return _res("invalid", "bad_header_line", 0, {}, ss, False, 0)
    start = lines[0]
    hlines = lines[1:-2]
    if len(hlines) > MAX_HEADERS:
        return _res("invalid", "too_many_headers", 0, {}, ss, False, 0)
    for ln in [start] + hlines:
        if len(ln) > MAX_LINE:
            return _res("invalid", "line_too_long", 0, {}, ss, False, 0)
        for b in ln:
            if b in (9, 32):
                continue
            if 33 <= b <= 126:
                continue
            return _res("invalid", "control_char", 0, {}, ss, False, 0)
    for ln in hlines:
        if ln[:1] in (b" ", b"\t"):
            return _res("invalid", "obs_fold", 0, {}, ss, False, 0)
    is_req = start.startswith(b"GET ")
    is_resp = start.startswith(b"HTTP/1.1 ")
    if not is_req and not is_resp:
        return _res("invalid", "bad_request_line", 0, {}, ss, False, 0)
    if is_req and ss:
        return _res("invalid", "unexpected_direction", 0, {}, ss, False, 0)
    if is_resp and not ss:
        return _res("invalid", "unexpected_direction", 0, {}, ss, False, 0)
    if is_req:
        parts = start.split(b" ")
        if len(parts) != 3:
            return _res("invalid", "bad_request_line", 0, {}, ss, False, 0)
        if parts[0] != b"GET":
            return _res("invalid", "bad_method", 0, {}, ss, False, 0)
        tgt = parts[1]
        if len(tgt) == 0 or len(tgt) > MAX_LINE:
            return _res("invalid", "bad_target", 0, {}, ss, False, 0)
        if any(b < 0x21 or b > 0x7E for b in tgt):
            return _res("invalid", "bad_target", 0, {}, ss, False, 0)
        if parts[2] != b"HTTP/1.1":
            return _res("invalid", "bad_version", 0, {}, ss, False, 0)
    else:
        st = start[len(b"HTTP/1.1 "):]
        if not st.startswith(b"101"):
            return _res("invalid", "bad_status", 0, {}, ss, False, 0)
        rest = st[3:]
        if rest != b"" and not rest.startswith(b" "):
            return _res("invalid", "bad_status_line", 0, {}, ss, False, 0)
    headers: dict[bytes, bytes] = {}
    for ln in hlines:
        if b":" not in ln:
            return _res("invalid", "bad_header_line", 0, {}, ss, False, 0)
        name, val = ln.split(b":", 1)
        if not name or not _TOKEN_RE.match(name):
            return _res("invalid", "bad_header_name", 0, {}, ss, False, 0)
        ln2 = name.lower()
        if ln2 in headers:
            return _res("invalid", "duplicate_header", 0, {}, ss, False, 0)
        headers[ln2] = val.strip(b" \t")
    if b"transfer-encoding" in headers:
        return _res("invalid", "transfer_encoding_forbidden", 0, {}, ss, False, 0)
    if b"content-length" in headers and headers[b"content-length"] != b"0":
        return _res("invalid", "body_forbidden", 0, {}, ss, False, 0)
    if b"sec-websocket-extensions" in headers and headers[b"sec-websocket-extensions"].strip(b" \t"):
        return _res("invalid", "extensions_unsupported", 0, {}, ss, False, 0)
    if b"sec-websocket-protocol" in headers and headers[b"sec-websocket-protocol"].strip(b" \t"):
        return _res("invalid", "subprotocol_unsupported", 0, {}, ss, False, 0)
    if is_req:
        host = headers.get(b"host")
        if host is None:
            return _res("invalid", "missing_host", 0, {}, ss, False, 0)
        if not host or any(b < 0x21 or b > 0x7E for b in host):
            return _res("invalid", "bad_host", 0, {}, ss, False, 0)
        up = headers.get(b"upgrade")
        if up is None:
            return _res("invalid", "missing_upgrade", 0, {}, ss, False, 0)
        if not _has_token(up, b"websocket"):
            return _res("invalid", "bad_upgrade", 0, {}, ss, False, 0)
        co = headers.get(b"connection")
        if co is None:
            return _res("invalid", "missing_connection", 0, {}, ss, False, 0)
        if not _has_token(co, b"upgrade"):
            return _res("invalid", "bad_connection", 0, {}, ss, False, 0)
        ver = headers.get(b"sec-websocket-version")
        if ver is None:
            return _res("invalid", "missing_version", 0, {}, ss, False, 0)
        if ver != b"13":
            return _res("invalid", "bad_version", 0, {}, ss, False, 0)
        key = headers.get(b"sec-websocket-key")
        if key is None:
            return _res("invalid", "missing_key", 0, {}, ss, False, 0)
        if not _b64_ok(key, 16):
            return _res("invalid", "bad_key", 0, {}, ss, False, 0)
        return _res("valid", "ok", hb, {"sec_websocket_key": bytes(key)}, ss, True, hb)
    up = headers.get(b"upgrade")
    if up is None:
        return _res("invalid", "missing_upgrade", 0, {}, ss, False, 0)
    if not _has_token(up, b"websocket"):
        return _res("invalid", "bad_upgrade", 0, {}, ss, False, 0)
    co = headers.get(b"connection")
    if co is None:
        return _res("invalid", "missing_connection", 0, {}, ss, False, 0)
    if not _has_token(co, b"upgrade"):
        return _res("invalid", "bad_connection", 0, {}, ss, False, 0)
    acc = headers.get(b"sec-websocket-accept")
    if acc is None:
        return _res("invalid", "missing_accept", 0, {}, ss, False, 0)
    if not _b64_ok(acc, 20):
        return _res("invalid", "bad_accept", 0, {}, ss, False, 0)
    return _res("valid", "ok", hb, {"sec_websocket_accept": bytes(acc)}, ss, True, hb)


def match_upgrade(request: dict, response: dict) -> bool:
    """True only if both valid with correct roles and RFC 6455 accept matches."""
    try:
        if not isinstance(request, dict) or not isinstance(response, dict):
            return False
        if request.get("status") != "valid" or response.get("status") != "valid":
            return False
        rm = request.get("safe_metadata") or {}
        sm = response.get("safe_metadata") or {}
        if rm.get("role") != "client" or rm.get("message") != "request":
            return False
        if sm.get("role") != "server" or sm.get("message") != "response":
            return False
        if not rm.get("valid_http_upgrade") or not sm.get("valid_http_upgrade"):
            return False
        rp = request.get("private_headers") or {}
        sp = response.get("private_headers") or {}
        key = rp.get("sec_websocket_key")
        acc = sp.get("sec_websocket_accept")
        if not isinstance(key, (bytes, bytearray)) or not isinstance(acc, (bytes, bytearray)):
            return False
        exp = base64.b64encode(hashlib.sha1(bytes(key) + _GUID).digest())
        return hmac.compare_digest(bytes(exp).strip(), bytes(acc).strip())
    except Exception:
        return False
