#!/usr/bin/env python3
"""WS2: Reproducible EN firmware round-trip builder (EXACT / NO-MODIFICATION).

Rebuilds the EN vendor package from the ORIGINAL tar bytes + package contract:
  1. re-derive inner image: 0xFF-filled buffer, script + payload slices copied
     from the original inner bytes at contract offsets, UNKNOWN tail preserved
     verbatim -> inner MUST hash-identically to the original (else FAIL).
  2. re-package outer TAR by header-preserving splice: original TAR bytes with
     ONLY the inner member data range replaced (same size) -> outer TAR MUST be
     byte-identical (headers/trailing zeros untouched).

Any structural deviation (member set/order/size, script change, payload hash
mismatch, unsupported override) FAILS CLOSED with nonzero exit.

This is the Golden (candidate A) path. Partition modification / UBIFS rewrite
for candidates B/C is intentionally NOT implemented here (see FLASH_CANDIDATES
recipe: BLOCKED pending a UBIFS writer + hardware).

Usage:
  python3 tools/fw/repack_firmware.py --tar <orig EN.tar> \\
      --contract docs/firmware/EN_PACKAGE_CONTRACT.json \\
      --out build/EN_REPACK_GOLDEN.tar --report build/repack_report.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

EXPECTED_TAR_SHA = "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c"
INNER = "SigmastarUpgradeSD_SSC8838G.bin"


def sha256_bytes(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--replace-payload", action="append", default=[],
                    help="BLOCKED: any use fails closed (no partition mod in Sprint 1)")
    args = ap.parse_args()

    if args.replace_payload:
        print("REPACK-FAIL: --replace-payload is UNSUPPORTED in Sprint 1 (exact-only builder; "
              "UBIFS/partition modification explicitly out of scope).")
        return 1

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    orig_tar_bytes = args.tar.read_bytes()
    if sha256_bytes(orig_tar_bytes) != EXPECTED_TAR_SHA:
        print(f"REPACK-FAIL: source TAR SHA mismatch (not the golden EN baseline).")
        return 1
    if sha256_bytes(orig_tar_bytes) != contract["source_tar_sha256"]:
        print("REPACK-FAIL: source TAR does not match contract source_tar_sha256.")
        return 1

    with tarfile.open(args.tar, "r") as tf:
        members = tf.getmembers()
        names = [m.name for m in members]
        if names != contract["outer_order"]:
            print(f"REPACK-FAIL: member order/names differ: {names} vs {contract['outer_order']}")
            return 1
        blobs = {m.name: tf.extractfile(m).read() for m in members}
        for m in members:
            exp = next(x for x in contract["outer_members"] if x["name"] == m.name)
            if len(blobs[m.name]) != exp["size"] or sha256_bytes(blobs[m.name]) != exp["sha256"]:
                print(f"REPACK-FAIL: member {m.name} differs from contract.")
                return 1

    inner = blobs[INNER]
    if sha256_bytes(inner) != contract["inner_sha256"]:
        print("REPACK-FAIL: inner image differs from contract.")
        return 1

    # 1. rebuild inner from parts (proves offsets/lengths/padding account for every byte)
    rebuilt = bytearray(len(inner))
    rebuilt[:] = b"\xff" * len(inner)
    script_end = contract["upgrade_script_end"]
    script_bytes = inner[:script_end + 1]  # script + trailing NL
    rebuilt[:script_end + 1] = script_bytes
    for r in contract["loads"]:
        if not r["within_image"]:
            print(f"REPACK-FAIL: contract load out of bounds: {r}")
            return 1
        chunk = inner[r["offset"]:r["end"]]
        if sha256_bytes(bytes(chunk)) != r["sha256"]:
            print(f"REPACK-FAIL: payload {r['section']}#{r['load_index']} hash mismatch.")
            return 1
        rebuilt[r["offset"]:r["end"]] = chunk
    tail = contract["tail_unknown"]
    tail_bytes = inner[tail["offset"]:tail["offset"] + tail["len"]]
    if tail_bytes.hex() != tail["hex"]:
        print("REPACK-FAIL: UNKNOWN tail bytes changed — refusing to guess.")
        return 1
    rebuilt[tail["offset"]:tail["offset"] + tail["len"]] = tail_bytes

    if bytes(rebuilt) != inner:
        # find first diff for the report (should never happen if accounting is complete)
        for i, (a, b) in enumerate(zip(rebuilt, inner)):
            if a != b:
                print(f"REPACK-FAIL: rebuilt inner differs at {hex(i)}: got {hex(a)} want {hex(b)}.")
                break
        return 1
    inner_identical = True

    # 2. header-preserving splice into outer TAR
    inner_member = next(x for x in contract["outer_members"] if x["name"] == INNER)
    doff = inner_member["data_offset"]
    size = inner_member["size"]
    if len(bytes(rebuilt)) != size:
        print("REPACK-FAIL: rebuilt inner size changed.")
        return 1
    out_bytes = bytearray(orig_tar_bytes)
    out_bytes[doff:doff + size] = bytes(rebuilt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(out_bytes))

    tar_identical = sha256_bytes(bytes(out_bytes)) == sha256_bytes(orig_tar_bytes)
    report = {
        "mode": "EXACT/NO-MODIFICATION",
        "source_tar_sha256": sha256_bytes(orig_tar_bytes),
        "rebuilt_tar_sha256": sha256_bytes(bytes(out_bytes)),
        "tar_byte_identical": tar_identical,
        "inner_byte_identical": inner_identical,
        "inner_sha256": sha256_bytes(bytes(rebuilt)),
        "members_byte_identical": {n: sha256_bytes(blobs[n]) for n in names},
        "tar_header_note": "Splice mode preserves original 512B headers + trailing zeros verbatim; "
                           "no TAR metadata was regenerated, so zero header differences remain. "
                           "A from-scratch python-tarfile rebuild would differ in ustar magic/version "
                           "bytes ('ustar  ' vs 'ustar\\x0000') + chksum — payload-irrelevant, "
                           "avoided by design here.",
        "verdict": "EXACT-ROUND-TRIP-OK" if (tar_identical and inner_identical) else "MISMATCH",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "EXACT-ROUND-TRIP-OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
