#!/usr/bin/env python3
"""Extract named files from the gzipped-cpio rootfs inner images (EN/VI).

Usage:
  python3 tools/fw/extract_rootfs_cpio.py build/rootfs_en_inner.bin build/fw_bin/ --names bootconfig/bin/cardv
"""
from __future__ import annotations
import argparse
from pathlib import Path


def pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def iter_cpio(data: bytes):
    off = 0
    while off + 110 <= len(data):
        if data[off:off + 6] != b"070701":
            raise ValueError(f"bad cpio magic at {hex(off)}")
        h = data[off:off + 110].decode("ascii")
        filesize = int(h[54:62], 16)
        namesize = int(h[94:102], 16)
        name = data[off + 110:off + 110 + namesize].split(b"\0")[0].decode("utf-8", "replace")
        dataoff = off + 110 + namesize + pad4(off + 110 + namesize)
        if name == "TRAILER!!!":
            return
        yield name, data[dataoff:dataoff + filesize]
        off = dataoff + filesize + pad4(dataoff + filesize)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inner", type=Path)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--names", nargs="*", default=["bootconfig/bin/cardv"])
    args = ap.parse_args()
    data = args.inner.read_bytes()
    args.outdir.mkdir(parents=True, exist_ok=True)
    found = 0
    for name, blob in iter_cpio(data):
        if name in args.names:
            out = args.outdir / Path(name).name
            out.write_bytes(blob)
            print(f"{name} -> {out} ({len(blob)} bytes)")
            found += 1
    if not found:
        print("WARNING: no requested names found")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
