#!/usr/bin/env python3
"""Synthetic DB generation/filter guards; never uses owner data or devices."""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from build_signs_bin import enc, write_signs
from inspect_signs_bin import inspect, RECORD


class SignToolsTests(unittest.TestCase):
    def test_utf8_boundary(self):
        encoded = enc("Biển báo tiếng Việt " * 10, 64)
        self.assertEqual(len(encoded), 64)
        encoded.split(b"\0", 1)[0].decode("utf-8", "strict")
        with self.assertRaises(ValueError):
            enc("label\ncommand", 64)

    def test_determinism_and_inspection(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rows = [(10.1, 106.1, 90, "R.420", "Biển R.420 bắt đầu khu đông dân cư"),
                    (10, 106, -999, "P.127", "Biển hạn chế tốc độ tối đa 60 km/h"),
                    (10.2, 106.2, 360, "R.421", "Biển R.421 hết khu đông dân cư")]
            write_signs(rows, tmp / "a.bin")
            write_signs(list(reversed(rows)), tmp / "b.bin")
            self.assertEqual((tmp / "a.bin").read_bytes(), (tmp / "b.bin").read_bytes())
            original, eligible, report = inspect((tmp / "a.bin").read_bytes())
            self.assertEqual(len(original), 3)
            self.assertEqual(len(eligible), 2)
            self.assertEqual(report["exclusions"], {"unknown_application_heading": 1})
            self.assertTrue(any(row[2] == 0 for row in original))
            self.assertNotIn('106.1', str(report))

    def test_bad_source_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "db.bin"
            out.write_bytes(b"keep-original")
            for row in [(float('nan'), 106, 90, "R.420", "test"),
                        (91, 106, 90, "R.420", "test"),
                        (10, 106, float('inf'), "R.420", "test"),
                        (10, 106, 90, "", "test")]:
                with self.assertRaises(ValueError):
                    write_signs([row], out)
                self.assertEqual(out.read_bytes(), b"keep-original")
            with self.assertRaises(ValueError):
                write_signs([], out)

    def test_integrity_and_unreviewed_speed(self):
        header = b'C2MSDB01' + struct.pack('<I', 1)
        row = RECORD.pack(10, 106, 90, enc('P.127', 16), enc('Biển hạn chế tốc độ tối đa 87 km/h', 64))
        _, eligible, report = inspect(header + row)
        self.assertEqual(eligible, [])
        self.assertEqual(report['exclusions'], {'unreviewed_speed_value': 1})
        for invalid in (header, header + row + b'extra', b'BADMAGIC' + header[8:] + row):
            with self.assertRaises(ValueError):
                inspect(invalid)
        corrupted = RECORD.pack(10, 106, 90, b'R.420\0'.ljust(16, b'\0'), b'\xff\0'.ljust(64, b'\0'))
        with self.assertRaises(ValueError):
            inspect(header + corrupted)


if __name__ == '__main__':
    unittest.main()
