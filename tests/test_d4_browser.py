#!/usr/bin/env python3
"""Actual Chrome D4 presentation/expiry on localhost, synthetic snapshots only.
No camera, card, GPS, external site, owner data, stock output or network change.
"""
from __future__ import annotations

import json
import os
import time
import unittest

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
                  + "; browser_errors=" + repr(errors[-5:]))

    def publish(self, event=1, active=1, state="ready", fresh=1):
        self.publisher_sequence += 1
        payload = signs_tests.snapshot(
            code="residential_start", speed_kmh=0, distance_m=self.publisher_sequence,
            monotonic_ms=int(time.monotonic()*1000), sequence=self.publisher_sequence,
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
        self.navigate("/signs")
        # Start the synthetic producer only after navigation/instrumentation. A
        # pre-navigation one-shot snapshot can expire before Chrome's first poll.
        self.publish()
        self.wait_js("!document.getElementById('warning').hidden")
        self.assertIn("GPS", self.evaluate("document.body.innerText"))
        self.assertEqual(self.evaluate("window.__beeps"), 0)
        self.assertEqual(self.evaluate("document.getElementById('sound').getAttribute('aria-pressed')"), "false")
        self.click_sound()
        self.wait_js("document.getElementById('sound').getAttribute('aria-pressed')==='true'")
        self.assertEqual(self.evaluate("window.__beeps"), 0, "enable is not replay")
        # One request may have started before the gesture. Observe two distinct
        # rendered heartbeats of the same event: the second necessarily comes
        # from a post-enable poll and establishes the silent baseline. Using the
        # displayed distance marker does not interfere with native fetch/JSON.
        for _ in range(2):
            self.publish(event=1)
            marker = json.dumps(f"Khoảng cách trong dữ liệu: {self.publisher_sequence} m")
            self.wait_js(f"document.getElementById('distance').textContent==={marker}")
        self.assertEqual(self.evaluate("window.__beeps"), 0, "baseline is silent")
        self.publish(event=2)
        self.wait_js("window.__beeps===1")
        self.publish(event=2)
        time.sleep(1.2)
        self.assertEqual(self.evaluate("window.__beeps"), 1, "heartbeat never repeats sound")
        self.publish(event=2, active=0)
        self.wait_js("document.getElementById('warning').hidden")
        self.publish(event=3)
        self.wait_js("!document.getElementById('warning').hidden")
        self.wait_js("window.__beeps===2")
        # No publisher heartbeat: both native status TTL and browser timer clear.
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
