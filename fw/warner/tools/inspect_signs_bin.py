#!/usr/bin/env python3
"""Validate private C2MSDB01 input and optionally stage a directional subset.

No device access. Reports contain counts/hashes only, never pin coordinates.
A binary DB does not establish rights, freshness, road matching or GPS I/O.
Unknown headings and unusual speed values are excluded from automatic use.
The original owner-provided file is never modified.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from build_signs_bin import write_signs

MAGIC = b"C2MSDB01"
RECORD = struct.Struct("<ddf16s64s")
TYPES = {"R.420", "R.421", "P.127", "P.125", "P.130", "P.131a"}
# Conservative review set, NOT a claim that other legally valid values cannot exist.
REVIEWED_SPEEDS = {5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120}
MAX_RECORDS = 40000


def string(raw: bytes) -> str:
    if b"\0" not in raw:
        raise ValueError("missing string termination")
    value = raw.split(b"\0", 1)[0].decode("utf-8", "strict")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("control character in DB text")
    return value


def inspect(data: bytes):
    if len(data) < 12 or data[:8] != MAGIC:
        raise ValueError("invalid magic/header")
    count = struct.unpack_from("<I", data, 8)[0]
    if not 0 < count <= MAX_RECORDS or len(data) != 12 + count * RECORD.size:
        raise ValueError("invalid count/length")
    rows = []
    types, direction = Counter(), defaultdict(Counter)
    speed_values, exclusions = Counter(), Counter()
    eligible = []
    for index in range(count):
        lat, lon, heading, typ_raw, label_raw = RECORD.unpack_from(data, 12 + index * RECORD.size)
        if not all(math.isfinite(v) for v in (lat, lon, heading)):
            raise ValueError("nonfinite DB number")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("coordinates outside range")
        if heading != -999 and not 0 <= heading <= 360:
            raise ValueError("invalid heading")
        kind, label = string(typ_raw), string(label_raw)
        if kind not in TYPES:
            raise ValueError("unreviewed type in DB")
        heading = 0 if heading == 360 else heading
        row = (lat, lon, heading, kind, label)
        rows.append(row)
        types[kind] += 1
        direction[kind]["unknown" if heading == -999 else "directional"] += 1
        speed = None
        if kind == "P.127":
            match = re.fullmatch(r"Biển hạn chế tốc độ tối đa ([0-9]+) km/h", label)
            if not match:
                raise ValueError("ambiguous speed-limit label")
            speed = int(match[1])
            speed_values[str(speed)] += 1
        if heading == -999:
            exclusions["unknown_application_heading"] += 1
        elif speed is not None and speed not in REVIEWED_SPEEDS:
            exclusions["unreviewed_speed_value"] += 1
        else:
            eligible.append(row)
    report = {"verdict": "HOST_DB_VALIDATED_NOT_DEPLOYED", "sha256": hashlib.sha256(data).hexdigest(),
              "bytes": len(data), "count": count, "type_counts": dict(types),
              "heading_counts_by_type": {k: dict(v) for k, v in direction.items()},
              "speed_values": dict(speed_values), "automatic_directional_candidates": len(eligible),
              "exclusions": dict(exclusions), "device_access": False,
              "source_rights_verified": False, "freshness_verified": False,
              "heading_semantics_runtime_verified": False,
              "warning": "GPS advisory data only, not camera TSR; exact road/heading and output still need validation."}
    return rows, eligible, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("--report", type=Path, help="host counts/hash report")
    ap.add_argument("--directional-out", type=Path, help="PRIVATE filtered DB output, new path only")
    args = ap.parse_args()
    try:
        # Prevent unbounded read of corrupt/misidentified files.
        if args.source.stat().st_size > 12 + MAX_RECORDS * RECORD.size:
            raise ValueError("oversized DB")
        rows, eligible, report = inspect(args.source.read_bytes())
        if args.directional_out:
            if args.directional_out.exists() or args.directional_out.resolve() == args.source.resolve():
                raise ValueError("output already exists/is input")
            write_signs(eligible, args.directional_out)
            blob = args.directional_out.read_bytes()
            report["filtered_sha256"] = hashlib.sha256(blob).hexdigest()
            report["filtered_bytes"] = len(blob)
            report["filtered_type_counts"] = dict(Counter(row[3] for row in eligible))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
    except (OSError, ValueError, UnicodeError, struct.error):
        print("SIGN-DB: BLOCK (invalid input/output, source unchanged)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
