#!/usr/bin/env python3
"""Native D3 web tests. Never touch a camera, WLAN, flash, or SD card.

Run: python tests/test_d3_web.py
Builds only in a temporary directory. Crypto/form/header core self-tests run
on Windows with GCC too. Full HTTP/file tests run only on Linux, always with
explicit --bind 127.0.0.1 and temporary config/run/status paths. They exercise
only localhost sockets; no WiFi controller or network-change command runs.
CC may select a native compiler. C2M_WEB_TEST_BINARY may select an already
built Linux host binary; the default is to build fw/d3/web.c with strict C99.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fw" / "d3" / "web.c"
LINUX = sys.platform.startswith("linux")


def compiler() -> list[str]:
    selected = os.environ.get("CC")
    if selected:
        # A quoted path is supported, including a Windows compiler path.
        parts = shlex.split(selected, posix=os.name != "nt")
        return [p.strip('"') for p in parts]
    found = shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
    if not found:
        raise unittest.SkipTest("native C compiler not installed")
    return [found]


def build(output: Path, core: bool = False) -> None:
    args = compiler() + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
    if core:
        args.append("-DC2M_WEB_CORE_ONLY")
    args += [str(SOURCE), "-o", str(output)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise AssertionError("C build failed:\n" + result.stdout + result.stderr)


class CoreTests(unittest.TestCase):
    def test_portable_native_self_test(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-web-core-") as tmp:
            binary = Path(tmp) / ("core.exe" if os.name == "nt" else "core")
            build(binary, core=True)
            result = subprocess.run([str(binary), "--self-test"], capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "c2m-web self-test: OK")
            self.assertEqual(result.stderr, "")
            denied = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertNotEqual(denied.returncode, 0, "core-only must never start a listener")

    def test_service_source_has_no_process_execution(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\b(?:system|popen|execl|execv|execvp|execve|posix_spawn|fork)\s*\(")
        self.assertNotIn('"0.0.0.0"', source)
        self.assertIn('"/dev/urandom"', source)
        self.assertIn("IW_MODE_MASTER", source)
        self.assertNotIn("_TIME_BITS", source)  # compatible with camera's old 32-bit glibc


@unittest.skipUnless(LINUX, "Linux-only HTTP/AP binding code; portable core tested above")
class LocalhostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build_tmp = tempfile.TemporaryDirectory(prefix="c2m-web-build-")
        supplied = os.environ.get("C2M_WEB_TEST_BINARY")
        cls.binary = Path(supplied).resolve() if supplied else Path(cls.build_tmp.name) / "c2m-web"
        if not supplied:
            build(cls.binary)
        result = subprocess.run([str(cls.binary), "--self-test"], capture_output=True,
                                text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.build_tmp.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="c2m-web-http-")
        self.base = Path(self.tmp.name)
        self.config = self.base / "config"
        self.run_dir = self.base / "run"
        self.status = self.base / "status"
        self.config.mkdir(mode=0o700)
        self.run_dir.mkdir(mode=0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.logs = ""
        self.proc = None
        self.start()
        code, headers, page = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertEqual(headers["cache-control"], "no-store")
        tokens = re.findall(rb'name="csrf" value="([0-9a-f]{64})"', page)
        self.assertEqual(len(tokens), 3)
        self.assertEqual(len(set(tokens)), 1)
        self.token = tokens[0].decode("ascii")

    def args(self) -> list[str]:
        return [str(self.binary), "--bind", "127.0.0.1", "--port", str(self.port),
                "--config-dir", str(self.config), "--run-dir", str(self.run_dir),
                "--status-file", str(self.status)]

    def start(self) -> None:
        self.proc = subprocess.Popen(self.args(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
        for _ in range(100):
            if self.proc.poll() is not None:
                out, err = self.proc.communicate()
                self.fail("loopback server failed to start: " + out + err)
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        self.fail("loopback server did not start")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                out, err = self.proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                out, err = self.proc.communicate()
                self.fail("server failed to terminate promptly")
            self.logs += out + err
            self.proc = None

    def tearDown(self) -> None:
        self.stop()
        self.tmp.cleanup()

    def raw(self, data: bytes, chunks: int = 0, half_close: bool = True) -> tuple[int, dict, bytes]:
        received = bytearray()
        with socket.create_connection(("127.0.0.1", self.port), timeout=6) as sock:
            sock.settimeout(6)
            if chunks:
                for start in range(0, len(data), chunks):
                    sock.sendall(data[start:start + chunks])
                    time.sleep(0.002)
            elif data:
                sock.sendall(data)
            if half_close:
                sock.shutdown(socket.SHUT_WR)
            while True:
                try:
                    part = sock.recv(16384)
                except ConnectionResetError:
                    break
                if not part:
                    break
                received.extend(part)
        head, sep, body = bytes(received).partition(b"\r\n\r\n")
        self.assertTrue(sep, "missing HTTP response")
        lines = head.decode("ascii").split("\r\n")
        code = int(lines[0].split(" ")[1])
        headers = dict(line.split(": ", 1) for line in lines[1:])
        headers = {key.lower(): value for key, value in headers.items()}
        self.assertEqual(int(headers["content-length"]), len(body))
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertNotIn("set-cookie", headers)
        return code, headers, body

    def request(self, method: str, path: str, body: bytes = b"", extra: dict | None = None,
                chunks: int = 0) -> tuple[int, dict, bytes]:
        headers = {"Host": self.host, "Content-Length": str(len(body))}
        if method == "POST":
            headers.update({"Content-Type": "application/x-www-form-urlencoded",
                            "Origin": self.origin})
        headers.update(extra or {})
        head = f"{method} {path} HTTP/1.1\r\n" + "".join(
            f"{key}: {value}\r\n" for key, value in headers.items()) + "\r\n"
        return self.raw(head.encode("ascii") + body, chunks=chunks)

    def post(self, path: str, fields: dict | None = None, extra: dict | None = None) -> tuple[int, dict, bytes]:
        data = {"csrf": self.token}
        data.update(fields or {})
        return self.request("POST", path, urlencode(data).encode("ascii"), extra)

    def status_json(self) -> dict:
        code, _, body = self.request("GET", "/api/status")
        self.assertEqual(code, 200)
        return json.loads(body)

    def test_unknown_status_vietnamese_page_and_no_invented_connectivity(self) -> None:
        state = self.status_json()
        self.assertIsNone(state["ap_active"])
        self.assertTrue(state["test_mode"])
        self.assertFalse(state["config_saved"])
        self.assertFalse(state["connect_pending"])
        self.assertFalse(state["controller_status_available"])
        for key in ("sta_supported", "sta_state", "bt_presence"):
            self.assertEqual(state[key], "unknown")
        self.assertNotIn("password", state)
        self.assertNotIn("psk", state)
        _, headers, body = self.request("GET", "/")
        self.assertIn("lang=\"vi\"", body.decode("utf-8"))
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])

    def test_save_pbkdf2_atomic_private_config_and_explicit_connect(self) -> None:
        ssid, password = 'Cà phê "\\ WiFi', 'pass"word\\123'
        marker = self.config / "unrelated"
        marker.write_text("preserve")
        code, headers, body = self.post("/api/wifi", {"ssid": ssid, "password": password})
        self.assertEqual(code, 303, body)
        self.assertEqual(headers["location"], "/?notice=saved")
        conf = self.config / "wifi.conf"
        data = conf.read_text()
        self.assertEqual(stat.S_IMODE(conf.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o700)
        self.assertIn("ssid=" + ssid.encode("utf-8").hex(), data)
        derived = hashlib.pbkdf2_hmac("sha1", password.encode("ascii"), ssid.encode("utf-8"), 4096, 32).hex()
        self.assertIn("psk=" + derived, data)
        self.assertNotIn(password, data)
        self.assertNotIn("update_config", data)
        self.assertFalse((self.run_dir / "connect.request").exists())
        self.assertTrue(self.status_json()["config_saved"])
        for path in ("/", "/api/status"):
            _, _, response = self.request("GET", path)
            self.assertNotIn(password.encode(), response)
            self.assertNotIn(derived.encode(), response)
        code, _, body = self.post("/api/connect")
        self.assertEqual(code, 303, body)
        job = self.run_dir / "connect.request"
        self.assertEqual(job.read_text(), "version=1\naction=connect\n")
        self.assertEqual(stat.S_IMODE(job.stat().st_mode), 0o600)
        self.assertTrue(self.status_json()["connect_pending"])
        self.assertEqual(self.post("/api/connect")[0], 409)
        self.assertEqual(self.post("/api/wifi", {"ssid": "IEEE", "password": "password"})[0], 409)
        self.assertEqual(conf.read_text(), data)
        self.assertEqual(self.post("/api/forget")[0], 303)
        self.assertFalse(conf.exists())
        self.assertTrue(job.exists(), "forget must not delete controller jobs")
        self.assertEqual(marker.read_text(), "preserve")
        self.assertFalse(list(self.config.glob(".c2m-web-*")))
        self.assertFalse(list(self.run_dir.glob(".c2m-web-*")))
        self.stop()
        self.assertNotIn(password, self.logs)
        self.assertNotIn(derived, self.logs)

    def test_raw_hex_psk_and_replacement(self) -> None:
        raw_psk = "AB" * 32
        self.assertEqual(self.post("/api/wifi", {"ssid": "IEEE", "password": raw_psk})[0], 303)
        first = (self.config / "wifi.conf").read_text()
        self.assertIn("psk=" + raw_psk.lower(), first)
        self.assertEqual(self.post("/api/wifi", {"ssid": "Internet", "password": "password"})[0], 303)
        second = (self.config / "wifi.conf").read_text()
        self.assertNotEqual(first, second)
        self.assertIn(hashlib.pbkdf2_hmac("sha1", b"password", b"Internet", 4096, 32).hex(), second)
        maximum = "s" * 32
        self.assertEqual(self.post("/api/wifi", {"ssid": maximum, "password": "p" * 63})[0], 303)
        longest = (self.config / "wifi.conf").read_text()
        self.assertIn("ssid=" + maximum.encode().hex(), longest)
        self.assertTrue(longest.endswith("    proto=RSN\n}\n"), "maximum SSID must not truncate config")

    def test_csrf_origin_host_and_restart_token(self) -> None:
        valid = {"ssid": "IEEE", "password": "password"}
        self.assertEqual(self.post("/api/wifi", dict(valid, csrf="0" * 64))[0], 403)
        self.assertEqual(self.request("POST", "/api/wifi", urlencode(valid).encode())[0], 403)
        self.assertEqual(self.post("/api/wifi", valid, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.post("/api/wifi", valid, {"Origin": "null"})[0], 403)
        self.assertEqual(self.post("/api/wifi", valid, {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.post("/api/wifi", valid, {"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("GET", "/", extra={"Host": "evil.example"})[0], 403)
        self.assertFalse((self.config / "wifi.conf").exists())
        old = self.token
        self.stop()
        self.start()
        _, _, page = self.request("GET", "/")
        new = re.search(rb'name="csrf" value="([0-9a-f]{64})"', page).group(1).decode()
        self.assertNotEqual(old, new)
        self.assertEqual(self.post("/api/wifi", valid)[0], 403)
        self.token = new
        self.assertEqual(self.post("/api/wifi", valid)[0], 303)

    def test_invalid_credentials_do_not_write_anything(self) -> None:
        cases = [("", "password"), ("s" * 33, "password"), ("é" * 17, "password"),
                 ("bad\nssid", "password"), ("bad\x00ssid", "password"),
                 ("IEEE", "short"), ("IEEE", "z" * 64), ("IEEE", "p" * 65),
                 ("IEEE", "pässword"), ("IEEE", "password\r")]
        for ssid, password in cases:
            with self.subTest(ssid=repr(ssid), length=len(password)):
                self.assertEqual(self.post("/api/wifi", {"ssid": ssid, "password": password})[0], 400)
        for suffix in ("&csrf=duplicate", "&unknown=1", "&", "&ssid=%ZZ"):
            body = urlencode({"csrf": self.token, "ssid": "IEEE", "password": "password"}).encode() + suffix.encode()
            self.assertEqual(self.request("POST", "/api/wifi", body)[0], 400)
        body = f"csrf={self.token}&ssid=%C0%AF&password=password".encode()
        self.assertEqual(self.request("POST", "/api/wifi", body)[0], 400)
        self.assertFalse(list(self.config.iterdir()))
        self.assertEqual(self.post("/api/connect")[0], 409)

    def test_partial_reads_and_http_rejections(self) -> None:
        data = urlencode({"csrf": self.token, "ssid": "IEEE", "password": "password"}).encode()
        self.assertEqual(self.request("POST", "/api/wifi", data, chunks=11)[0], 303)
        prefix = f"POST /api/forget HTTP/1.1\r\nHost: {self.host}\r\n".encode()
        cases = [(prefix + b"Content-Length: 0\r\nContent-Length: 0\r\n\r\n", 400),
                 (prefix + b"Content-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n", 400),
                 (prefix + b"Content-Length: 8193\r\n\r\n", 413),
                 (prefix + b"Content-Length: -1\r\n\r\n", 400),
                 (prefix + b"Content-Length: 1\r\n\r\nab", 400),
                 (prefix + b"Content-Length: 5\r\n\r\nab", 400),
                 (prefix + b"\r\n", 411),
                 (prefix + b"Expect: 100-continue\r\nContent-Length: 0\r\n\r\n", 417),
                 (b"GET / HTTP/1.1\r\n\r\n", 400),
                 (f"GET / HTTP/1.1\r\nHost: {self.host}\r\nHost: {self.host}\r\n\r\n".encode(), 400),
                 (b"GET / HTTP/1.1\r\nHost: a\x00b\r\n\r\n", 400),
                 (b"GET / HTTP/1.1\r\nX-Pad: " + b"a" * 8192 + b"\r\n\r\n", 431)]
        for packet, expected in cases:
            with self.subTest(expected=expected, size=len(packet)):
                self.assertEqual(self.raw(packet)[0], expected)
        self.assertEqual(self.request("POST", "/api/forget", b"{}", {"Content-Type": "application/json"})[0], 415)
        for path in ("/../wifi.conf", "/%2e%2e/wifi.conf", "/api/reset", "/api/flash", "/api/wifi/../forget"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertTrue((self.config / "wifi.conf").exists())

    def test_absolute_client_read_timeout(self) -> None:
        started = time.monotonic()
        self.assertEqual(self.raw(b"GET / HTTP/1.1\r\n", half_close=False)[0], 408)
        elapsed = time.monotonic() - started
        self.assertGreater(elapsed, 2.5)
        self.assertLess(elapsed, 4.2)
        self.assertEqual(self.request("GET", "/")[0], 200)

    def test_status_allowlist_escape_and_symlink_rejection(self) -> None:
        secret = "must-not-be-reflected-passphrase"
        self.status.write_text('sta_supported=yes\nsta_state=associated_no_ip\n'
                               'sta_ssid=<script>"&\\\nsta_ipv4=192.168.1.2\n'
                               'last_error=dhcp_helper_missing\nbt_presence=seen\n'
                               f'password={secret}\npsk={secret}\n', encoding="utf-8")
        state = self.status_json()
        self.assertTrue(state["controller_status_available"])
        self.assertEqual(state["sta_state"], "associated_no_ip")
        self.assertEqual(state["last_error"], "dhcp_helper_missing")
        self.assertEqual(state["bt_presence"], "seen")
        _, _, page = self.request("GET", "/")
        self.assertIn(b"&lt;script&gt;", page)
        self.assertNotIn(b"<script>", page)
        self.assertNotIn(secret.encode(), page)
        self.status.write_text(f"last_error={secret}\nsta_ipv4=not.an.address\n")
        state = self.status_json()
        self.assertEqual(state["last_error"], "controller_error")
        self.assertEqual(state["sta_ipv4"], "")
        self.assertNotIn(secret, json.dumps(state))
        self.status.unlink()
        self.status.symlink_to(self.config / "unrelated")
        self.assertFalse(self.status_json()["controller_status_available"])

    def test_unsafe_file_and_directory_rejected_without_modification(self) -> None:
        victim = self.base / "victim"
        victim.write_text("DO NOT CHANGE")
        conf = self.config / "wifi.conf"
        conf.symlink_to(victim)
        self.assertEqual(self.post("/api/wifi", {"ssid": "IEEE", "password": "password"})[0], 500)
        self.assertEqual(self.post("/api/forget")[0], 500)
        self.assertEqual(self.post("/api/connect")[0], 409)
        self.assertTrue(conf.is_symlink())
        self.assertEqual(victim.read_text(), "DO NOT CHANGE")
        conf.unlink()
        os.link(victim, conf)
        conf.chmod(0o600)
        self.assertEqual(self.post("/api/forget")[0], 500)
        conf.unlink()
        self.assertEqual(self.post("/api/wifi", {"ssid": "IEEE", "password": "password"})[0], 303)
        (self.run_dir / "connect.request").symlink_to(victim)
        self.assertEqual(self.post("/api/connect")[0], 500)
        self.assertEqual(victim.read_text(), "DO NOT CHANGE")
        self.stop()
        for mode in (0o755, 0o777):
            self.config.chmod(mode)
            result = subprocess.run(self.args(), capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), mode)
        self.config.chmod(0o700)
        alias = self.base / "alias"
        alias.symlink_to(self.config, target_is_directory=True)
        args = self.args()
        args[args.index("--config-dir") + 1] = str(alias)
        self.assertNotEqual(subprocess.run(args, capture_output=True, timeout=5).returncode, 0)

    def test_unsafe_explicit_bind_is_rejected_before_listener(self) -> None:
        self.stop()
        for bind in ("0.0.0.0", "192.168.1.2", "127.0.0.2", "localhost"):
            args = self.args()
            args[args.index("--bind") + 1] = bind
            result = subprocess.run(args, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Only explicit loopback binding", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
