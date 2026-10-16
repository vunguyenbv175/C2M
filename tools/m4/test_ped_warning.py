#!/usr/bin/env python3
"""Offline unit tests for pedWarning schema extension (no hardware/network/git).

Validates tools/m4/libflow_protocol.py pedWarning support:
- valid bool envelopes pass with no warnings
- missing/extra strict
- non-bool (int 0/1 included) warns, list/non-dict warns
- arbitrary bad key types do not raise
- replay_guard default-deny still blocks pedWarning (no policy change,
  no warning numeric derivation).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import msgpack

sys.path.insert(0, str(Path(__file__).resolve().parent))
from libflow_protocol import (
    KNOWN_KEYS,
    KNOWN_TOPICS,
    SCHEMA_FIELD_KINDS,
    SCHEMAS,
    decode_ws_binary,
)
from replay_guard import classify_inner_key, guard_replay


_SENTINEL = object()


def envelope(topic="ped", key="pedWarning", body=_SENTINEL, fid=1, t=2):
    if body is _SENTINEL:
        body = {"ped_on": False, "pcw_on": False}
    inner = {"frame_id": fid, "time": t, "key": key, "data": body}
    outer = {
        "time": t,
        "source": "AdasScreenService",
        "topic": topic,
        "data": msgpack.packb(inner, use_bin_type=True),
    }
    return msgpack.packb(outer, use_bin_type=True)


class PedWarningTests(unittest.TestCase):
    def test_known_and_schema(self):
        self.assertIn("pedWarning", KNOWN_KEYS)
        self.assertIn("pedWarning", SCHEMAS)
        self.assertEqual(SCHEMAS["pedWarning"], {"ped_on", "pcw_on"})
        self.assertEqual(
            SCHEMA_FIELD_KINDS.get("pedWarning"),
            {"ped_on": "bool", "pcw_on": "bool"},
        )
        self.assertIn("ped", KNOWN_TOPICS)

    def test_valid_bools(self):
        for body in (
            {"ped_on": False, "pcw_on": False},
            {"ped_on": True, "pcw_on": False},
            {"ped_on": False, "pcw_on": True},
            {"ped_on": True, "pcw_on": True},
        ):
            r = decode_ws_binary(envelope(body=dict(body)))
            self.assertEqual(r.inner["key"], "pedWarning")
            self.assertEqual(r.inner["data"], body)
            self.assertEqual(r.warnings, [], r.warnings)

    def test_missing(self):
        r = decode_ws_binary(envelope(body={"ped_on": True}))
        self.assertTrue(any("missing" in w for w in r.warnings), r.warnings)
        self.assertTrue(any("pcw_on" in w for w in r.warnings), r.warnings)

    def test_extra(self):
        r = decode_ws_binary(
            envelope(body={"ped_on": True, "pcw_on": False, "zz_extra": True})
        )
        self.assertTrue(any("extra" in w for w in r.warnings), r.warnings)

    def test_nonbool_rejected(self):
        # int 0/1 are NOT bool and must warn; str/None/float also warn.
        for bad in (0, 1, 2, "x", None, 0.0, 1.5):
            r = decode_ws_binary(
                envelope(body={"ped_on": bad, "pcw_on": False})
            )
            self.assertTrue(
                any("not bool" in w for w in r.warnings),
                (bad, r.warnings),
            )
            r2 = decode_ws_binary(
                envelope(body={"ped_on": False, "pcw_on": bad})
            )
            self.assertTrue(
                any("not bool" in w for w in r2.warnings),
                (bad, r2.warnings),
            )

    def test_wrong_body_kind(self):
        for bad_body in ([], [{"ped_on": True, "pcw_on": False}], None, 0, "x"):
            r = decode_ws_binary(envelope(body=bad_body))
            self.assertTrue(
                any("not a dict" in w for w in r.warnings),
                (bad_body, r.warnings),
            )

    def test_unknown_key_no_traceback(self):
        r = decode_ws_binary(envelope(key="evil_vendor_key_xyz", body={"a": 1}))
        self.assertTrue(
            any(w.startswith("unknown inner key:") for w in r.warnings),
            r.warnings,
        )
        # Arbitrary bad key types must not raise.
        for bad_key in (123, ["x"], {"y": 1}, None):
            inner = {"frame_id": 1, "time": 2, "key": bad_key, "data": {}}
            outer = {
                "time": 2,
                "source": "s",
                "topic": "ped",
                "data": msgpack.packb(inner, use_bin_type=True),
            }
            blob = msgpack.packb(outer, use_bin_type=True)
            try:
                res = decode_ws_binary(blob)
            except Exception as e:  # noqa: BLE001 - must not raise
                self.fail(f"decode raised on bad key {bad_key!r}: {e!r}")
            self.assertIsInstance(res.warnings, list)

    def test_replay_guard_default_deny(self):
        # pedWarning is decodable but NEVER L2 replayable; default-deny holds
        # without touching m4_policy.json and without deriving warning values.
        self.assertEqual(classify_inner_key("pedWarning"), "DENY")
        self.assertEqual(classify_inner_key("vehicleWarning"), "DENY")
        self.assertEqual(classify_inner_key("anything_unknown_xyz"), "DENY")
        ok, blocked = guard_replay([{"key": "pedWarning"}])
        self.assertEqual(ok, [])
        self.assertEqual(len(blocked), 1)
        ok2, blocked2 = guard_replay(
            [{"key": "pedWarning"}, {"key": "vehicleWarning"}]
        )
        self.assertEqual(ok2, [])
        self.assertEqual(len(blocked2), 2)


if __name__ == "__main__":
    unittest.main()
