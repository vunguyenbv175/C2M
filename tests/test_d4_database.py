#!/usr/bin/env python3
"""Synthetic private-DB subset gates; no real source/data/card/device access."""
from __future__ import annotations
import hashlib
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("d4_database", ROOT / "fw/d4/prepare_database.py")
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


def record(heading=90.0, typ="R.420", lat=10.0, lon=106.0):
    return db.RECORD.pack(lat, lon, heading, typ.encode().ljust(16, b"\0"), b"fixture\0".ljust(64,b"\0"))


def blob(*rows):
    return db.MAGIC + struct.pack("<I", len(rows)) + b"".join(rows)


class DatabaseTests(unittest.TestCase):
    def prepare(self, data):
        return db.prepare(data, hashlib.sha256(data).hexdigest())

    def test_only_directional_area_signs_no_numeric_speed(self):
        data = blob(record(), record(270,"R.421"), record(-999,"P.127"),
                    record(90,"P.127"), record(-999), record(360,"R.421"))
        out, report = self.prepare(data)
        self.assertEqual(report["output_records"], 3)
        self.assertEqual(report["numeric_speed_limit_records_deployed"], 0)
        self.assertEqual(report["unknown_application_heading_excluded"], 2)
        self.assertEqual(report["output_type_counts"], {"R.420": 1, "R.421": 2})
        self.assertEqual(len(out), 312)
        self.assertEqual(db.RECORD.unpack_from(out, 212)[2], 0)
        text = str(report)
        self.assertNotIn("fixture", text)
        self.assertNotIn("latitude", text)

    def test_pin_and_exact_header_count(self):
        data=blob(record())
        for pin in ("", "g"*64, "0"*64):
            with self.assertRaises(ValueError): db.prepare(data,pin)
        for value in (b"", data[:-1],data+b"x",b"BADMAGIC"+data[8:],db.MAGIC+struct.pack("<I",0),
                      db.MAGIC+struct.pack("<I",40001)):
            with self.assertRaises(ValueError): self.prepare(value)

    def test_bad_rows_and_zero_eligible_are_blocked(self):
        for row in (record(float("nan")),record(361),record(-1),record(lat=91),
                    record(lon=float("inf")),record(typ=""),record(typ="R.4\n"),
                    record(-999),record(90,"P.127")):
            with self.assertRaises(ValueError): self.prepare(blob(row))
        raw=bytearray(record()); raw[35]=1
        with self.assertRaises(ValueError): self.prepare(blob(bytes(raw)))
        raw=bytearray(record()); raw[36:100]=b"x"*64
        with self.assertRaises(ValueError): self.prepare(blob(bytes(raw)))


if __name__=="__main__":unittest.main(verbosity=2)
