#!/usr/bin/env python3
"""Pure package preflight tests; no ARM execution, vault, camera or keys."""
from pathlib import Path
import struct
import tempfile
import unittest

from package_ram_debug import checked_elf


def header():
    b = bytearray(64)
    b[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<H", b, 16, 2)
    struct.pack_into("<H", b, 18, 40)
    return b


class PackagePreflightTests(unittest.TestCase):
    def test_header_arch_endian_class_type_and_size_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="c2m-ram-package-") as name:
            path = Path(name) / "binary"
            valid = header()
            path.write_bytes(valid)
            self.assertEqual(checked_elf(path), valid)
            variants = [b"", b"MZ" + bytes(100), bytes(valid[:51])]
            for offset, value in ((4, 2), (5, 2), (16, 3), (18, 62)):
                mutated = bytearray(valid)
                mutated[offset] = value
                variants.append(mutated)
            for blob in variants:
                with self.subTest(blob_length=len(blob)):
                    path.write_bytes(blob)
                    with self.assertRaises(ValueError):
                        checked_elf(path)
            with self.assertRaises(ValueError):
                checked_elf(Path(name))
            with self.assertRaises(ValueError):
                checked_elf(Path(name) / "absent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
