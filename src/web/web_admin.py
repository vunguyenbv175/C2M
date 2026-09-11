#!/usr/bin/env python3
"""EF-A05 Web Admin V0 — read-only. Mirrors EnhanceCore + MockADASProvider for host demo.

Endpoints: /  /status  /diagnostics
No settings-write, no updater, no stock control.
"""
from __future__ import annotations
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import sys
sys.path.insert(0, "tools/m4")
from normalize_adas import normalize_stock  # noqa: E402  (reuse EF-A01 mapping)


def mock_snapshot(scenario: str, tick: int) -> dict:
    now = 1_000 + tick * 200
    nums: dict = {}
    if scenario in ("lead", "fcw"):
        dist, ttc = (6.5, 1.1) if scenario == "fcw" else (22.0, 3.4)
        nums["vehicleMeasure"] = [{"vehicle_class": 1, "vehicle_id": 1, "vehicle_width": 1.8,
                                   "longitude_dist": dist, "lateral_dist": 0.3, "ttc": ttc,
                                   "is_crucial": 1, "is_second_crucial": 0}]
        if scenario == "fcw":
            nums["vehicleWarning"] = [{"vehicle_id": 1, "headway": 0.9, "warning_level": 2,
                                       "fcw": 1, "headway_warning": 1, "vb_warning": 0, "sag_warning": 0}]
    if scenario == "ldw":
        nums["laneWarningRes"] = [{"deviate_state": 1, "turn_radius": 250.0, "turn_frequently": 0}]
    if scenario == "ped":
        nums["pedestrians"] = [{"id": 7, "world_x": 1.2, "world_y": 8.0, "is_key": 0,
                                "is_danger": 1, "ttc_m": 1.4, "ttc": 1.4, "have_bike": 0}]
    return {"now_ms": now, "last_frame_ms": now - 100, "frame_id": tick,
            "libflow_reachable": True, "subscription_active": True,
            "cardv_reachable": True, "frame_seen": True, "nums": nums,
            "cardv": {"AdasStatus": "ON", "HeavyCalibStatus": "CALIB_OK"}}


INDEX_HTML = """<!doctype html><meta charset=utf-8><title>C2M Enhanced V0 (HOST PROTOTYPE)</title>
<h1>C2M Enhanced — read-only V0 — HOST PROTOTYPE</h1>
<p>Mock transport only; not connected to device. Stock app/recorder untouched. Scenario: <b>{scenario}</b></p>
<ul><li><a href=/status>/status</a></li><li><a href=/diagnostics>/diagnostics</a></li></ul>
<pre id=s>loading…</pre>
<script>setInterval(async()=>{s.textContent=JSON.stringify(await(await fetch('/status')).json(),null,2)},1000)</script>
"""


class Handler(BaseHTTPRequestHandler):
    scenario = "lead"
    started = time.time()
    tick = 0

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Handler.tick += 1
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, INDEX_HTML.format(scenario=Handler.scenario).encode(), "text/html; charset=utf-8")
        elif path == "/status":
            adas = normalize_stock(mock_snapshot(Handler.scenario, Handler.tick))
            body = {"service": "c2m-enhance-v0", "mode": "read-only",
                    "transport": "mock (HOST PROTOTYPE)",
                    "scenario": Handler.scenario, "uptime_s": round(time.time() - Handler.started, 1),
                    "adas": adas,
                    "display": {"objects": len(adas["vehicles"]) + len(adas["pedestrians"]),
                                "warnings": {k: v for k, v in
                                             (("fcw", adas["fcw"]), ("ldw", adas["ldw"]), ("pcw", adas["pcw"]))}}}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json")
        elif path == "/diagnostics":
            body = {"timestamp_ms": int(time.time() * 1000), "soc_temp_c": 0.0,
                    "mem_used_percent": 0.0, "storage_used_percent": 0.0, "sd_health": "MOCK",
                    "camera_state": "MOCK", "adas_state": "MOCK",
                    "m4_state": "MOCK-unproven-transport", "gps_state": "MOCK",
                    "road_db_version": "mock-v1",
                    "services": {"c2m-enhance": True, "stock-recorder": True}}
            self._send(200, json.dumps(body, ensure_ascii=False).encode(), "application/json")
        else:
            self._send(404, b'{"error":"not-found"}', "application/json")

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--scenario", default="lead", choices=["idle", "lead", "fcw", "ldw", "ped"])
    args = ap.parse_args()
    Handler.scenario = args.scenario
    srv = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"c2m-web V0 read-only on http://127.0.0.1:{args.port}/ scenario={args.scenario}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
