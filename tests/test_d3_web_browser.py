#!/usr/bin/env python3
"""Real Chromium form regression against native D3 server on loopback only.

No camera, WiFi, card, firmware, or owner credentials. Uses synthetic test data
and a fresh temporary browser profile. Requires Linux, Chromium/Chrome and
websocket-client; C2M_REQUIRE_BROWSER_TEST=1 makes missing prerequisites fail.
Run: python3 tests/test_d3_web_browser.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

import test_d3_web as web_tests

try:
    import websocket
except ImportError:
    websocket = None


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        browser = os.environ.get("C2M_BROWSER") or next(
            (p for name in ("google-chrome", "chromium", "chromium-browser")
             if (p := shutil.which(name))), None)
        if not sys.platform.startswith("linux") or not browser or websocket is None:
            reason = "Linux, Chromium/Chrome and websocket-client required"
            if os.environ.get("C2M_REQUIRE_BROWSER_TEST") == "1":
                raise AssertionError(reason)
            raise unittest.SkipTest(reason)
        cls.browser = browser
        web_tests.LocalhostTests.setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        web_tests.LocalhostTests.tearDownClass()

    def setUp(self) -> None:
        self.http = web_tests.LocalhostTests()
        self.http.setUp()
        self.addCleanup(self.http.tearDown)
        self.profile = tempfile.TemporaryDirectory(prefix="c2m-browser-")
        self.addCleanup(self.profile.cleanup)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.debug_port = sock.getsockname()[1]
        self.debug_origin = f"http://127.0.0.1:{self.debug_port}"
        self.browser_proc = subprocess.Popen([
            self.browser, "--headless=new", "--disable-gpu", "--no-proxy-server",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--no-first-run", "--no-default-browser-check",
            f"--remote-debugging-port={self.debug_port}",
            f"--remote-allow-origins={self.debug_origin}",
            f"--user-data-dir={self.profile.name}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.close_browser)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 15
        while True:
            try:
                with opener.open(self.debug_origin + "/json/list", timeout=1) as response:
                    targets = json.load(response)
                target = next(t for t in targets if t.get("type") == "page")
                break
            except (OSError, ValueError, StopIteration):
                if self.browser_proc.poll() is not None or time.monotonic() > deadline:
                    self.fail("isolated browser failed to start")
                time.sleep(0.05)
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10,
                                             origin=self.debug_origin, http_no_proxy=["127.0.0.1"])
        self.sequence = 0
        self.events = []
        self.command("Network.enable")
        self.command("Page.enable")
        self.command("Page.navigate", {"url": self.http.origin + "/"})
        self.wait_load()

    def close_browser(self) -> None:
        ws = getattr(self, "ws", None)
        if ws:
            try:
                self.command("Browser.close")
            except Exception:
                pass
            ws.close()
        try:
            self.browser_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.browser_proc.terminate()
            self.browser_proc.wait(timeout=5)

    def receive(self) -> dict:
        message = json.loads(self.ws.recv())
        if "method" in message:
            self.events.append(message)
        return message

    def command(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        sequence = self.sequence
        self.ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = self.receive()
            if message.get("id") == sequence:
                self.assertNotIn("error", message)
                return message.get("result", {})
        self.fail("browser command timed out: " + method)

    def evaluate(self, expression: str):
        result = self.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        self.assertNotIn("exceptionDetails", result)
        return result["result"].get("value")

    def wait_load(self) -> None:
        # Page.loadEventFired can arrive before Runtime.evaluate's response.
        if any(event.get("method") == "Page.loadEventFired" for event in self.events):
            return
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = self.receive()
            if message.get("method") == "Page.loadEventFired":
                return
        self.fail("browser navigation timed out")

    def test_native_http_forms_preserve_origin_and_complete(self) -> None:
        self.assertEqual(self.evaluate("document.forms.length"), 3)
        # Fill the actual service-rendered form, not a scripted HTTP request.
        self.events.clear()
        self.evaluate("""(()=>{const f=document.forms[0];
            f.elements.ssid.value='BrowserFixture';
            f.elements.password.value='synthetic-passphrase';
            f.requestSubmit();return 'submitted';})()""")
        self.wait_load()
        self.assertEqual(self.evaluate("location.href"), self.http.origin + "/?notice=saved")
        self.assertTrue((self.http.config / "wifi.conf").is_file())
        self.assertFalse((self.http.run_dir / "connect.request").exists())
        # Verify the browser generated the canonical Origin on the actual POST.
        posts = [event["params"] for event in self.events
                 if event.get("method") == "Network.requestWillBeSent"
                 and event["params"].get("request", {}).get("method") == "POST"]
        self.assertTrue(posts, "missing browser POST evidence")
        self.assertEqual(posts[0]["request"]["headers"].get("Origin"), self.http.origin)
        self.events.clear()
        self.evaluate("document.forms[1].requestSubmit(); 'submitted'")
        self.wait_load()
        self.assertEqual(self.evaluate("location.href"), self.http.origin + "/?notice=queued")
        self.assertEqual((self.http.run_dir / "connect.request").read_text(),
                         "version=1\naction=connect\n")
        self.events.clear()
        self.evaluate("document.forms[2].requestSubmit(); 'submitted'")
        self.wait_load()
        self.assertEqual(self.evaluate("location.href"), self.http.origin + "/?notice=forgotten")
        self.assertFalse((self.http.config / "wifi.conf").exists())
        self.assertTrue((self.http.run_dir / "connect.request").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
