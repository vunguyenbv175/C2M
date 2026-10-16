#!/usr/bin/env python3
"""Local-only Android ADB public-key encoding and dedicated owner-key preparation.
No USB/network/camera commands. The private RSA key stays on the workstation.
Key creation is EXPLICIT; importing or encoding performs no key generation.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

COMMENT = b"c2m-owner"
ANDROID_BYTES = 524
PUBLIC_PAYLOAD_BYTES = 711


def android_public_key(modulus: int, exponent: int) -> bytes:
    if type(modulus) is not int or modulus.bit_length() != 2048 or not modulus & 1:
        raise ValueError("expected odd RSA2048 modulus")
    if type(exponent) is not int or exponent != 65537:
        raise ValueError("expected exponent65537")
    n0inv = (-pow(modulus & 0xFFFFFFFF, -1, 1 << 32)) & 0xFFFFFFFF
    rr = pow(2, 4096, modulus)
    return (struct.pack("<II", 64, n0inv) + modulus.to_bytes(256, "little") +
            rr.to_bytes(256, "little") + struct.pack("<I", exponent))


def public_payload(modulus: int, exponent: int) -> bytes:
    result = base64.b64encode(android_public_key(modulus, exponent)) + b" " + COMMENT + b"\0"
    assert len(result) == PUBLIC_PAYLOAD_BYTES
    return result


def validate_public_payload(payload: bytes) -> bytes:
    if not isinstance(payload, bytes) or len(payload) != PUBLIC_PAYLOAD_BYTES:
        raise ValueError("bad public payload length")
    if payload[700:] != b" " + COMMENT + b"\0":
        raise ValueError("bad fixed public comment")
    try:
        raw = base64.b64decode(payload[:700], validate=True)
    except Exception:
        raise ValueError("bad public key encoding") from None
    if len(raw) != ANDROID_BYTES or base64.b64encode(raw) != payload[:700]:
        raise ValueError("noncanonical public key")
    modulus = int.from_bytes(raw[8:264], "little")
    exponent = struct.unpack_from("<I", raw, 520)[0]
    if raw != android_public_key(modulus, exponent):
        raise ValueError("bad Android RSA fields")
    return raw


def fingerprint(payload: bytes) -> str:
    # Android's USB-debugging dialog uses MD5 of the 524-byte public struct,
    # NOT the DER/PEM fingerprint. MD5 here is an identifier, not authentication.
    raw = validate_public_payload(payload)
    digest = hashlib.md5(raw, usedforsecurity=False).hexdigest().upper()
    return ":".join(digest[i:i+2] for i in range(0, len(digest), 2))


def parse_rsa_spki(der: bytes) -> tuple[int, int]:
    """Strict minimal DER reader for openssl PUBLIC SPKI output only (<=1KiB)."""
    if not isinstance(der, bytes) or not 32 <= len(der) <= 1024:
        raise ValueError("bad public DER size")

    def item(data, offset, expected):
        if offset+2 > len(data) or data[offset] != expected:
            raise ValueError("bad public DER tag")
        size = data[offset+1]; start = offset+2
        if size & 0x80:
            count = size & 0x7F
            if count not in (1, 2) or start+count > len(data) or data[start] == 0:
                raise ValueError("bad public DER length")
            size = int.from_bytes(data[start:start+count], "big"); start += count
            if size < 128 or (count == 2 and size < 256):
                raise ValueError("nonminimal public DER length")
        end = start+size
        if end > len(data):
            raise ValueError("truncated public DER")
        return data[start:end], end

    seq, end = item(der, 0, 0x30)
    if end != len(der):raise ValueError("extra public DER bytes")
    algorithm, pos = item(seq, 0, 0x30)
    if algorithm != bytes.fromhex("06092a864886f70d0101010500"):
        raise ValueError("not RSA public SPKI")
    bits, pos = item(seq, pos, 0x03)
    if pos != len(seq) or not bits or bits[0] != 0:
        raise ValueError("bad public BIT STRING")
    rsa, end = item(bits[1:], 0, 0x30)
    if end != len(bits)-1:raise ValueError("extra RSA public bytes")
    n, pos = item(rsa, 0, 0x02); e, pos = item(rsa, pos, 0x02)
    if pos != len(rsa) or len(n) != 257 or n[0] != 0 or not n[1] & 0x80:
        raise ValueError("not RSA2048 public integer")
    if e != b"\x01\x00\x01":raise ValueError("not exponent65537")
    return int.from_bytes(n, "big"), int.from_bytes(e, "big")


def prepare_new_key(directory: Path) -> dict:
    """Explicit caller-approved new directory; never reads/dumps private bytes."""
    openssl = shutil.which("openssl")
    if not openssl:raise RuntimeError("OpenSSL unavailable")
    if directory.exists() or directory.is_symlink():
        raise RuntimeError("Refuse existing owner-key directory")
    directory.mkdir(mode=0o700, parents=False)
    if os.name == "nt":
        who = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, check=True, timeout=5).stdout
        import csv
        sid = next(csv.reader([who.strip()]))[1]
        if not sid.startswith("S-1-5-"):raise RuntimeError("Cannot verify owner SID")
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                       capture_output=True, check=True, timeout=5)
    private = directory / "owner_rsa.pem"
    subprocess.run([openssl, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                    "-pkeyopt", "rsa_keygen_pubexp:65537", "-out", str(private)],
                   capture_output=True, check=True, timeout=30)
    if os.name != "nt":private.chmod(0o600)
    # Only PUBLIC DER is returned by this subprocess; private file never copied.
    result = subprocess.run([openssl, "pkey", "-in", str(private), "-pubout", "-outform", "DER"],
                            capture_output=True, check=True, timeout=5)
    n, e = parse_rsa_spki(result.stdout)
    payload = public_payload(n, e); validate_public_payload(payload)
    public = directory / "owner_adb_public_payload.bin"
    with public.open("xb") as f:f.write(payload)
    summary = {"private_key_on_workstation_only": True, "new_dedicated_key": True,
               "private_key_uploaded": False, "adb_ui_md5_fingerprint": fingerprint(payload),
               "public_payload_bytes": len(payload), "public_payload_sha256": hashlib.sha256(payload).hexdigest(),
               "rsa_bits": 2048, "exponent": 65537, "no_device_access": True}
    with (directory / "safe_key_metadata.json").open("x", encoding="utf-8") as f:
        json.dump(summary, f, indent=2); f.write("\n")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--create-new-owner-key", type=Path, required=True)
    a = p.parse_args()
    try:
        report = prepare_new_key(a.create_new_owner_key)
    except Exception:
        print(json.dumps({"status": "error", "reason": "owner key preparation failed; no device accessed"}))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
