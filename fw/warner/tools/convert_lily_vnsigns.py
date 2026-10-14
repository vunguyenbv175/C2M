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
import argparse
import gzip
import json
import glob
import os

from build_signs_bin import write_signs


TYPE_MAP = {
    "r420": ("R.420", "Biển R.420 bắt đầu khu đông dân cư"),
    "r421": ("R.421", "Biển R.421 hết khu đông dân cư"),
    "limit": ("P.127", None),
    "p125": ("P.125", "Biển P.125 cấm vượt"),
    "p130": ("P.130", "Biển P.130 cấm dừng đỗ"),
    "p131a": ("P.131a", "Biển P.131a cấm đỗ"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_dir")
    ap.add_argument("out")
    args = ap.parse_args()
    src_dir, out = args.source_dir, args.out
    recs = []
    for f in sorted(glob.glob(os.path.join(src_dir, "*_pins.bin"))):
        with open(f, "rb") as stream:
            pins = json.loads(gzip.decompress(stream.read()))
        for p in pins:
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
    count = write_signs(recs, out)
    print(f"wrote {count} records to {out}")


if __name__ == "__main__":
    main()
