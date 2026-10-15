#!/usr/bin/env python3
"""Native debug-supervisor tests. Never touch a camera, WLAN, flash, or SD.

Run: python tests/test_debug_supervisor.py
Builds fw/debug/supervisor.c in a temp dir with strict C99. Portable
--help/--self-test run everywhere (incl. Windows GCC). Mock-exec
integration runs only on Linux: private temp run/config/status paths,
mock dropbear/dropbearkey fixtures, --loopback-test and --ap-state-file.
No real SSH, radio, firewall, route, or passwd change.
CC may select a compiler. C2M_DEBUG_TEST_BINARY may reuse a built binary.
"""
from __future__ import annotations

import base64
import os
import shlex
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fw" / "debug" / "supervisor.c"
HEADER = ROOT / "fw" / "debug" / "supervisor.h"
BOOT = ROOT / "fw" / "debug" / "debug_boot.sh"
LINUX = sys.platform.startswith("linux")


def compiler() -> list[str]:
    selected = os.environ.get("CC")
    if selected:
        parts = shlex.split(selected, posix=os.name != "nt")
        return [p.strip('"') for p in parts]
    found = shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
    if not found:
        raise unittest.SkipTest("native C compiler not installed")
    return [found]


def build(output: Path) -> None:
    args = compiler() + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                         str(SOURCE), "-o", str(output)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise AssertionError("C build failed:\n" + result.stdout + result.stderr)


