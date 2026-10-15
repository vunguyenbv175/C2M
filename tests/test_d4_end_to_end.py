#!/usr/bin/env python3
"""Synthetic GPS file -> native D4 daemon -> native web -> actual Chrome.

Linux-only integration, entirely in private temporary directories and on
127.0.0.1. No camera/card, real GPS path/API, private database, camera audio,
WiFi operation or external HTTP request. Unlike presentation-only tests, this
test never fabricates a sign-status snapshot: only the real producer writes it.
Requires a native C compiler, Chrome/Chromium and websocket-client;
C2M_REQUIRE_BROWSER_TEST=1 makes missing browser prerequisites fail, not skip.
Run: python3 -B tests/test_d4_end_to_end.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import stat
import struct
import subprocess
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import test_d3_web as web_tests
import test_d3_web_browser as browser_tests


ROOT = Path(__file__).resolve().parents[1]
STATUS_KEYS = {"version", "source", "state", "gps_fresh", "active", "sequence",
               "code", "speed_kmh", "distance_m", "event_id", "monotonic_ms"}
API_KEYS = STATUS_KEYS | {"status_available", "expires_in_ms"}


def synthetic_gps(second: int) -> bytes:
    """Vendor LE GPS region, signed NMEA DDMM, not decimal degrees."""
    utc = datetime.datetime(2026, 10, 15, 12) + datetime.timedelta(seconds=second)
    record = bytearray(0x1c0)
    struct.pack_into("<10I", record, 0, 8, utc.year - 1900, utc.month - 1,
                     utc.day, utc.hour, utc.minute, utc.second, 0, 1, 3)
    struct.pack_into("<dd", record, 0x40, 1000.0, 10600.0)
    struct.pack_into("<dd", record, 0x58, 36.0, 0.0)
    snapshot = bytearray(0x4f0)
    snapshot[0x330:0x4f0] = record
    return bytes(snapshot)


class GPSWriter:
    """Advance UTC by one second only after a real monotonic second elapsed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.stopping = threading.Event()
        self.errors: list[Exception] = []
        self.thread = threading.Thread(target=self.run, name="synthetic-d4-gps", daemon=True)

    def publish(self, second: int) -> None:
        temporary = self.path.with_suffix(".next")
        try:
            with temporary.open("xb") as stream:
                os.chmod(temporary, 0o600)
                stream.write(synthetic_gps(second))
            # The adapter opens on every poll; each descriptor sees a complete
            # immutable region for its two matching read-only pread() calls.
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def start(self) -> None:
        self.publish(0)
        self.thread.start()

    def run(self) -> None:
        second = 0
        try:
            # Event.wait uses elapsed time, not GPS/wall clock. Delayed writes
            # never catch up in a burst or invent rapidly advancing GPS UTC.
            while not self.stopping.wait(1.0):
                second += 1
                self.publish(second)
        except Exception as error:
            self.errors.append(error)
            self.stopping.set()

    def stop(self) -> None:
        self.stopping.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise AssertionError("synthetic GPS writer did not stop")
        if self.errors:
            raise AssertionError("synthetic GPS writer failed: " + repr(self.errors))


