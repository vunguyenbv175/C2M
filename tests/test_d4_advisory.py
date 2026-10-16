#!/usr/bin/env python3
"""Synthetic D4 offline GPS advisory tests.

No camera, UART, network, vendor IPC, or real package paths are used. The
portable test builds the native core and runs its no-I/O self-test. Linux-only
checks exercise descriptor-safe DB/GPS loading and the atomic private status
heartbeat using a private temporary tree.
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
LINUX = sys.platform.startswith("linux")
SOURCES = ["fw/d4/advisory.c", "fw/d3/gps_snapshot.c",
           "fw/warner/warner.c", "fw/warner/db.c"]
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
         "-Ifw/d4", "-Ifw/d3", "-Ifw/warner"]
# Independent regression driver: an unchanged file/UTC second must never become
# fresh again just because the gate reanchors it after a stale interval.
FROZEN_GPS_DRIVER = r'''
#include "advisory.h"
#include <string.h>
#define REQUIRE(x) do { if (!(x)) return __LINE__; } while (0)
int main(void)
{
    struct c2m_d4_advisory core;
    struct c2m_d4_cooldown cooldown;
    struct c2m_d4_status status;
    struct c2m_gps_snapshot gps;
    warner_sign_t sign;
    uint64_t now;
    uint32_t max_seen = 0;
    memset(&gps, 0, sizeof(gps));
    memset(&sign, 0, sizeof(sign));
    sign.lat = 0.0005;
    memcpy(sign.type, "R.420", 6);
    gps.mask = C2M_GPS_RMC_MASK;
    gps.utc_seconds = INT64_C(1709164800);
    gps.speed_kmh = 36;
    gps.heading_usable = 1;
    c2m_d4_init(&core, &sign, 1, &cooldown);
    c2m_d4_prepare(&core, &gps, 0, 1, 0, &status);
    REQUIRE(status.state == C2M_D4_WARMING_UP && !status.active);
    c2m_d4_published(&core, 1);
    /* A lone never-advancing sample eventually reports stale, not perpetual
     * warming_up; new positions and subseconds cannot refresh GPS time.
     * (now/5)%1000 steps 100 per 500ms poll, covering live-shape 100..900;
     * 999 is covered explicitly below. */
    for (now = 500; now < 10000; now += 500) {
        gps.subsecond_raw = (uint32_t)((now / 5) % 1000);
        if (gps.subsecond_raw > max_seen) max_seen = gps.subsecond_raw;
        REQUIRE(gps.subsecond_raw <= 999u);
        c2m_d4_prepare(&core, &gps, now, 1, 0, &status);
        REQUIRE(!status.gps_fresh && !status.active);
        REQUIRE(status.state == (now < 2500 ? C2M_D4_WARMING_UP : C2M_D4_STALE));
        c2m_d4_published(&core, 1);
    }
    REQUIRE(max_seen >= 900);
    gps.subsecond_raw = 999;
    c2m_d4_prepare(&core, &gps, 9500, 1, 0, &status);
    REQUIRE(!status.gps_fresh && !status.active);
    REQUIRE(status.state == C2M_D4_STALE);
    c2m_d4_published(&core, 1);
    ++gps.utc_seconds;
    c2m_d4_prepare(&core, &gps, 10000, 1, 0, &status);
    REQUIRE(status.state == C2M_D4_STALE && !status.active);
    c2m_d4_published(&core, 1);
    ++gps.utc_seconds;
    c2m_d4_prepare(&core, &gps, 11000, 1, 0, &status);
    REQUIRE(status.state == C2M_D4_READY && status.active);
    REQUIRE(status.event_id == 1);
    c2m_d4_published(&core, 1);
    c2m_d4_prepare(&core, &gps, 13499, 1, 0, &status);
    REQUIRE(status.gps_fresh && status.active && status.event_id == 1);
    c2m_d4_published(&core, 1);
    c2m_d4_prepare(&core, &gps, 13500, 1, 0, &status);
    REQUIRE(status.state == C2M_D4_STALE && !status.gps_fresh && !status.active);
    c2m_d4_published(&core, 1);
    max_seen = 0;
    for (now = 14000; now <= 30000; now += 500) {
        gps.latitude_deg = (now % 1000) ? 0.00001 : 0;
        gps.subsecond_raw = (uint32_t)((now / 5) % 1000);
        REQUIRE(gps.subsecond_raw <= 999u);
        if (gps.subsecond_raw > max_seen) max_seen = gps.subsecond_raw;
        c2m_d4_prepare(&core, &gps, now, 1, 0, &status);
        REQUIRE(status.state == C2M_D4_STALE && !status.gps_fresh && !status.active);
        REQUIRE(status.code == C2M_D4_NONE && status.distance_m == 0 && status.event_id == 0);
        c2m_d4_published(&core, 1);
    }
    REQUIRE(max_seen >= 900);
    /* Failed polls force two-sample reacquisition, and successful delivery's
     * sign cooldown still suppresses the same sign once GPS is fresh again. */
    c2m_d4_prepare(&core, NULL, 31000, 1, 0, &status);
    REQUIRE(status.state == C2M_D4_STALE && !status.active);
    c2m_d4_published(&core, 1);
    ++gps.utc_seconds;
    c2m_d4_prepare(&core, &gps, 32000, 1, 0, &status);
    REQUIRE(!status.gps_fresh && !status.active);
    c2m_d4_published(&core, 1);
    ++gps.utc_seconds;
    c2m_d4_prepare(&core, &gps, 33000, 1, 0, &status);
    REQUIRE(status.gps_fresh && status.state == C2M_D4_READY && !status.active);
    c2m_d4_published(&core, 1);
    return 0;
}
'''


def compiler() -> list[str]:
    cc = shlex.split(os.environ.get("CC", "gcc"), posix=os.name != "nt")
    if not cc or not shutil.which(cc[0]):
        raise unittest.SkipTest("host C compiler not available")
    return cc


def db_bytes(lat: float = 10.0, lon: float = 106.0013, heading: float = 90.0,
             sign_type: bytes = b"R.420\0") -> bytes:
    record = struct.pack("<ddf", lat, lon, heading)
    record += sign_type.ljust(16, b"\0")
    record += b"synthetic".ljust(64, b"\0")
    return b"C2MSDB01" + struct.pack("<I", 1) + record


def gps_bytes(utc: int, *, lat: float = 10.0, lon: float = 106.0,
              speed: float = 36.0, course: float = 90.0) -> bytes:
    blob = bytearray(0x4F0)
    struct.pack_into("<I", blob, 0, 8)       # RMC
    struct.pack_into("<I", blob, 4, 124)     # 2024
    struct.pack_into("<I", blob, 8, 1)       # February (zero based)
    struct.pack_into("<I", blob, 0x0C, 29)
    hour, rem = divmod(utc, 3600)
    minute, second = divmod(rem, 60)
    struct.pack_into("<I", blob, 0x10, hour % 24)
    struct.pack_into("<I", blob, 0x14, minute)
    struct.pack_into("<I", blob, 0x18, second)
    struct.pack_into("<I", blob, 0x20, 1)   # signal
    struct.pack_into("<I", blob, 0x24, 2)   # fix
    def ddmm(degrees: float) -> float:
        magnitude = abs(degrees)
        whole = int(magnitude)
        raw = whole * 100.0 + (magnitude - whole) * 60.0
        return -raw if degrees < 0 else raw
    struct.pack_into("<d", blob, 0x40, ddmm(lat))
    struct.pack_into("<d", blob, 0x48, ddmm(lon))
    struct.pack_into("<d", blob, 0x58, speed)
    struct.pack_into("<d", blob, 0x60, course)
    # Synthetic car_info has the GPS record at FILE offset 0x330.
    return bytes(0x330) + bytes(blob[:0x1C0])


class D4AdvisoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-d4-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        suffix = ".exe" if os.name == "nt" else ""
        cls.binary = base / ("c2m-d4" + suffix)
        cls.regression = base / ("frozen-gps" + suffix)
        driver = base / "frozen-gps.c"
        driver.write_text(FROZEN_GPS_DRIVER, encoding="utf-8")
        for source, binary in (("fw/d4/main.c", cls.binary), (str(driver), cls.regression)):
            command = compiler() + FLAGS + [source] + SOURCES + ["-lm", "-o", str(binary)]
            result = subprocess.run(command, cwd=ROOT, text=True,
                                    capture_output=True, timeout=90)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_help_and_pure_core_selftest(self) -> None:
        for argument in ("--help", "--self-test"):
            result = subprocess.run([str(self.binary), argument], text=True,
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline GPS", subprocess.run(
            [str(self.binary), "--help"], text=True, capture_output=True,
            check=True).stdout)

    def test_frozen_gps_stays_stale_until_confirmed_advance(self) -> None:
        result = subprocess.run([str(self.regression)], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0,
                         f"frozen GPS regression failed: exit={result.returncode} {result.stderr}")

    def test_cli_rejects_partial_relative_duplicate_and_unknown_paths(self) -> None:
        # All invalid invocations stop before any default/fixture path is read.
        bad_arguments = [[], ["--unknown"], ["--serve", "--db", "/fixture/db"],
                         ["--serve", "--db"],
                         ["--serve", "--db", "relative"],
                         ["--serve", "--network", "/fixture/no"],
                         ["--serve", "--db", "/fixture/a", "--db", "/fixture/b"]]
        for arguments in bad_arguments:
            with self.subTest(arguments=arguments):
                result = subprocess.run([str(self.binary)] + arguments,
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stderr)

    @unittest.skipIf(LINUX, "non-Linux unsupported adapter contract")
    def test_non_linux_serve_is_explicitly_unsupported_without_io(self) -> None:
        result = subprocess.run([str(self.binary), "--serve"], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("unsupported", result.stderr)
        self.assertEqual(result.stdout, "")

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_linux_fixture_active_hold_and_frozen_gps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-fixture-") as name:
            root = Path(name)
            db = root / "db.bin"
            gps = root / "car_info"
            status = root / "status"
            db.write_bytes(db_bytes())
            gps.write_bytes(gps_bytes(0))
            db.chmod(0o600)
            gps.chmod(0o600)
            command = [str(self.binary), "--serve", "--db", str(db),
                       "--gps-file", str(gps), "--status-file", str(status)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(self._wait_for(status, lambda text:
                    "state=warming_up\n" in text), self._read(status))
                # Replace the synthetic immutable file, advancing exactly one
                # UTC second. The two identical reads are still performed by
                # the production reader.
                replacement = root / "gps.next"
                replacement.write_bytes(gps_bytes(1))
                replacement.chmod(0o600)
                os.replace(replacement, gps)
                self.assertTrue(self._wait_for(status, lambda text:
                    "state=ready\n" in text and "active=1\n" in text and
                    "code=residential_start\n" in text), self._read(status))
                first = self._read(status)
                self._assert_status(first, state="ready", active=1)
                # The mandatory web schema enumerates eleven fields; adding
                # any twelfth/unknown key would make its strict parser reject.
                self.assertEqual(first.count("\n"), 11)
                self.assertIn("speed_kmh=0\n", first)
                self.assertNotIn("lat", first)
                self.assertEqual(stat.S_IMODE(status.stat().st_mode), 0o600)
                self.assertEqual(status.stat().st_nlink, 1)
                event = self._field(first, "event_id")
                # A heartbeat during the eight-second hold keeps one event.
                time.sleep(1.2)
                second = self._read(status)
                self.assertEqual(self._field(second, "event_id"), event)
                self.assertEqual(self._field(second, "code"), "residential_start")
                # Identical UTC seconds age out, despite a readable file.
                self.assertTrue(self._wait_for(status, lambda text:
                    "state=stale\n" in text and "active=0\n" in text), self._read(status))
                # Continue through another stale-gate reanchor interval: a
                # freeze must not oscillate back to warming_up/ready.
                previous = int(self._field(self._read(status), "sequence"))
                deadline = time.monotonic() + 3.2
                while time.monotonic() < deadline:
                    text = self._read(status)
                    self._assert_status(text, state="stale", active=0)
                    current = int(self._field(text, "sequence"))
                    self.assertGreaterEqual(current, previous)
                    previous = current
                    time.sleep(0.05)
            finally:
                self._stop(process)
                self.assertEqual(self._field(self._read(status), "state"), "disabled")

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_malformed_db_symlink_gps_and_status_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-reject-") as name:
            root = Path(name)
            bad_db = root / "bad-db"
            target_db = root / "target-db"
            target_db.write_bytes(db_bytes())
            os.symlink(target_db, bad_db)
            gps = root / "car_info"
            gps.write_bytes(gps_bytes(0))
            status = root / "status"
            target_status = root / "status-target"
            target_status.write_text("must-not-be-replaced\n")
            os.symlink(target_status, status)
            for item in (target_db, gps, target_status):
                item.chmod(0o600)
            process = subprocess.Popen(
                [str(self.binary), "--serve", "--db", str(bad_db),
                 "--gps-file", str(gps), "--status-file", str(status)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(1.2)
                self.assertFalse(status.exists() and not status.is_symlink())
                self.assertEqual(target_status.read_text(), "must-not-be-replaced\n")
            finally:
                self._stop(process)

            malformed = root / "malformed"
            malformed.write_bytes(b"C2MSDB01" + struct.pack("<I", 1))
            normal_status = root / "normal-status"
            process = subprocess.Popen(
                [str(self.binary), "--serve", "--db", str(malformed),
                 "--gps-file", str(gps), "--status-file", str(normal_status)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(self._wait_for(normal_status, lambda text:
                    "state=no_database\n" in text), self._read(normal_status))
                self.assertEqual(self._field(self._read(normal_status), "active"), "0")
            finally:
                self._stop(process)

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_fifo_links_mutations_and_replaced_db(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-fs-") as name:
            root = Path(name)
            db, gps, status = root / "db", root / "gps", root / "status"
            gps.write_bytes(gps_bytes(0))
            gps.chmod(0o600)

            def run_until(expected: str, update=None) -> None:
                if status.exists():
                    status.unlink()
                process = subprocess.Popen(
                    [str(self.binary), "--serve", "--db", str(db),
                     "--gps-file", str(gps), "--status-file", str(status)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if update:
                        self.assertTrue(self._wait_for(status, lambda text:
                            "state=warming_up\n" in text), self._read(status))
                        update()
                    self.assertTrue(self._wait_for(status, lambda text:
                        f"state={expected}\n" in text and "active=0\n" in text),
                        self._read(status))
                finally:
                    self._stop(process)
                self.assertIn("state=disabled\n", self._read(status))
                self.assertFalse(list(root.glob(".c2m-d4-*.tmp")))

            # FIFO must never block at open; a hardlinked DB is untrusted too.
            os.mkfifo(db, 0o600)
            run_until("no_database")
            db.unlink()
            other = root / "other"
            other.write_bytes(db_bytes())
            other.chmod(0o600)
            os.link(other, db)
            run_until("no_database")
            db.unlink()
            other.unlink()
            # Exact length/count validation rejects trailing bytes and bounds.
            for payload in (db_bytes() + b"x", b"C2MSDB01" + struct.pack("<I", 40001),
                            bytes(4_000_013)):
                db.write_bytes(payload)
                db.chmod(0o600)
                run_until("no_database")
            db.write_bytes(db_bytes())
            db.chmod(0o666)
            run_until("no_database")
            db.chmod(0o600)
            # Metadata replacement poisons the loaded DB until restart.
            def replace_database() -> None:
                replacement = root / "db.next"
                replacement.write_bytes(db_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, db)
            run_until("no_database", replace_database)
            # GPS adapter never blocks on FIFOs and rejects final symlinks.
            gps.unlink()
            os.mkfifo(gps, 0o600)
            run_until("waiting_gps")
            gps.unlink()
            other.write_bytes(gps_bytes(0))
            other.chmod(0o600)
            os.symlink(other, gps)
            run_until("waiting_gps")

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_publish_failure_does_not_consume_event_or_cooldown(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-publish-") as name:
            root = Path(name)
            db, gps, status = root / "db", root / "gps", root / "status"
            db.write_bytes(db_bytes())
            gps.write_bytes(gps_bytes(0))
            db.chmod(0o600)
            gps.chmod(0o600)
            # After the first inactive heartbeat, a directory blocks delivery
            # of event 1 without consuming its event ID or sign cooldown.
            process = subprocess.Popen(
                [str(self.binary), "--serve", "--db", str(db),
                 "--gps-file", str(gps), "--status-file", str(status)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(self._wait_for(status, lambda text:
                    "state=warming_up\n" in text), self._read(status))
                status.unlink()
                status.mkdir(mode=0o700)
                replacement = root / "gps.next"
                replacement.write_bytes(gps_bytes(1))
                replacement.chmod(0o600)
                os.replace(replacement, gps)
                time.sleep(1.2)
                self.assertTrue(status.is_dir())
                status.rmdir()
                self.assertTrue(self._wait_for(status, lambda text:
                    "active=1\n" in text and "event_id=1\n" in text), self._read(status))
            finally:
                self._stop(process)

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_missing_database_and_gps_emit_honest_inactive_heartbeats(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-missing-") as name:
            root = Path(name)
            db, gps, status = root / "db", root / "gps", root / "status"
            for have_db, expected in ((False, "no_database"), (True, "waiting_gps")):
                if have_db:
                    db.write_bytes(db_bytes())
                    db.chmod(0o600)
                if status.exists():
                    status.unlink()
                process = subprocess.Popen(
                    [str(self.binary), "--serve", "--db", str(db),
                     "--gps-file", str(gps), "--status-file", str(status)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertTrue(self._wait_for(status, lambda text:
                        f"state={expected}\n" in text), self._read(status))
                    text = self._read(status)
                    self._assert_status(text, state=expected, active=0)
                    self.assertEqual(self._field(text, "gps_fresh"), "0")
                    self.assertEqual(self._field(text, "code"), "none")
                    self.assertEqual(self._field(text, "event_id"), "0")
                finally:
                    self._stop(process)

    @unittest.skipUnless(LINUX, "descriptor/process integration is Linux-only")
    def test_symlink_ancestors_and_writable_db_parent_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c2m-d4-ancestor-") as name:
            root = Path(name)
            real = root / "real"
            real.mkdir(mode=0o700)
            alias = root / "alias"
            os.symlink(real, alias)
            db, gps, status = real / "db", real / "gps", root / "status"
            db.write_bytes(db_bytes())
            gps.write_bytes(gps_bytes(0))
            db.chmod(0o600)
            gps.chmod(0o600)
            for db_path, gps_path, status_path, expected in (
                (alias / "db", gps, status, "no_database"),
                (db, alias / "gps", status, "waiting_gps"),
                (db, gps, alias / "status", None),
            ):
                if status.exists():
                    status.unlink()
                process = subprocess.Popen(
                    [str(self.binary), "--serve", "--db", str(db_path),
                     "--gps-file", str(gps_path), "--status-file", str(status_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    if expected:
                        self.assertTrue(self._wait_for(status_path, lambda text:
                            f"state={expected}\n" in text and "active=0\n" in text),
                            self._read(status_path))
                    else:
                        time.sleep(1.2)
                        self.assertFalse((real / "status").exists())
                        self.assertIsNone(process.poll())
                finally:
                    self._stop(process)
            writable = root / "writable"
            writable.mkdir(mode=0o700)
            insecure_db = writable / "db"
            insecure_db.write_bytes(db_bytes())
            insecure_db.chmod(0o600)
            writable.chmod(0o777)
            status.unlink(missing_ok=True)
            process = subprocess.Popen(
                [str(self.binary), "--serve", "--db", str(insecure_db),
                 "--gps-file", str(gps), "--status-file", str(status)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(self._wait_for(status, lambda text:
                    "state=no_database\n" in text), self._read(status))
            finally:
                self._stop(process)
                writable.chmod(0o700)

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        process.terminate()
        process.wait(timeout=5)
        stdout, stderr = process.communicate()
        if process.returncode not in (0, 1):
            raise AssertionError(f"D4 process failed: {process.returncode}: {stdout} {stderr}")

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="ascii")
        except (FileNotFoundError, UnicodeError):
            return ""

    @classmethod
    def _wait_for(cls, path: Path, predicate, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = cls._read(path)
            if text and predicate(text):
                return True
            time.sleep(0.05)
        return False

    @staticmethod
    def _field(text: str, key: str) -> str:
        prefix = key + "="
        for line in text.splitlines():
            if line.startswith(prefix):
                return line[len(prefix):]
        raise AssertionError((key, text))

    def _assert_status(self, text: str, *, state: str, active: int) -> None:
        keys = ("version", "source", "state", "gps_fresh", "active", "sequence", "code",
                "speed_kmh", "distance_m", "event_id", "monotonic_ms")
        self.assertTrue(text.endswith("\n"), text)
        self.assertNotIn("\r", text)
        lines = text.splitlines()
        self.assertEqual(len(lines), len(keys), text)
        self.assertEqual(tuple(line.split("=", 1)[0] for line in lines), keys, text)
        fields = dict(line.split("=", 1) for line in lines)
        self.assertEqual(fields["version"], "1")
        self.assertEqual(fields["source"], "gps_offline")
        self.assertEqual(fields["state"], state, text)
        self.assertEqual(fields["active"], str(active), text)
        self.assertEqual(fields["speed_kmh"], "0")
        for key, maximum in (("gps_fresh", 1), ("active", 1), ("sequence", 2**32 - 1),
                             ("event_id", 2**32 - 1), ("distance_m", 2000),
                             ("monotonic_ms", 2**64 - 1)):
            value = fields[key]
            self.assertTrue(value.isascii() and value.isdecimal(), text)
            self.assertEqual(str(int(value)), value, text)
            self.assertLessEqual(int(value), maximum, text)
        if active:
            self.assertEqual(state, "ready")
            self.assertEqual(fields["gps_fresh"], "1")
            self.assertIn(fields["code"], ("residential_start", "residential_end"))
            self.assertGreater(int(fields["event_id"]), 0)
        else:
            self.assertEqual(fields["code"], "none")
            self.assertEqual(fields["distance_m"], "0")
            self.assertEqual(fields["event_id"], "0")


if __name__ == "__main__":
    unittest.main()
