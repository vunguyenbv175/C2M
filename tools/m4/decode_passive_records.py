#!/usr/bin/env python3
"""Offline decoder for M4 observer_v4 passive stdout records.

Reads observer_v4 private stdout (record lines only), reassembles strictly
bounded contiguous per-direction TCP streams, parses WS framing at known
boundaries only (no heuristic header search), and decodes complete FIN
opcode 0x1 JSON / opcode 0x2 MessagePack application messages.

Safety / scope:
- OFFLINE only. No sockets, no SSH, no hardware, no network. Local files only.
- NEVER guesses TCP reassembly: contiguous bytes only, exact-dedup of
  retransmissions, overlap/conflict suspends the flow, gaps and truncated
  captures flush pending incomplete frame bytes. Mid-stream runs have no
  guaranteed WS boundary: offset-0 of each run is a candidate boundary and is
  reported as ``candidate_unverified`` unless it decodes to a complete
  recognized schema. Candidate boundaries are NOT an authenticated WS
  handshake: no handshake was observed; passive bytes only.
- SAFE metadata only. Never emits payload values (speed/warning/TTC/time /
  frame IDs / GPS / MAC / raw bytes / source strings / credentials). Unknown
  protocol field names from raw JSON/MessagePack are NEVER published;
  only documented allowlist names appear. Unknown strings are REDACTED.
- ``complete application message decoded`` describes transport decode only and
  is NOT M4 rendering/delivery proof. This tool never injects or replays.
- Fail-closed: malformed record hex/count/truncation and limit violations
  produce explicit errors (no raw tracebacks, no raw byte values). Any
  malformed record aborts the whole decode (no partial messages).
- MessagePack decoding uses the real libflow_protocol source only. If that
  source is unavailable the MessagePack path fails closed (no fallback
  decoder is constructed, nothing is recognized).

Record line format (same as observer_v3 formatter):
  pkt=<n> len=<wire> src_ip=<8hex> dst_ip=<8hex> sport=<p> dport=<p>
  seq=<u32> ack=<u32> tcp_flags=<2hex> payload_len=<n> captured=<n>
  truncated=<0|1> leg=<token> payload_hex=<hex>

observer_v4 properties honoured here:
- Complete small TCP payloads (payload_len <= 1536) are kept; truncated
  records (captured < payload_len) are unusable for reassembly.
- ACK-only (payload_len == 0) and unknown-endpoint records are skipped.
- Emitted pkt sequence may have gaps (all recv counted, only matching legs
  emitted); pkt gaps are informational, TCP seq gaps are reassembly gaps.
- Known endpoints are the EXACT pair camera c0a8207b / peer c0a82081 with
  the service port (8080/24012/26012) on the CAMERA side and an ephemeral
  (non-service) port on the peer side. Anything else is skipped. Direction
  is by exact camera sender (src == camera), never by port coincidence.

Bounds (fail-closed):
- input file <= 98304 bytes (96 KiB, runner output cap ~100 KiB)
- <= 48 pkt records total, <= 16 records per service port
- total reassembled stream bytes <= 98304
- single WS frame payload <= 65536 (64 KiB); larger is flagged, not decoded
- TCP payload per record <= 1536 (v4 complete-payload ceiling)

Usage:
  python3 tools/m4/decode_passive_records.py CAPTURE_FILE [--report OUT_JSON]
Without --report the JSON report goes to stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_LIB_AVAILABLE = False
try:
    from libflow_protocol import (
        KNOWN_TOPICS as _LIB_KNOWN_TOPICS,
        KNOWN_KEYS as _LIB_KNOWN_KEYS,
        SCHEMAS as _LIB_SCHEMAS,
        decode_ws_binary as _lib_decode_ws_binary,
    )
    _LIB_AVAILABLE = True
except Exception:
    try:
        from tools.m4.libflow_protocol import (  # type: ignore
            KNOWN_TOPICS as _LIB_KNOWN_TOPICS,
            KNOWN_KEYS as _LIB_KNOWN_KEYS,
            SCHEMAS as _LIB_SCHEMAS,
            decode_ws_binary as _lib_decode_ws_binary,
        )
        _LIB_AVAILABLE = True
    except Exception:
        _LIB_AVAILABLE = False

if _LIB_AVAILABLE:
    KNOWN_TOPICS = set(_LIB_KNOWN_TOPICS)
    KNOWN_INNER_KEYS = set(_LIB_KNOWN_KEYS)
    INNER_SCHEMAS = {k: set(v) for k, v in _LIB_SCHEMAS.items()}
else:
    # Fail closed: without the real protocol source nothing is known and
    # no fallback decoder is constructed.
    KNOWN_TOPICS: set[str] = set()
    KNOWN_INNER_KEYS: set[str] = set()
    INNER_SCHEMAS: dict[str, set[str]] = {}

# Documented JSON shapes (mirrors replay_guard.SHAPES / m4_policy allow-list).
DOCUMENTED_JSON_SHAPES: dict[str, set[str]] = {
    "DispBrightSet": {"type", "uuid", "brightness"},
    "StorageStatus": {"type", "uuid", "status"},
    "ScreenModeSet": {"type", "uuid", "theme"},
    "ClientConn": {"type", "uuid", "connected"},
}
ALLOW_JSON_UUIDS = set(DOCUMENTED_JSON_SHAPES)
DENY_JSON_UUIDS = {"AdasStatus", "HeavyCalibStatus", "GPSLevel", "GPSSpeed", "RecordVoice"}


def _load_policy_uuid_sets() -> tuple[set[str], set[str]]:
    """Best-effort load of known UUID sets from sibling m4_policy.json.

    Falls back to the hardcoded documented sets. Never raises; never fetches.
    """
    try:
        here = Path(__file__).resolve().parent / "m4_policy.json"
        if here.is_file() and here.stat().st_size <= 65536:
            obj = json.loads(here.read_text(encoding="utf-8"))
            allow = obj.get("allow_l2_json_uuids")
            deny = obj.get("deny_json_uuids")
            if isinstance(allow, list) and isinstance(deny, list):
                a = {str(x) for x in allow if isinstance(x, str)}
                d = {str(x) for x in deny if isinstance(x, str)}
                if a and d:
                    # Only ever expand within documented names; unknown file
                    # content must not widen what we publish.
                    return (a & (ALLOW_JSON_UUIDS | DENY_JSON_UUIDS)) | ALLOW_JSON_UUIDS, \
                           (d & (ALLOW_JSON_UUIDS | DENY_JSON_UUIDS)) | DENY_JSON_UUIDS
    except Exception:
        pass
    return set(ALLOW_JSON_UUIDS), set(DENY_JSON_UUIDS)


_ALLOW_UUIDS, _DENY_UUIDS = _load_policy_uuid_sets()
KNOWN_JSON_UUIDS = set(_ALLOW_UUIDS) | set(_DENY_UUIDS)

SERVICE_PORTS = {8080, 24012, 26012}
# Exact observer_v4 endpoints (full 8-hex network-order IPv4).
CAM_HEX = "c0a8207b"  # 192.168.32.123 camera (service side)
PEER_HEX = "c0a82081"  # 192.168.32.129 peer (ephemeral side)

MAX_INPUT_BYTES = 98304
MAX_RECORDS = 48
MAX_PER_PORT = 16
MAX_STREAM_BYTES = 98304
MAX_FRAME_BYTES = 65536
MAX_PAYLOAD_PER_RECORD = 1536
MAX_FRAMES_PER_FLOW = 128

SEQ_MOD = 2 ** 32

DISCLAIMER_DECODE = (
    "complete application message decoded means transport-level WS+payload "
    "parse only; it is NOT proof of M4 rendering, display, or delivery."
)
DISCLAIMER_NO_INJECTION = (
    "offline read-only decoder: performs no network I/O, no replay, "
    "no injection, no hardware access."
)
DISCLAIMER_BOUNDARY = (
    "flow start boundaries are candidate WS frame alignments from passive "
    "bytes only; no WS handshake was observed or authenticated, so "
    "candidate_unverified means no recognized schema was decoded there."
)

_RECORD_RE = re.compile(
    r"^pkt=(\d+)\s+len=(\d+)\s+src_ip=([0-9a-fA-F]{8})\s+"
    r"dst_ip=([0-9a-fA-F]{8})\s+sport=(\d+)\s+dport=(\d+)\s+"
    r"seq=(\d+)\s+ack=(\d+)\s+tcp_flags=([0-9a-fA-F]{2})\s+"
    r"payload_len=(\d+)\s+captured=(\d+)\s+truncated=([01])\s+"
    r"leg=(\S+)\s+payload_hex=([0-9a-fA-F]*)$"
)


class RecordError(ValueError):
    pass


def _type_kind(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (bytes, bytearray)):
        return "bytes"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, (list, tuple)):
        return "list"
    return "other"


def parse_record_line(line: str, lineno: int) -> dict:
    """Parse one observer record line strictly. Raises RecordError (sanitized)."""
    m = _RECORD_RE.match(line.strip())
    if not m:
        raise RecordError(f"line {lineno}: malformed record line (format mismatch)")
    try:
        pkt = int(m.group(1))
        wire_len = int(m.group(2))
        src_hex = m.group(3).lower()
        dst_hex = m.group(4).lower()
        sport = int(m.group(5))
        dport = int(m.group(6))
        seq = int(m.group(7))
        ack = int(m.group(8))
        flags = int(m.group(9), 16)
        payload_len = int(m.group(10))
        captured = int(m.group(11))
        truncated = int(m.group(12))
        leg = m.group(13)
        payload_hex = m.group(14)
    except Exception:
        raise RecordError(f"line {lineno}: malformed record line (bad numeric field)")
    for name, val, hi in (("sport", sport, 65535), ("dport", dport, 65535),
                          ("seq", seq, SEQ_MOD - 1), ("ack", ack, SEQ_MOD - 1),
                          ("payload_len", payload_len, 10_000_000),
                          ("captured", captured, 10_000_000)):
        if not (0 <= val <= hi):
            raise RecordError(f"line {lineno}: pkt={pkt} field {name} out of range")
    if truncated not in (0, 1):
        raise RecordError(f"line {lineno}: pkt={pkt} bad truncated flag")
    if len(payload_hex) % 2 != 0:
        raise RecordError(f"line {lineno}: pkt={pkt} payload_hex odd length")
    if len(payload_hex) // 2 != captured:
        raise RecordError(
            f"line {lineno}: pkt={pkt} captured={captured} disagrees with "
            f"payload_hex bytes={len(payload_hex) // 2}"
        )
    if captured > payload_len:
        raise RecordError(
            f"line {lineno}: pkt={pkt} captured exceeds payload_len"
        )
    expect_trunc = 1 if captured < payload_len else 0
    if truncated != expect_trunc:
        raise RecordError(
            f"line {lineno}: pkt={pkt} truncated flag disagrees with "
            f"captured/payload_len counts"
        )
    try:
        payload_bytes = bytes.fromhex(payload_hex) if payload_hex else b""
    except Exception:
        raise RecordError(f"line {lineno}: pkt={pkt} payload_hex not valid hex")
    if len(payload_bytes) != captured:
        raise RecordError(f"line {lineno}: pkt={pkt} payload byte count mismatch")
    return {
        "pkt": pkt, "wire_len": wire_len, "src_hex": src_hex, "dst_hex": dst_hex,
        "sport": sport, "dport": dport, "seq": seq, "ack": ack,
        "tcp_flags": flags, "payload_len": payload_len, "captured": captured,
        "truncated": truncated, "leg": leg, "payload": payload_bytes,
        "lineno": lineno,
    }


def is_known_endpoint(rec: dict) -> bool:
    """Exact observer_v4 pair: camera/peer with the service on CAMERA side.

    The peer side must be ephemeral (non-service); a peer port coinciding
    with a service number is ambiguous and skipped fail-closed.
    """
    s, d = rec["src_hex"], rec["dst_hex"]
    if {s, d} != {CAM_HEX, PEER_HEX}:
        return False
    if s == CAM_HEX:
        return rec["sport"] in SERVICE_PORTS and rec["dport"] not in SERVICE_PORTS
    return rec["dport"] in SERVICE_PORTS and rec["sport"] not in SERVICE_PORTS


def is_server_sender(rec: dict) -> bool:
    """Direction by exact camera sender, never by port coincidence."""
    return rec["src_hex"] == CAM_HEX


def safe_json_summary(obj: dict) -> dict:
    uuid_val = obj.get("uuid")
    uuid_is_str = isinstance(uuid_val, str)
    uuid_known = uuid_is_str and uuid_val in KNOWN_JSON_UUIDS
    if uuid_is_str and uuid_val in _ALLOW_UUIDS:
        uuid_class = "ALLOW-L2"
    elif uuid_is_str and uuid_val in _DENY_UUIDS:
        uuid_class = "DENY"
    else:
        uuid_class = "UNKNOWN"
    out: dict = {
        "msg_format": "json_text",
        "dict_size": len(obj),
        "uuid_known": bool(uuid_known),
        "uuid_class": uuid_class,
        "uuid": uuid_val if uuid_known else ("REDACTED_UNKNOWN" if "uuid" in obj else "ABSENT"),
        "known_message": bool(uuid_known),
    }
    if uuid_known and uuid_val in DOCUMENTED_JSON_SHAPES:
        want = DOCUMENTED_JSON_SHAPES[uuid_val]
        keys = set(obj.keys())
        # keys here are strings by construction (json dict); filter safely.
        present = sorted([k for k in keys if isinstance(k, str) and k in want])
        missing = sorted(list(want - {k for k in keys if isinstance(k, str)}))
        extra_count = len(keys - want)
        out["known_fields_present"] = present
        out["known_fields_missing"] = missing
        out["extra_field_count"] = extra_count
        out["shape_ok"] = (extra_count == 0 and len(missing) == 0)
        out["field_type_kinds"] = {k: _type_kind(obj[k]) for k in present}
        out["recognized_schema"] = bool(out["shape_ok"])
    else:
        # Deny-known UUIDs without a documented transmit shape, or unknown
        # UUIDs: publish counts/types only, never raw field names or values.
        # A DENY-known uuid is a known_message but NEVER a recognized schema,
        # so it can never claim verified_recognized.
        hist: dict[str, int] = {}
        for v in obj.values():
            k = _type_kind(v)
            hist[k] = hist.get(k, 0) + 1
        out["known_fields_present"] = []
        out["known_fields_missing"] = []
        out["extra_field_count"] = len(obj)
        out["field_names_redacted"] = True
        out["type_histogram"] = dict(sorted(hist.items()))
        out["shape_ok"] = False
        out["recognized_schema"] = False
    return out


def safe_msgpack_summary(payload: bytes) -> dict:
    """SAFE summary of a libflow outer/inner MessagePack envelope.

    Strict success: decode_ok requires the real decoder source plus dict
    outer AND dict inner. recognized_schema additionally requires all
    mandatory outer/inner fields, BIN inner data, known topic/key, and an
    actually verified body schema (empty vectors okay; TSR static keys stay
    runtime-unverified, hence known but not recognized). Only documented
    allowlist names are ever published.
    """
    out: dict = {
        "msg_format": "msgpack_libflow",
        "decode_ok": False,
        "recognized_schema": False,
        "known_message": False,
        "schema_ok": False,
        "outer_complete": False,
        "inner_complete": False,
    }
    if not _LIB_AVAILABLE:
        out["decode_error"] = "libflow decoder unavailable (fail-closed)"
        return out
    try:
        res = _lib_decode_ws_binary(payload)
    except Exception:
        out["decode_error"] = "inner MessagePack decode failed"
        return out
    outer = res.outer
    inner = res.inner
    raw_warnings = list(getattr(res, "warnings", []) or [])
    outer_is_dict = isinstance(outer, dict)
    inner_is_dict = isinstance(inner, dict)
    out["outer_is_dict"] = outer_is_dict
    out["inner_is_dict"] = inner_is_dict
    documented_outer = {"time", "source", "topic", "data"}
    documented_inner = {"frame_id", "time", "key", "data"}
    topic_known = False
    key_known = False
    if outer_is_dict:
        assert isinstance(outer, dict)
        topic_val = outer.get("topic")
        topic_known = isinstance(topic_val, str) and topic_val in KNOWN_TOPICS
        out["outer_field_count"] = len(outer)
        str_keys = {k for k in outer.keys() if isinstance(k, str)}
        out["outer_expected_present"] = sorted(list(str_keys & documented_outer))
        out["outer_expected_missing"] = sorted(list(documented_outer - str_keys))
        out["outer_extra_field_count"] = len(str_keys - documented_outer)
        out["outer_topic_known"] = bool(topic_known)
        out["outer_topic"] = topic_val if topic_known else (
            "REDACTED_UNKNOWN" if "topic" in outer else "ABSENT")
        # Never publish source/time values.
        out["outer_has_data_bin"] = isinstance(outer.get("data"), (bytes, bytearray, memoryview))
        out["outer_complete"] = (
            not (documented_outer - str_keys)
            and isinstance(outer.get("data"), (bytes, bytearray, memoryview))
        )
    else:
        out["outer_field_count"] = 0
        out["outer_topic_known"] = False
        out["outer_topic"] = "REDACTED_UNKNOWN"
        out["outer_has_data_bin"] = False
    if inner_is_dict:
        assert isinstance(inner, dict)
        key_val = inner.get("key")
        key_known = isinstance(key_val, str) and key_val in KNOWN_INNER_KEYS
        out["inner_field_count"] = len(inner)
        ikeys = {k for k in inner.keys() if isinstance(k, str)}
        out["inner_expected_present"] = sorted(list(ikeys & documented_inner))
        out["inner_expected_missing"] = sorted(list(documented_inner - ikeys))
        out["inner_extra_field_count"] = len(ikeys - documented_inner)
        out["inner_key_known"] = bool(key_known)
        out["inner_key"] = key_val if key_known else (
            "REDACTED_UNKNOWN" if "key" in inner else "ABSENT")
        out["inner_complete"] = not (documented_inner - ikeys)
        body = inner.get("data")
        if isinstance(key_val, str) and key_val in INNER_SCHEMAS and isinstance(body, dict):
            expected = INNER_SCHEMAS[key_val]
            bkeys = {k for k in body.keys() if isinstance(k, str)}
            present = sorted(list(bkeys & expected))
            missing = sorted(list(expected - bkeys))
            out["body_kind"] = "dict"
            out["body_item_count"] = len(body)
            out["body_known_fields_present"] = present
            out["body_known_fields_missing"] = missing
            out["body_extra_field_count"] = len(bkeys - expected)
            out["body_field_type_kinds"] = {k: _type_kind(body[k]) for k in present}
            out["schema_ok"] = (len(bkeys - expected) == 0 and len(missing) == 0)
            out["known_message"] = bool(topic_known and key_known)
        elif isinstance(key_val, str) and key_val in INNER_SCHEMAS and isinstance(body, list):
            expected = INNER_SCHEMAS[key_val]
            checked = 0
            items_missing_total = 0
            items_extra_total = 0
            for item in body[:50]:
                if isinstance(item, dict):
                    ik = {k for k in item.keys() if isinstance(k, str)}
                    items_missing_total += len(expected - ik)
                    items_extra_total += len(ik - expected)
                    checked += 1
            out["body_kind"] = "list"
            out["body_item_count"] = len(body)
            out["body_items_checked"] = checked
            out["body_items_missing_total"] = items_missing_total
            out["body_items_extra_total"] = items_extra_total
            out["body_field_names_redacted"] = True
            out["schema_ok"] = (items_missing_total == 0 and items_extra_total == 0 and checked == len(body))
            out["known_message"] = bool(topic_known and key_known)
        elif isinstance(key_val, str) and key_val in {"tsr_trace_res_list", "tsr_warning"}:
            out["body_kind"] = _type_kind(body)
            if isinstance(body, (list, tuple)):
                out["body_item_count"] = len(body)
            elif isinstance(body, dict):
                out["body_item_count"] = len(body)
            else:
                out["body_item_count"] = 0
            out["body_field_names_redacted"] = True
            out["schema_ok"] = False
            out["runtime_unverified"] = True
            # Statically known key, runtime-unverified payload: known, not recognized.
            out["known_message"] = bool(topic_known and key_known)
        else:
            out["body_kind"] = _type_kind(body)
            out["body_field_names_redacted"] = True
            if isinstance(body, (list, tuple)):
                out["body_item_count"] = len(body)
            elif isinstance(body, dict):
                out["body_item_count"] = len(body)
            else:
                out["body_item_count"] = 0
            out["schema_ok"] = False
            out["known_message"] = False
    else:
        out["inner_key_known"] = False
        out["inner_key"] = "REDACTED_UNKNOWN"
        out["body_kind"] = _type_kind(inner)
        out["body_field_names_redacted"] = True
        out["schema_ok"] = False
        out["known_message"] = False
    out["decode_ok"] = bool(outer_is_dict and inner_is_dict)
    if not out["decode_ok"]:
        out["decode_error"] = "libflow envelope is not dict outer+inner"
    out["recognized_schema"] = bool(
        out["decode_ok"] and out["known_message"] and out["outer_complete"]
        and out["inner_complete"] and out["schema_ok"]
    )
    # Sanitize lib warnings: never echo unknown raw names/values.
    safe_warnings: list[str] = []
    for w in raw_warnings:
        try:
            s = str(w)
        except Exception:
            s = "unprintable warning"
        if s.startswith("unknown inner key:"):
            safe_warnings.append("unknown inner key: REDACTED")
        elif "extra:" in s or "extra " in s:
            # Raw extra lists may hold unpublished field names -> redact names.
            safe_warnings.append("schema extra fields present (names redacted)")
        elif "inner MessagePack decode failed" in s:
            safe_warnings.append("inner MessagePack decode failed")
        elif "outer frame is not a map" in s:
            safe_warnings.append("outer frame is not a map")
        elif "missing" in s:
            # Missing lists name allowlisted expected fields; cap length.
            safe_warnings.append(s[:160])
        elif "runtime-unverified" in s:
            safe_warnings.append("TSR key statically known; payload schema/units runtime-unverified")
        else:
            safe_warnings.append("schema warning (redacted)")
    out["lib_warnings_count"] = len(raw_warnings)
    out["lib_warnings_sanitized"] = safe_warnings[:8]
    return out


def _parse_ws_frames(run_buf: bytes | bytearray, server_sender: bool) -> tuple[list[dict], int, str | None]:
    """Parse sequential WS frames from a contiguous run at known boundaries.

    Returns (frame_entries, decoded_upto, suspended_reason). Never searches
    for headers inside unknown bytes: parsing stops at the first incomplete,
    invalid, too-large, or fragmented frame.
    """
    frames: list[dict] = []
    off = 0
    n = len(run_buf)
    while off < n:
        if len(frames) >= MAX_FRAMES_PER_FLOW * 2:
            return frames, off, "frame_cap_exceeded"
        remaining = n - off
        if remaining < 2:
            break  # incomplete header -> pending
        b0 = run_buf[off]
        b1 = run_buf[off + 1]
        fin = (b0 >> 7) & 1
        rsv = (b0 >> 4) & 7
        opcode = b0 & 0x0F
        masked = (b1 >> 7) & 1
        len7 = b1 & 0x7F
        if rsv != 0:
            frames.append({"offset": off, "complete": False, "kind": "invalid_rsv",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": 0, "detail": "RSV bits must be zero"})
            return frames, off, "invalid_rsv"
        if opcode not in (0x0, 0x1, 0x2, 0x8, 0x9, 0xA):
            frames.append({"offset": off, "complete": False, "kind": "invalid_opcode",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": 0, "detail": "unknown opcode"})
            return frames, off, "invalid_opcode"
        # Direction: server frames unmasked, client frames masked.
        if server_sender and masked != 0:
            frames.append({"offset": off, "complete": False, "kind": "invalid_mask_direction",
                           "opcode": opcode, "masked": True, "payload_len": 0,
                           "detail": "server frame must be unmasked"})
            return frames, off, "invalid_mask_direction"
        if not server_sender and masked != 1:
            frames.append({"offset": off, "complete": False, "kind": "invalid_mask_direction",
                           "opcode": opcode, "masked": False, "payload_len": 0,
                           "detail": "client frame must be masked"})
            return frames, off, "invalid_mask_direction"
        is_control = opcode >= 0x8
        if is_control:
            if fin != 1:
                frames.append({"offset": off, "complete": False, "kind": "invalid_control",
                               "opcode": opcode, "masked": bool(masked),
                               "payload_len": 0, "detail": "control frame must not be fragmented"})
                return frames, off, "invalid_control"
            if len7 > 125:
                frames.append({"offset": off, "complete": False, "kind": "invalid_control",
                               "opcode": opcode, "masked": bool(masked),
                               "payload_len": 0, "detail": "control payload must be <=125"})
                return frames, off, "invalid_control"
            header_len = 2 + (4 if masked else 0)
            total = header_len + len7
            if remaining < total:
                break  # incomplete control -> pending
            frames.append({"offset": off, "complete": True, "kind": "control",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": len7,
                           "control": "close" if opcode == 0x8 else ("ping" if opcode == 0x9 else "pong")})
            off += total
            continue
        # Data frames.
        if fin != 1 or opcode == 0x0:
            frames.append({"offset": off, "complete": False, "kind": "fragment_unsupported",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": 0,
                           "detail": "fragments/continuations unsupported; flag not decode"})
            return frames, off, "fragment_unsupported"
        header_len = 2
        if len7 == 126:
            if remaining < 4:
                break
            ext = (run_buf[off + 2] << 8) | run_buf[off + 3]
            if ext < 126:
                # Non-minimal encoding: must have used the 7-bit form.
                frames.append({"offset": off, "complete": False, "kind": "invalid_length",
                               "opcode": opcode, "masked": bool(masked),
                               "payload_len": 0, "detail": "non-minimal 16-bit length encoding"})
                return frames, off, "invalid_length"
            pay_len = ext
            header_len = 4 + (4 if masked else 0)
        elif len7 == 127:
            if remaining < 10:
                break
            ext = 0
            for i in range(8):
                ext = (ext << 8) | run_buf[off + 2 + i]
            if ext >> 63:
                frames.append({"offset": off, "complete": False, "kind": "invalid_length",
                               "opcode": opcode, "masked": bool(masked),
                               "payload_len": 0, "detail": "64-bit length MSB set"})
                return frames, off, "invalid_length"
            if ext < 65536:
                # Non-minimal encoding: must have used the 7-bit/16-bit form.
                frames.append({"offset": off, "complete": False, "kind": "invalid_length",
                               "opcode": opcode, "masked": bool(masked),
                               "payload_len": 0, "detail": "non-minimal 64-bit length encoding"})
                return frames, off, "invalid_length"
            pay_len = ext
            header_len = 10 + (4 if masked else 0)
        else:
            pay_len = len7
            header_len = 2 + (4 if masked else 0)
        if pay_len > MAX_FRAME_BYTES:
            frames.append({"offset": off, "complete": False, "kind": "frame_too_large",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": pay_len,
                           "detail": "frame exceeds 64KiB; flag not decode"})
            return frames, off, "frame_too_large"
        total = header_len + pay_len
        # Bound total frame size sanity (header + payload).
        if total > MAX_FRAME_BYTES + 16:
            frames.append({"offset": off, "complete": False, "kind": "frame_too_large",
                           "opcode": opcode, "masked": bool(masked),
                           "payload_len": pay_len,
                           "detail": "frame exceeds 64KiB; flag not decode"})
            return frames, off, "frame_too_large"
        if remaining < total:
            break  # split across segments -> pending
        if masked:
            key_off = off + (header_len - 4)
            mask_key = bytes(run_buf[key_off:key_off + 4])
            enc = bytes(run_buf[off + header_len:off + header_len + pay_len])
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(enc))
        else:
            payload = bytes(run_buf[off + header_len:off + header_len + pay_len])
        entry: dict = {"offset": off, "complete": True, "opcode": opcode,
                       "masked": bool(masked), "payload_len": pay_len,
                       "kind": "json" if opcode == 0x1 else "msgpack"}
        if opcode == 0x1:
            try:
                text = payload.decode("utf-8")
            except Exception:
                entry["kind"] = "invalid_json"
                entry["complete"] = False
                entry["detail"] = "text payload is not valid UTF-8"
                frames.append(entry)
                return frames, off, "invalid_json"
            try:
                obj = json.loads(text)
            except Exception:
                entry["kind"] = "invalid_json"
                entry["complete"] = False
                entry["detail"] = "text payload is not JSON"
                frames.append(entry)
                return frames, off, "invalid_json"
            if not isinstance(obj, dict):
                entry["kind"] = "invalid_json"
                entry["complete"] = False
                entry["detail"] = "JSON top level is not an object"
                frames.append(entry)
                return frames, off, "invalid_json"
            # Only str keys considered; non-str keys fail closed (redacted).
            try:
                for k in obj.keys():
                    if not isinstance(k, str):
                        raise ValueError("non-string key")
            except Exception:
                entry["kind"] = "invalid_json"
                entry["complete"] = False
                entry["detail"] = "JSON object has non-string keys"
                frames.append(entry)
                return frames, off, "invalid_json"
            entry["json"] = safe_json_summary(obj)
            # JSON dict parsed: WS frame complete and application complete.
            entry["app_complete"] = True
        elif opcode == 0x2:
            mp = safe_msgpack_summary(payload)
            entry["msgpack"] = mp
            # A raw opcode2 whose envelope does not fully decode (outer+inner
            # dicts) is a complete WS frame but NOT a complete application
            # message. Parsing continues at the exact next boundary.
            entry["app_complete"] = bool(mp.get("decode_ok"))
        else:  # pragma: no cover - unreachable (opcode filtered above)
            entry["kind"] = "invalid_opcode"
            entry["complete"] = False
            frames.append(entry)
            return frames, off, "invalid_opcode"
        frames.append(entry)
        off += total
    return frames, off, None


class FlowState:
    def __init__(self, key: tuple, server_sender: bool, label: str):
        self.key = key
        self.server_sender = server_sender
        self.label = label
        self.pkt_numbers: list[int] = []
        self.run_base: int | None = None
        self.run_buf = bytearray()
        self.run_decoded = 0
        self.frames: list[dict] = []
        self.frame_offset_base = 0  # cumulative decoded bytes before current run
        self.gaps = 0
        self.retrans_dedup = 0
        self.overlap_extended = 0
        self.conflicts = 0
        self.truncated_skipped = 0
        self.oversize_skipped = 0
        self.suspended: str | None = None
        self.start_boundary: str | None = None
        self.had_data = False

    def _discard_pending(self):
        # Flush incomplete trailing bytes of the current run; keep completed.
        if len(self.run_buf) > self.run_decoded:
            del self.run_buf[self.run_decoded:]
        self.run_decoded = len(self.run_buf)

    def add_record(self, rec: dict, errors: list[str], stream_budget: list[int]):
        if self.suspended and self.suspended.startswith("conflict"):
            return
        seq = rec["seq"]
        data = rec["payload"]
        length = rec["payload_len"]
        if rec["truncated"]:
            self.truncated_skipped += 1
            # Truncated captures are unusable: flush pending, skip the whole
            # advertised payload span (do not append captured prefix).
            self._discard_pending()
            self.frame_offset_base += self.run_decoded
            # Next run restarts fresh; represent skip by resetting run.
            if self.run_base is not None:
                self.run_base = (seq + length) % SEQ_MOD
                self.run_buf = bytearray()
                self.run_decoded = 0
            else:
                self.run_base = (seq + length) % SEQ_MOD
            self.gaps += 1
            return
        if length > MAX_PAYLOAD_PER_RECORD:
            self.oversize_skipped += 1
            self._discard_pending()
            self.frame_offset_base += self.run_decoded
            self.run_base = (seq + length) % SEQ_MOD
            self.run_buf = bytearray()
            self.run_decoded = 0
            self.gaps += 1
            return
        if len(data) == 0:
            return
        self.had_data = True
        self.pkt_numbers.append(rec["pkt"])
        if not self.run_buf and self.run_base is None:
            if stream_budget[0] + len(data) > MAX_STREAM_BYTES:
                errors.append(f"flow {self.label}: stream byte budget exceeded")
                self.suspended = "budget_exceeded"
                return
            self.run_base = seq
            self.run_buf = bytearray(data)
            stream_budget[0] += len(data)
            self._try_parse()
            return
        assert self.run_base is not None
        run_next = (self.run_base + len(self.run_buf)) % SEQ_MOD
        delta = (seq - run_next) % SEQ_MOD
        if delta == 0:
            if stream_budget[0] + len(data) > MAX_STREAM_BYTES:
                errors.append(f"flow {self.label}: stream byte budget exceeded")
                self.suspended = "budget_exceeded"
                return
            self.run_buf.extend(data)
            stream_budget[0] += len(data)
            self._try_parse()
            return
        if delta < SEQ_MOD // 2:
            # Forward gap: flush pending incomplete, start new candidate run.
            self.gaps += 1
            self._discard_pending()
            self.frame_offset_base += self.run_decoded
            if stream_budget[0] + len(data) > MAX_STREAM_BYTES:
                errors.append(f"flow {self.label}: stream byte budget exceeded")
                self.suspended = "budget_exceeded"
                self.run_base = seq
                self.run_buf = bytearray()
                self.run_decoded = 0
                return
            self.run_base = seq
            self.run_buf = bytearray(data)
            self.run_decoded = 0
            stream_budget[0] += len(data)
            self._try_parse()
            return
        # seq behind run_next: retransmission / overlap.
        behind = (run_next - seq) % SEQ_MOD
        base = self.run_base
        assert base is not None
        offset = (seq - base) % SEQ_MOD
        if offset >= len(self.run_buf):
            # Stale/duplicate outside current run window after a gap reset.
            self.conflicts += 1
            self.suspended = "conflict_stale_overlap"
            return
        if length <= behind and offset + length <= len(self.run_buf):
            # Fully duplicate region.
            existing = bytes(self.run_buf[offset:offset + length])
            if existing == data:
                self.retrans_dedup += 1
                return
            self.conflicts += 1
            self.suspended = "conflict_overlap_bytes_differ"
            return
        # Partial overlap extending past run_next.
        if offset < len(self.run_buf):
            overlap_len = len(self.run_buf) - offset
            if overlap_len < 0:
                overlap_len = 0
            if overlap_len > length:
                overlap_len = length
            existing = bytes(self.run_buf[offset:offset + overlap_len])
            if existing != data[:overlap_len]:
                self.conflicts += 1
                self.suspended = "conflict_overlap_bytes_differ"
                return
            tail = data[overlap_len:]
            if tail:
                if stream_budget[0] + len(tail) > MAX_STREAM_BYTES:
                    errors.append(f"flow {self.label}: stream byte budget exceeded")
                    self.suspended = "budget_exceeded"
                    return
                self.run_buf.extend(tail)
                stream_budget[0] += len(tail)
                self.overlap_extended += 1
            else:
                self.retrans_dedup += 1
            self._try_parse()
            return
        self.conflicts += 1
        self.suspended = "conflict_overlap_bytes_differ"

    def _try_parse(self):
        if self.suspended is not None:
            return
        if len(self.frames) >= MAX_FRAMES_PER_FLOW:
            if self.suspended is None:
                self.suspended = "frame_cap_exceeded"
            if self.start_boundary is None:
                self.start_boundary = "candidate_unverified"
            return
        suffix = bytes(self.run_buf[self.run_decoded:])
        if not suffix:
            if self.start_boundary is None and (self.frames or self.had_data):
                self.start_boundary = "candidate_unverified"
            return
        frames, _upto, suspended_reason = _parse_ws_frames(suffix, self.server_sender)
        # Snapshot: f["offset"] is relative to the suffix start, i.e. to the
        # run_decoded value at entry. Accumulate from the snapshot so that
        # several complete frames in one suffix get absolute offsets.
        base = self.run_decoded
        for f in frames:
            if len(self.frames) >= MAX_FRAMES_PER_FLOW:
                # Cap BEFORE growth: do not store further frames.
                if self.suspended is None:
                    self.suspended = "frame_cap_exceeded"
                break
            run_off = base + int(f["offset"])
            entry = dict(f)
            entry["offset"] = run_off
            entry["stream_offset"] = self.frame_offset_base + run_off
            if entry.get("complete") and entry.get("kind") == "json":
                entry["recognized"] = bool(entry.get("json", {}).get("recognized_schema"))
                entry["app_complete"] = True
            elif entry.get("complete") and entry.get("kind") == "msgpack":
                mp = entry.get("msgpack", {})
                entry["recognized"] = bool(mp.get("recognized_schema"))
                entry["app_complete"] = bool(mp.get("decode_ok"))
            elif entry.get("complete") and entry.get("kind") == "control":
                # A legitimate control frame carries no application schema and
                # never verifies the candidate boundary.
                entry["recognized"] = False
                entry["app_complete"] = False
            else:
                entry["recognized"] = False
                entry["app_complete"] = False
            entry.pop("payload", None)
            self.frames.append(entry)
            if entry.get("complete") and entry.get("kind") in ("json", "msgpack", "control"):
                self.run_decoded = run_off + _frame_total_len(self.run_buf, entry, self.server_sender)
            else:
                # Invalid/fragment/too-large entry stops this run.
                break
        if self.start_boundary is None and (self.frames or suspended_reason is not None):
            first = self.frames[0] if self.frames else None
            if (first is not None and first.get("complete")
                    and first.get("app_complete") and first.get("recognized")):
                self.start_boundary = "verified_recognized"
            else:
                self.start_boundary = "candidate_unverified"
        if suspended_reason is not None and self.suspended is None:
            # Suspend further parsing of this run (no heuristic search).
            self.suspended = suspended_reason


def _frame_total_len(run_buf: bytearray, f: dict, server_sender: bool) -> int:
    off = f["offset"]
    if off + 2 > len(run_buf):
        return 0
    b1 = run_buf[off + 1]
    masked = (b1 >> 7) & 1
    len7 = b1 & 0x7F
    if f.get("kind") == "control":
        return 2 + (4 if masked else 0) + int(f.get("payload_len", 0))
    if len7 == 126:
        return 4 + (4 if masked else 0) + int(f.get("payload_len", 0))
    if len7 == 127:
        return 10 + (4 if masked else 0) + int(f.get("payload_len", 0))
    return 2 + (4 if masked else 0) + int(f.get("payload_len", 0))


def decode_capture_text(text: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    # API-level input bound (main() also enforces this on files).
    try:
        if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
            return _error_report(
                [f"input too large: over {MAX_INPUT_BYTES} bytes (fail-closed)"],
                warnings, 0, 0,
            )
    except Exception:
        return _error_report(["input encoding failure (fail-closed)"], warnings, 0, 0)
    records: list[dict] = []
    seen_pkt: set[int] = set()
    per_port: dict[int, int] = {}
    skipped_ack = 0
    skipped_endpoint = 0
    malformed = 0
    lines = text.splitlines()
    if len(lines) > 10000:
        return _error_report(errors + ["input has too many lines"], warnings, 0, 0)

    for idx, raw in enumerate(lines, start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if not s.startswith("pkt="):
            # Observer header/summary lines are informational; ignore.
            continue
        if len(records) >= MAX_RECORDS + 200:
            # Hard stop to stay bounded even before limit error.
            errors.append("record count far exceeds bound; stopped parsing")
            break
        try:
            rec = parse_record_line(s, idx)
        except RecordError as e:
            malformed += 1
            errors.append(str(e)[:200])
            continue
        if rec["pkt"] in seen_pkt:
            malformed += 1
            errors.append(f"line {idx}: duplicate pkt={rec['pkt']}")
            continue
        seen_pkt.add(rec["pkt"])
        records.append(rec)

    # Fail-closed: ANY malformed record aborts the whole decode. No partial
    # application messages are reported alongside record errors.
    if errors:
        return _error_report(errors, warnings, len(records), malformed)

    if len(records) > MAX_RECORDS:
        return _error_report(
            errors + [f"record limit exceeded: {len(records)} > {MAX_RECORDS}"],
            warnings, len(records), malformed,
        )
    # Per-service-port bound counts records touching each service port.
    for rec in records:
        ports = set()
        if rec["sport"] in SERVICE_PORTS:
            ports.add(rec["sport"])
        if rec["dport"] in SERVICE_PORTS:
            ports.add(rec["dport"])
        for p in ports or (rec["dport"],):
            per_port[p] = per_port.get(p, 0) + 1
    for p, c in sorted(per_port.items()):
        if p in SERVICE_PORTS and c > MAX_PER_PORT:
            return _error_report(
                errors + [f"per-port record limit exceeded: port {p} has {c} > {MAX_PER_PORT}"],
                warnings, len(records), malformed,
            )

    records.sort(key=lambda r: r["pkt"])
    # Informational pkt-sequence gaps (emitted only matching legs).
    pkt_gaps = 0
    for a, b in zip(records, records[1:]):
        if b["pkt"] > a["pkt"] + 1:
            pkt_gaps += 1

    flows: dict[tuple, FlowState] = {}
    stream_budget = [0]
    for rec in records:
        if rec["payload_len"] == 0:
            skipped_ack += 1
            continue
        if not is_known_endpoint(rec):
            skipped_endpoint += 1
            continue
        # All surviving records (including oversize ones) go through
        # FlowState.add_record, which flushes the pending run on oversize /
        # truncated captures so nothing is ever decoded across dropped bytes.
        key = (rec["src_hex"], rec["dst_hex"], rec["sport"], rec["dport"])
        st = flows.get(key)
        if st is None:
            label = f"{rec['src_hex']}:{rec['sport']}->{rec['dst_hex']}:{rec['dport']}"
            st = FlowState(key, is_server_sender(rec), label)
            flows[key] = st
        st.add_record(rec, errors, stream_budget)
        if stream_budget[0] > MAX_STREAM_BYTES:
            return _error_report(
                errors + [f"total stream byte budget exceeded (> {MAX_STREAM_BYTES})"],
                warnings, len(records), malformed,
            )

    flow_reports = []
    complete_messages = 0
    recognized_messages = 0
    candidate_unverified_flows = 0
    for key in sorted(flows.keys()):
        st = flows[key]
        # Ensure start boundary set even with no complete frame.
        if st.start_boundary is None:
            st.start_boundary = "candidate_unverified" if st.had_data else "no_data"
        if st.start_boundary == "candidate_unverified":
            candidate_unverified_flows += 1
        msgs = [f for f in st.frames
                if f.get("complete") and f.get("app_complete")
                and f.get("kind") in ("json", "msgpack")]
        complete_messages += len(msgs)
        recognized_messages += sum(1 for f in msgs if f.get("recognized"))
        direction = "server_to_client" if st.server_sender else "client_to_server"
        service_port = st.key[2] if st.key[0] == CAM_HEX else st.key[3]
        flow_reports.append({
            "flow": st.label,
            "direction": direction,
            "service_port": service_port,
            "server_sender": bool(st.server_sender),
            "pkt_numbers": list(st.pkt_numbers)[:MAX_RECORDS],
            "bytes_assembled": len(st.run_buf) + st.frame_offset_base,
            "run_bytes_pending": len(st.run_buf) - st.run_decoded,
            "gaps": st.gaps,
            "retrans_dedup": st.retrans_dedup,
            "overlap_extended": st.overlap_extended,
            "conflicts": st.conflicts,
            "truncated_skipped": st.truncated_skipped,
            "oversize_skipped": st.oversize_skipped,
            "suspended": st.suspended,
            "start_boundary": st.start_boundary,
            "frames": st.frames[:64],
            "complete_messages": len(msgs),
            "recognized_messages": sum(1 for f in msgs if f.get("recognized")),
        })
        if st.gaps:
            warnings.append(f"flow {st.label}: {st.gaps} gap/truncation flush(es); no decode across gaps")
        if st.conflicts or (st.suspended or "").startswith("conflict"):
            warnings.append(f"flow {st.label}: overlap conflict; flow suspended (fail-closed)")
        if st.truncated_skipped:
            warnings.append(f"flow {st.label}: {st.truncated_skipped} truncated capture(s) flushed, not decoded")
        if st.oversize_skipped:
            warnings.append(f"flow {st.label}: {st.oversize_skipped} oversize capture(s) flushed, not decoded")

    status = "ok" if not errors else "error"
    report = {
        "tool": "decode_passive_records",
        "observer": "observer_v4",
        "status": status,
        "fail_closed": bool(errors),
        "limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "max_records": MAX_RECORDS,
            "max_per_service_port": MAX_PER_PORT,
            "max_stream_bytes": MAX_STREAM_BYTES,
            "max_frame_bytes": MAX_FRAME_BYTES,
            "max_payload_per_record": MAX_PAYLOAD_PER_RECORD,
            "max_frames_per_flow": MAX_FRAMES_PER_FLOW,
        },
        "input": {
            "records_total": len(records),
            "malformed_records": malformed,
            "skipped_ack_only": skipped_ack,
            "skipped_unknown_endpoint": skipped_endpoint,
            "pkt_sequence_gaps": pkt_gaps,
            "flows": len(flow_reports),
        },
        "flows": flow_reports,
        "complete_messages": complete_messages,
        "recognized_messages": recognized_messages,
        "candidate_unverified_flows": candidate_unverified_flows,
        "errors": errors[:32],
        "warnings": warnings[:32],
        "disclaimers": [DISCLAIMER_DECODE, DISCLAIMER_NO_INJECTION, DISCLAIMER_BOUNDARY],
    }
    return report


def _error_report(errors: list[str], warnings: list[str], n_records: int, malformed: int) -> dict:
    return {
        "tool": "decode_passive_records",
        "observer": "observer_v4",
        "status": "error",
        "fail_closed": True,
        "limits": {
            "max_input_bytes": MAX_INPUT_BYTES,
            "max_records": MAX_RECORDS,
            "max_per_service_port": MAX_PER_PORT,
            "max_stream_bytes": MAX_STREAM_BYTES,
            "max_frame_bytes": MAX_FRAME_BYTES,
            "max_payload_per_record": MAX_PAYLOAD_PER_RECORD,
            "max_frames_per_flow": MAX_FRAMES_PER_FLOW,
        },
        "input": {
            "records_total": n_records,
            "malformed_records": malformed,
            "skipped_ack_only": 0,
            "skipped_unknown_endpoint": 0,
            "pkt_sequence_gaps": 0,
            "flows": 0,
        },
        "flows": [],
        "complete_messages": 0,
        "recognized_messages": 0,
        "candidate_unverified_flows": 0,
        "errors": [e[:200] for e in errors[:32]],
        "warnings": [w[:200] for w in warnings[:32]],
        "disclaimers": [DISCLAIMER_DECODE, DISCLAIMER_NO_INJECTION, DISCLAIMER_BOUNDARY],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline decoder for M4 observer_v4 passive records. "
                    "Local files only; no network. SAFE metadata output only.")
    ap.add_argument("capture", help="observer stdout capture file (text)")
    ap.add_argument("--report", default=None,
                    help="write JSON report to this file (default: stdout)")
    args = ap.parse_args(argv)
    cap = Path(args.capture)
    try:
        size = cap.stat().st_size
    except Exception:
        print(json.dumps(_error_report(["cannot open capture file"], [], 0, 0), indent=2))
        return 2
    if size > MAX_INPUT_BYTES:
        rep = _error_report(
            [f"input too large: {size} > {MAX_INPUT_BYTES} (fail-closed)"], [], 0, 0)
        _emit(rep, args.report)
        return 2
    try:
        text = cap.read_text(encoding="utf-8", errors="strict")
    except Exception:
        rep = _error_report(["capture file is not valid UTF-8 text (fail-closed)"], [], 0, 0)
        _emit(rep, args.report)
        return 2
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        rep = _error_report(["input too large after decode (fail-closed)"], [], 0, 0)
        _emit(rep, args.report)
        return 2
    try:
        report = decode_capture_text(text)
    except Exception:
        # Never leak tracebacks or raw values.
        report = _error_report(["internal decode failure (fail-closed)"], [], 0, 0)
    rc = 0 if report.get("status") == "ok" else 1
    _emit(report, args.report)
    return rc


def _emit(report: dict, dest: str | None) -> None:
    blob = json.dumps(report, indent=2, ensure_ascii=False)
    # Runner output cap ~100 KiB: keep report bounded.
    if len(blob.encode("utf-8")) > 100 * 1024:
        slim = dict(report)
        slim["flows"] = []
        slim["warnings"] = (slim.get("warnings", [])[:8] +
                            ["report truncated to respect output cap"])
        blob = json.dumps(slim, indent=2, ensure_ascii=False)
    if dest:
        try:
            Path(dest).write_text(blob + "\n", encoding="utf-8")
        except Exception:
            print(blob)
    else:
        print(blob)


if __name__ == "__main__":
    sys.exit(main())