class EndToEndTests(unittest.TestCase):
    # Borrow helpers, not a TestCase base/imported class: unittest must not
    # discover and rerun the unrelated D3 form regression methods here.
    setUpClass = browser_tests.BrowserTests.__dict__["setUpClass"]
    tearDownClass = browser_tests.BrowserTests.__dict__["tearDownClass"]
    close_browser = browser_tests.BrowserTests.close_browser
    receive = browser_tests.BrowserTests.receive
    command = browser_tests.BrowserTests.command
    evaluate = browser_tests.BrowserTests.evaluate
    wait_load = browser_tests.BrowserTests.wait_load

    def setUp(self) -> None:
        browser_tests.BrowserTests.setUp(self)
        self.http.stop()
        self.fixture = self.http.base / "producer"
        self.fixture.mkdir(mode=0o700)
        self.sign_status = self.fixture / "sign-status"
        original_args = self.http.args
        self.http.args = lambda: original_args() + ["--sign-status-file", str(self.sign_status)]
        self.http.start()

    def read_producer_status(self) -> dict:
        try:
            text = self.sign_status.read_text(encoding="ascii")
        except FileNotFoundError:
            return {}
        self.assertLessEqual(len(text), 512)
        lines = text.splitlines()
        fields = dict(line.split("=", 1) for line in lines)
        self.assertEqual(len(lines), len(fields), "no duplicate producer fields")
        self.assertEqual(set(fields), STATUS_KEYS, "no coordinates or free-text labels")
        self.assertEqual(fields["source"], "gps_offline")
        return fields

    def read_api(self) -> dict:
        code, headers, body = self.http.request("GET", "/api/signs")
        self.assertEqual(code, 200)
        self.assertTrue(headers["content-type"].startswith("application/json"))
        state = json.loads(body)
        self.assertEqual(set(state), API_KEYS, "GPS coordinates must not leave the producer")
        self.assertEqual(state["source"], "gps_offline")
        return state

    def read_dom(self) -> dict:
        return self.evaluate("""(() => {
            const el = id => document.getElementById(id), warning = el('warning');
            if (!warning) return {};
            return {visible: !warning.hidden && getComputedStyle(warning).display !== 'none'
                        && warning.getBoundingClientRect().height > 0,
                    hidden: warning.hidden, sign: el('sign').textContent,
                    speed: el('speed').textContent, distance: el('distance').textContent,
                    fresh: el('fresh').textContent, empty: !el('empty').hidden,
                    sound: el('sound').getAttribute('aria-pressed'),
                    lang: document.documentElement.lang};
        })()""")

    def assert_producer_alive(self, producer: subprocess.Popen, writer: GPSWriter) -> None:
        self.assertFalse(writer.errors, repr(writer.errors))
        if producer.poll() is not None:
            out, err = producer.communicate()
            self.fail("native D4 producer exited early: " + out + err)

    def test_native_gps_producer_web_render_and_stale_clear(self) -> None:
        binary = self.fixture / "c2m-d4"
        sources = [ROOT / "fw" / "d4" / "main.c", ROOT / "fw" / "d4" / "advisory.c",
                   ROOT / "fw" / "d3" / "gps_snapshot.c", ROOT / "fw" / "warner" / "db.c",
                   ROOT / "fw" / "warner" / "warner.c"]
        args = web_tests.compiler() + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
        args += [str(source) for source in sources]
        for directory in ("d4", "d3", "warner"):
            args += ["-I", str(ROOT / "fw" / directory)]
        args += ["-lm", "-o", str(binary)]
        built = subprocess.run(args, capture_output=True, text=True, timeout=90)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)

        database = self.fixture / "synthetic-signs.bin"
        # Exactly one heading-known R.420, about 80 m due north of the
        # decoded synthetic GPS (10 degrees N, 106 degrees E). Empty label:
        # the visible Vietnamese label must come from the web allowlist.
        database.write_bytes(b"C2MSDB01" + struct.pack("<I", 1) +
                             struct.pack("<ddf16s64s", 10.00072, 106.0, 0.0, b"R.420", b""))
        database.chmod(0o644)
        database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
        self.assertEqual(stat.S_IMODE(self.fixture.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o644)
        self.assertEqual(database.stat().st_uid, os.getuid())
        self.assertFalse(self.sign_status.exists(), "only the native daemon may publish status")
        gps = self.fixture / "synthetic-gps.bin"
        writer = GPSWriter(gps)
        producer = None
        try:
            writer.start()
            # All three absolute overrides are mandatory: never mix a host
            # fixture with any production default, and use invoking-UID trust.
            producer = subprocess.Popen([
                str(binary), "--serve", "--db", str(database), "--gps-file", str(gps),
                "--status-file", str(self.sign_status)], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 10
            self.events.clear()
            self.command("Page.navigate", {"url": self.http.origin + "/signs"})
            self.wait_load()
            raw, api, dom = {}, {}, {}
            while time.monotonic() < deadline:
                self.assert_producer_alive(producer, writer)
                raw, api, dom = self.read_producer_status(), self.read_api(), self.read_dom()
                if (raw.get("state") == "ready" and raw.get("active") == "1"
                        and api["state"] == "ready" and api["active"] and dom.get("visible")):
                    break
                time.sleep(0.05)
            else:
                self.fail(f"GPS -> producer -> Chrome did not become active within 10s: {raw}, {api}, {dom}")

            self.assertEqual(raw["gps_fresh"], "1")
            self.assertEqual(raw["code"], "residential_start")
            self.assertEqual(raw["speed_kmh"], "0", "R.420 is not a legal numeric speed limit")
            self.assertTrue(api["status_available"])
            self.assertTrue(api["gps_fresh"])
            self.assertEqual(api["code"], "residential_start")
            self.assertEqual(api["speed_kmh"], 0)
            self.assertEqual(api["event_id"], int(raw["event_id"]))
            self.assertGreater(api["event_id"], 0)
            self.assertGreater(api["expires_in_ms"], 0)
            self.assertLessEqual(api["expires_in_ms"], 3000)
            self.assertGreaterEqual(api["distance_m"], 70)
            self.assertLessEqual(api["distance_m"], 95)
            self.assertEqual(dom["sign"], "Bắt đầu khu dân cư")
            self.assertEqual(dom["speed"], "")
            self.assertIn("Khoảng cách trong dữ liệu:", dom["distance"])
            self.assertIn("GPS mới theo nguồn ngoại tuyến", dom["fresh"])
            self.assertEqual(dom["lang"], "vi")
            self.assertEqual(dom["sound"], "false", "no camera or browser audio requested")
            self.assertFalse(dom["empty"])
            self.assertEqual(stat.S_IMODE(self.sign_status.stat().st_mode), 0o600)
            self.assertEqual(self.sign_status.stat().st_uid, os.getuid())
            active_sequence = int(raw["sequence"])
            active_monotonic = int(raw["monotonic_ms"])

            # Freeze, do not remove/corrupt GPS and do not stop the producer.
            # Its live heartbeats must report stale GPS; this is not merely
            # web TTL expiry after killing a synthetic status publisher.
            stopped_at = time.monotonic()
            writer.stop()
            frozen_hash = hashlib.sha256(gps.read_bytes()).hexdigest()
            deadline = stopped_at + 6
            while time.monotonic() < deadline:
                self.assert_producer_alive(producer, writer)
                raw, api, dom = self.read_producer_status(), self.read_api(), self.read_dom()
                if (raw.get("state") == "stale" and raw.get("active") == "0"
                        and api["state"] == "stale" and not api["active"]
                        and dom.get("hidden") and dom.get("sign") == ""
                        and "Dữ liệu đã cũ" in dom.get("fresh", "")):
                    break
                time.sleep(0.05)
            else:
                self.fail(f"frozen GPS did not clear producer/API/Chrome within 6s: {raw}, {api}, {dom}")
            self.assertLessEqual(time.monotonic() - stopped_at, 6)
            self.assertEqual(raw["gps_fresh"], "0")
            self.assertEqual(raw["code"], "none")
            self.assertEqual(raw["event_id"], "0")
            self.assertEqual(raw["distance_m"], "0")
            self.assertGreater(int(raw["sequence"]), active_sequence)
            self.assertGreater(int(raw["monotonic_ms"]), active_monotonic)
            self.assertTrue(api["status_available"], "producer is still publishing fresh heartbeats")
            self.assertFalse(api["gps_fresh"])
            self.assertEqual(api["code"], "none")
            self.assertEqual(api["event_id"], 0)
            self.assertGreater(api["expires_in_ms"], 0)
            self.assertFalse(dom["visible"])
            self.assertEqual(dom["speed"], "")
            self.assertEqual(dom["distance"], "")
            self.assertTrue(dom["empty"])
            self.assertEqual(hashlib.sha256(gps.read_bytes()).hexdigest(), frozen_hash)
            self.assertEqual(list(self.http.config.iterdir()), [])
            self.assertEqual(list(self.http.run_dir.iterdir()), [])

            requests = [event["params"]["request"] for event in self.events
                        if event.get("method") == "Network.requestWillBeSent"]
            self.assertTrue(any(urlsplit(request["url"]).path == "/api/signs" for request in requests),
                            "actual Chrome must poll the real native API")
            for request in requests:
                url = urlsplit(request["url"])
                self.assertEqual(url.scheme + "://" + url.netloc, self.http.origin)
                self.assertEqual(request["method"], "GET")
                self.assertIn(url.path, ("/signs", "/signs.js", "/api/signs", "/favicon.ico"),
                              "no ConfigCGI, camera output, GPS API or controller requests")
                self.assertNotIn("config.cgi", request["url"].lower())
            self.assertIsNone(producer.poll())
        finally:
            try:
                writer.stop()
            finally:
                try:
                    if producer is not None:
                        # Terminate only the child created above, never a
                        # process-name kill or any stock/camera process.
                        if producer.poll() is None:
                            producer.terminate()
                        try:
                            out, err = producer.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            producer.kill()
                            out, err = producer.communicate(timeout=5)
                            self.fail("test-owned D4 daemon did not stop: " + out + err)
                        self.assertEqual(producer.returncode, 0, out + err)
                        self.assertEqual(out + err, "", "no location logging or camera output")
                finally:
                    self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), database_hash,
                                     "the native producer must never modify the synthetic database")


if __name__ == "__main__":
    unittest.main(verbosity=2)
