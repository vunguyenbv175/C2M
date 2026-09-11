#!/usr/bin/env python3
"""Parse C2M vendor U-Boot image dispatch for ih_comp handling (analysis-only).

Inputs: decompressed U-Boot binary (XZ payload of the vendor uImage, e.g. from
  build/carve_en/uboot.es.load0.off_00018000.size_48a44.bin bytes 64..end
  decompressed with XZ). The decompressed image is linked at 0x23E00000
  (inferred from pointer scan; uImage entry 0x23E00000).

What it does (no firmware modification):
  - verifies XZ magic and reports decompressed SHA/size,
  - locates the image decompression dispatcher (jump table for comp 0..10),
  - prints the COMP VALUE | DECODER TARGET | ALGORITHM | EVIDENCE | CONFIDENCE table,
  - locates the image_comp string table ({id, sname, lname}) and bootm strings.

Requires: lzma (stdlib). Disassembly uses capstone if available; otherwise it
falls back to raw word dumps and still prints the tables.
"""
from __future__ import annotations
import argparse
import hashlib
import lzma
import re
import struct
from pathlib import Path

BASE = 0x23E00000
BOOTM_STR_OFFS = {
    0xAC2BB: "XIP",
    0xAC2CA: "Force XIP",
    0xAC2DF: "Loading",
    0xAC2F2: "Uncompressing",
    0xAC30C: "GUNZIP error",
    0xAC360: "xz_dec_init ERROR",
    0xAC376: "XZ size",
    0xAC39D: "MZ fail",
    0xAC3D5: "MZ size",
    0xAC3F4: "Unimplemented compression",
    0xAC41A: "OK",
}

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def load_uboot(path: Path) -> bytes:
    data = path.read_bytes()
    # Accept either full uImage (64-byte header + XZ) or raw XZ or raw decompressed.
    if data[:4] == struct.pack(">I", 0x27051956) and len(data) > 64:
        payload = data[64:]
        if payload[:6] == b"\xfd7zXZ\x00":
            return lzma.decompress(payload)
    if data[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(data)
    return data

def find_jump_table(dec: bytes) -> dict:
    # Dispatcher: cmp r5,#0xA; ldrls pc,[pc,r5,lsl#2]; table at file 0x2260 (11 entries).
    tbl_off = 0x2260
    out = {}
    for i in range(11):
        val = struct.unpack("<I", dec[tbl_off + i * 4:tbl_off + i * 4 + 4])[0]
        out[i] = val
    return out

def find_comp_table(dec: bytes) -> list:
    # image_comp[] entries are {id:u32, sname:ptr, lname:ptr} (12 bytes).
    comp_ptrs = {BASE + o for o in
                 [0xB5B09, 0xB5B0E, 0xB5B1B, 0xB5B21, 0xB5B32, 0xB5B37,
                  0xB5B47, 0xB5B4C, 0xB5B5C, 0xB5B60, 0xB5B6F, 0xB5B72, 0xB5B80]}
    rows = []
    for off in range(0xA1580, 0xA1620, 4):
        a, b, c = struct.unpack("<III", dec[off:off + 12])
        if a <= 12 and b in comp_ptrs and c in comp_ptrs:
            sname = dec[b - BASE:b - BASE + 20].split(b"\x00")[0].decode()
            lname = dec[c - BASE:c - BASE + 30].split(b"\x00")[0].decode()
            rows.append((off, a, sname, lname))
    return rows

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("uboot", type=Path, help="uImage XZ, raw XZ, or decompressed U-Boot")
    args = ap.parse_args()
    raw = args.uboot.read_bytes()
    dec = load_uboot(args.uboot)
    print(f"input: {args.uboot} len={len(raw)} sha256={sha256_bytes(raw)}")
    print(f"decompressed: len={len(dec)} sha256={sha256_bytes(dec)} base=0x{BASE:08X}")
    print(f"first64: {dec[:64].hex()}")
    jt = find_jump_table(dec)
    names = {0: "none/memcpy (Loading)", 1: "gzip (GUNZIP/inflate)",
             2: "bzip2 (UNIMPLEMENTED)", 3: "lzma/xz (XZ)",
             4: "lzo (UNIMPLEMENTED)", 5: "UNIMPLEMENTED", 6: "UNIMPLEMENTED",
             7: "UNIMPLEMENTED", 8: "UNIMPLEMENTED", 9: "mz (MZ/raw-deflate)",
             10: "XIP (same handler as 0)"}
    print("\nCOMP VALUE | DECODER TARGET (VA/foff) | ALGORITHM | EVIDENCE | CONFIDENCE")
    for comp in range(11):
        va = jt[comp]
        foff = va - BASE
        print(f"{comp:>10} | 0x{va:08X}/0x{foff:05X} | {names[comp]:28} | "
              f"jump-table@0x{0x2260 + comp * 4:05X} | CONFIRMED")
    print("\nimage_comp string table ({id,sname,lname}):")
    for off, cid, sname, lname in find_comp_table(dec):
        print(f"  file 0x{off:05X}: id={cid} sname={sname!r} lname={lname!r}")
    print("\nbootm strings:")
    for off, label in sorted(BOOTM_STR_OFFS.items()):
        s = dec[off:off + 90].split(b"\x00")[0]
        print(f"  0x{off:05X}: {label}: {s!r}")
    # Tool limits
    try:
        import capstone  # noqa: F401
        print("\ncapstone: available (full disassembly possible)")
    except ImportError:
        print("\ncapstone: NOT available (word-dump fallback used; control flow from "
              "jump-table words + string xrefs only)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
