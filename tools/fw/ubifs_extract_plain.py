#!/usr/bin/env python3
"""Extract every fully-uncompressed regular file from a UBIFS image (no LZO needed).

Usage:
  python3 tools/fw/ubifs_extract_plain.py <customer.ubifs> <outdir> [--max-bytes N]
Writes <outdir>/... mirror tree + manifest.json with sha256 per file.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubifs_extract_file import decompress_block, latest_data_blocks, latest_dentries, latest_inodes, path_index, scan_nodes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--max-bytes", type=int, default=5_000_000)
    args = ap.parse_args()

    image = args.image.read_bytes()
    nodes = scan_nodes(image)
    entries = path_index(latest_dentries(nodes))
    inodes = latest_inodes(nodes)
    manifest: list[dict] = []
    for path in sorted(entries):
        ino = int(entries[path]["target"])
        meta = inodes.get(ino)
        if not meta or not meta.get("size"):
            continue
        blocks = latest_data_blocks(nodes, ino)
        if not blocks:
            continue
        if any(int(r["compression"]) != 0 for r in blocks.values()):
            status = "skip-compressed"
            manifest.append({"path": path, "size": meta["size"], "status": status})
            continue
        if meta["size"] > args.max_bytes:
            manifest.append({"path": path, "size": meta["size"], "status": "skip-too-big"})
            continue
        out = bytearray(int(meta["size"]))
        for block, rec in sorted(blocks.items()):
            decoded = decompress_block(rec)
            out[block * 4096:block * 4096 + len(decoded)] = decoded
        blob = bytes(out)
        dest = args.outdir / path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        manifest.append({"path": path, "size": len(blob),
                         "sha256": hashlib.sha256(blob).hexdigest(), "status": "extracted"})
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    n = sum(1 for m in manifest if m["status"] == "extracted")
    print(f"extracted={n} total={len(manifest)} -> {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
