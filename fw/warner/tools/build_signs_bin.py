#!/usr/bin/env python3
"""Build the compact signs.bin for c2m-warner.
Usage:
  python3 build_signs_bin.py --demo signs.bin        # 5 demo signs (HCMC)
  python3 build_signs_bin.py --sqlite signs.db signs.bin
Record: double lat, double lon, float heading (-999=unknown),
        char type[16], char label[64] (utf-8, NUL-padded). LE.
"""
import argparse
import math
import os
import sqlite3
import struct
import sys
import tempfile

MAGIC = b"C2MSDB01"
REC = struct.Struct("<ddf16s64s")


def enc(s, n):
    if not isinstance(s, str) or any(ord(c) < 32 or ord(c) == 127 for c in s):
        raise ValueError("invalid database string")
    # Trim on a UTF-8 character boundary, not in the middle of a codepoint.
    b = s.encode("utf-8")[: n - 1].decode("utf-8", "ignore").encode("utf-8")
    return b + b"\x00" * (n - len(b))


def write_signs(signs, out):
    from pathlib import Path
    rows = []
    for lat, lon, heading, typ, label in signs:
        if not all(math.isfinite(float(v)) for v in (lat, lon, heading)):
            raise ValueError("nonfinite coordinates/heading")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("coordinates outside range")
        if heading != -999 and not 0 <= heading <= 360:
            raise ValueError("invalid heading")
        if not typ:
            raise ValueError("empty sign type")
        rows.append((lat, lon, 0 if heading == 360 else heading, typ, label))
    if not 0 < len(rows) <= 40000:
        raise ValueError("database count outside deployment bound")
    rows.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[4]))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=out.name + ".", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(MAGIC + struct.pack("<I", len(rows)))
            for lat, lon, hdg, typ, label in rows:
                stream.write(REC.pack(lat, lon, float(hdg), enc(typ, 16), enc(label, 64)))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, out)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return len(rows)


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
    if not path:
        raise ValueError("exactly one source is required: --demo or --sqlite")
    con = sqlite3.connect("file:" + os.path.abspath(path) + "?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT lat, lon, COALESCE(heading_deg, -999), sign_type, label_vi FROM signs"
        ).fetchall()
    finally:
        con.close()
    return [(r[0], r[1], r[2] if r[2] is not None else -999.0, r[3], r[4] or r[3])
            for r in rows]


def main():
    ap = argparse.ArgumentParser()
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--sqlite")
    ap.add_argument("out")
    a = ap.parse_args()
    signs = demo_signs() if a.demo else from_sqlite(a.sqlite)
    print(f"wrote {write_signs(signs, a.out)} signs -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
