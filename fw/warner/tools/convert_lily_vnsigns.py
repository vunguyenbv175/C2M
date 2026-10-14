#!/usr/bin/env python3
"""Convert Lily APK (com.sensornotes.xiaozhi) vnsigns assets to signs_vn.bin.

The Lily app bundles an offline Vietnamese traffic-sign database in
assets/vnsigns/: gzip-compressed JSON files named {lat5}_{lon5}_pins.bin
on a 0.5-degree grid. Each pin: {"y":lat,"g":lon,"t":type,"v":value,
"b":bearing,"u":heading}.

Usage:
  1. Extract assets/vnsigns/ from the Lily APK (XAPK -> APK -> assets).
  2. python3 convert_lily_vnsigns.py /path/to/vnsigns/ signs_vn.bin

Output: C2MSDB01 signs.bin (see build_signs_bin.py for the record format).
"""
import gzip
import json
import glob
import os
import struct
import sys

MAGIC = b"C2MSDB01"
REC = struct.Struct("<ddf16s64s")


def enc(s, n):
    b = s.encode("utf-8")[: n - 1]
    return b + b"\x00" * (n - len(b))


TYPE_MAP = {
    "r420": ("R.420", "Biển R.420 bắt đầu khu đông dân cư"),
    "r421": ("R.421", "Biển R.421 hết khu đông dân cư"),
    "limit": ("P.127", None),
    "p125": ("P.125", "Biển P.125 cấm vượt"),
    "p130": ("P.130", "Biển P.130 cấm dừng đỗ"),
    "p131a": ("P.131a", "Biển P.131a cấm đỗ"),
}


def main():
    src_dir, out = sys.argv[1], sys.argv[2]
    recs = []
    for f in glob.glob(os.path.join(src_dir, "*_pins.bin")):
        for p in json.loads(gzip.decompress(open(f, "rb").read())):
            t = p.get("t", "?")
            if t not in TYPE_MAP:
                continue
            code, label = TYPE_MAP[t]
            if t == "limit":
                label = f"Biển hạn chế tốc độ tối đa {p.get('v', 0)} km/h"
            heading = float(p.get("u", -1))
            if heading < 0:
                heading = -999.0
            recs.append((p["y"], p["g"], heading, code, label))
    with open(out, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<I", len(recs)))
        for lat, lon, hdg, code, label in recs:
            fh.write(REC.pack(lat, lon, hdg, enc(code, 16), enc(label, 64)))
    print(f"wrote {len(recs)} records to {out}")


if __name__ == "__main__":
    main()
