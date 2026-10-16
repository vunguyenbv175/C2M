#!/usr/bin/env python3
"""Host-only guards for tools/gps/c2m_gps_probe.c + build_gps_probe_arm.sh.

Never touches /tmp/car_info, camera, UART, network, or status files.
Compiles --self-test/--help only. Portable: runs on Windows and Linux.
Linux QEMU/ARM gates run in parent CI (manual workflow), not here.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "gps" / "c2m_gps_probe.c"
SNAPSHOT_C = ROOT / "fw" / "d3" / "gps_snapshot.c"
SNAPSHOT_H = ROOT / "fw" / "d3" / "gps_snapshot.h"
ARM_SCRIPT = ROOT / "tools" / "gps" / "build_gps_probe_arm.sh"

# Private struct members must never be touched by the observer TU itself.
# (Header legitimately defines them; observer must not reference them.)
FORBIDDEN_CODE = (
    "latitude_deg",
    "longitude_deg",
    "speed_kmh",
    "course_deg",
    "subsecond_raw",
    "utc_seconds",
    "heading_usable",
    "fopen(",
    "open(",
    "O_WRONLY",
    "O_RDWR",
    "O_CREAT",
    "write(",
    "fwrite(",
    "socket(",
    "ioctl",
    "system(",
    "popen(",
    "execl(",
    "execvp(",
    "getenv(",
    "--gps-file",
    "--db",
    "--status-file",
    "--ifname",
    "--device",
    "/dev/tty",
    "tty",
    "uart",
    "serial",
)

REQUIRED = (
    "C2M_GPS_DEFAULT_PATH",
    '"--observe"',
    '"--self-test"',
    '"--help"',
    "c2m_gps_read",
    "c2m_gps_freshness_update",
    "c2m_gps_decode",
    "C2M_GPS_PROBE_SAMPLES",
    "samples_fixed",
    "interval_ms_fixed",
    "self_test=",
    "fresh_final",
    "c2m-gps-probe-v1",
    "CLOCK_MONOTONIC",
    "nanosleep",
)

REQUIRED_ARM = (
    "--out",
    "--sysroot",
    "armv7-a",
    "vfpv3-d16",
    "mfloat-abi=hard",
    "_TIME_BITS=32",
    "nostartfiles",
    "ld-linux-armhf.so.3",
    "check_elf.py",
    "--allow-dynamic",
    "qemu-arm-static",
    "--self-test",
    "--help",
    "readelf -V",
    "sha256sum",
    "compat.h",
    "c2m_gps_probe.c",
    "gps_snapshot.c",
    "-lm",
    "set -eu",
)


def find_cc():
    if os.environ.get("CC"):
        found = shutil.which(os.environ["CC"])
        if found:
            return found
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Git/mingw64/bin/gcc.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    win_get = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    if win_get.is_dir():
        for gcc in win_get.glob("BrechtSanders.WinLibs*/mingw64/bin/gcc.exe"):
            if gcc.is_file():
                return str(gcc)
    return None


class GpsProbeHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (SOURCE, SNAPSHOT_C, SNAPSHOT_H, ARM_SCRIPT):
            if not path.is_file():
                raise AssertionError(f"Missing file: {path}")
        cls.cc = find_cc()
        if not cls.cc:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="c2m-gps-probe-")
        cls.build = Path(cls.temp.name)
        cls.binary = cls.build / ("c2m-gps-probe.exe" if os.name == "nt" else "c2m-gps-probe")
        cmd = [cls.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
               str(SOURCE), str(SNAPSHOT_C),
               "-I", str(SNAPSHOT_H.parent),
               "-o", str(cls.binary), "-lm"]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(f"Compilation failed:\n{result.stdout}{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_observe(self, *args):
        return subprocess.run([str(self.binary), *args], text=True,
                              capture_output=True, timeout=15)

    def test_source_is_read_only_no_private(self):
        raw = SOURCE.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        code = re.sub(r"//.*", "", code)
        for token in FORBIDDEN_CODE:
            self.assertNotIn(token, code, f"forbidden observer token: {token}")
        for token in REQUIRED:
            self.assertIn(token, raw, f"missing required token: {token}")
        self.assertIn("/tmp/car_info", raw)
        # Fixed CLI: explicit --observe/--help/--self-test, no file overrides.
        self.assertNotIn("--gps-file", raw)
        self.assertNotIn("--status-file", raw)
        # Observer never formats private numerics.
        self.assertNotIn("%f", code)
        self.assertNotIn("%lf", code)

    def test_self_test_passes_and_bounded(self):
        result = self.run_observe("--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        for case in ("bounds_samples_fixed", "bounds_interval_fixed",
                     "decode_valid_ok", "decode_second_ok",
                     "decode_zero_rejected", "decode_short_rejected",
                     "fresh_first_unconfirmed", "fresh_advance_confirmed",
                     "fresh_repeat_holds", "fresh_stale_gate",
                     "fresh_failure_resets"):
            self.assertIn("PASS " + case, result.stdout)
        self.assertIn("samples_fixed=10", result.stdout)
        self.assertIn("interval_ms_fixed=500", result.stdout)
        self.assertIn("path_fixed=/tmp/car_info", result.stdout)
        self.assertIn("self_test=passed", result.stdout)
        self.assertLess(len(result.stdout.encode("utf-8")), 8192)
        # No private payload in self-test output: no decimal coordinates.
        self.assertNotIn("-12.5", result.stdout)
        self.assertNotIn("45.5", result.stdout)
        self.assertNotIn("359.5", result.stdout)

    def test_cli_usage_without_hardware(self):
        result = self.run_observe("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("/tmp/car_info", result.stdout)
        self.assertIn("--observe", result.stdout)
        self.assertIn("--self-test", result.stdout)
        for args in ((), ("--bogus",), ("--observe", "extra"),
                     ("--gps-file", "/tmp/x"), ("--self-test", "extra")):
            result = self.run_observe(*args)
            self.assertEqual(result.returncode, 2, str(args))

    def test_line_endings_and_no_shell(self):
        raw = SOURCE.read_bytes()
        self.assertNotIn(b"\r", raw, "source must be LF-only")
        text = raw.decode("utf-8")
        for token in ("system(", "popen(", "execl(", "`iw ", "$(iw"):
            self.assertNotIn(token, text)

    def test_arm_script_guards(self):
        raw = ARM_SCRIPT.read_bytes().decode("utf-8")
        self.assertNotIn("\r", raw, "script must be LF-only")
        for token in REQUIRED_ARM:
            self.assertIn(token, raw, f"missing ARM script token: {token}")
        # Fail-closed: no pipes hiding exit status.
        for token in ("| tee", "|tee", "| grep", "|grep", "| cat", "|cat", "| sha256sum"):
            self.assertNotIn(token, raw, f"pipe hiding exit: {token}")
        self.assertIn("set -eu", raw)
        self.assertIn("--out DIR --sysroot STOCK_ROOTFS", raw)
        # Wrapper pattern: ALL system headers before compat.h.
        for header in ("<errno.h>", "<fcntl.h>", "<float.h>", "<math.h>",
                       "<stdint.h>", "<stdio.h>", "<string.h>",
                       "<sys/stat.h>", "<sys/types.h>", "<time.h>",
                       "<unistd.h>", '"compat.h"'):
            self.assertIn(header, raw, f"missing wrapper header: {header}")
        # Production files are read, never edited in place.
        self.assertNotIn("sed -i", raw)
        self.assertIn("gps-probe-selftest-arm.txt", raw)
        self.assertIn("gps-probe-help-arm.txt", raw)
        self.assertIn("gps_probe_arm_hashes.txt", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
