#!/usr/bin/env python3
"""D4 source-only web checks; never access a camera, GPS, WiFi, SD or Internet.

Run: python tests/test_d4_web.py
Portable C parser tests and mocked browser JS tests run on Windows too.
HTTP/filesystem tests explicitly skip outside Linux and use only localhost and
private temporary files. See test_d3_web.py for compiler/binary overrides.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import test_d3_web as d3

SOURCE = d3.SOURCE
FIELDS = dict(version="1", source="gps_offline", state="ready", gps_fresh="1",
              active="1", sequence="42", code="speed_limit", speed_kmh="50",
              distance_m="125", event_id="7", monotonic_ms="10000")


def snapshot(**changes: object) -> bytes:
    fields = dict(FIELDS, **{k: str(v) for k, v in changes.items()})
    return "".join(f"{k}={v}\n" for k, v in fields.items()).encode("ascii")


def static_string(name: str) -> str:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index(f"static const char {name}[] =")
    end = source.index(";\n    respond", start)
    # These static resources use only JSON-compatible C string escapes.
    return "".join(json.loads(token) for token in re.findall(r'"(?:[^"\\]|\\.)*"', source[start:end]))


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-d4-parser-")
        base = Path(cls.tmp.name)
        cls.binary = base / ("parser.exe" if os.name == "nt" else "parser")
        wrapper = base / "parser.c"
        wrapper.write_text(r'''#define C2M_WEB_CORE_ONLY
#define main d3_main
#include "SOURCE_PATH"
#undef main
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
int main(int argc, char **argv)
{
    char text[C2M_WEB_MAX_BODY + 2];
    size_t n;
    uint64_t now;
    struct sign_status s;
    int result;
    if (argc != 2 || sign_number(argv[1], UINT64_MAX, &now) < 0) return 2;
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
#endif
    n = fread(text, 1, sizeof(text)-1, stdin); text[n] = 0;
    result = parse_sign_status(text, n, now, &s);
    printf("{\"valid\":%s,\"state\":\"%s\",\"code\":\"%s\",\"active\":%u,"
           "\"gps_fresh\":%u,\"status_available\":%u,\"speed_kmh\":%u,\"distance_m\":%u,"
           "\"sequence\":%" PRIu32 ",\"event_id\":%" PRIu32 ",\"monotonic_ms\":%" PRIu64
           ",\"expires_in_ms\":%u}\n", result == 0 ? "true" : "false", sign_states[s.state],
           sign_codes[s.code], s.active, s.gps_fresh, s.available, s.speed, s.distance,
           s.sequence, s.event_id, s.monotonic_ms, s.expires);
    return 0;
}
'''.replace("SOURCE_PATH", SOURCE.as_posix()), encoding="utf-8")
        result = subprocess.run(d3.compiler() + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                                                str(wrapper), "-o", str(cls.binary)],
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def parse(self, content: bytes, now: int = 10000) -> dict:
        result = subprocess.run([str(self.binary), str(now)], input=content,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_invalid(self, content: bytes, now: int = 10000) -> None:
        state = self.parse(content, now)
        self.assertFalse(state["valid"], content[:160])
        self.assertFalse(state["active"])
        self.assertFalse(state["status_available"])
        self.assertEqual(state["state"], "error")
        self.assertEqual(state["code"], "none")
        self.assertEqual(state["speed_kmh"], 0)
        self.assertEqual(state["distance_m"], 0)

    def test_valid_boundary_values_and_order_independence(self) -> None:
        state = self.parse(snapshot())
        self.assertTrue(state["valid"])
        self.assertTrue(state["active"])
        self.assertEqual(state["expires_in_ms"], 3000)
        self.assertEqual(state["code"], "speed_limit")
        for speed in (10, 130):
            state = self.parse(snapshot(speed_kmh=speed, distance_m=2000,
                                        sequence=4294967295, event_id=4294967295))
            self.assertTrue(state["valid"])
            self.assertEqual(state["speed_kmh"], speed)
            self.assertEqual(state["sequence"], 4294967295)
        reversed_lines = b"\n".join(reversed(snapshot().splitlines())) + b"\n"
        self.assertEqual(self.parse(reversed_lines), self.parse(snapshot()))
        state = self.parse(snapshot(monotonic_ms=18446744073709551615), 18446744073709551615)
        self.assertTrue(state["valid"])
        self.assertEqual(state["monotonic_ms"], 18446744073709551615)

    def test_age_future_and_unsigned_wrap_fail_closed(self) -> None:
        state = self.parse(snapshot(), 12999)
        self.assertTrue(state["active"])
        self.assertEqual(state["expires_in_ms"], 1)
        for now in (13000, 13001, 18446744073709551615):
            state = self.parse(snapshot(), now)
            self.assertTrue(state["valid"])
            self.assertEqual(state["state"], "stale")
            self.assertFalse(state["active"])
            self.assertFalse(state["gps_fresh"])
            self.assertEqual(state["expires_in_ms"], 0)
            self.assertEqual(state["code"], "none")
        self.assertTrue(self.parse(snapshot(monotonic_ms=10250))["valid"])
        self.assert_invalid(snapshot(monotonic_ms=10251))
        self.assert_invalid(snapshot(monotonic_ms=18446744073709551615))
        self.assert_invalid(snapshot(monotonic_ms=18446744073709551616))
        self.assertTrue(self.parse(snapshot(monotonic_ms=0), 0)["valid"])

    def test_all_states_and_none_are_nonactive_except_ready(self) -> None:
        for value in ("waiting_gps", "warming_up", "stale", "no_database", "disabled", "error"):
            state = self.parse(snapshot(state=value))
            self.assertTrue(state["valid"])
            self.assertEqual(state["state"], value)
            self.assertFalse(state["active"])
            self.assertEqual(state["code"], "none")
        for changes in ({"gps_fresh": 0}, {"active": 0}, {"code": "none"}, {"speed_kmh": 0}):
            state = self.parse(snapshot(**changes))
            self.assertTrue(state["valid"])
            self.assertFalse(state["active"])
            self.assertEqual(state["code"], "none")
            self.assertEqual(state["speed_kmh"], 0)
            self.assertEqual(state["distance_m"], 0)
        for code in ("residential_start", "residential_end"):
            state = self.parse(snapshot(code=code))
            self.assertTrue(state["active"])
            self.assertEqual(state["code"], code)
            self.assertEqual(state["speed_kmh"], 0)

    def test_strict_schema_duplicates_missing_and_unknown_private_fields(self) -> None:
        for key in FIELDS:
            with self.subTest(key=key):
                self.assert_invalid(snapshot() + f"{key}={FIELDS[key]}\n".encode())
                self.assert_invalid(b"".join(line + b"\n" for line in snapshot().splitlines()
                                             if not line.startswith(key.encode() + b"=")))
        for key in ("lat", "lon", "password", "db_path", "sta_ssid"):
            self.assert_invalid(snapshot(**{key: "secret-never-reflect"}))
        for key, bad in (("version", "2"), ("source", "camera"), ("state", "unknown"),
                         ("state", '<script>secret</script>'), ("code", "custom"),
                         ("gps_fresh", "2"), ("active", "true"), ("speed_kmh", "9"),
                         ("speed_kmh", "131"), ("distance_m", "2001"),
                         ("sequence", "4294967296"), ("event_id", "4294967296")):
            with self.subTest(key=key, bad=bad):
                self.assert_invalid(snapshot(**{key: bad}))

    def test_ascii_framing_size_and_numeric_format(self) -> None:
        cases = [b"", snapshot()[:-1], snapshot() + b"\n", b"\n" + snapshot(),
                 snapshot().replace(b"\n", b"\r\n"), snapshot() + b"bad\n",
                 snapshot() + b"=empty\n", snapshot() + b"x=\n", b"x" * 8193,
                 snapshot().replace(b"ready", b"read\x00y"),
                 snapshot().replace(b"ready", b"read\x7fy"),
                 snapshot().replace(b"ready", b"read\xffy"),
                 snapshot().replace(b"ready", b"ready ")]
        for content in cases:
            self.assert_invalid(content)
        for key in ("sequence", "event_id", "monotonic_ms", "speed_kmh", "distance_m"):
            for bad in ("", "-1", "+1", "1.0", "1e2", "0x10", " 1", "01", "9" * 81):
                with self.subTest(key=key, bad=bad):
                    self.assert_invalid(snapshot(**{key: bad}))


class StaticAndBrowserTests(unittest.TestCase):
    def test_offline_resources_csp_and_no_status_interpolation(self) -> None:
        page, script = static_string("page"), static_string("script")
        self.assertIn('src="/signs.js" defer', page)
        self.assertEqual(page.count("<script"), 1)
        self.assertIn("Biển trong dữ liệu gần vị trí GPS — không xác nhận làn/hướng/giới hạn đang hiệu lực", page)
        self.assertIn("KHÔNG qua loa camera", page)
        self.assertIn('aria-pressed="false"', page)
        self.assertIn("Chỉ tham khảo", page)
        self.assertIn("createOscillator()", script)
        self.assertIn("fetch('/api/signs'", script)
        self.assertIn("mode:'same-origin'", script)
        self.assertIn("credentials:'omit'", script)
        self.assertIn("redirect:'error'", script)
        self.assertIn("setInterval(poll, 1000)", script)
        for bad in ("innerHTML", "document.write", "eval(", "new Function", "speechSynthesis",
                    "getCurrentPosition", "watchPosition", "WebSocket", "sendBeacon",
                    "localStorage", "sessionStorage", "https://", "http://", "<iframe"):
            self.assertNotIn(bad, script + page)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("signs_page ? \"; script-src 'self'; connect-src 'self'\" : \"\"", source)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable; mock browser execution skipped")
    def test_browser_expiry_sound_new_event_muted_and_background(self) -> None:
        script = static_string("script")
        with tempfile.TemporaryDirectory(prefix="c2m-d4-js-") as tmp:
            path = Path(tmp) / "browser.cjs"
            # No network, browser device APIs or real audio: VM exercises timers,
            # gestures, rendered text and oscillator calls using deterministic mocks.
            runner = r'''
const vm = require('node:vm'), assert = require('node:assert/strict');
let now = 10000, beeps = 0, pending = [], status, fail = false;
const elements = new Map(), events = {}, windowEvents = {}, timers = [], intervals = [];
function element(id) {
  if (!elements.has(id)) elements.set(id, {textContent:'',hidden:id==='warning',disabled:false,
    setAttribute(k,v){this[k]=v;},addEventListener(k,v){this[k]=v;}});
  return elements.get(id);
}
const document = {hidden:false,getElementById:element,addEventListener(k,v){events[k]=v;}};
class Audio {
  constructor(){this.state='suspended';this.currentTime=0;this.destination={};}
  async resume(){this.state='running';} async suspend(){this.state='suspended';}
  createOscillator(){return {frequency:{},connect(){},disconnect(){},start(){beeps++;},stop(){}};}
  createGain(){return {gain:{setValueAtTime(){},linearRampToValueAtTime(){}},connect(){},disconnect(){}};}
}
const window = {AudioContext:Audio,addEventListener(k,v){windowEvents[k]=v;}};
const context = {window,document,console,AbortController,performance:{now:()=>now},Date:{now:()=>now},
  setTimeout(fn,ms){const t={fn,at:now+ms,live:true};timers.push(t);return t;},
  clearTimeout(t){if(t)t.live=false;},setInterval(fn,ms){intervals.push({fn,ms});},
  async fetch(url,options){assert.equal(url,'/api/signs');assert.equal(options.mode,'same-origin');
    if(fail) throw Error('no update');const value=JSON.parse(JSON.stringify(status));
    return {ok:true,headers:{get:()=> 'application/json; charset=utf-8'},json:async()=>value};}
};
const fresh = (id=1) => ({version:1,source:'gps_offline',status_available:true,state:'ready',gps_fresh:true,
  active:true,sequence:1,event_id:id,code:'speed_limit',speed_kmh:50,distance_m:100,
  monotonic_ms:10000,expires_in_ms:3000});
const tick = async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const advance = ms=>{now+=ms;for(const t of timers){if(t.live&&t.at<=now){t.live=false;t.fn();}}};
status=fresh();vm.runInNewContext(SCRIPT,context);
(async()=>{
 await tick();assert.equal(element('warning').hidden,false);assert.equal(element('speed').textContent,'50 km/h');
 assert.equal(beeps,0,'default muted');await element('sound').click();assert.equal(beeps,0,'no beep on enabling');
 const poll=intervals.find(t=>t.ms===1000).fn;
 await poll();assert.equal(beeps,0,'same event never repeated');
 status=fresh(2);await poll();assert.equal(beeps,1);await poll();assert.equal(beeps,1);
 status.active=false;await poll();assert.equal(element('warning').hidden,true);
 status=fresh(2);await poll();assert.equal(beeps,1,'same event after inactive remains silent');
 advance(3001);assert.equal(element('warning').hidden,true,'browser expires without another poll');
 status=fresh(3);await poll();assert.equal(beeps,2);
 fail=true;await poll();assert.equal(element('warning').hidden,true,'failed polling clears warning');fail=false;
 status=fresh(4);await poll();assert.equal(beeps,3);
 document.hidden=true;events.visibilitychange();assert.equal(element('warning').hidden,true);
 status=fresh(5);await poll();assert.equal(beeps,3,'hidden page never beeps');
 document.hidden=false;events.visibilitychange();await tick();assert.equal(beeps,3,'background mutes until another gesture');
 await element('sound').click();await poll();assert.equal(beeps,3,'enabling never replays current event');
 status=fresh(6);status.state='stale';await poll();assert.equal(element('warning').hidden,true);assert.equal(beeps,3);
 status=fresh(7);status.code='<img src=x onerror=alert(1)>';await poll();assert.equal(element('warning').hidden,true);
 assert.equal(beeps,3);status=fresh(8);status.expires_in_ms=0;await poll();assert.equal(element('warning').hidden,true);
 status=fresh(9);status.gps_fresh=false;await poll();assert.equal(element('warning').hidden,true);
 status=fresh(10);await poll();assert.equal(beeps,4);
 windowEvents.pagehide();assert.equal(element('warning').hidden,true);windowEvents.pageshow();await tick();
 assert.equal(beeps,4,'page cache restore does not replay audio');
 console.log('mock browser: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
            runner = runner.replace("SCRIPT", json.dumps(script, ensure_ascii=True))
            path.write_text(runner, encoding="utf-8")
            result = subprocess.run([shutil.which("node"), str(path)], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("mock browser: OK", result.stdout)


@unittest.skipUnless(d3.LINUX, "Linux-only HTTP/safe-file checks; portable D4 parser and JS tested above")
class LocalhostSignTests(unittest.TestCase):
    # Reuse only fixture helpers, not all D3 test methods (D3 suite runs separately).
    setUpClass = d3.LocalhostTests.__dict__["setUpClass"]
    tearDownClass = d3.LocalhostTests.__dict__["tearDownClass"]
    setUp = d3.LocalhostTests.setUp
    tearDown = d3.LocalhostTests.tearDown
    start = d3.LocalhostTests.start
    stop = d3.LocalhostTests.stop
    raw = d3.LocalhostTests.raw
    request = d3.LocalhostTests.request
    post = d3.LocalhostTests.post
    status_json = d3.LocalhostTests.status_json

    def args(self) -> list[str]:
        self.sign_status = self.base / "sign-status"
        return d3.LocalhostTests.args(self) + ["--sign-status-file", str(self.sign_status)]

    def write_status(self, **changes: object) -> None:
        fields = {"monotonic_ms": int(time.monotonic() * 1000)}
        fields.update(changes)
        self.sign_status.write_bytes(snapshot(**fields))
        self.sign_status.chmod(0o600)

    def signs_json(self) -> dict:
        code, headers, body = self.request("GET", "/api/signs")
        self.assertEqual(code, 200)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        return json.loads(body)

    def assert_unavailable(self) -> None:
        state = self.signs_json()
        self.assertFalse(state["status_available"])
        self.assertFalse(state["active"])
        self.assertEqual(state["code"], "none")
        self.assertEqual(state["state"], "error")

    def test_independent_status_expiry_and_no_private_reflection(self) -> None:
        self.assert_unavailable()
        self.status.write_text("sta_supported=yes\nsta_state=connected\n")
        self.assert_unavailable()
        self.write_status()
        state = self.signs_json()
        self.assertTrue(state["active"])
        self.assertEqual(state["code"], "speed_limit")
        self.assertGreater(state["expires_in_ms"], 2000)
        self.assertEqual(self.status_json()["sta_state"], "connected")
        self.assertEqual(set(state), set(FIELDS) | {"status_available", "expires_in_ms"})
        # Exercise wire-level parsing too; the portable tests cover exact edges.
        self.sign_status.write_bytes(snapshot(monotonic_ms=int(time.monotonic()*1000)+10000))
        self.assert_unavailable()
        self.write_status()
        self.sign_status.write_bytes(self.sign_status.read_bytes() + b"active=1\n")
        self.assert_unavailable()
        self.sign_status.write_bytes(snapshot(monotonic_ms=int(time.monotonic()*1000))[:-1])
        self.assert_unavailable()
        self.sign_status.write_bytes(snapshot(monotonic_ms=int(time.monotonic()*1000)-3001))
        state = self.signs_json()
        self.assertEqual(state["state"], "stale")
        self.assertFalse(state["active"])
        self.sign_status.write_bytes(snapshot(state="secret-private-database-row"))
        state = self.signs_json()
        self.assertFalse(state["status_available"])
        self.assertNotIn("secret", json.dumps(state))
        self.assertNotIn("lat", state)
        self.assertNotIn("lon", state)

    def test_safe_file_checks_symlink_ancestor_nlink_mode_type_size_and_owner(self) -> None:
        self.write_status()
        original = self.sign_status.read_bytes()
        victim = self.base / "victim"
        victim.write_bytes(original)
        self.sign_status.unlink()
        self.sign_status.symlink_to(victim)
        self.assert_unavailable()
        self.assertEqual(victim.read_bytes(), original)
        self.sign_status.unlink()
        os.link(victim, self.sign_status)
        self.assert_unavailable()
        self.sign_status.unlink()
        self.write_status()
        self.sign_status.chmod(0o666)
        self.assert_unavailable()
        self.sign_status.unlink()
        self.sign_status.mkdir()
        self.assert_unavailable()
        self.sign_status.rmdir()
        os.mkfifo(self.sign_status, 0o600)
        self.assert_unavailable()  # non-blocking open must not hang on FIFO
        self.sign_status.unlink()
        self.sign_status.write_bytes(b"x" * 8193)
        self.assert_unavailable()
        self.write_status()
        if os.geteuid() == 0:
            os.chown(self.sign_status, 65534, -1)
            self.assert_unavailable()
            os.chown(self.sign_status, 0, -1)
        self.stop()
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        args = self.args()
        args[-1] = str(alias / "sign-status")
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(100):
            try:
                self.assert_unavailable()
                break
            except OSError:
                time.sleep(0.02)
        else:
            self.fail("server did not start for ancestor-symlink test")

    def test_route_guards_headers_navigation_and_read_only(self) -> None:
        self.write_status()
        before = {str(p): p.read_bytes() for p in (self.sign_status,)}
        _, wifi_headers, wifi_page = self.request("GET", "/")
        self.assertIn(b'href="/signs"', wifi_page)
        self.assertEqual(wifi_headers["content-security-policy"], "default-src 'none'; style-src 'unsafe-inline'; "
                         "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        code, headers, page = self.request("GET", "/signs")
        self.assertEqual(code, 200)
        self.assertIn("script-src 'self'; connect-src 'self'", headers["content-security-policy"])
        self.assertNotIn("script-src 'unsafe-inline'", headers["content-security-policy"])
        self.assertIn(b'src="/signs.js"', page)
        for path in ("/signs", "/api/signs", "/signs.js"):
            self.assertEqual(self.request("GET", path, extra={"Origin": "http://evil.example"})[0], 403)
            self.assertEqual(self.request("GET", path, extra={"Origin": "null"})[0], 403)
            self.assertEqual(self.request("GET", path, extra={"Host": "evil.example"})[0], 403)
            self.assertEqual(self.request("GET", path, extra={"Sec-Fetch-Site": "cross-site"})[0], 403)
            self.assertEqual(self.request("GET", path, extra={"Sec-Fetch-Site": "same-site"})[0], 403)
            self.assertEqual(self.request("GET", path, extra={"Sec-Fetch-Site": "same-origin"})[0], 200)
            self.assertEqual(self.post(path)[0], 404)
        _, script_headers, script = self.request("GET", "/signs.js")
        self.assertEqual(script_headers["content-type"], "application/javascript; charset=utf-8")
        self.assertEqual(script.decode("utf-8"), static_string("script"))
        self.assertEqual(before[str(self.sign_status)], self.sign_status.read_bytes())
        self.assertEqual(list(self.config.iterdir()), [])
        self.assertEqual(list(self.run_dir.iterdir()), [])
        for path in ("/signs?x=secret", "/api/signs/../status", "/signs.js?secret"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.stop()
        args = self.args()
        args[-1] = "relative-status"
        denied = subprocess.run(args, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("absolute", denied.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