def make_owner_pub(seed_byte: int = 1) -> tuple[str, str]:
    """Deterministic valid ssh-ed25519 line + expected 16-hex FNV-1a fp."""
    raw32 = bytes(((seed_byte + i - 1) % 256) + 1 for i in range(32))
    # Rebuild the exact 51-byte wire blob the C parser expects.
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + raw32
    assert len(blob) == 51
    b64 = base64.b64encode(blob).decode("ascii")
    assert len(b64) == 68 and "=" not in b64
    line = f"ssh-ed25519 {b64} test-key_1"
    # FNV-1a 64 over the 32-byte raw key, matching supervisor.c.
    h = 14695981039346656037
    for byte in raw32:
        h ^= byte
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return line, format(h, "016x")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_status(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def write_mock_dropbearkey(path: Path) -> None:
    path.write_text("#!/bin/sh\n"
                    "f=\"\"\nprev=\"\"\n"
                    "for a in \"$@\"; do\n"
                    "  if [ \"$prev\" = \"-f\" ]; then f=\"$a\"; fi\n"
                    "  prev=\"$a\"\n"
                    "done\n"
                    "[ -n \"$f\" ] || exit 1\n"
                    "printf 'mock-hostkey\\n' > \"$f\"\n"
                    "chmod 600 \"$f\"\n"
                    "exit 0\n", encoding="utf-8")
    path.chmod(0o700)


def write_mock_dropbear(path: Path, log: Path | None = None,
                        bind_real: bool = True) -> None:
    """Mock listener. bind_real=True execs a real TCP listener (same PID,
    so /proc/PID/fd ownership proof succeeds); False only sleeps, so the
    supervisor must NEVER report active (anti-false-active fixture)."""
    py = shutil.which("python3") or "/usr/bin/python3"
    lines = ["#!/bin/sh",
             f'LOG="{log}"' if log is not None else 'LOG=""',
             f'PY="{py}"',
             'prev=""', 'pidf=""', 'bindp=""',
             'for a in "$@"; do',
             '  if [ "$prev" = "-P" ]; then pidf="$a"; fi',
             '  if [ "$prev" = "-p" ]; then bindp="$a"; fi',
             '  prev="$a"',
             "done",
             'if [ -n "$LOG" ]; then printf "%s\\n" "$@" > "$LOG"; fi',
             'if [ -n "$pidf" ]; then echo $$ > "$pidf"; fi']
    if bind_real:
        lines += ['host=${bindp%:*}', 'port=${bindp##*:}',
                  'exec "$PY" -c \'import socket,sys,signal;'
                  "h=sys.argv[1];p=int(sys.argv[2]);"
                  "s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
                  "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
                  "s.bind((h,p));s.listen(5);signal.pause()\'"
                  ' "$host" "$port"']
    else:
        lines += ['trap "exit 0" TERM INT', "sleep 30", "exit 0"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o700)


class CoreTests(unittest.TestCase):
    def test_portable_native_self_test(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-debug-core-") as tmp:
            binary = Path(tmp) / ("core.exe" if os.name == "nt" else "core")
            build(binary)
            result = subprocess.run([str(binary), "--self-test"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip().splitlines()[-1],
                             "c2m-debug self-test: OK")
            self.assertEqual(result.stderr, "")
            denied = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=5)
            self.assertNotEqual(denied.returncode, 0)

    def test_help_lists_serve_and_fixtures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-debug-help-") as tmp:
            binary = Path(tmp) / ("help.exe" if os.name == "nt" else "help")
            build(binary)
            result = subprocess.run([str(binary), "--help"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertIn("--serve", result.stdout)
            self.assertIn("--loopback-test", result.stdout)
            self.assertIn("--ap-state-file", result.stdout)
            self.assertIn("starting", result.stdout)

    def test_source_pins_ap_only_no_killall_or_shell(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        header = HEADER.read_text(encoding="utf-8")
        for token in ("192.168.1.1", "wlan0", '"-l"', '"-D"', '"-s"',
                      '"-j"', '"-k"', '"-M"', '"600"', "geteuid",
                      "IW_MODE_MASTER", "DROPBEAR_SVR_MULTIUSER",
                      "starting", "listener_unverified",
                      "process_running_listener_unverified",
                      "getpgid", "/proc/net/tcp", "any_override",
                      "c2m_debug_cli_valid"):
            self.assertIn(token, source + header, token)
        self.assertIn('#define C2M_DEBUG_BIND_ADDR "192.168.1.1"', header)
        self.assertIn('#define C2M_DEBUG_LOOPBACK_ADDR "127.0.0.1"', header)
        # 0.0.0.0 must only appear as a rejected-bind self-test vector,
        # never as a default bind address.
        self.assertNotRegex(source, r"\bsystem\s*\(")
        self.assertNotRegex(source, r"\bpopen\s*\(")
        # No shell-out to process killers: mentions live only in comments,
        # never as argv strings or calls.
        for token in ('"pkill"', '"killall"', "pkill(", "killall("):
            self.assertNotIn(token, source + header, token)
        self.assertIn('!strcmp(path, "/customer/c2m")', source)
        self.assertIn("window_expired", source)
        self.assertNotIn("_TIME_BITS", source)
        boot = BOOT.read_text(encoding="utf-8")
        self.assertIn("nice -n 10", boot)
        self.assertIn("--serve", boot)
        self.assertIn("supervisor.lock", boot)
        code_only = "\n".join(ln for ln in boot.splitlines()
                              if not ln.lstrip().startswith("#"))
        self.assertNotIn("pkill", code_only)
        self.assertNotIn("killall", code_only)
        # Launcher creates nothing and guards nothing: supervisor owns
        # leaves (safe_dir) and duplicates (run-dir lock).
        self.assertNotIn("mkdir", code_only)
        self.assertNotIn("chmod", code_only)
        self.assertNotIn("once", code_only)
        self.assertIn("debug_owner.pub", boot)


@unittest.skipUnless(LINUX, "mock-exec integration is Linux-only")
class LoopbackFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build_tmp = tempfile.TemporaryDirectory(prefix="c2m-debug-build-")
        supplied = os.environ.get("C2M_DEBUG_TEST_BINARY")
        cls.binary = Path(supplied).resolve() if supplied else \
            Path(cls.build_tmp.name) / "c2m-debug"
        if not supplied:
            build(cls.binary)
        result = subprocess.run([str(cls.binary), "--self-test"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.build_tmp.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="c2m-debug-fixture-")
        self.base = Path(self.tmp.name)
        self.run_dir = self.base / "run"
        self.config = self.base / "config"
        self.status = self.base / "status"
        self.owner = self.base / "owner.pub"
        self.dropbear = self.base / "mock-dropbear"
        self.dropbearkey = self.base / "mock-dropbearkey"
        self.argv_log = self.base / "argv.log"
        self.run_dir.mkdir(mode=0o700)
        self.config.mkdir(mode=0o700)
        write_mock_dropbear(self.dropbear, self.argv_log, bind_real=True)
        write_mock_dropbearkey(self.dropbearkey)
        self.line, self.fp = make_owner_pub()
        self.owner.write_text(self.line + "\n", encoding="utf-8")
        self.owner.chmod(0o600)
        self.port = free_port()
        self.proc = None

    def tearDown(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.tmp.cleanup()

    def args(self, extra: list[str] | None = None) -> list[str]:
        cmd = [str(self.binary), "--serve", "--loopback-test",
               "--dropbear", str(self.dropbear),
               "--dropbearkey", str(self.dropbearkey),
               "--owner-pub", str(self.owner),
               "--run-dir", str(self.run_dir),
               "--config-dir", str(self.config),
               "--status-file", str(self.status),
               "--port", str(self.port),
               "--poll-ms", "100"]
        return cmd + (extra or [])

    def wait_status(self, want: str, timeout: float = 8.0) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        last: dict[str, str] = {}
        while time.monotonic() < deadline:
            if self.status.exists():
                try:
                    last = read_status(self.status)
                except OSError:
                    pass
                if last.get("state") == want:
                    return last
            if self.proc is not None and self.proc.poll() is not None:
                # Process exited; return whatever status exists.
                if self.status.exists():
                    try:
                        last = read_status(self.status)
                    except OSError:
                        pass
                if last.get("state") == want:
                    return last
                break
            time.sleep(0.05)
        if self.status.exists():
            try:
                last = read_status(self.status)
            except OSError:
                pass
        return last

    def test_window_expiry_stops_owned_listener(self) -> None:
        self.proc = subprocess.Popen(self.args(["--window-sec", "2"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        state = self.wait_status("active", timeout=10.0)
        self.assertEqual(state.get("state"), "active", state)
        self.assertEqual(state.get("key_fp"), self.fp)
        self.assertEqual(state.get("bind"), f"127.0.0.1:{self.port}")
        rc = self.proc.wait(timeout=12)
        self.assertEqual(rc, 0, f"expiry should exit 0, got {rc}")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "expired")
        self.assertEqual(final.get("reason"), "window_expired")
        self.assertEqual(final.get("key_fp"), self.fp)
        self.assertNotIn(self.line, self.status.read_text())
        # Transient listener artifacts removed; persistent hostkey kept.
        self.assertFalse((self.run_dir / "authorized_keys").exists())
        self.assertFalse((self.run_dir / "dropbear.pid").exists())
        hostkey = self.config / "host_ed25519"
        self.assertTrue(hostkey.exists())
        self.assertEqual(stat.S_IMODE(hostkey.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.status.stat().st_mode), 0o600)
        # Dropbear argv pins key-only, no-forwarding, bounded session flags.
        logged = (self.argv_log.read_text(encoding="utf-8")
                  if self.argv_log.exists() else "")
        for flag in ("-F", "-E", "-s", "-j", "-k", "-D", "-r", "-p",
                     "-P", "-I", "120", "-K", "20", "-T", "3",
                     "-M", "600"):
            self.assertIn(flag, logged, flag)
        self.assertNotIn("-l", logged.split())
        _, _ = self.proc.communicate()

    def test_no_false_active_without_listener(self) -> None:
        # Sleep-only mock holds NO socket: starting is honest, active must
        # never appear, and the run fails listener_unverified.
        write_mock_dropbear(self.dropbear, self.argv_log, bind_real=False)
        self.proc = subprocess.Popen(self.args(["--window-sec", "30"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        starting = self.wait_status("starting", timeout=10.0)
        self.assertEqual(starting.get("state"), "starting", starting)
        seen: set[str] = set()
        rc = self.proc.wait(timeout=25)
        # Collect every state ever published.
        if self.status.exists():
            try:
                seen.add(read_status(self.status).get("state", "?"))
            except OSError:
                pass
        self.assertNotEqual(rc, 0, "unproven listener must fail closed")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "failed")
        self.assertEqual(final.get("reason"), "listener_unverified")
        self.assertNotIn("active", seen,
                         "active must never be published without proof")
        _, _ = self.proc.communicate()

    def test_overrides_rejected_without_loopback_no_io(self) -> None:
        cases = [
            ["--serve", "--dropbear", str(self.dropbear)],
            ["--serve", "--window-sec", "2",
             "--run-dir", str(self.run_dir)],
            ["--serve", "--ap-state-file", str(self.base / "ap.state")],
            ["--serve", "--port", "2223"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                if (self.base / "ap.state").exists():
                    (self.base / "ap.state").write_text("up\n")
                result = subprocess.run([str(self.binary)] + argv,
                                        capture_output=True, text=True,
                                        timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                # Rejected in main() before any filesystem/network I/O.
                self.assertFalse(self.status.exists(),
                                 "rejected CLI must not touch status")

    def test_loopback_flag_order_independent(self) -> None:
        # Overrides BEFORE --loopback-test are accepted all the same.
        cmd = [str(self.binary), "--serve",
               "--dropbear", str(self.dropbear),
               "--dropbearkey", str(self.dropbearkey),
               "--owner-pub", str(self.owner),
               "--run-dir", str(self.run_dir),
               "--config-dir", str(self.config),
               "--status-file", str(self.status),
               "--port", str(self.port),
               "--poll-ms", "100",
               "--window-sec", "2",
               "--loopback-test"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        self.assertEqual(self.wait_status("active", timeout=10.0).get("state"),
                         "active")
        self.assertEqual(self.proc.wait(timeout=12), 0)
        self.assertEqual(read_status(self.status).get("state"), "expired")
        _, _ = self.proc.communicate()

    def test_ap_change_stops_listener(self) -> None:
        ap = self.base / "ap.state"
        ap.write_text("up\n", encoding="utf-8")
        self.proc = subprocess.Popen(
            self.args(["--window-sec", "30", "--ap-state-file", str(ap)]),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(self.wait_status("active", timeout=10.0).get("state"),
                         "active")
        ap.write_text("down\n", encoding="utf-8")
        rc = self.proc.wait(timeout=12)
        self.assertNotEqual(rc, 0, "AP loss must fail closed")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "failed")
        self.assertEqual(final.get("reason"), "ap_changed_or_unverifiable")
        _, _ = self.proc.communicate()

    def test_ap_state_file_rejected_without_loopback(self) -> None:
        ap = self.base / "ap.state"
        ap.write_text("up\n", encoding="utf-8")
        result = subprocess.run(
            [str(self.binary), "--serve", "--ap-state-file", str(ap)],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.status.exists())

    def test_invalid_owner_key_fails_closed(self) -> None:
        self.owner.write_text("ssh-rsa AAAAB3NzaC1yc2E invalid\n",
                              encoding="utf-8")
        result = subprocess.run(self.args(["--window-sec", "2"]),
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "inactive")
        self.assertEqual(final.get("reason"), "key_missing_or_invalid")
        self.assertNotIn("AAAAB3NzaC1yc2E", self.status.read_text())

    def test_symlink_owner_key_refused(self) -> None:
        victim = self.base / "victim"
        victim.write_text("DO NOT CHANGE", encoding="utf-8")
        self.owner.unlink()
        self.owner.symlink_to(victim)
        result = subprocess.run(self.args(["--window-sec", "2"]),
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "inactive")
        self.assertEqual(victim.read_text(), "DO NOT CHANGE")

    def test_persistent_hostkey_reused_without_overwrite(self) -> None:
        first = subprocess.Popen(self.args(["--window-sec", "2"]),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.assertEqual(first.wait(timeout=15), 0)
        first.communicate()
        hostkey = self.config / "host_ed25519"
        content = hostkey.read_bytes()
        mtime = hostkey.stat().st_mtime_ns
        time.sleep(0.05)
        # Second boot must reuse the same file, not regenerate it.
        port2 = free_port()
        self.port = port2
        second = subprocess.run(self.args(["--window-sec", "2"]),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(hostkey.read_bytes(), content)
        self.assertEqual(hostkey.stat().st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
