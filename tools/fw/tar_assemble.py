#!/usr/bin/env python3
"""Assemble the outer vendor TAR with raw headers replicating the stock encoding.

Golden TAR header encoding (measured, all 4 members): size/mtime as
11-octal+NUL, chksum 6-octal+NUL+space, magic `ustar  \\x00` (NOT python
tarfile's `ustar\\x0000`), uname/gname `zac`, devmajor/devminor NUL-filled.
This writer copies the golden 512 B headers verbatim and patches ONLY the
size + chksum fields, so a Candidate B TAR differs from golden headers in
exactly those two fields (plus new data) — fully explained, no mystery bytes.

Golden mode: reassemble from original member bytes -> must be byte-identical
(proves the writer). Package mode: --members-json [{name, file}] + sizes
from files; metadata (order/mode/mtime/uid/gid) from the EN contract.

Usage:
  python3 tools/fw/tar_assemble.py --mode golden --tar <orig> --contract <json> --out <tar>
  python3 tools/fw/tar_assemble.py --mode package --tar <orig> --contract <json> \\
      --members-json members.json --out <tar> --report report.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def patch_header(hdr: bytes, size: int) -> bytes:
    h = bytearray(hdr)
    h[124:136] = ("%011o\x00" % size).encode("ascii")
    h[148:156] = b" " * 8
    chksum = sum(h)
    h[148:156] = ("%06o\x00 " % chksum).encode("ascii")
    return bytes(h)


def read_raw_members(tar_path: Path) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    raw = tar_path.read_bytes()
    members = []
    off = 0
    while True:
        hdr = raw[off:off + 512]
        if hdr == b"\x00" * 512:
            break
        size = int(hdr[124:136].split(b"\x00")[0].strip() or b"0", 8)
        data = raw[off + 512:off + 512 + size]
        members.append((hdr, data))
        off += 512 + ((size + 511) // 512) * 512
    trailing = raw[off:]
    assert trailing and all(b == 0 for b in trailing), "nonzero TAR trailer"
    return raw, members


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("golden", "package"), required=True)
    ap.add_argument("--tar", type=Path, required=True, help="original golden TAR (headers+trailer source)")
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--members-json", type=Path, help="package mode: [{name, file}]")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    raw, golden = read_raw_members(args.tar)
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    names = [m["name"] for m in contract["outer_members"]]
    if [n for n, _ in [(contract["outer_members"][i]["name"], 0) for i in range(len(golden))]] != names:
        raise SystemExit("tar_assemble: contract order != golden order")

    if args.mode == "golden":
        blobs = [data for _, data in golden]
    else:
        spec = {m["name"]: Path(m["file"]) for m in json.loads(args.members_json.read_text())}
        if set(spec) != set(names):
            raise SystemExit(f"tar_assemble: member set {sorted(spec)} != {names}")
        blobs = [spec[n].read_bytes() for n in names]

    out = bytearray()
    for (hdr, _old), blob, meta in zip(golden, blobs, contract["outer_members"]):
        if len(blob) != meta["size"] and args.mode == "golden":
            raise SystemExit("golden member size changed")
        out += patch_header(hdr, len(blob))
        out += blob + b"\x00" * ((-len(blob)) % 512)
    # preserve golden trailing-zero run exactly (measured 1536 bytes)
    tmp = 0
    while True:
        hdr = raw[tmp:tmp + 512]
        if hdr == b"\x00" * 512:
            break
        size = int(hdr[124:136].split(b"\x00")[0].strip() or b"0", 8)
        tmp += 512 + ((size + 511) // 512) * 512
    out += raw[tmp:]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(bytes(out))
    rep = {"mode": args.mode,
           "out_sha256": hashlib.sha256(bytes(out)).hexdigest(),
           "out_size": len(out),
           "byte_identical_to_golden": bytes(out) == raw}
    print(json.dumps(rep, indent=2))
    if args.report:
        args.report.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    if args.mode == "golden" and bytes(out) != raw:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
