#!/usr/bin/env python3
"""Extract appended FDT (DTB) from a decompressed C2M kernel image.

The vendor kernel embeds one valid FDT at file offset 0x389D20 (totalsize
0xC5E4, version 17) in both EN and VI builds. This tool scans for the FDT
magic 0xD00DFEED, validates the header (totalsize bounds, version), and
writes each candidate. No firmware is modified.

Usage:
  python tools/fw/extract_appended_dtb.py <raw_kernel> -o <out_dir>
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path

FDT_MAGIC = 0xD00DFEED

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def find_fdts(data: bytes) -> list:
    out = []
    pos = 0
    magic_be = struct.pack(">I", FDT_MAGIC)
    while True:
        j = data.find(magic_be, pos)
        if j < 0:
            break
        if j + 40 <= len(data):
            try:
                magic, totalsize, off_struct, off_strings, off_rsv, ver, compver, \
                    bootcpuid, sz_strings, sz_struct = struct.unpack(">10I", data[j:j + 40])
            except struct.error:
                pos = j + 1
                continue
            if magic == FDT_MAGIC and 40 <= totalsize <= len(data) - j and ver >= 16:
                # Basic sanity: struct/strings offsets inside totalsize.
                if off_struct < totalsize and off_strings < totalsize:
                    out.append((j, totalsize, ver))
        pos = j + 1
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kernel", type=Path, help="decompressed kernel raw file")
    ap.add_argument("-o", "--output", type=Path, required=True, help="output directory")
    args = ap.parse_args()
    data = args.kernel.read_bytes()
    cands = find_fdts(data)
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"input: {args.kernel} len={len(data)} sha256={sha256_bytes(data)}")
    print(f"candidates: {len(cands)}")
    for idx, (off, size, ver) in enumerate(cands):
        blob = data[off:off + size]
        # Re-validate magic + totalsize.
        magic = struct.unpack(">I", blob[:4])[0]
        assert magic == FDT_MAGIC
        outp = args.output / f"dtb.{idx}.off_{off:06x}.size_{size:x}.dtb"
        outp.write_bytes(blob)
        print(f"  [{idx}] off=0x{off:06X} size=0x{size:X} ({size}) ver={ver} "
              f"sha256={sha256_bytes(blob)} -> {outp.name}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
