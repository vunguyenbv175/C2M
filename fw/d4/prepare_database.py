#!/usr/bin/env python3
"""Prepare owner-private directional R.420/R.421 subset for D4 advisory.

No downloadable source is fetched; no coordinates/labels/records are printed.
The supplied SHA256 is mandatory. Unknown-direction speed-limit points are
excluded, never reinterpreted as applying both directions. This is not proof
of legal applicability, road association, data rights or freshness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct

MAGIC = b"C2MSDB01"
RECORD = struct.Struct("<ddf16s64s")
MAX_COUNT = 40000


def text_field(value: bytes) -> str:
    prefix, separator, padding = value.partition(b"\0")
    if not separator or any(padding):
        raise ValueError("noncanonical string field")
    text = prefix.decode("utf-8", "strict")
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("control character in database string")
    return text


def prepare(data: bytes, expected_sha256: str) -> tuple[bytes, dict]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("mandatory SHA256 pin must be 64 hex digits")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError("private database SHA256 mismatch")
    if len(data) < 12 or data[:8] != MAGIC:
        raise ValueError("invalid database header")
    count = struct.unpack_from("<I", data, 8)[0]
    if not 1 <= count <= MAX_COUNT or len(data) != 12 + count * RECORD.size:
        raise ValueError("invalid count or exact file size")
    kept = []
    classes: Counter[str] = Counter()
    source_types: Counter[str] = Counter()
    unknown = 0
    for offset in range(12, len(data), RECORD.size):
        raw = data[offset:offset + RECORD.size]
        lat, lon, heading, typ_raw, label_raw = RECORD.unpack(raw)
        typ = text_field(typ_raw)
        text_field(label_raw)
        if not typ or not all(math.isfinite(v) for v in (lat, lon, heading)):
            raise ValueError("invalid coordinate/heading/type")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("coordinate outside range")
        if heading != -999 and not 0 <= heading <= 360:
            raise ValueError("heading outside range")
        source_types[typ] += 1
        if heading == -999:
            unknown += 1
            continue
        if typ not in ("R.420", "R.421"):
            continue
        if heading == 360:
            raw = RECORD.pack(lat, lon, 0.0, typ_raw, label_raw)
        kept.append(raw)
        classes[typ] += 1
    if not kept:
        raise ValueError("no eligible directional area records")
    output = MAGIC + struct.pack("<I", len(kept)) + b"".join(kept)
    report = {
        "format": "C2MSDB01",
        "purpose": "EXPERIMENTAL_GPS_NEARBY_AREA_SIGN_ADVISORY_NOT_LEGAL_SPEED",
        "source_sha256": digest,
        "source_records": count,
        "source_type_counts": dict(sorted(source_types.items())),
        "unknown_application_heading_excluded": unknown,
        "output_records": len(kept),
        "output_type_counts": dict(sorted(classes.items())),
        "output_bytes": len(output),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "numeric_speed_limit_records_deployed": 0,
        "heading_and_same_road_semantics": "UNVERIFIED_EXPERIMENTAL",
        "rights_and_freshness": "OWNER_PRIVATE_PERMITTED_USE_REVIEW_REQUIRED",
        "raw_records_or_locations_in_report": False,
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.source.is_symlink() or not args.source.is_file():
            raise ValueError("source must be a regular nonsymlink file")
        if args.source.stat().st_size > 12 + MAX_COUNT * RECORD.size:
            raise ValueError("source exceeds database size bound")
        if args.out.exists() or args.report.exists() or args.out.is_symlink() or args.report.is_symlink():
            raise ValueError("output/report already exists; refusing overwrite")
        if args.out.resolve() == args.report.resolve():
            raise ValueError("output and report alias")
        output, report = prepare(args.source.read_bytes(), args.sha256)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("xb") as stream:
            stream.write(output)
        if args.out.read_bytes() != output:
            raise ValueError("database read-back mismatch")
        with args.report.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, UnicodeError) as error:
        print("BLOCK: " + str(error))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
