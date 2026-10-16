#!/usr/bin/env python3
"""Pure same-poll shadow trace and frozen-reference differential tests.

No camera/filesystem fixture/network/private data. Builds production, shadow and
frozen pre-trace freshness libraries in a temporary directory on Windows/Linux.
Checks return values AND every state byte, not just diagnostic strings.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from test_d3_gps import Snapshot, Freshness, SOURCE, configure_library

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/gps_freshness_reference.c"
EPOCH = 1709164800  # Synthetic only, never sourced from a camera.
MAX_MS = (1 << 64) - 1
REASONS = {
    "no_state", "no_sample", "invalid_sample", "first_anchor",
    "monotonic_regression", "timeout", "utc_regression", "repeat_unconfirmed",
    "repeat_confirmed", "zero_elapsed", "step_tolerance", "reference_tolerance",
    "advancing",
}
STEPS = {"unavailable", "first", "repeat", "one_step", "jump", "regress"}


class Trace(ctypes.Structure):
    _fields_ = [("reason", ctypes.c_char_p), ("utc_step", ctypes.c_char_p)]


def sample(delta: int = 0) -> Snapshot:
    return Snapshot(EPOCH + delta, 100, 8, 10.0, 106.0, 36.0, 90.0, 1)


class ShadowTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("CC", "gcc")) or shutil.which("cc")
        if not cc:
            raise RuntimeError("host C compiler required")
        approved = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp/opencode"
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-shadow-trace-",
                                              dir=approved if os.name == "nt" and approved.is_dir() else None)
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.libs = []
        cls.paths = []
        # Register unloading BEFORE building/loading, even if a later build fails.
        cls.addClassCleanup(cls.unload)
        for name, source, flags in (("production", SOURCE, []),
                                    ("shadow", SOURCE, ["-DC2M_D4_SHADOW_OBSERVE"]),
                                    ("baseline", REFERENCE, [])):
            path = base / (name + (".dll" if os.name == "nt" else ".so"))
            cmd = [cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
                   "-shared"] + ([] if os.name == "nt" else ["-fPIC"])
            # ABI helpers are independent of Python's expected structure layout.
            abi = base / (name + "_abi.c")
            abi.write_text('#include "gps_snapshot.h"\n#include <stddef.h>\n'
                           'size_t trace_test_state_size(void) { return sizeof(struct c2m_gps_freshness); }\n'
                           'size_t trace_test_snapshot_size(void) { return sizeof(struct c2m_gps_snapshot); }\n',
                           encoding="utf-8")
            r = subprocess.run(cmd + flags + ["-I", str(SOURCE.parent), str(source),
                               str(abi), "-lm", "-o", str(path)],
                               capture_output=True, text=True, timeout=60)
            if r.returncode:
                raise RuntimeError("compile failed:\n" + r.stdout + r.stderr)
            lib = ctypes.CDLL(str(path)) if name == "baseline" else configure_library(path)
            cls.libs.append(lib)
            cls.paths.append(path)
            if name == "baseline":
                init, update = lib.baseline_freshness_init, lib.baseline_freshness_update
            else:
                init, update = lib.c2m_gps_freshness_init, lib.c2m_gps_freshness_update
            init.argtypes, init.restype = [ctypes.POINTER(Freshness)], None
            update.argtypes = [ctypes.POINTER(Freshness), ctypes.POINTER(Snapshot), ctypes.c_uint64]
            update.restype = ctypes.c_int
            lib.trace_init, lib.trace_update = init, update
            for symbol in ("trace_test_state_size", "trace_test_snapshot_size"):
                fn = getattr(lib, symbol)
                fn.argtypes, fn.restype = [], ctypes.c_size_t
        cls.shadow = cls.libs[1]
        cls.shadow.c2m_gps_shadow_last_trace.argtypes = []
        cls.shadow.c2m_gps_shadow_last_trace.restype = ctypes.POINTER(Trace)

    @classmethod
    def unload(cls):
        if os.name == "nt":
            import _ctypes
            for lib in cls.libs:
                _ctypes.FreeLibrary(lib._handle)
        cls.libs.clear()

    def states(self):
        states = [Freshness() for _ in self.libs]
        for lib, state in zip(self.libs, states):
            lib.trace_init(ctypes.byref(state))
        return states

    def step(self, states, gps, ms, reason=None, utc_step=None, fresh=None):
        pointer = ctypes.byref(gps) if gps is not None else None
        original = bytes(gps) if gps is not None else None
        results = [lib.trace_update(ctypes.byref(state), pointer, ms)
                   for lib, state in zip(self.libs, states)]
        self.assertEqual(results[0], results[2], "production differs from frozen reference")
        self.assertEqual(results[1], results[2], "shadow differs from frozen reference")
        self.assertEqual(bytes(states[0]), bytes(states[2]), "production mutated state differently")
        self.assertEqual(bytes(states[1]), bytes(states[2]), "trace changed freshness state")
        self.assertEqual(bytes(gps) if gps is not None else None, original)
        trace = self.shadow.c2m_gps_shadow_last_trace().contents
        got = trace.reason.decode("ascii"), trace.utc_step.decode("ascii")
        self.assertIn(got[0], REASONS)
        self.assertIn(got[1], STEPS)
        if reason is not None:
            self.assertEqual(got[0], reason)
        if utc_step is not None:
            self.assertEqual(got[1], utc_step)
        if fresh is not None:
            self.assertEqual(results[1], fresh)
        return got

    def test_frozen_reference_pin(self):
        # Independently compared to git f15d1b3's freshness body before pinning.
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                         "335a420c33263bdb56bb86f3558f32998617f827c0480ee6773eb871e48a3c9d")

    def test_abi_and_production_exclusion(self):
        for lib in self.libs:
            self.assertEqual(lib.trace_test_state_size(), ctypes.sizeof(Freshness))
            self.assertEqual(lib.trace_test_snapshot_size(), ctypes.sizeof(Snapshot))
        with self.assertRaises(AttributeError):
            getattr(self.libs[0], "c2m_gps_shadow_last_trace")
        raw = self.paths[0].read_bytes()
        for text in (b"repeat_unconfirmed", b"reference_tolerance", b"utc_step=",
                     b"freshness_reason=", b"poll_dt_ms="):
            self.assertNotIn(text, raw)
        header = (SOURCE.parent / "gps_snapshot.h").read_text()
        self.assertIn("#define C2M_GPS_STALE_MS UINT64_C(2500)", header)
        self.assertIn("#define C2M_GPS_DELTA_TOLERANCE_MS UINT64_C(3000)", header)

    def test_every_reason_and_priority(self):
        seen = set()

        def feed(states, gps, ms, reason, utc_step, fresh):
            seen.add(self.step(states, gps, ms, reason, utc_step, fresh)[0])

        # NULL state: trace is refreshed, no stale diagnostic from previous call.
        for lib in self.libs:
            self.assertEqual(lib.trace_update(None, ctypes.byref(sample()), 1000), 0)
        trace = self.shadow.c2m_gps_shadow_last_trace().contents
        self.assertEqual((trace.reason, trace.utc_step), (b"no_state", b"unavailable"))
        seen.add("no_state")
        s = self.states()
        feed(s, None, 0, "no_sample", "unavailable", 0)
        bad = sample(); bad.subsecond_raw = 1000
        feed(s, bad, 0, "invalid_sample", "unavailable", 0)
        # No anchor wins over fabricated preexisting observation time.
        for state in s:
            state.last_observation_ms = 10000
        feed(s, sample(), 1000, "first_anchor", "first", 0)
        feed(s, sample(), 1500, "repeat_unconfirmed", "repeat", 0)
        feed(s, sample(1), 2000, "advancing", "one_step", 1)
        feed(s, sample(1), 4499, "repeat_confirmed", "repeat", 1)
        # Timeout wins even if the same poll also regresses GPS UTC.
        feed(s, sample(-1), 4500, "timeout", "regress", 0)
        feed(s, sample(), 5500, "advancing", "one_step", 1)
        feed(s, sample(1), 5499, "monotonic_regression", "one_step", 0)
        feed(s, sample(), 5500, "utc_regression", "regress", 0)
        feed(s, sample(1), 5500, "zero_elapsed", "one_step", 0)
        feed(s, sample(6), 6500, "step_tolerance", "jump", 0)
        feed(s, None, 7000, "no_sample", "unavailable", 0)
        feed(s, sample(7), 7500, "first_anchor", "first", 0)
        feed(s, sample(8), 8500, "advancing", "one_step", 1)
        # Per-step agreement may pass while cumulative replay/drift fails.
        s = self.states()
        feed(s, sample(), 0, "first_anchor", "first", 0)
        for i in range(1, 4):
            feed(s, sample(i), i, "advancing", "one_step", 1)
        feed(s, sample(4), 4, "reference_tolerance", "one_step", 0)
        self.assertEqual(seen, REASONS)

    def test_tolerance_boundaries_and_wrap(self):
        # GPS step 4s vs 1000ms: difference3000 passes, 999ms:3001 fails.
        for ms, reason, fresh in ((1000, "advancing", 1), (999, "step_tolerance", 0)):
            states = self.states()
            self.step(states, sample(), 0, "first_anchor", "first", 0)
            self.step(states, sample(4), ms, reason, "jump", fresh)
        # Cumulative difference3000 passes;3001 fails while per-step passes.
        for ms, reason, fresh in ((1000, "advancing", 1), (999, "reference_tolerance", 0)):
            states = self.states()
            self.step(states, sample(), 0)
            for i in range(1, 4):
                self.step(states, sample(i), i * 100)
            self.step(states, sample(4), ms, reason, "one_step", fresh)
        states = self.states()
        self.step(states, sample(), MAX_MS - 2000, "first_anchor", "first", 0)
        self.step(states, sample(1), MAX_MS - 1000, "advancing", "one_step", 1)
        self.step(states, sample(2), MAX_MS, "advancing", "one_step", 1)
        self.step(states, sample(3), 0, "monotonic_regression", "one_step", 0)

    def test_invalid_samples_and_reset_reacquisition(self):
        for field, invalid in (("mask", 0), ("subsecond_raw", 1000),
                               ("utc_seconds", 946684799), ("utc_seconds", 4102444800),
                               ("latitude_deg", float("nan")), ("longitude_deg", 181),
                               ("speed_kmh", -1), ("course_deg", 360)):
            with self.subTest(field=field, invalid=invalid):
                states = self.states()
                self.step(states, sample(), 1000)
                self.step(states, sample(1), 2000, "advancing", "one_step", 1)
                gps = sample(2); setattr(gps, field, invalid)
                self.step(states, gps, 2100, "invalid_sample", "unavailable", 0)
                self.assertEqual(bytes(states[1]), bytes(ctypes.sizeof(Freshness)))
                self.step(states, sample(3), 3000, "first_anchor", "first", 0)
                self.step(states, sample(4), 4000, "advancing", "one_step", 1)

    def test_seeded_sequences_match_frozen_reference(self):
        rng = random.Random(0xD4A2)
        # 100 independent sequences x100 polls =10,000 comparisons per build.
        for _ in range(100):
            states = self.states()
            utc, ms = 0, rng.choice([0, 1000, MAX_MS - 20000])
            for _ in range(100):
                ms = (ms + rng.choice([-3000, -1, 0, 1, 500, 999, 1000, 2499, 2500, 4001])) & MAX_MS
                utc += rng.choice([-5, -1, 0, 0, 1, 1, 2, 4, 10])
                gps = sample(utc)
                fault = rng.randrange(30)
                if fault == 0:
                    gps = None
                elif fault == 1:
                    gps.subsecond_raw = 1000
                elif fault == 2:
                    gps.mask = 0
                self.step(states, gps, ms)


if __name__ == "__main__":
    unittest.main(verbosity=2)
