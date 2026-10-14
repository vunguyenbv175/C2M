#!/usr/bin/env python3
"""Synthetic host-only guards for TSR config inspection/staging."""
import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tsr_profile import apply_profile, decode_source, inspect

ROOT = Path(__file__).resolve().parents[2]


class TsrProfileTests(unittest.TestCase):
    def setUp(self):
        self.stock = (b"# --enable_tsr=false (comment must remain)\n"
                      b"--enable_vehicle=true\n"
                      b"  --enable_tsr=false  \n"
                      b"--tsrw_interval=0\n"
                      b"--tsrw_sli_speed_min_thresh=0\n"
                      b"--tsrw_sli_speed_max_thresh=200\n"
                      b"--unrelated=private-value\n")

    def test_narrow_change_and_idempotency(self):
        output, report = apply_profile(self.stock, {"enable_tsr": "true", "tsrw_interval": "5"})
        expected = self.stock.replace(b"  --enable_tsr=false  \n", b"  --enable_tsr=true  \n").replace(
            b"--tsrw_interval=0\n", b"--tsrw_interval=5\n")
        self.assertEqual(output, expected)
        self.assertEqual(report["verdict"], "HOST_STAGED_ONLY")
        self.assertTrue(report["outside_authorized_keys_unchanged"])
        self.assertNotIn("private-value", json.dumps(report))
        repeated, second = apply_profile(output, {"enable_tsr": "true", "tsrw_interval": "5"})
        self.assertEqual(output, repeated)
        self.assertEqual(second["changes"], [])

    def test_strict_base64(self):
        self.assertEqual(decode_source(base64.encodebytes(self.stock), True), self.stock)
        for bad in (b"%%invalid", base64.b64encode(self.stock)[:-1], b"", b"Zg==junk"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    decode_source(bad, True)

    def test_bad_decoded(self):
        for bad in (b"", self.stock[:-1], self.stock.replace(b"\n", b"\r\n"),
                    self.stock + b"\0\n", b"\xff\n"):
            with self.assertRaises(ValueError):
                decode_source(bad, False)

    def test_absent_duplicate_comment_and_unrelated(self):
        with self.assertRaises(ValueError):
            apply_profile(self.stock, {"tsrw_sli_over_min_thresh": "5"})
        with self.assertRaises(ValueError):
            apply_profile(self.stock, {"enable_vehicle": "false"})
        for suffix in (b"--enable_tsr=true\n", b"--enable_tsr=false #inline\n",
                       b"--enable_tsr false\n", b"--enable_tsr=TRUE\n"):
            with self.assertRaises(ValueError):
                inspect(self.stock + suffix)
        self.assertEqual(inspect(b"# --enable_tsr=true\n"), {})

    def test_invalid_numbers_and_minmax(self):
        for value in ("nan", "inf", "-1", "1e300", "3601", "5\n--other=true"):
            with self.assertRaises(ValueError):
                apply_profile(self.stock, {"tsrw_interval": value})
        with self.assertRaises(ValueError):
            apply_profile(self.stock, {"tsrw_sli_speed_min_thresh": "100",
                                       "tsrw_sli_speed_max_thresh": "50"})
        with self.assertRaises(ValueError):
            apply_profile(self.stock, {"enable_tsr": True})

    def test_private_staging_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="tsr-profile-") as td:
            tmp = Path(td)
            source, profile, out = tmp / "source", tmp / "profile.json", tmp / "staged"
            source.write_bytes(base64.encodebytes(self.stock))
            profile.write_text(json.dumps({"enable_tsr": "true"}), encoding="utf-8")
            command = [sys.executable, str(ROOT / "tools/fw/tsr_profile.py"),
                       "--source", str(source), "--encoded", "--profile", str(profile), "--out-dir", str(out)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertNotIn("private-value", run.stdout + run.stderr)
            decoded = (out / "adas_de.flag").read_bytes()
            self.assertEqual(base64.b64decode((out / "adas.flag").read_bytes()), decoded)
            snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(snapshot, {p.name: p.read_bytes() for p in out.iterdir()})
            self.assertEqual(source.read_bytes(), base64.encodebytes(self.stock))


if __name__ == "__main__":
    unittest.main()
