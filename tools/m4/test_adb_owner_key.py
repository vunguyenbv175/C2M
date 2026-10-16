#!/usr/bin/env python3
"""Synthetic local-only RSA public encoding; no key creation, USB or network."""
import base64
import hashlib
import struct
import unittest
from unittest.mock import patch

from adb_owner_key import (android_public_key, fingerprint, parse_rsa_spki,
                           public_payload, validate_public_payload)

# Deliberately synthetic non-prime modulus: never a real private key.
N = (1 << 2047) | (1 << 1025) | 0xF12345AB


def tlv(tag, value):
    size = len(value)
    if size < 128: length = bytes([size])
    elif size < 256: length = b"\x81" + bytes([size])
    else: length = b"\x82" + size.to_bytes(2, "big")
    return bytes([tag]) + length + value


def spki(n=N):
    rsa = tlv(0x30, tlv(2, b"\0" + n.to_bytes(256, "big")) + tlv(2, b"\x01\0\x01"))
    return tlv(0x30, tlv(0x30, bytes.fromhex("06092a864886f70d0101010500")) + tlv(3, b"\0" + rsa))


class OwnerKeyTests(unittest.TestCase):
    def test_android_struct_arithmetic(self):
        raw = android_public_key(N, 65537)
        self.assertEqual(len(raw), 524)
        self.assertEqual(struct.unpack_from("<I", raw)[0], 64)
        inv = struct.unpack_from("<I", raw, 4)[0]
        self.assertEqual((inv * (N & 0xFFFFFFFF)) & 0xFFFFFFFF, 0xFFFFFFFF)
        self.assertEqual(int.from_bytes(raw[8:264], "little"), N)
        self.assertEqual(int.from_bytes(raw[264:520], "little"), pow(2, 4096, N))
        self.assertEqual(struct.unpack_from("<I", raw, 520)[0], 65537)

    def test_fixed_payload_and_md5_identifier(self):
        payload = public_payload(N, 65537)
        self.assertEqual(len(payload), 711)
        self.assertEqual(payload[700:], b" c2m-owner\0")
        raw = validate_public_payload(payload)
        digest = hashlib.md5(raw, usedforsecurity=False).hexdigest().upper()
        self.assertEqual(fingerprint(payload), ":".join(digest[i:i+2] for i in range(0, 32, 2)))

    def test_invalid_modulus_exponent(self):
        for n, e in ((N & ~1, 65537), (1 << 1024 | 1, 65537), (N, 3), (N, True), (True, 65537)):
            with self.assertRaises(ValueError):android_public_key(n, e)

    def test_payload_mutations_fail(self):
        good = public_payload(N, 65537)
        samples = [good[:-1], good+b"x", b"!"+good[1:], good[:-2]+b"X\0"]
        raw = bytearray(validate_public_payload(good))
        for idx in (0, 4, 8, 300, 520):
            bad = bytearray(raw); bad[idx] ^= 1
            samples.append(base64.b64encode(bad)+b" c2m-owner\0")
        for bad in samples:
            with self.assertRaises(ValueError):validate_public_payload(bad)

    def test_strict_public_der(self):
        self.assertEqual(parse_rsa_spki(spki()), (N, 65537))
        for bad in (spki()[:-1], spki()+b"x", b"\0"+spki()[1:], spki().replace(b"\x01\0\x01", b"\x01\0\x03")):
            with self.assertRaises(ValueError):parse_rsa_spki(bad)

    def test_no_side_effects_on_encode(self):
        with patch("subprocess.run", side_effect=AssertionError("no subprocess during encoding")):
            payload = public_payload(N, 65537)
            self.assertEqual(validate_public_payload(payload), android_public_key(N, 65537))
            self.assertTrue(fingerprint(payload))


if __name__ == "__main__":
    unittest.main()
