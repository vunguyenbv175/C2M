#!/usr/bin/env python3
"""Actual Chrome D4 presentation/expiry on localhost, synthetic snapshots only.
No camera, card, GPS, external site, owner data, stock output or network change.
"""
from __future__ import annotations

import json
import os
import threading
import time
import unittest
import urllib.request

import test_d3_web_browser as browser_tests
import test_d3_web as web_tests
import test_d4_web as signs_tests


class SignBrowserTests(unittest.TestCase):
    setUpClass = browser_tests.BrowserTests.__dict__["setUpClass"]
    tearDownClass = browser_tests.BrowserTests.__dict__["tearDownClass"]
    setUp = browser_tests.BrowserTests.setUp
    close_browser = browser_tests.BrowserTests.close_browser
    receive = browser_tests.BrowserTests.receive
    command = browser_tests.BrowserTests.command
    evaluate = browser_tests.BrowserTests.evaluate
    wait_load = browser_tests.BrowserTests.wait_load

    def navigate(self, path):
        self.events.clear()
        self.command("Page.navigate", {"url": self.http.origin + path})
        self.wait_load()

    def api_snapshot(self):
        # Live server-side snapshot age for failure diagnostics only. Never
        # used to synchronize the test; the browser's rendered DOM is the
        # verdict. Loopback synthetic fixture traffic only.
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(self.http.origin + "/api/signs", timeout=2) as response:
                return repr(response.read(512).decode("utf-8", "replace"))
        except Exception as exc:
            return "unavailable:" + repr(exc)

    def wait_js(self, expression, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.05)
        # Keep failures actionable without changing the production page or
        # relaxing its three-second native/browser freshness contract.
        diagnostic = self.evaluate("""(()=>({
            href:location.href,
            readyState:document.readyState,
            documentHidden:document.hidden,
            hidden:document.getElementById('warning')?.hidden,
            fresh:document.getElementById('fresh')?.textContent,
            distance:document.getElementById('distance')?.textContent,
            beeps:window.__beeps
        }))()""")
        errors = [event["params"] for event in self.events
                  if event.get("method") in ("Runtime.exceptionThrown", "Network.loadingFailed")]
        self.fail("browser state did not converge: " + expression + "; state=" + repr(diagnostic)
                  + "; api_snapshot=" + self.api_snapshot()
                  + "; browser_errors=" + repr(errors[-5:]))

    def _write_snapshot(self, sequence, event, active, state, fresh, distance):
        payload = signs_tests.snapshot(
            code="residential_start", speed_kmh=0, distance_m=distance,
            monotonic_ms=int(time.monotonic()*1000), sequence=sequence,
            event_id=event, active=active, state=state, gps_fresh=fresh)
        # The server may read while a poll is in progress. Replace a complete,
        # mode-correct snapshot instead of exposing write_bytes' truncation gap.
        temporary = self.sign_status.with_name(self.sign_status.name + ".tmp")
        try:
            temporary.write_bytes(payload)
            temporary.chmod(0o600)
            os.replace(temporary, self.sign_status)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _publish_once(self):
        with self._hb_lock:
            self.publisher_sequence += 1
            params = dict(self._hb_params)
            sequence = self.publisher_sequence
        self._write_snapshot(sequence=sequence, **params)

    def _heartbeat_loop(self):
        try:
            while not self._hb_stop.wait(self._hb_interval):
                self._publish_once()
        except Exception as exc:
            self._hb_error.append(exc)

    def start_heartbeat(self, interval=0.5):
        # Continuous synthetic producer: a fresh monotonic snapshot every
        # interval so every browser poll observes age well under the native
        # 3s TTL even when CI fetch latency spikes. Frozen explicitly only
        # for the expiry portion via stop_heartbeat.
        self._hb_lock = threading.Lock()
        self._hb_params = {"event": 1, "active": 1, "state": "ready",
                           "fresh": 1, "distance": 0}
        self._hb_stop = threading.Event()
        self._hb_error = []
        self._hb_interval = interval
        self._hb_thread = None
        self._publish_once()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()
        self.addCleanup(self.stop_heartbeat)

    def stop_heartbeat(self):
        # Freeze the producer so the snapshot ages out genuinely: both the
        # native status TTL and the browser timer must then clear the warning.
        thread = getattr(self, "_hb_thread", None)
        if thread is None:
            return
        self._hb_thread = None
        if getattr(self, "_hb_stop", None) is not None:
            self._hb_stop.set()
        thread.join(timeout=5)
        if thread.is_alive():
            self.fail("sign heartbeat thread did not stop")
        if getattr(self, "_hb_error", []):
            self.fail("sign heartbeat failed: " + repr(self._hb_error[0]))

    def set_producer(self, **changes):
        # Mutate heartbeat payload under the lock; the next 500ms tick
        # publishes the change with a fresh monotonic timestamp.
        with self._hb_lock:
            self._hb_params.update(changes)

    def next_distance(self):
        # Advance the stable generation marker the baseline waits on. The
        # heartbeat keeps republishing this marker, so the render converges
        # deterministically instead of racing a one-shot sequence number.
        with self._hb_lock:
            self._hb_params["distance"] += 1
            return self._hb_params["distance"]

    def configure_sign_server(self):
        self.http.stop()
        self.sign_status = self.http.base / "sign-status"
        original_args = self.http.args
        self.http.args = lambda: original_args() + ["--sign-status-file", str(self.sign_status)]
        self.http.start()
        self.publisher_sequence = 0

    def click_sound(self):
        coords = self.evaluate("(()=>{const r=document.getElementById('sound').getBoundingClientRect();"
                               "return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
        for kind in ("mousePressed", "mouseReleased"):
            self.command("Input.dispatchMouseEvent", {"type": kind, "x": coords["x"], "y": coords["y"],
                                                     "button": "left", "clickCount": 1})

    def test_actual_render_audio_gesture_dedup_and_expiry(self):
        self.configure_sign_server()
        self.command("Runtime.enable")
        # Add instrumentation before the first page JS; actual browser audio
        # constructor/autoplay policy stays intact. Counts scheduling, not hearing.
        # An IIFE avoids introducing page-global lexical bindings. Do not wrap
        # fetch/Response.json: baseline synchronization uses rendered fixture data.
        self.command("Page.addScriptToEvaluateOnNewDocument", {"source": """
            (()=>{
                window.__beeps=0;
                const original=AudioContext.prototype.createOscillator;
                AudioContext.prototype.createOscillator=function(){
                    const oscillator=original.call(this),start=oscillator.start.bind(oscillator);
                    oscillator.start=function(...args){window.__beeps++;return start(...args);};return oscillator;};
            })();
        """})
        # Start the synthetic producer after instrumentation but before
        # navigation, so the page's immediate first poll already observes a
        # fresh snapshot; the 500ms heartbeats then keep every later poll
        # under the 3s TTL.
        self.start_heartbeat()
        self.navigate("/signs")
        # Heartbeats keep refreshing, so this asserts a genuine fresh render
        # in a bounded 6s rather than a race against one snapshot's 3s TTL.
        self.wait_js("!document.getElementById('warning').hidden", timeout=6)
        self.assertIn("GPS", self.evaluate("document.body.innerText"))
        self.assertEqual(self.evaluate("window.__beeps"), 0)
        self.assertEqual(self.evaluate("document.getElementById('sound').getAttribute('aria-pressed')"), "false")
        self.click_sound()
        self.wait_js("document.getElementById('sound').getAttribute('aria-pressed')==='true'")
        self.assertEqual(self.evaluate("window.__beeps"), 0, "enable is not replay")
        # One request may have started before the gesture. Observe two distinct
        # rendered heartbeats of the same event: the second necessarily comes
        # from a post-enable poll and establishes the silent baseline. The
        # heartbeat keeps republishing the marker, so each bump converges
        # without racing a one-shot sequence number or touching fetch/JSON.
        for _ in range(2):
            marker = self.next_distance()
            self.wait_js(f"document.getElementById('distance').textContent==={json.dumps(f'Khoảng cách trong dữ liệu: {marker} m')}")
        self.assertEqual(self.evaluate("window.__beeps"), 0, "baseline is silent")
        self.set_producer(event=2)
        self.wait_js("window.__beeps===1")
        # Heartbeats keep refreshing the same event: never a repeated sound.
        time.sleep(1.2)
        self.assertEqual(self.evaluate("window.__beeps"), 1, "heartbeat never repeats sound")
        self.set_producer(active=0)
        self.wait_js("document.getElementById('warning').hidden")
        self.set_producer(event=3, active=1)
        self.wait_js("!document.getElementById('warning').hidden")
        self.wait_js("window.__beeps===2")
        # Freeze the producer explicitly only here: both native status TTL
        # and browser timer must then clear a genuinely expiring warning.
        self.stop_heartbeat()
        self.wait_js("document.getElementById('warning').hidden", timeout=5)
        self.assertEqual(self.evaluate("window.__beeps"), 2)
        # Disconnect native status producer: never preserve previous warning.
        self.sign_status.unlink()
        self.wait_js("document.getElementById('warning').hidden")
        self.assertEqual(list(self.http.config.iterdir()), [])
        self.assertEqual(list(self.http.run_dir.iterdir()), [])
        # Actual browser requests may only use the isolated loopback origin.
        urls = [event["params"]["request"]["url"] for event in self.events
                if event.get("method") == "Network.requestWillBeSent"]
        self.assertTrue(any(url.endswith("/api/signs") for url in urls))
        self.assertFalse(any(url.startswith(("http://", "https://")) and not url.startswith(self.http.origin + "/") for url in urls))
        self.assertFalse(any("Config.cgi" in url or "/api/connect" in url for url in urls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
