#!/usr/bin/env python3
"""Bounded stationary-host TSR capture with a verified legacy CGI identity.

Never runs automatically. Sends only a GET identity request, WebSocket
handshake, stock libflow TSR subscription and close/control frames. No
settings, UART, FIFO or M4 warning writes. Ports/names are static evidence;
production WS path/activation/bind and payload units are runtime-unverified.
Requires owner-authorized stationary use. Output is private observation only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import websocket

from libflow_protocol import decode_ws_binary, pack_subscription

IDENTITY_PATH = "/cgi-bin/Config.cgi?action=get&property=Camera.menu.UUID"
MAX_FRAME = 256 * 1024


def check_identity(host: str, expected: str) -> dict:
    request = urllib.request.Request("http://" + host + IDENTITY_PATH,
                                    headers={"Connection": "close"}, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=3) as response:
        data = response.read(4097)
        if response.status != 200 or len(data) > 4096:
            raise ValueError("identity response invalid")
    try:
        lines = data.decode("ascii", "strict").splitlines()
    except UnicodeDecodeError:
        raise ValueError("identity is not legacy CGI") from None
    ids = [line.split("=", 1)[1] for line in lines if line.startswith("Camera.menu.UUID=")]
    if ids != [expected]:
        raise ValueError("device identity mismatch")
    return {"identity_verified": True, "identity_response_sha256": hashlib.sha256(data).hexdigest()}


def describe(payload: bytes) -> dict:
    result = decode_ws_binary(payload)
    row = {"frame_sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
           "outer_topic": result.outer.get("topic"), "warnings": result.warnings,
           "schema_runtime_verified": False}
    if isinstance(result.inner, dict):
        row["inner_key"] = result.inner.get("key")
        body = result.inner.get("data")
        if isinstance(body, dict):
            row["body_fields"] = sorted(str(key) for key in body)
        elif isinstance(body, list):
            row["body_count"] = len(body)
        row["body_type"] = type(body).__name__
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", choices=["192.168.1.1"], default="192.168.1.1")
    ap.add_argument("--expected-uuid", required=True, help="owner-supplied exact device UUID, never guessed")
    ap.add_argument("--port", type=int, choices=[25012, 26012], default=25012)
    ap.add_argument("--path", default="/", help="production path remains unverified")
    ap.add_argument("--seconds", type=int, choices=range(1, 61), default=15)
    ap.add_argument("--max-frames", type=int, choices=range(1, 101), default=50)
    ap.add_argument("--out", type=Path, required=True, help="new PRIVATE directory under ignored build/")
    ap.add_argument("--stationary-authorized", action="store_true")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[2]
    allowed = (repo / "build").resolve()
    out = args.out.resolve()
    if not args.stationary_authorized or not out.is_relative_to(allowed) or out == allowed or out.exists():
        ap.error("require owner authorization and a new output directory under build/")
    if not args.path.startswith("/") or len(args.path) > 128 or any(c in args.path for c in "?#\r\n"):
        ap.error("invalid explicit WS path")
    started = time.monotonic()
    report = {"verdict": "NOT_CAPTURED", "device_settings_writes": False,
              "uart_access": False, "warning_injection": False, "port": args.port,
              "path": args.path, "runtime_schema_verified": False, "frames": []}
    ws = None
    created = False
    try:
        report.update(check_identity(args.host, args.expected_uuid))
        # Identity verification must precede WS and creation of evidence output.
        out.mkdir(parents=True, exist_ok=False)
        created = True
        ws = websocket.create_connection("ws://%s:%d%s" % (args.host, args.port, args.path),
                                         timeout=3, enable_multithread=False,
                                         http_no_proxy=[args.host])
        ws.send(pack_subscription("c2m-tsr-readonly", "tsr"), opcode=websocket.ABNF.OPCODE_BINARY)
        deadline = time.monotonic() + args.seconds
        while len(report["frames"]) < args.max_frames and time.monotonic() < deadline:
            ws.settimeout(min(2, max(0.05, deadline - time.monotonic())))
            try:
                opcode, data = ws.recv_data(control_frame=True)
            except websocket.WebSocketTimeoutException:
                continue
            if opcode == websocket.ABNF.OPCODE_CLOSE:
                break
            if opcode != websocket.ABNF.OPCODE_BINARY:
                continue
            if len(data) > MAX_FRAME:
                report["verdict"] = "BLOCKED_OVERSIZED_FRAME"
                break
            index = len(report["frames"])
            # Raw captured vendor message bytes remain private/ignored only.
            (out / ("frame-%03d.msgpack" % index)).write_bytes(data)
            try:
                row = describe(data)
            except Exception:
                row = {"decode": "FAILED", "bytes": len(data), "frame_sha256": hashlib.sha256(data).hexdigest()}
            report["frames"].append(row)
        if report["verdict"] == "NOT_CAPTURED":
            report["verdict"] = "CAPTURED_UNVERIFIED" if report["frames"] else "NO_FRAMES_NOT_DETECTION_FAILURE"
    except (OSError, ValueError, urllib.error.URLError, websocket.WebSocketException):
        # Avoid echoing identity/network response, secrets or raw payload.
        report["verdict"] = "BLOCKED_IDENTITY_OR_SERVICE_UNAVAILABLE"
    finally:
        if ws is not None:
            try:
                ws.close()
            except (OSError, websocket.WebSocketException):
                pass
        report["elapsed_s"] = round(time.monotonic() - started, 3)
        if created:
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # stdout is limited to status/counts, no config or identity.
    print(json.dumps({"verdict": report["verdict"], "frames": len(report["frames"]),
                      "device_settings_writes": False, "uart_access": False}))
    return 1 if report["verdict"].startswith("BLOCKED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
