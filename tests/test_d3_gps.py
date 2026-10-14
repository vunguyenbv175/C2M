#!/usr/bin/env python3
"""Synthetic host tests for the EN read-only GPS snapshot contract.

Run: python tests/test_d3_gps.py
Requires host GCC (or CC). Builds only in a temporary directory; no vendor
firmware, hardware, UART, IPC, or real /tmp/car_info is used. The pure decoder,
freshness state and --self-test run on Windows and Linux. Filesystem tests and
deterministic syscall fault injection run only on Linux.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import math
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "fw" / "d3" / "gps_snapshot.c"
OFFSET = 0x330
RECORD_BYTES = 0x1C0
MIN_FILE_BYTES = 0x4F0
MAX_FILE_BYTES = 2 * 1024 * 1024
OK, INVALID, IO_ERROR, UNSTABLE, UNSUPPORTED = 0, -1, -2, -3, -4
LINUX = sys.platform.startswith("linux")


class Snapshot(ctypes.Structure):
    _fields_ = [
        ("utc_seconds", ctypes.c_int64),
        ("hundredths", ctypes.c_uint32),
        ("mask", ctypes.c_uint32),
        ("latitude_deg", ctypes.c_double),
        ("longitude_deg", ctypes.c_double),
        ("speed_kmh", ctypes.c_double),
        ("course_deg", ctypes.c_double),
        ("heading_usable", ctypes.c_int),
    ]


class Freshness(ctypes.Structure):
    _fields_ = [
        ("last_utc_seconds", ctypes.c_int64),
        ("last_advance_ms", ctypes.c_uint64),
        ("last_observation_ms", ctypes.c_uint64),
        ("reference_utc_seconds", ctypes.c_int64),
        ("reference_ms", ctypes.c_uint64),
        ("have_anchor", ctypes.c_int),
        ("confirmed", ctypes.c_int),
    ]


def record(*, mask=8, year=124, month=1, day=29, hour=12, minute=34,
           second=56, hundredths=78, signal=1, fix=2, latitude=-1230.0,
           longitude=4530.0, speed=25.0, course=123.5) -> bytes:
    """Explicit little-endian nmeaINFO, not a native ABI struct."""
    blob = bytearray(RECORD_BYTES)
    for offset, value in (
        (0, mask), (4, year), (8, month), (0x0C, day), (0x10, hour),
        (0x14, minute), (0x18, second), (0x1C, hundredths),
        (0x20, signal), (0x24, fix),
    ):
        struct.pack_into("<I", blob, offset, value & 0xFFFFFFFF)
    for offset, value in (
        (0x40, latitude), (0x48, longitude), (0x58, speed), (0x60, course),
    ):
        struct.pack_into("<d", blob, offset, value)
    return bytes(blob)


def configure_library(path: Path):
    lib = ctypes.CDLL(str(path))
    lib.c2m_gps_decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(Snapshot)]
    lib.c2m_gps_decode.restype = ctypes.c_int
    lib.c2m_gps_read.argtypes = [ctypes.c_char_p, ctypes.POINTER(Snapshot)]
    lib.c2m_gps_read.restype = ctypes.c_int
    lib.c2m_gps_freshness_init.argtypes = [ctypes.POINTER(Freshness)]
    lib.c2m_gps_freshness_init.restype = None
    lib.c2m_gps_freshness_update.argtypes = [ctypes.POINTER(Freshness),
                                           ctypes.POINTER(Snapshot),
                                           ctypes.c_uint64]
    lib.c2m_gps_freshness_update.restype = ctypes.c_int
    return lib


# Interpose only the reader's syscalls in an independent test library. The
# fixture stays read-only. This reliably covers torn/short reads, EINTR and
# flags without racing a real writer or relaxing production checks.
LINUX_SHIM = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
static int hook_open(const char *, int);
static ssize_t hook_pread(int, void *, size_t, off_t);
static int hook_fstat(int, struct stat *);
static int hook_close(int);
#define open hook_open
#define pread hook_pread
#define fstat hook_fstat
#define close hook_close
#include "gps_snapshot.c"
#undef open
#undef pread
#undef fstat
#undef close
static int mode, reads, stats, closes, flags_seen, contract_ok;
void gps_hook_reset(int value)
{
    mode = value; reads = stats = closes = flags_seen = 0; contract_ok = 1;
}
int gps_hook_reads(void) { return reads; }
int gps_hook_closes(void) { return closes; }
int gps_hook_contract_ok(void) { return contract_ok; }
int gps_hook_safe_flags(void)
{
    return (flags_seen & O_ACCMODE) == O_RDONLY &&
           (flags_seen & O_NOFOLLOW) && (flags_seen & O_NONBLOCK) &&
           (flags_seen & O_CLOEXEC) &&
           !(flags_seen & (O_CREAT | O_TRUNC | O_APPEND));
}
static int hook_open(const char *path, int flags)
{
    flags_seen = flags;
    return open(path, flags);
}
static ssize_t hook_pread(int fd, void *bytes, size_t size, off_t offset)
{
    ssize_t result;
    ++reads;
    if (size != C2M_GPS_RECORD_BYTES || offset != C2M_GPS_FILE_OFFSET)
        contract_ok = 0;
    if (mode == 3 && reads == 1) { errno = EINTR; return -1; }
    if (mode == 4) { errno = EIO; return -1; }
    result = pread(fd, bytes, size, offset);
    if (mode == 1 && reads == 2 && result > 0)
        ((unsigned char *)bytes)[size - 1] ^= 1;
    if (mode == 2 && reads == 1 && result > 0) --result;
    if (mode == 6 && reads == 2 && result > 0) --result;
    return result;
}
static int hook_fstat(int fd, struct stat *st)
{
    int result = fstat(fd, st);
    ++stats;
    if (mode == 5 && stats == 2 && result == 0)
        st->st_size = C2M_GPS_MAX_FILE_BYTES + 1;
    if (mode == 7 && stats == 2) { errno = EIO; return -1; }
    return result;
}
static int hook_close(int fd)
{
    int result = close(fd);
    ++closes;
    if (mode == 8) { errno = EIO; return -1; }
    return result;
}
"""


class GpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = os.environ.get("CC")
        if compiler:
            cls.cc = [compiler] if Path(compiler).is_file() else shlex.split(compiler)
        else:
            compiler = shutil.which("gcc") or shutil.which("cc")
            if not compiler:
                raise RuntimeError("Host GCC required (install gcc or set CC)")
            cls.cc = [compiler]
        temp_parent = None
        if os.name == "nt":
            approved = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "opencode"
            if approved.is_dir():
                temp_parent = approved
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-gps-", dir=temp_parent)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.build = Path(cls.tmp.name)
        cls.flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-pedantic", "-I", str(SOURCE.parent)]
        dll_suffix = ".dll" if os.name == "nt" else ".so"
        cls.library_path = cls.build / ("gps_snapshot" + dll_suffix)
        shared_flags = ["-shared"] + ([] if os.name == "nt" else ["-fPIC"])
        cls.compile(*shared_flags, str(SOURCE), "-o", str(cls.library_path), "-lm")
        cls.lib = configure_library(cls.library_path)
        if os.name == "nt":
            # A loaded DLL cannot be deleted on Windows. Unload before the
            # temporary-directory cleanup (class cleanups execute LIFO).
            cls.addClassCleanup(cls.release_windows_library)
        cls.executable = cls.build / ("gps-selftest.exe" if os.name == "nt"
                                      else "gps-selftest")
        cls.compile("-DC2M_GPS_SELFTEST", str(SOURCE), "-o", str(cls.executable), "-lm")
        if LINUX:
            shim = cls.build / "reader_hooks.c"
            shim.write_text(LINUX_SHIM, encoding="utf-8")
            hook_path = cls.build / "gps_hooks.so"
            cls.compile(*shared_flags, str(shim), "-o", str(hook_path), "-lm")
            cls.hooks = configure_library(hook_path)
            cls.hooks.gps_hook_reset.argtypes = [ctypes.c_int]
            cls.hooks.gps_hook_reset.restype = None
            for name in ("reads", "closes", "contract_ok", "safe_flags"):
                fn = getattr(cls.hooks, "gps_hook_" + name)
                fn.argtypes = []
                fn.restype = ctypes.c_int

    @classmethod
    def release_windows_library(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle)
        cls.lib = None

    @classmethod
    def compile(cls, *args):
        result = subprocess.run(cls.cc + cls.flags + list(args), cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Host compile failed:\n" + result.stdout + result.stderr)

    def decode(self, blob=record(), expected=OK, *, size=None, lib=None):
        out = Snapshot()
        ctypes.memset(ctypes.byref(out), 0xA5, ctypes.sizeof(out))
        buffer = ctypes.create_string_buffer(blob) if blob is not None else None
        if size is None:
            size = len(blob) if blob is not None else RECORD_BYTES
        result = (lib or self.lib).c2m_gps_decode(buffer, size, ctypes.byref(out))
        self.assertEqual(result, expected)
        if expected != OK:
            self.assertEqual(bytes(out), bytes(ctypes.sizeof(out)))
        return out

    def fresh(self, state, sample, ms):
        return self.lib.c2m_gps_freshness_update(
            ctypes.byref(state), ctypes.byref(sample) if sample is not None else None, ms)

    def fixture(self, name="fixture.bin", blob=None, size=MIN_FILE_BYTES):
        path = self.build / name
        data = bytearray(size)
        if blob is None:
            blob = record()
        if size >= OFFSET + len(blob):
            data[OFFSET:OFFSET + len(blob)] = blob
        path.write_bytes(data)
        return path

    def read(self, path, expected=OK, lib=None):
        out = Snapshot()
        ctypes.memset(ctypes.byref(out), 0xA5, ctypes.sizeof(out))
        encoded = os.fsencode(path) if path is not None else None
        result = (lib or self.lib).c2m_gps_read(encoded, ctypes.byref(out))
        self.assertEqual(result, expected)
        if expected != OK:
            self.assertEqual(bytes(out), bytes(ctypes.sizeof(out)))
        return out

    def test_self_test_cli(self):
        result = subprocess.run([str(self.executable), "--self-test"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "gps snapshot synthetic self-test: OK")
        bad = subprocess.run([str(self.executable)], capture_output=True,
                             text=True, timeout=5)
        self.assertEqual(bad.returncode, 2)

    def test_valid_contract_and_units(self):
        out = self.decode()
        self.assertEqual(out.utc_seconds, int(dt.datetime(
            2024, 2, 29, 12, 34, 56, tzinfo=dt.timezone.utc).timestamp()))
        self.assertEqual(out.hundredths, 78)
        self.assertEqual(out.latitude_deg, -12.5)
        self.assertEqual(out.longitude_deg, 45.5)
        self.assertEqual(out.speed_kmh, 25.0)  # No extra knots->km/h factor.
        self.assertEqual(out.course_deg, 123.5)
        self.assertEqual(out.heading_usable, 1)
        self.decode(record(mask=0xFFFFFFFF, signal=3, fix=3))
        # Ignored fields must not accidentally be interpreted as lat/lon.
        blob = bytearray(record())
        struct.pack_into("<d", blob, 0x50, math.nan)
        blob[-1] = 255
        self.decode(bytes(blob))

    def test_size_null_and_unaligned(self):
        for blob in (b"", record()[:-1], record() + b"\0", None):
            with self.subTest(size=len(blob) if blob is not None else None):
                self.decode(blob, INVALID)
        self.assertEqual(self.lib.c2m_gps_decode(None, RECORD_BYTES, None), INVALID)
        buf = ctypes.create_string_buffer(b"X" + record())
        out = Snapshot()
        self.assertEqual(self.lib.c2m_gps_decode(ctypes.byref(buf, 1), RECORD_BYTES,
                                               ctypes.byref(out)), OK)

    def test_rmc_signal_and_fix(self):
        for kwargs in ({"mask": 0}, {"mask": 1}, {"mask": 0x100},
                       {"mask": 0xFFFFFFF7}, {"signal": 0}, {"signal": -1},
                       {"signal": -(2**31)}, {"fix": 0}, {"fix": 1},
                       {"fix": -1}):
            with self.subTest(kwargs=kwargs):
                self.decode(record(**kwargs), INVALID)

    def test_timestamp_bounds_and_calendar(self):
        bad = (
            {"year": 99}, {"year": 200}, {"year": 2024}, {"year": -1},
            {"month": -1}, {"month": 12}, {"day": 0}, {"day": -1},
            {"month": 3, "day": 31}, {"month": 1, "day": 30},
            {"year": 123, "month": 1, "day": 29}, {"hour": 24},
            {"hour": -1}, {"minute": 60}, {"second": 60}, {"second": -1},
            {"hundredths": 100}, {"hundredths": -1},
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                self.decode(record(**kwargs), INVALID)
        valid = (
            {"year": 100, "month": 0, "day": 1, "hour": 0,
             "minute": 0, "second": 0, "hundredths": 0},
            {"year": 100, "month": 1, "day": 29},
            {"year": 196, "month": 1, "day": 29},
            {"year": 199, "month": 11, "day": 31, "hour": 23,
             "minute": 59, "second": 59, "hundredths": 99},
        )
        for kwargs in valid:
            values = dict(year=124, month=1, day=29, hour=12, minute=34, second=56)
            values.update(kwargs)
            with self.subTest(kwargs=kwargs):
                out = self.decode(record(**kwargs))
                expected = dt.datetime(values["year"] + 1900, values["month"] + 1,
                                       values["day"], values["hour"],
                                       values["minute"], values["second"],
                                       tzinfo=dt.timezone.utc)
                self.assertEqual(out.utc_seconds, int(expected.timestamp()))

    def test_all_months_and_leap_years(self):
        for year in range(2000, 2100):
            for month in range(1, 13):
                date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
                out = self.decode(record(year=year - 1900, month=month - 1,
                                         day=1, hour=0, minute=0, second=0))
                self.assertEqual(out.utc_seconds, int(date.timestamp()))

    def test_ddmm_sign_minutes_and_bounds(self):
        for field, bad_values in (
            ("latitude", (60.0, 1260.0, 8999.0, 9000.01, 9100.0, -9060.0)),
            ("longitude", (60.0, 12360.0, 17999.0, 18000.01, 18100.0)),
        ):
            for value in (*bad_values, math.nan, math.inf, -math.inf, 1e300):
                with self.subTest(field=field, value=value):
                    self.decode(record(**{field: value}), INVALID)
        for lat, lon, expected_lat, expected_lon in (
            (0.0, 0.0, 0.0, 0.0), (-9000.0, 18000.0, -90.0, 180.0),
            (9000.0, -18000.0, 90.0, -180.0),
            (-0.0, -0.0, -0.0, -0.0),
            (59.999, -17959.999, 59.999 / 60, -(179 + 59.999 / 60)),
            (1234.5, -12345.5, 12 + 34.5 / 60, -(123 + 45.5 / 60)),
        ):
            out = self.decode(record(latitude=lat, longitude=lon))
            self.assertAlmostEqual(out.latitude_deg, expected_lat, places=10)
            self.assertAlmostEqual(out.longitude_deg, expected_lon, places=10)
        zero = self.decode(record(latitude=-0.0, longitude=-0.0))
        self.assertEqual(math.copysign(1, zero.latitude_deg), -1)

    def test_speed_course_and_heading_boundaries(self):
        for value in (-0.1, 300.0001, math.nan, math.inf, -math.inf):
            with self.subTest(speed=value):
                self.decode(record(speed=value), INVALID)
        for value, usable in ((0, 0), (4.9999, 0), (5, 1), (300, 1)):
            out = self.decode(record(speed=value))
            self.assertEqual(out.heading_usable, usable)
            self.assertEqual(out.speed_kmh, value)
        for value in (-0.001, 360, 1000, math.nan, math.inf, -math.inf):
            with self.subTest(course=value):
                self.decode(record(course=value), INVALID)
        self.decode(record(course=0))
        self.decode(record(course=359.999999))
        self.decode(record(speed=0, course=math.nan), INVALID)

    def test_freshness_two_advances_and_exact_stale_boundary(self):
        state = Freshness()
        self.lib.c2m_gps_freshness_init(ctypes.byref(state))
        sample = self.decode()
        self.assertEqual(self.fresh(state, sample, 10000), 0)
        self.assertEqual(self.fresh(state, sample, 10500), 0)
        sample.utc_seconds += 1
        self.assertEqual(self.fresh(state, sample, 11000), 1)
        self.assertEqual(self.fresh(state, sample, 13499), 1)
        self.assertEqual(self.fresh(state, sample, 13500), 0)
        self.assertEqual(state.confirmed, 0)
        self.assertEqual(self.fresh(state, sample, 14000), 0)
        sample.utc_seconds += 1
        self.assertEqual(self.fresh(state, sample, 14500), 1)

    def test_repeated_coordinates_can_be_fresh_hundredths_cannot(self):
        state = Freshness()
        sample = self.decode(record(speed=0))
        self.assertEqual(self.fresh(state, sample, 0), 0)
        sample.hundredths = 99
        sample.latitude_deg += 0.1
        self.assertEqual(self.fresh(state, sample, 1000), 0)
        sample.utc_seconds += 1
        self.assertEqual(self.fresh(state, sample, 2000), 1)
        self.assertEqual(sample.heading_usable, 0)
        # Identical coordinates are fine when UTC advances, including at rest.
        for ms in range(3000, 13000, 1000):
            sample.utc_seconds += 1
            self.assertEqual(self.fresh(state, sample, ms), 1)
        sample.hundredths = 0
        sample.latitude_deg += 1
        self.assertEqual(self.fresh(state, sample, 14500), 0)

    def test_freshness_delta_tolerance_and_cumulative_drift(self):
        for delta, expected in ((4, 1), (5, 0)):
            state = Freshness()
            sample = self.decode()
            self.assertEqual(self.fresh(state, sample, 0), 0)
            sample.utc_seconds += delta
            self.assertEqual(self.fresh(state, sample, 1000), expected)
        state = Freshness()
        sample = self.decode()
        self.assertEqual(self.fresh(state, sample, 0), 0)
        for n in range(1, 5):
            sample.utc_seconds += 1
            self.assertEqual(self.fresh(state, sample, n), 1 if n < 4 else 0)
        # An instantaneous timestamp jump is not an advancing-clock proof.
        state = Freshness()
        sample = self.decode()
        self.fresh(state, sample, 500)
        sample.utc_seconds += 1
        self.assertEqual(self.fresh(state, sample, 500), 0)

    def test_freshness_failures_regressions_and_poll_gaps(self):
        for failure in ("read", "utc", "monotonic", "gap", "invalid"):
            with self.subTest(failure=failure):
                state = Freshness()
                sample = self.decode()
                self.fresh(state, sample, 1000)
                sample.utc_seconds += 1
                self.assertEqual(self.fresh(state, sample, 2000), 1)
                if failure == "read":
                    self.assertEqual(self.fresh(state, None, 2100), 0)
                elif failure == "utc":
                    sample.utc_seconds -= 1
                    self.assertEqual(self.fresh(state, sample, 2100), 0)
                elif failure == "monotonic":
                    self.assertEqual(self.fresh(state, sample, 1900), 0)
                elif failure == "gap":
                    sample.utc_seconds += 3
                    self.assertEqual(self.fresh(state, sample, 5000), 0)
                else:
                    sample.utc_seconds = 0
                    self.assertEqual(self.fresh(state, sample, 2100), 0)
                self.assertEqual(state.confirmed, 0)
        self.assertEqual(self.lib.c2m_gps_freshness_update(None, None, 0), 0)
        # No overflow at a large monotonic epoch.
        state = Freshness()
        sample = self.decode()
        self.assertEqual(self.fresh(state, sample, 2**64 - 2000), 0)
        sample.utc_seconds += 1
        self.assertEqual(self.fresh(state, sample, 2**64 - 1000), 1)

    @unittest.skipIf(LINUX, "non-Linux fail-closed adapter only")
    def test_non_linux_adapter_never_opens(self):
        self.read("not-a-real-file", UNSUPPORTED)

    @unittest.skipUnless(LINUX, "Linux-only safe filesystem adapter")
    def test_read_offset_bounds_and_no_writes(self):
        path = self.fixture()
        before = path.read_bytes()
        out = self.read(path)
        self.assertEqual(out.latitude_deg, -12.5)
        self.assertEqual(path.read_bytes(), before)
        self.read(self.fixture("max.bin", size=MAX_FILE_BYTES))
        for size in (0, OFFSET, MIN_FILE_BYTES - 1, MAX_FILE_BYTES + 1):
            with self.subTest(size=size):
                self.read(self.fixture("bad-size.bin", size=size), INVALID)
        # The old offset-zero interpretation must be rejected.
        wrong = self.fixture("wrong-offset.bin", blob=bytes(RECORD_BYTES))
        data = bytearray(wrong.read_bytes())
        data[:RECORD_BYTES] = record()
        wrong.write_bytes(data)
        self.read(wrong, INVALID)
        # Extra eight vendor-written bytes do not belong to nmeaINFO.
        extra = self.fixture("trailer.bin", size=MIN_FILE_BYTES + 8)
        data = bytearray(extra.read_bytes())
        data[-8:] = b"\xff" * 8
        extra.write_bytes(data)
        self.read(extra)

    @unittest.skipUnless(LINUX, "Linux-only safe filesystem adapter")
    def test_read_rejects_symlink_fifo_directory_and_missing(self):
        path = self.fixture("regular.bin")
        link = self.build / "symlink.bin"
        link.symlink_to(path)
        self.read(link, IO_ERROR)
        fifo = self.build / "fixture.fifo"
        os.mkfifo(fifo)
        # A subprocess timeout makes a missing O_NONBLOCK fail promptly,
        # rather than leaving the whole test suite blocked in open().
        code = (
            "import ctypes,sys; l=ctypes.CDLL(sys.argv[1]); "
            "l.c2m_gps_read.argtypes=[ctypes.c_char_p,ctypes.c_void_p]; "
            "b=ctypes.create_string_buffer(128); "
            "r=l.c2m_gps_read(sys.argv[2].encode(),b); "
            "sys.exit(0 if r == -1 else 1)"
        )
        result = subprocess.run([sys.executable, "-c", code,
                                 str(self.library_path), str(fifo)], timeout=5)
        self.assertEqual(result.returncode, 0)
        self.read(self.build, INVALID)
        self.read(self.build / "absent.bin", IO_ERROR)
        self.read(None, INVALID)
        self.read("", INVALID)
        self.assertEqual(self.lib.c2m_gps_read(os.fsencode(path), None), INVALID)

    @unittest.skipUnless(LINUX, "Linux-only safe filesystem adapter")
    def test_mtime_is_not_freshness(self):
        path = self.fixture("mtime.bin")
        os.utime(path, (1, 1))
        sample = self.read(path)
        state = Freshness()
        self.assertEqual(self.fresh(state, sample, 0), 0)
        os.utime(path, (2000000000, 2000000000))
        again = self.read(path)
        self.assertEqual(self.fresh(state, again, 1000), 0)

    @unittest.skipUnless(LINUX, "Linux-only deterministic syscall injection")
    def test_read_short_torn_eintr_and_exact_contract(self):
        path = self.fixture("hooks.bin")
        original = path.read_bytes()
        for mode, expected, read_count in (
            (0, OK, 2), (1, UNSTABLE, 2), (2, INVALID, 1),
            (3, OK, 3), (4, IO_ERROR, 1), (5, UNSTABLE, 2),
            (6, INVALID, 2), (7, IO_ERROR, 2), (8, IO_ERROR, 2),
        ):
            with self.subTest(mode=mode):
                self.hooks.gps_hook_reset(mode)
                self.read(path, expected, self.hooks)
                self.assertTrue(self.hooks.gps_hook_safe_flags())
                self.assertEqual(self.hooks.gps_hook_contract_ok(), 1)
                self.assertEqual(self.hooks.gps_hook_reads(), read_count)
                self.assertEqual(self.hooks.gps_hook_closes(), 1)
                self.assertEqual(path.read_bytes(), original)
        self.hooks.gps_hook_reset(0)
        self.read(self.fixture("malformed.bin", blob=record(second=60)),
                  INVALID, self.hooks)
        self.assertEqual(self.hooks.gps_hook_closes(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
