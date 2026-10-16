#!/usr/bin/env python3
"""D5 lifetime-boot debug-supervisor tests. Never touch camera/WLAN/flash/SD.

Covers the D5 Vietnamese-firmware variant: first 120-minute SSH cap removed,
D4 default 7200 preserved, explicit build variant C2M_DEBUG_LIFETIME via
build_dropbear.sh --lifetime. D5 --serve production lifetime window 0 keeps
AP gate / key-only / root / owned-PID listener proof / persistent hostkey /
no-password / no-forward unchanged; 600 s idle session timeout (-M600) is a
session bound, not the listener lifetime. No deadline during boot/lifetime,
AP startup 60 s still bounded, AP loss stops the owned listener, no
autorestart loops.

Run: python tests/test_d5_debug_supervisor.py
Builds fw/debug/supervisor.c twice (D4 default + D5 lifetime) with strict C99.
Portable --help/--self-test run everywhere. Mock-exec integration runs only
on Linux with private temp run/config/status paths, mock dropbear fixtures,
--loopback-test and --ap-state-file. No real SSH, radio, firewall, route,
or passwd change. No 7200 s waits: fixtures use window 0 (boot-lifetime)
and short sleeps beyond the former 2 s expiry to prove no deadline.
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
BUILD_SCRIPT = ROOT / "fw" / "debug" / "build_dropbear.sh"
PATCH = ROOT / "tools" / "fw" / "patch_debug_dropbear.py"
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


def build(output: Path, lifetime: bool = False) -> None:
    args = compiler() + ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
    if lifetime:
        args += ["-DC2M_DEBUG_LIFETIME=1"]
    args += [str(SOURCE), "-o", str(output)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise AssertionError("C build failed:\n" + result.stdout + result.stderr)


def make_owner_pub(seed_byte: int = 1) -> tuple[str, str]:
    raw32 = bytes(((seed_byte + i - 1) % 256) + 1 for i in range(32))
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + raw32
    assert len(blob) == 51
    b64 = base64.b64encode(blob).decode("ascii")
    assert len(b64) == 68 and "=" not in b64
    line = f"ssh-ed25519 {b64} test-key_1"
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


class EditionSourceTests(unittest.TestCase):
    def test_header_preserves_d4_default_and_lifetime_variant(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("#ifndef C2M_DEBUG_LIFETIME", header)
        self.assertIn("#define C2M_DEBUG_LIFETIME 0", header)
        self.assertIn("#if C2M_DEBUG_LIFETIME", header)
        self.assertIn("#define C2M_DEBUG_WINDOW_SEC 0", header)
        self.assertIn("#define C2M_DEBUG_WINDOW_SEC 7200", header)
        # D4 default 7200 must remain the else-branch value.
        idx0 = header.index("#define C2M_DEBUG_WINDOW_SEC 0")
        idx7200 = header.index("#define C2M_DEBUG_WINDOW_SEC 7200")
        self.assertLess(idx0, idx7200)
        self.assertIn("lifetime=boot", header)
        self.assertIn("--lifetime", header)
        # VI raw-cpio facts added alongside EN baseline (no revert).
        self.assertIn("1000", header)
        self.assertIn("0755 1000:1000", header)
        self.assertIn("0775 1001:1001", header)
        self.assertIn("/tmp", header)

    def test_build_script_lifetime_flag_and_edition_report(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--lifetime", script)
        self.assertIn("C2M_DEBUG_LIFETIME", script)
        self.assertIn("-DC2M_DEBUG_LIFETIME=1", script)
        self.assertIn("c2m-debug-edition.txt", script)
        self.assertIn("c2m-debug-macros", script)
        self.assertIn("edition=lifetime-boot", script)
        self.assertIn("edition=window-7200", script)
        # Helper keeps the same install name in both editions.
        self.assertIn('"$out/c2m-debug"', script)
        self.assertNotIn("c2m-debug-lifetime", script.split("Host tools allowed")[0]
                         if "Host tools allowed" in script else script)

    def test_cli_valid_source_allows_zero_only_with_macro(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("#if C2M_DEBUG_LIFETIME", source)
        self.assertIn("window_sec < 0 || window_sec > 86400", source)
        self.assertIn("window_sec < 1 || window_sec > 86400", source)
        self.assertIn("cli_lifetime_zero_allowed", source)
        self.assertIn("cli_zero_rejected_d4_default", source)

    def test_status_lifetime_semantics_source(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('lifetime=%s', source)
        self.assertIn('"boot"', source)
        self.assertIn('"window"', source)
        self.assertIn("window_sec=%d", source)

    def test_serve_no_deadline_but_bounded_ap_no_restart_source(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("has_deadline", source)
        self.assertIn("has_deadline && now >= deadline", source)
        self.assertIn("C2M_DEBUG_STARTUP_AP_MS", source)
        self.assertIn("ap_changed_or_unverifiable", source)
        # No autorestart loops: single serve pass, no retry/restart loop.
        self.assertNotIn("restart", source.lower().split("no autorestart")[0][-500:]
                         if "no autorestart" in source.lower() else "restart_loop")
        self.assertIn("No autorestart", source)
        # Idle sessions stay bounded by -M600 (session, not listener).
        self.assertIn('"-M"', source)
        self.assertIn('"600"', source)

    def test_portable_self_test_both_editions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d5-core-") as tmp:
            d4 = Path(tmp) / ("d4.exe" if os.name == "nt" else "d4")
            d5 = Path(tmp) / ("d5.exe" if os.name == "nt" else "d5")
            build(d4, lifetime=False)
            build(d5, lifetime=True)
            r4 = subprocess.run([str(d4), "--self-test"], capture_output=True,
                                text=True, timeout=30)
            self.assertEqual(r4.returncode, 0, r4.stdout + r4.stderr)
            self.assertIn("c2m-debug self-test: OK", r4.stdout)
            self.assertIn("d4_default_window_7200", r4.stdout)
            self.assertIn("cli_zero_rejected_d4_default", r4.stdout)
            r5 = subprocess.run([str(d5), "--self-test"], capture_output=True,
                                text=True, timeout=30)
            self.assertEqual(r5.returncode, 0, r5.stdout + r5.stderr)
            self.assertIn("c2m-debug self-test: OK", r5.stdout)
            self.assertIn("cli_lifetime_zero_allowed", r5.stdout)
            self.assertIn("lifetime_default_window_zero", r5.stdout)
            # VI stock vectors run in both editions (same PASS names, extended).
            for out in (r4.stdout, r5.stdout):
                self.assertIn("PASS stock_tmp_cpio_fact", out)
                self.assertIn("PASS stock_var_cpio_fact", out)
                self.assertIn("PASS stock_root", out)
            # Static: supervisor table carries the exact VI 1000:1000 0755
            # /tmp+/var exception alongside the EN 0775 1001 baseline.
            source = SOURCE.read_text(encoding="utf-8")
            self.assertIn('!strcmp(path, "/tmp")', source)
            self.assertIn("uid == 1000 && gid == 1000", source)
            self.assertIn("uid == 1001 && gid == 1001", source)
            # Static: dropbear patch keeps upstream OLD contexts and adds the
            # exact VI 1000:1000 0755 /tmp owner exception (PERM needs none:
            # 0755 has no group/other-write bit).
            patch = PATCH.read_text(encoding="utf-8")
            self.assertIn("filestat.st_uid == 1001", patch)
            self.assertIn("0775", patch)
            self.assertIn("filestat.st_uid == 1000", patch)
            self.assertIn("0755", patch)
            self.assertIn("C2M_DEBUG_TMP_ANCESTOR", patch)

    def test_d4_default_rejects_zero_cli_no_io(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d5-cli-") as tmp:
            d4 = Path(tmp) / ("d4.exe" if os.name == "nt" else "d4")
            d5 = Path(tmp) / ("d5.exe" if os.name == "nt" else "d5")
            build(d4, lifetime=False)
            build(d5, lifetime=True)
            port = free_port()
            base = Path(tmp)
            status = base / "status-never"
            # D4: window 0 rejected even with loopback, before any I/O.
            # On Linux this is the CLI gate (exit 2, no status file); on
            # Windows --serve is unsupported (also exit 2), so the gate is
            # proven portably by the self-test vectors above.
            r = subprocess.run(
                [str(d4), "--serve", "--loopback-test",
                 "--port", str(port), "--window-sec", "0",
                 "--poll-ms", "100",
                 "--status-file", str(status)],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 2, r.stderr)
            if not LINUX:
                self.skipTest("--serve gate needs Linux; self-test covers it")
            self.assertFalse(status.exists())
            # D4 production default window 7200 is the only valid default;
            # lifetime binary must NOT reject window 0 at the gate. Use a
            # missing-owner fixture so it fails fast with 1 (not 2).
            run_dir = base / "run"
            config = base / "config"
            run_dir.mkdir(mode=0o700)
            config.mkdir(mode=0o700)
            owner = base / "owner.pub"
            line, _ = make_owner_pub()
            owner.write_text(line + "\n", encoding="utf-8")
            owner.chmod(0o600)
            dropbear = base / "mock-dropbear"
            dropbearkey = base / "mock-dropbearkey"
            write_mock_dropbear(dropbear, None, bind_real=False)
            write_mock_dropbearkey(dropbearkey)
            status2 = base / "status2"
            r2 = subprocess.run(
                [str(d5), "--serve", "--loopback-test",
                 "--dropbear", str(dropbear),
                 "--dropbearkey", str(dropbearkey),
                 "--owner-pub", str(owner),
                 "--run-dir", str(run_dir),
                 "--config-dir", str(config),
                 "--status-file", str(status2),
                 "--port", str(port),
                 "--window-sec", "0",
                 "--poll-ms", "100"],
                capture_output=True, text=True, timeout=15)
            # 0 must pass the CLI gate, so exit is NOT 2 (serve runs, then
            # fails listener_unverified=1 because mock holds no socket).
            self.assertNotEqual(r2.returncode, 2,
                                f"lifetime window 0 must pass gate: {r2.stderr}")


@unittest.skipUnless(LINUX, "mock-exec integration is Linux-only")
class LifetimeLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.build_tmp = tempfile.TemporaryDirectory(prefix="c2m-d5-build-")
        supplied = os.environ.get("C2M_DEBUG_TEST_BINARY_LIFETIME")
        if supplied:
            cls.binary = Path(supplied).resolve()
        else:
            cls.binary = Path(cls.build_tmp.name) / "c2m-debug-lifetime"
            build(cls.binary, lifetime=True)
        # Lifetime self-test must pass before fixtures run.
        result = subprocess.run([str(cls.binary), "--self-test"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        # Reference D4 binary for default-unchanged checks.
        cls.d4binary = Path(cls.build_tmp.name) / "c2m-debug-d4"
        build(cls.d4binary, lifetime=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.build_tmp.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="c2m-d5-fixture-")
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

    def args(self, extra: list[str] | None = None,
             binary: Path | None = None) -> list[str]:
        cmd = [str(binary or self.binary), "--serve", "--loopback-test",
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

    def test_lifetime_survives_beyond_former_expiry(self) -> None:
        # Window 0 = boot-lifetime: still active well past the former 2 s cap.
        self.proc = subprocess.Popen(self.args(["--window-sec", "0"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        state = self.wait_status("active", timeout=10.0)
        self.assertEqual(state.get("state"), "active", state)
        self.assertEqual(state.get("window_sec"), "0", state)
        self.assertEqual(state.get("lifetime"), "boot", state)
        self.assertEqual(state.get("key_fp"), self.fp)
        self.assertEqual(state.get("bind"), f"127.0.0.1:{self.port}")
        # Former short timeout was 2 s; sleep 3.5 s and require still active
        # with the supervisor still running (no deadline fired).
        time.sleep(3.5)
        self.assertIsNone(self.proc.poll(),
                          "lifetime supervisor must not expire like D4 window 2")
        mid = read_status(self.status)
        self.assertEqual(mid.get("state"), "active", mid)
        self.assertEqual(mid.get("lifetime"), "boot", mid)
        # SIGTERM stops the owned listener cleanly (no restart).
        self.proc.terminate()
        rc = self.proc.wait(timeout=8)
        self.assertEqual(rc, 0, f"SIGTERM stop should exit 0, got {rc}")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "expired", final)
        self.assertEqual(final.get("reason"), "stopped", final)
        self.assertEqual(final.get("window_sec"), "0", final)
        self.assertEqual(final.get("lifetime"), "boot", final)
        self.assertNotIn(self.line, self.status.read_text())
        self.assertFalse((self.run_dir / "authorized_keys").exists())
        self.assertFalse((self.run_dir / "dropbear.pid").exists())
        self.assertTrue((self.config / "host_ed25519").exists())
        self.assertEqual(stat.S_IMODE(self.status.stat().st_mode), 0o600)
        _, _ = self.proc.communicate()
        self.proc = None
        # Owned listener proof: port is free after stop (foreign would linger).
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", self.port))
            except OSError as exc:
                self.fail(f"owned listener did not stop, port still held: {exc}")

    def test_ap_loss_stops_lifetime_listener_no_restart(self) -> None:
        ap = self.base / "ap.state"
        ap.write_text("up\n", encoding="utf-8")
        self.proc = subprocess.Popen(
            self.args(["--window-sec", "0", "--ap-state-file", str(ap)]),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(self.wait_status("active", timeout=10.0).get("state"),
                         "active")
        ap.write_text("down\n", encoding="utf-8")
        rc = self.proc.wait(timeout=12)
        self.assertNotEqual(rc, 0, "AP loss must fail closed")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "failed", final)
        self.assertEqual(final.get("reason"), "ap_changed_or_unverifiable", final)
        self.assertEqual(final.get("lifetime"), "boot", final)
        # No autorestart: process exited, exactly one failure, no new active.
        self.assertIsNotNone(self.proc.poll())
        _, _ = self.proc.communicate()
        self.proc = None

    def test_foreign_listener_does_not_satisfy_owned_proof(self) -> None:
        # Foreign process holds the same port; sleep-only mock holds no socket.
        # Supervisor must never report active (owned-PID fd check rejects foreign).
        write_mock_dropbear(self.dropbear, self.argv_log, bind_real=False)
        foreign = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        foreign.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        foreign.bind(("127.0.0.1", self.port))
        foreign.listen(5)
        try:
            self.proc = subprocess.Popen(self.args(["--window-sec", "0"]),
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
            starting = self.wait_status("starting", timeout=10.0)
            self.assertEqual(starting.get("state"), "starting", starting)
            rc = self.proc.wait(timeout=20)
            self.assertNotEqual(rc, 0, "foreign listener must not satisfy proof")
            final = read_status(self.status)
            self.assertEqual(final.get("state"), "failed", final)
            self.assertEqual(final.get("reason"), "listener_unverified", final)
            _, _ = self.proc.communicate()
            self.proc = None
        finally:
            foreign.close()

    def test_no_false_active_sleep_only_lifetime(self) -> None:
        # Sleep-only mock holds NO socket: starting is honest, active must
        # never appear. Proof fails after 5 s even with no deadline, so the
        # run fails closed with listener_unverified (same as D4).
        write_mock_dropbear(self.dropbear, self.argv_log, bind_real=False)
        self.proc = subprocess.Popen(self.args(["--window-sec", "0"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        starting = self.wait_status("starting", timeout=10.0)
        self.assertEqual(starting.get("state"), "starting", starting)
        rc = self.proc.wait(timeout=20)
        self.assertNotEqual(rc, 0, "unproven listener must fail closed")
        final = read_status(self.status)
        self.assertEqual(final.get("state"), "failed", final)
        self.assertEqual(final.get("reason"), "listener_unverified", final)
        self.assertEqual(final.get("lifetime"), "boot", final)
        _, _ = self.proc.communicate()
        self.proc = None

    def test_argv_pins_keyonly_noforward_idle600(self) -> None:
        self.proc = subprocess.Popen(self.args(["--window-sec", "0"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        self.assertEqual(self.wait_status("active", timeout=10.0).get("state"),
                         "active")
        self.proc.terminate()
        self.assertEqual(self.proc.wait(timeout=8), 0)
        _, _ = self.proc.communicate()
        self.proc = None
        logged = (self.argv_log.read_text(encoding="utf-8")
                  if self.argv_log.exists() else "")
        for flag in ("-F", "-E", "-s", "-j", "-k", "-D", "-r", "-p",
                     "-P", "-I", "120", "-K", "20", "-T", "3",
                     "-M", "600"):
            self.assertIn(flag, logged, flag)
        self.assertNotIn("-l", logged.split())

    def test_status_lifetime_boot_and_d4_compat(self) -> None:
        # D5 lifetime status carries window_sec=0 + lifetime=boot.
        self.proc = subprocess.Popen(self.args(["--window-sec", "0"]),
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        state = self.wait_status("active", timeout=10.0)
        self.assertEqual(state.get("version"), "1", state)
        self.assertEqual(state.get("window_sec"), "0", state)
        self.assertEqual(state.get("lifetime"), "boot", state)
        self.proc.terminate()
        self.proc.wait(timeout=8)
        _, _ = self.proc.communicate()
        self.proc = None
        # D4 windowed status keeps D4 schema plus the compatible new key
        # lifetime=window (old readers ignore it).
        self.status.unlink(missing_ok=True)
        (self.run_dir / "authorized_keys").unlink(missing_ok=True)
        (self.run_dir / "dropbear.pid").unlink(missing_ok=True)
        port2 = free_port()
        self.port = port2
        write_mock_dropbear(self.dropbear, self.argv_log, bind_real=True)
        proc2 = subprocess.Popen(
            self.args(["--window-sec", "2"], binary=self.d4binary),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10.0
            got: dict[str, str] = {}
            while time.monotonic() < deadline:
                if self.status.exists():
                    try:
                        got = read_status(self.status)
                    except OSError:
                        pass
                    if got.get("state") == "active":
                        break
                time.sleep(0.05)
            self.assertEqual(got.get("state"), "active", got)
            self.assertEqual(got.get("window_sec"), "2", got)
            self.assertEqual(got.get("lifetime"), "window", got)
            self.assertEqual(proc2.wait(timeout=12), 0)
            self.assertEqual(read_status(self.status).get("state"), "expired")
        finally:
            if proc2.poll() is None:
                proc2.terminate()
                try:
                    proc2.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc2.kill()
                    proc2.wait()
            _, _ = proc2.communicate()

    def test_invalid_cli_rejected_lifetime(self) -> None:
        cases = [
            ["--serve", "--loopback-test",
             "--port", "0", "--window-sec", "0", "--poll-ms", "100"],
            ["--serve", "--loopback-test",
             "--port", str(self.port), "--window-sec", "86401",
             "--poll-ms", "100"],
            ["--serve", "--loopback-test",
             "--port", str(self.port), "--window-sec", "0",
             "--poll-ms", "49"],
            ["--serve", "--dropbear", str(self.dropbear)],
            ["--serve", "--window-sec", "0",
             "--run-dir", str(self.run_dir)],
            ["--serve", "--ap-state-file", str(self.base / "ap.state")],
        ]
        (self.base / "ap.state").write_text("up\n", encoding="utf-8")
        for argv in cases:
            with self.subTest(argv=argv):
                before = self.status.exists()
                result = subprocess.run(
                    [str(self.binary)] + argv,
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                if not before:
                    self.assertFalse(self.status.exists(),
                                     "rejected CLI must not touch status")


if __name__ == "__main__":
    unittest.main(verbosity=2)
