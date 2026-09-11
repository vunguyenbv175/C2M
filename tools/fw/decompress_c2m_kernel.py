#!/usr/bin/env python3
"""Fail-closed decompressor for C2M vendor U-Boot ih_comp=9 (mz) kernel images.

Vendor kernels are uImage (magic 0x27051956) with ih_comp=9 ("mz compressed").
Empirically the payload is a raw DEFLATE stream (zlib wbits=-15, no gzip/zlib
header or trailer). This tool verifies the header and CRCs before decoding and
never silently falls back to another codec.

Usage:
  python tools/fw/decompress_c2m_kernel.py <input_uimage> -o <output_raw>
"""
from __future__ import annotations
import argparse
import binascii
import hashlib
import struct
import sys
import zlib
from pathlib import Path

UIMAGE_MAGIC = 0x27051956
UIMAGE_FMT = ">IIIIIIIBBBB32s"
UIMAGE_HDR_LEN = 64
EXPECTED_COMP = 9

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def parse_header(data: bytes) -> dict:
    if len(data) < UIMAGE_HDR_LEN:
        raise ValueError(f"input too short ({len(data)} < 64)")
    magic, hcrc, ts, size, load, entry, dcrc, os_, arch, ftype, comp, name = struct.unpack(
        UIMAGE_FMT, data[:UIMAGE_HDR_LEN])
    if magic != UIMAGE_MAGIC:
        raise ValueError(f"bad uImage magic 0x{magic:08X}, want 0x{UIMAGE_MAGIC:08X}")
    hdr_zero = struct.pack(UIMAGE_FMT, magic, 0, ts, size, load, entry, dcrc,
                           os_, arch, ftype, comp, name)
    calc_hcrc = binascii.crc32(hdr_zero) & 0xFFFFFFFF
    if calc_hcrc != hcrc:
        raise ValueError(f"header CRC mismatch stored=0x{hcrc:08X} calc=0x{calc_hcrc:08X}")
    payload = data[UIMAGE_HDR_LEN:]
    if len(payload) != size:
        raise ValueError(f"payload length {len(payload)} != header size {size}")
    calc_dcrc = binascii.crc32(payload) & 0xFFFFFFFF
    if calc_dcrc != dcrc:
        raise ValueError(f"data CRC mismatch stored=0x{dcrc:08X} calc=0x{calc_dcrc:08X}")
    if comp != EXPECTED_COMP:
        raise ValueError(f"ih_comp={comp}, this tool only handles comp==9 (mz)")
    return {"magic": magic, "hcrc": hcrc, "size": size, "load": load,
            "entry": entry, "dcrc": dcrc, "os": os_, "arch": arch,
            "type": ftype, "comp": comp, "name": name, "payload": payload}

def decompress_mz(payload: bytes) -> bytes:
    # Raw DEFLATE only. No fallback: any other codec must fail closed.
    co = zlib.decompressobj(-15)
    out = co.decompress(payload)
    # Must consume entire input and hit end-of-stream with no trailing bytes.
    if not co.eof:
        raise ValueError("raw-deflate stream did not reach end-of-stream (truncated?)")
    if co.unused_data:
        raise ValueError(f"raw-deflate left {len(co.unused_data)} unused trailing bytes")
    if co.unconsumed_tail:
        raise ValueError("raw-deflate left unconsumed tail")
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description="Decompress C2M ih_comp=9 kernel (fail-closed).")
    ap.add_argument("input", type=Path, help="uImage kernel file (with 64-byte header)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="raw decompressed output")
    args = ap.parse_args()
    data = args.input.read_bytes()
    hdr = parse_header(data)
    payload = hdr["payload"]
    out = decompress_mz(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    print(f"input: {args.input} size={len(data)} sha256={sha256_bytes(data)}")
    print(f"payload: size={len(payload)} sha256={sha256_bytes(payload)}")
    print(f"header: magic=0x{hdr['magic']:08X} load=0x{hdr['load']:08X} "
          f"entry=0x{hdr['entry']:08X} comp={hdr['comp']} name={hdr['name']!r}")
    print(f"output: {args.output} size={len(out)} sha256={sha256_bytes(out)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
