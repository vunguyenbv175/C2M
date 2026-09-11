#!/usr/bin/env python3
"""Derive UBIFS geometry from the image superblock (read-only, no guessing).

Parses UBIFS_SB_NODE (type 6) at image offset 0 with the vendor field map
proven in Sprint 2 (min_io@32, leb_size@36, leb_cnt@40 — leb_cnt*leb_size
must equal the image size exactly, else FAIL).

Outputs JSON + the exact mkfs.ubifs invocation for a no-op rebuild.

Usage:
  python3 tools/fw/ubifs_geometry.py <image.ubifs> [-o geometry.json]
"""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path

COMPR = {0: "none", 1: "lzo", 2: "zlib", 3: "zstd"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    d = args.image.read_bytes()
    magic, _crc, _sq, nlen, ntype, _grp = struct.unpack_from("<IIQIBB", d, 0)
    if magic != 0x06101831 or ntype != 6:
        raise SystemExit(f"geometry: no UBIFS superblock at offset 0 "
                         f"(magic={hex(magic)} type={ntype})")
    min_io, leb_size, leb_cnt, max_leb = struct.unpack_from("<IIII", d, 32)
    max_bud, log_lebs, lpt_lebs, orph_lebs = struct.unpack_from("<QIII", d, 48)
    jhead, fanout, lsave, fmt = struct.unpack_from("<IIII", d, 68)
    compr = struct.unpack_from("<H", d, 84)[0]
    geo = {"min_io_size": min_io, "leb_size": leb_size, "leb_cnt": leb_cnt,
           "max_leb_cnt": max_leb, "max_bud_bytes": max_bud,
           "log_lebs": log_lebs, "lpt_lebs": lpt_lebs, "orph_lebs": orph_lebs,
           "jhead_cnt": jhead, "fanout": fanout, "lsave_cnt": lsave,
           "fmt_version": fmt, "default_compr": compr,
           "default_compr_name": COMPR.get(compr, f"UNKNOWN-{compr}"),
           "image_bytes": len(d),
           "leb_cnt_times_leb_size": leb_cnt * leb_size}
    if geo["leb_cnt_times_leb_size"] != len(d):
        raise SystemExit(f"geometry: leb_cnt*leb_size={geo['leb_cnt_times_leb_size']} "
                         f"!= image {len(d)} — refusing to guess geometry")
    if compr not in COMPR:
        raise SystemExit(f"geometry: unknown default compressor {compr}")
    geo["mkfs_ubifs_args"] = ["mkfs.ubifs", "-m", str(min_io), "-e", str(leb_size),
                              "-c", str(max_leb), "-x", COMPR[compr],
                              "-r", "<tree>", "-o", "<out.ubifs>"]
    if args.output:
        args.output.write_text(json.dumps(geo, indent=2), encoding="utf-8")
    print(json.dumps(geo, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
