#!/usr/bin/env python3
"""List + grep the gzipped-cpio rootfs inner images (fully available, no LZO).

Usage:
  python3 tools/fw/rootfs_cpio_grep.py build/rootfs_en_inner.bin --list build/rootfs_en_list.txt
  python3 tools/fw/rootfs_cpio_grep.py build/rootfs_en_inner.bin --grep subscribe --grep libflow
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_rootfs_cpio import iter_cpio


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inner", type=Path)
    ap.add_argument("--list", type=Path)
    ap.add_argument("--grep", action="append", default=[])
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    data = args.inner.read_bytes()
    names: list[tuple[str, int]] = []
    blobs: dict[str, bytes] = {}
    for name, blob in iter_cpio(data):
        names.append((name, len(blob)))
        blobs[name] = blob
    if args.list:
        args.list.write_text("\n".join(f"{s:>10d} {n}" for n, s in names), encoding="utf-8")
    print(f"{args.tag} cpio entries={len(names)}")
    interesting = [n for n, _ in names
                   if "minieye" in n or "adas" in n.lower() or "libflow" in n or "cardv" in n
                   or n.endswith(".flag") or "calib" in n.lower() or "screen" in n.lower()]
    print("--- adas/cardv/screen-related paths:")
    for n in interesting:
        print(f"  {blobs[n].__len__():>10d} {n}")
    for pat in args.grep:
        nb = pat.encode()
        hits = [(n, blobs[n].find(nb)) for n, _ in names if nb in blobs[n]]
        print(f"--- grep {pat!r}: {len(hits)} files")
        for n, off in hits[:20]:
            print(f"  {n} @ {hex(off)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
