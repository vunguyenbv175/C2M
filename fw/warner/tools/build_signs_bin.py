#!/usr/bin/env python3
"""Build the compact signs.bin for c2m-warner.
Usage:
  python3 build_signs_bin.py --demo signs.bin        # 5 demo signs (HCMC)
  python3 build_signs_bin.py --sqlite signs.db signs.bin
Record: double lat, double lon, float heading (-999=unknown),
        char type[16], char label[64] (utf-8, NUL-padded). LE.
"""
import argparse
import sqlite3
import struct
import sys

MAGIC = b"C2MSDB01"
REC = struct.Struct("<ddf16s64s")


def enc(s, n):
    b = s.encode("utf-8")[: n - 1]
    return b + b"\x00" * (n - len(b))


def demo_signs():
    # same scenario as ~/workspace/c2m-gps/demo.py (driving east in HCMC)
    import math

    def dest(lat, lon, brg, d):
        ad = d / 6371000.0
        br = math.radians(brg)
        p1 = math.radians(lat)
        p2 = math.asin(math.sin(p1) * math.cos(ad) + math.cos(p1) * math.sin(ad) * math.cos(br))
        l2 = math.radians(lon) + math.atan2(
            math.sin(br) * math.sin(ad) * math.cos(p1),
            math.cos(ad) - math.sin(p1) * math.sin(p2))
        return math.degrees(p2), ((math.degrees(l2) + 540) % 360) - 180

    lat0, lon0 = 10.7720, 106.6900
    return [
        (*dest(lat0, lon0, 90, 300), 90.0, "P.127", "Biển hạn chế tốc độ tối đa 60"),
        (*dest(lat0, lon0, 90, 500), 90.0, "W.207", "Biển giao nhau với đường không ưu tiên"),
        (*dest(lat0, lon0, 90, -100), 90.0, "P.127", "Biển đã đi qua"),
        (*dest(lat0, lon0, 180, 200), 90.0, "P.131a", "Biển lệch bên"),
        (*dest(lat0, lon0, 90, 300), 270.0, "P.102", "Biển chiều ngược lại"),
    ]


def from_sqlite(path):
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT lat, lon, COALESCE(heading_deg, -999), sign_type, label_vi FROM signs"
    ).fetchall()
    return [(r[0], r[1], r[2] if r[2] is not None else -999.0, r[3], r[4] or r[3])
            for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--sqlite", default=None)
    ap.add_argument("out")
    a = ap.parse_args()
    signs = demo_signs() if a.demo else from_sqlite(a.sqlite)
    with open(a.out, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", len(signs)))
        for lat, lon, hdg, typ, label in signs:
            f.write(REC.pack(lat, lon, float(hdg), enc(typ, 16), enc(label, 64)))
    print(f"wrote {len(signs)} signs -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
