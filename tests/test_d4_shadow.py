#!/usr/bin/env python3
"""Host guards for D4 compile-time diagnostic shadow (fw/d4/main.c shadow mode).

Never touches camera, UART, network, vendor IPC, real package paths, or any
status file. Portable --help/--self-test/CLI checks run on Windows and Linux.
Synthetic fixture --observe runtime is Linux-only (descriptor-safe loader).
Target shadow CLI is only --observe/--help/--self-test; no --serve/fixture
path flags. TEST ONLY path overrides are compile-time constants, never CLI.
"""
from __future__ import annotations

import os
import re
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "d4" / "main.c"
ADVISORY_C = ROOT / "fw" / "d4" / "advisory.c"
SNAPSHOT_C = ROOT / "fw" / "d3" / "gps_snapshot.c"
DB_C = ROOT / "fw" / "warner" / "db.c"
WARNER_C = ROOT / "fw" / "warner" / "warner.c"
ARM_SCRIPT = ROOT / "fw" / "d4" / "build_shadow_arm.sh"
SOURCES = [str(ADVISORY_C.relative_to(ROOT)), str(SNAPSHOT_C.relative_to(ROOT)),
           str(DB_C.relative_to(ROOT)), str(WARNER_C.relative_to(ROOT))]
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
         "-Ifw/d4", "-Ifw/d3", "-Ifw/warner"]
LINUX = sys.platform.startswith("linux")

REQUIRED_SOURCE = (
    "C2M_D4_SHADOW_OBSERVE",
    "C2M_D4_SHADOW_SAMPLES",
    "C2M_D4_SHADOW_MAX_MS",
    "C2M_D4_SHADOW_DB_PATH",
    "C2M_D4_SHADOW_GPS_PATH",
    "C2M_D4_SHADOW_TEST_ALLOW",
    "shadow_observe",
    "observer_simulation_not_production_delivery",
    "status_writes=0",
    "samples_fixed",
    "monotonic_bound_ms",
    "completion=",
    "interrupted_signal",
    "error_sleep",
    "error_monotonic_bound",
    "error_monotonic_regression",
    "database_open",
    "database_unchanged",
    "gps_parent_ok",
    "c2m_gps_read",
    "c2m_d4_prepare",
    "c2m_d4_published",
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
    "C2M_D4_SHADOW_OBSERVE",
    "fw/d4/main.c",
    "fw/d4/advisory.c",
    "fw/d3/gps_snapshot.c",
    "fw/warner/db.c",
    "fw/warner/warner.c",
    "-lm",
    "set -eu",
    "c2m-d4-shadow",
    "shadow-selftest-arm.txt",
    "shadow-help-arm.txt",
    "d4_shadow_arm_hashes.txt",
    "--observe",
    "/tmp/car_info",
    "/customer/c2m/signs-d4.bin",
)


def find_cc() -> str:
    cc = shutil.which(os.environ.get("CC", "gcc"))
    if cc:
        return cc
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("host C compiler not available")


def db_bytes(lat: float = 10.0, lon: float = 106.0013, heading: float = 90.0,
             sign_type: bytes = b"R.420\0") -> bytes:
    record = struct.pack("<ddf", lat, lon, heading)
    record += sign_type.ljust(16, b"\0")
    record += b"synthetic".ljust(64, b"\0")
    return b"C2MSDB01" + struct.pack("<I", 1) + record


def gps_bytes(utc: int, *, lat: float = 10.0, lon: float = 106.0,
              speed: float = 36.0, course: float = 90.0,
              subsecond: int = 0) -> bytes:
    if not 0 <= subsecond <= 999:
        raise ValueError("subsecond raw must be 0..999")
    blob = bytearray(0x4F0)
    struct.pack_into("<I", blob, 0, 8)
    struct.pack_into("<I", blob, 4, 124)
    struct.pack_into("<I", blob, 8, 1)
    struct.pack_into("<I", blob, 0x0C, 29)
    hour, rem = divmod(utc, 3600)
    minute, second = divmod(rem, 60)
    struct.pack_into("<I", blob, 0x10, hour % 24)
    struct.pack_into("<I", blob, 0x14, minute)
    struct.pack_into("<I", blob, 0x18, second)
    struct.pack_into("<I", blob, 0x1C, subsecond)
    struct.pack_into("<I", blob, 0x20, 1)
    struct.pack_into("<I", blob, 0x24, 2)

    def ddmm(degrees: float) -> float:
        magnitude = abs(degrees)
        whole = int(magnitude)
        raw = whole * 100.0 + (magnitude - whole) * 60.0
        return -raw if degrees < 0 else raw

    struct.pack_into("<d", blob, 0x40, ddmm(lat))
    struct.pack_into("<d", blob, 0x48, ddmm(lon))
    struct.pack_into("<d", blob, 0x58, speed)
    struct.pack_into("<d", blob, 0x60, course)
    return bytes(0x330) + bytes(blob[:0x1C0])


