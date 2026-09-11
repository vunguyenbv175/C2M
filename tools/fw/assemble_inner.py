#!/usr/bin/env python3
"""Assemble the SigmaStar inner upgrade image from (script + payloads + tail).

Layout rule (proven by EN_PACKAGE_CONTRACT byte accounting): a 0xFF-filled
buffer of total_size; script text + 1x LF at offset 0; each payload at its
fatload offset; UNKNOWN tail bytes verbatim at the end. Every byte is thus
script / payload / 0xFF pad / UNKNOWN tail — anything else FAILS.

Two modes:
  --mode golden   rebuild from the ORIGINAL TAR bytes + EN contract and
                  require byte-identical output (proves the assembler).
  --mode layout   build a NEW layout from --layout-json
                  {script_text, payloads: [{section, load_index, offset, size,
                  file}], tail_hex, total_size} (used for Candidate B).

For Candidate B the caller (build_candidates.py) computes the new layout:
same offsets up to customer.es, misc/oneed shifted by the customer delta,
script fatload/ubi-write lines regenerated — all recorded in layout JSON.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

INNER = "SigmastarUpgradeSD_SSC8838G.bin"


def assemble(total: int, script: bytes, payloads: list[tuple[int, bytes]],
             tail: bytes, tail_offset: int) -> bytes:
    buf = bytearray(total)
    buf[:] = b"\xff" * total
    if not script.endswith(b"\n"):
        raise SystemExit("assemble: script must end with single LF")
    buf[:len(script)] = script
    for off, blob in payloads:
        if not (len(script) <= off <= off + len(blob) <= tail_offset):
            raise SystemExit(f"assemble: payload out of bounds @{hex(off)}")
        buf[off:off + len(blob)] = blob
    if tail_offset + len(tail) != total:
        raise SystemExit("assemble: tail must end exactly at total_size")
    buf[tail_offset:tail_offset + len(tail)] = tail
    # overlap check: payload ranges must not intersect script or each other
    used = sorted([(0, len(script))] + [(o, o + len(b)) for o, b in payloads]
                  + [(tail_offset, total)])
    for (a0, a1), (b0, b1) in zip(used, used[1:]):
        if a1 > b0:
            raise SystemExit(f"assemble: overlapping ranges {hex(a0)}..{hex(a1)} vs {hex(b0)}..{hex(b1)}")
    return bytes(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("golden", "layout"), required=True)
    ap.add_argument("--tar", type=Path, help="original TAR (golden mode)")
    ap.add_argument("--contract", type=Path, help="EN contract (golden mode)")
    ap.add_argument("--layout-json", type=Path, help="layout spec (layout mode)")
    ap.add_argument("--payload-dir", type=Path, help="dir holding payload files (layout mode)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    if args.mode == "golden":
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        with tarfile.open(args.tar, "r") as tf:
            inner = tf.extractfile(INNER).read()
        script = inner[:contract["upgrade_script_end"] + 1]
        payloads = [(r["offset"], inner[r["offset"]:r["end"]]) for r in contract["loads"]]
        tail = contract["tail_unknown"]
        out = assemble(len(inner), script, payloads,
                       bytes.fromhex(tail["hex"]), tail["offset"])
        identical = out == inner
        rep = {"mode": "golden",
               "byte_identical": identical,
               "sha256": hashlib.sha256(out).hexdigest()}
        print(json.dumps(rep, indent=2))
        if not identical:
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(out)
        if args.report:
            args.report.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        return 0

    spec = json.loads(args.layout_json.read_text(encoding="utf-8"))
    payloads = []
    for p in spec["payloads"]:
        blob = (args.payload_dir / p["file"]).read_bytes()
        if len(blob) != p["size"]:
            raise SystemExit(f"layout: {p['file']} size {len(blob)} != {p['size']}")
        payloads.append((p["offset"], blob))
    out = assemble(spec["total_size"], spec["script_text"].encode("latin-1"),
                   payloads, bytes.fromhex(spec["tail_hex"]), spec["tail_offset"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(out)
    rep = {"mode": "layout", "total_size": len(out),
           "sha256": hashlib.sha256(out).hexdigest(),
           "md5": hashlib.md5(out).hexdigest()}
    print(json.dumps(rep, indent=2))
    if args.report:
        args.report.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