def compile_binary(cc: str, output: Path, extra_flags: list[str]) -> None:
    cmd = [cc] + FLAGS + extra_flags + [str(MAIN_C.relative_to(ROOT))] + SOURCES + ["-lm", "-o", str(output)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(f"compile failed {extra_flags}:\n{result.stdout}{result.stderr}")


class D4ShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (MAIN_C, ADVISORY_C, SNAPSHOT_C, DB_C, WARNER_C, ARM_SCRIPT):
            if not path.is_file():
                raise AssertionError(f"Missing file: {path}")
        cls.cc = find_cc()
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        suffix = ".exe" if os.name == "nt" else ""
        cls.prod = base / ("c2m-d4-prod" + suffix)
        cls.shadow = base / ("c2m-d4-shadow" + suffix)
        compile_binary(cls.cc, cls.prod, [])
        compile_binary(cls.cc, cls.shadow, ["-DC2M_D4_SHADOW_OBSERVE"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_bin(self, binary: Path, *args: str, timeout: float = 10.0):
        return subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=timeout)

    def test_production_cli_unchanged(self) -> None:
        result = self.run_bin(self.prod, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--serve", result.stdout)
        self.assertIn("--db", result.stdout)
        result = self.run_bin(self.prod, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D4 synthetic advisory self-test: OK", result.stdout)
        for args in ((), ("--unknown",), ("--observe",), ("--observe", "extra"),
                     ("--serve", "--db", "/fixture/db"),
                     ("--serve", "--db", "relative"),
                     ("--serve", "--network", "/fixture/no")):
            with self.subTest(args=args):
                result = self.run_bin(self.prod, *args)
                self.assertEqual(result.returncode, 2, str(args))

    def test_shadow_cli_only_observe_help_selftest(self) -> None:
        result = self.run_bin(self.shadow, "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--observe", result.stdout)
        self.assertIn("--self-test", result.stdout)
        self.assertIn("--help", result.stdout)
        self.assertIn("/tmp/car_info", result.stdout)
        self.assertIn("/customer/c2m/signs-d4.bin", result.stdout)
        self.assertIn("observer simulation", result.stdout)
        self.assertIn("Never writes", result.stdout)
        self.assertIn("10 samples", result.stdout)
        self.assertNotIn("--serve", result.stdout)
        self.assertNotIn("--db", result.stdout)
        self.assertNotIn("--gps-file", result.stdout)
        self.assertNotIn("--status-file", result.stdout)
        result = self.run_bin(self.shadow, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D4 synthetic advisory self-test: OK", result.stdout)
        for args in ((), ("--unknown",), ("--serve",),
                     ("--serve", "--db", "/x", "--gps-file", "/y", "--status-file", "/z"),
                     ("--db", "/x"), ("--gps-file", "/x"), ("--status-file", "/x"),
                     ("--observe", "extra"), ("--self-test", "extra")):
            with self.subTest(args=args):
                result = self.run_bin(self.shadow, *args)
                self.assertEqual(result.returncode, 2, str(args))
        # Shadow binary must not embed production serve/fixture flags.
        raw = self.shadow.read_bytes()
        self.assertIn(b"--observe", raw)
        self.assertNotIn(b"--serve", raw)
        self.assertNotIn(b"--db", raw)
        self.assertNotIn(b"--gps-file", raw)
        self.assertNotIn(b"--status-file", raw)
        self.assertNotIn(b"c2m_d4_status", raw)

    def test_shadow_source_shares_loader_no_status_writer(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        for token in REQUIRED_SOURCE:
            self.assertIn(token, text, f"missing shadow token: {token}")
        # Production loader/core/GPS stay shared, never copied loosely.
        for token in ("checked_parent", "database_open", "database_unchanged",
                      "c2m_gps_read", "c2m_d4_prepare", "c2m_d4_published",
                      "c2m_d4_init", "directory_ok", "db_stat_ok", "same_file"):
            self.assertIn(token, text)
        # Shadow mode is ifdef-guarded; production path keeps its writer/serve.
        self.assertIn("#ifndef C2M_D4_SHADOW_OBSERVE", text)
        self.assertIn("#ifdef C2M_D4_SHADOW_OBSERVE", text)
        self.assertIn("C2M_D4_SHADOW_TEST_ALLOW", text)
        self.assertIn("write_status", text)
        self.assertIn("static int serve(", text)
        self.assertIn("static int shadow_observe(", text)
        # Extract shadow observer body: it must never touch status files,
        # private GPS numerics, or server/shell/IPC primitives.
        start = text.find("static int shadow_observe(")
        self.assertGreaterEqual(start, 0)
        end = text.find("#endif /* C2M_D4_SHADOW_OBSERVE */", start)
        self.assertGreater(end, start)
        body = text[start:end]
        for token in ("write_status", "target_ok", "renameat", "O_CREAT",
                      "O_WRONLY", "O_RDWR", "--serve", "--db", "--gps-file",
                      "--status-file", "C2M_D4_DEFAULT_STATUS",
                      "/tmp/c2m_d4_status", "latitude_deg",
                      "longitude_deg", "speed_kmh", "course_deg",
                      "subsecond_raw", "utc_seconds", "heading_usable",
                      "fopen(", "socket(", "ioctl", "system(", "popen(",
                      "getenv(", "/dev/", "uart", "%f", "%lf"):
            self.assertNotIn(token, body, f"forbidden shadow observer token: {token}")
        # Shadow observer reports simulation explicitly and bounds the run.
        for token in ("observer_simulation_not_production_delivery",
                      "C2M_D4_SHADOW_SAMPLES", "C2M_D4_SHADOW_MAX_MS",
                      "monotonic regression", "monotonic bound exceeded",
                      "completion=", "interrupted_signal", "error_sleep"):
            self.assertIn(token, body)
        # No CR line endings.
        self.assertNotIn("\r", text)

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_invalid_gps_reports_same_poll_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-invalid-") as name:
            root = Path(name)
            db_path, gps_path = root / "db.bin", root / "car_info"
            db_path.write_bytes(db_bytes())
            bad = bytearray(gps_bytes(7))
            struct.pack_into("<I", bad, 0x330 + 0x1C, 1000)
            gps_path.write_bytes(bad)
            db_path.chmod(0o600)
            gps_path.chmod(0o600)
            fixture_bin = root / "shadow-invalid"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE", "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{db_path}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            result = self.run_bin(fixture_bin, "--observe", timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self._assert_safe_output(result.stdout)
            rows = self._sample_rows(result.stdout)
            self.assertEqual(len(rows), 10)
            self.assertTrue(all("gps_result=invalid" in row and
                                "freshness_reason=no_sample" in row and
                                "utc_step=unavailable" in row and "gps_fresh=0" in row
                                for row in rows), result.stdout)

    def test_arm_script_guards(self) -> None:
        raw = ARM_SCRIPT.read_bytes().decode("utf-8")
        self.assertNotIn("\r", raw, "script must be LF-only")
        for token in REQUIRED_ARM:
            self.assertIn(token, raw, f"missing ARM script token: {token}")
        for token in ("| tee", "|tee", "| grep", "|grep", "| cat", "|cat", "| sha256sum"):
            self.assertNotIn(token, raw, f"pipe hiding exit: {token}")
        self.assertIn("set -eu", raw)
        self.assertIn("--out DIR --sysroot STOCK_ROOTFS", raw)
        for header in ("<errno.h>", "<fcntl.h>", "<inttypes.h>", "<math.h>",
                       "<stdint.h>", "<stdio.h>", "<string.h>",
                       "<sys/stat.h>", "<sys/types.h>", "<time.h>",
                       "<unistd.h>", '"compat.h"'):
            self.assertIn(header, raw, f"missing wrapper header: {header}")
        self.assertNotIn("sed -i", raw)
        # Target build is pure shadow; TEST ONLY macros must never appear.
        self.assertNotIn("C2M_D4_SHADOW_TEST_ALLOW", raw)
        self.assertNotIn("C2M_D4_SHADOW_TEST_DB", raw)
        self.assertNotIn("C2M_D4_SHADOW_TEST_GPS", raw)
        # Target binary is guarded to contain no status path or serve flag.
        self.assertIn("c2m_d4_status", raw)
        self.assertIn("--serve", raw)

    @staticmethod
    def _parse_summary(stdout: str) -> dict[str, str]:
        for line in stdout.splitlines():
            if line.startswith("summary "):
                fields: dict[str, str] = {}
                for part in line.split():
                    if "=" in part:
                        key, _, value = part.partition("=")
                        fields[key] = value
                return fields
        raise AssertionError(f"missing summary line:\n{stdout[-2000:]}")

    @staticmethod
    def _sample_rows(stdout: str) -> list[str]:
        return [line for line in stdout.splitlines() if line.startswith("sample=")]

    def _assert_safe_output(self, stdout: str) -> None:
        for forbidden in ("latitude", "longitude", "speed_kmh", "course=", "heading=",
                          "synthetic", "utc=", "subsecond=", "106.0013",
                          "R.420", "R.421", "c2m_d4_status", "--serve",
                          "record_id", "latitude=", "longitude=",
                          "course_deg=", "UTC="):
            self.assertNotIn(forbidden, stdout, f"private/unsafe token leaked: {forbidden}")
        self.assertLess(len(stdout.encode("utf-8")), 8192)
        self.assertIn("d4_shadow=observer_v2", stdout)
        rows = self._sample_rows(stdout)
        reasons = {"no_state", "no_sample", "invalid_sample", "first_anchor",
                   "monotonic_regression", "timeout", "utc_regression",
                   "repeat_unconfirmed", "repeat_confirmed", "zero_elapsed",
                   "step_tolerance", "reference_tolerance", "advancing"}
        for idx, row in enumerate(rows):
            fields = dict(part.split("=", 1) for part in row.split())
            self.assertEqual(set(fields), {
                "sample", "state", "gps_fresh", "active", "code", "distance_m",
                "event_id", "sequence", "delivery_sim", "gps_result", "poll_dt_ms",
                "utc_step", "freshness_reason"})
            self.assertIn(fields["gps_result"], {"ok", "invalid", "io_error",
                                                "unstable", "unsupported"})
            self.assertIn(fields["freshness_reason"], reasons)
            self.assertIn(fields["utc_step"], {"unavailable", "first", "repeat",
                                              "one_step", "jump", "regress"})
            self.assertRegex(fields["poll_dt_ms"], r"^\d+$")
            self.assertLessEqual(int(fields["poll_dt_ms"]), 30000)
            if idx == 0:
                self.assertEqual(fields["poll_dt_ms"], "0")
            if fields["gps_result"] != "ok":
                self.assertEqual(fields["freshness_reason"], "no_sample")
                self.assertEqual(fields["utc_step"], "unavailable")
                self.assertEqual(fields["gps_fresh"], "0")

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_advancing_gps_finite_no_status_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-fix-") as name:
            root = Path(name)
            db_path = root / "db.bin"
            gps_path = root / "car_info"
            status_probe = root / "status-should-never-exist"
            system_status = Path("/tmp/c2m_d4_status")
            before = system_status.read_bytes() if system_status.is_file() else None
            db_path.write_bytes(db_bytes())
            # Old bug shape: unscaled 1-3 digit fraction 100 then 200 must
            # decode yet never refresh a UTC second by itself.
            gps_path.write_bytes(gps_bytes(0, subsecond=100))
            db_path.chmod(0o600)
            gps_path.chmod(0o600)
            fixture_bin = root / "c2m-d4-shadow-fixture"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE",
                "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{db_path}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            bin_digest_before = hashlib.sha256(fixture_bin.read_bytes()).hexdigest()
            # Advancing GPS in the background: one UTC second per poll,
            # second sample carries raw 200 (old fraction shape).
            proc = subprocess.Popen([str(fixture_bin), "--observe"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                subs = [200, 0, 0, 0, 0, 0, 0, 0, 0]
                for idx, utc in enumerate(range(1, 10)):
                    time.sleep(1.0)
                    if proc.poll() is not None:
                        break
                    # Mid-run DB replacement poisons the loaded DB: later
                    # rows must report no_database without any file writes.
                    if utc == 5:
                        replacement = root / "db.next"
                        replacement.write_bytes(db_bytes(lat=10.0005))
                        replacement.chmod(0o600)
                        os.replace(replacement, db_path)
                    tmp_next = root / f"gps.next.{utc}"
                    tmp_next.write_bytes(gps_bytes(utc, subsecond=subs[idx]))
                    tmp_next.chmod(0o600)
                    os.replace(tmp_next, gps_path)
                try:
                    stdout, stderr = proc.communicate(timeout=25)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    self.fail(f"shadow --observe did not finish finite: {stdout[-2000:]} {stderr[-2000:]}")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
            self.assertEqual(proc.returncode, 0, f"{stdout[-3000:]} {stderr[-2000:]}")
            self.assertEqual(stderr, "", stderr)
            self.assertIn("d4_shadow=observer_v2", stdout)
            self.assertIn("samples_fixed=10", stdout)
            self.assertIn("interval_s_fixed=1", stdout)
            self.assertIn("monotonic_bound_ms=30000", stdout)
            self.assertIn("delivery_sim=observer_simulation_not_production_delivery", stdout)
            self.assertIn("status_writes=0", stdout)
            samples = self._sample_rows(stdout)
            summary = self._parse_summary(stdout)
            # Summary reports ACTUAL completed rows, not a fixed constant.
            self.assertEqual(int(summary["samples"]), len(samples))
            self.assertEqual(summary["completion"], "complete")
            self.assertEqual(len(samples), 10, stdout)
            self._assert_safe_output(stdout)
            for line in samples:
                self.assertIn("delivery_sim=observer_simulation_not_production_delivery", line)
                self.assertRegex(line, r"state=(waiting_gps|warming_up|ready|stale|no_database|disabled|error)")
                self.assertRegex(line, r"code=(none|residential_start|residential_end)")
            # Advancing GPS must confirm freshness at least once before the
            # mid-run DB replacement poisons later rows.
            self.assertTrue(any("gps_fresh=1" in row and "gps_result=ok" in row and
                                "freshness_reason=advancing" in row for row in samples), stdout)
            self.assertTrue(any("state=no_database" in line for line in samples),
                            f"DB replacement must poison later rows:\n{stdout}")
            self.assertFalse(status_probe.exists())
            self.assertFalse(list(root.glob(".c2m-d4-*.tmp")))
            self.assertEqual(bin_digest_before,
                             hashlib.sha256(fixture_bin.read_bytes()).hexdigest())
            after = system_status.read_bytes() if system_status.is_file() else None
            self.assertEqual(before, after, "shadow mutated /tmp/c2m_d4_status")

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_frozen_gps_goes_stale_finite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-frozen-") as name:
            root = Path(name)
            db_path = root / "db.bin"
            gps_path = root / "car_info"
            db_path.write_bytes(db_bytes())
            gps_path.write_bytes(gps_bytes(7, subsecond=100))
            db_path.chmod(0o600)
            gps_path.chmod(0o600)
            fixture_bin = root / "c2m-d4-shadow-frozen"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE",
                "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{db_path}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            result = subprocess.run([str(fixture_bin), "--observe"],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            samples = self._sample_rows(result.stdout)
            summary = self._parse_summary(result.stdout)
            self.assertEqual(len(samples), 10)
            self.assertEqual(int(summary["samples"]), 10)
            self.assertEqual(summary["completion"], "complete")
            self.assertIn("db_valid=1", result.stdout)
            # Frozen UTC never becomes fresh again; subseconds cannot refresh.
            self.assertNotRegex(result.stdout, r"gps_fresh=1")
            self.assertTrue(all("gps_fresh=0" in line and "active=0" in line for line in samples))
            states = [re.search(r"state=(\w+)", line).group(1) for line in samples]  # type: ignore[union-attr]
            self.assertIn("warming_up", states)
            self.assertIn("stale", states)
            self.assertIn("freshness_reason=first_anchor", samples[0])
            self.assertIn("utc_step=first", samples[0])
            self.assertTrue(all("gps_result=ok" in row for row in samples))
            self.assertTrue(any("freshness_reason=timeout" in row for row in samples))
            self.assertTrue(any("freshness_reason=repeat_unconfirmed" in row for row in samples))
            self._assert_safe_output(result.stdout)

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_db_symlink_rejected_finite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-link-") as name:
            root = Path(name)
            real_db = root / "real-db.bin"
            link_db = root / "link-db.bin"
            gps_path = root / "car_info"
            real_db.write_bytes(db_bytes())
            real_db.chmod(0o600)
            gps_path.write_bytes(gps_bytes(0))
            gps_path.chmod(0o600)
            if link_db.exists() or link_db.is_symlink():
                link_db.unlink()
            os.symlink(real_db, link_db)
            fixture_bin = root / "c2m-d4-shadow-link"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE",
                "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{link_db}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            result = subprocess.run([str(fixture_bin), "--observe"],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            samples = self._sample_rows(result.stdout)
            summary = self._parse_summary(result.stdout)
            self.assertEqual(len(samples), 10)
            self.assertEqual(int(summary["samples"]), 10)
            self.assertEqual(summary["completion"], "complete")
            self.assertIn("db_valid=0", result.stdout)
            self.assertIn("db_count=0", result.stdout)
            self.assertTrue(all("state=no_database" in line for line in samples))
            self._assert_safe_output(result.stdout)
            self.assertFalse(list(root.glob(".c2m-d4-*.tmp")))

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_sigterm_reports_actual_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-term-") as name:
            root = Path(name)
            db_path = root / "db.bin"
            gps_path = root / "car_info"
            db_path.write_bytes(db_bytes())
            gps_path.write_bytes(gps_bytes(0))
            db_path.chmod(0o600)
            gps_path.chmod(0o600)
            fixture_bin = root / "c2m-d4-shadow-term"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE",
                "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{db_path}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            proc = subprocess.Popen([str(fixture_bin), "--observe"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(2.5)
                proc.terminate()
                try:
                    stdout, stderr = proc.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    self.fail("shadow did not stop after SIGTERM")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
                    self.fail("shadow ignored SIGTERM")
            # Interrupted observer must NOT report full success.
            self.assertNotEqual(proc.returncode, 0, f"rc=0 after SIGTERM:\n{stdout}")
            samples = self._sample_rows(stdout)
            summary = self._parse_summary(stdout)
            self.assertEqual(int(summary["samples"]), len(samples),
                             f"summary must report actual completed rows:\n{stdout}")
            self.assertLess(len(samples), 10, f"expected early stop:\n{stdout}")
            self.assertEqual(summary["completion"], "interrupted_signal")
            self.assertIn("delivery_sim=observer_simulation_not_production_delivery", stdout)
            self._assert_safe_output(stdout)
            self.assertFalse(list(root.glob(".c2m-d4-*.tmp")))

    @unittest.skipUnless(LINUX, "descriptor/fixture --observe runtime is Linux-only")
    def test_shadow_fixture_missing_db_finite_no_status_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-shadow-miss-") as name:
            root = Path(name)
            db_path = root / "missing-db.bin"
            gps_path = root / "missing-gps"
            fixture_bin = root / "c2m-d4-shadow-missing"
            compile_binary(self.cc, fixture_bin, [
                "-DC2M_D4_SHADOW_OBSERVE",
                "-DC2M_D4_SHADOW_TEST_ALLOW",
                f'-DC2M_D4_SHADOW_TEST_DB="{db_path}"',
                f'-DC2M_D4_SHADOW_TEST_GPS="{gps_path}"',
            ])
            result = subprocess.run([str(fixture_bin), "--observe"],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertIn("db_valid=0", result.stdout)
            self.assertIn("db_count=0", result.stdout)
            self.assertIn("delivery_sim=observer_simulation_not_production_delivery", result.stdout)
            self.assertIn("status_writes=0", result.stdout)
            samples = self._sample_rows(result.stdout)
            summary = self._parse_summary(result.stdout)
            self.assertEqual(len(samples), 10)
            self.assertEqual(int(summary["samples"]), 10)
            self.assertEqual(summary["completion"], "complete")
            # Exact shipping-binary missing-DB contract (parent QEMU gate).
            self.assertTrue(all("state=no_database" in line and "gps_fresh=0" in line
                                and "active=0" in line for line in samples),
                            result.stdout)
            self._assert_safe_output(result.stdout)
            self.assertTrue(all("gps_result=io_error" in row and
                                "freshness_reason=no_sample" in row and
                                "utc_step=unavailable" in row for row in samples))


if __name__ == "__main__":
    unittest.main(verbosity=2)
