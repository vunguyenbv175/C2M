#!/usr/bin/env python3
"""List all file paths in a raw UBIFS image with sizes and per-file compression
histograms — without decompressing anything (works with no LZO library).

Usage:
  python3 tools/fw/ubifs_ls.py <customer.ubifs> [-o inventory.json] [--limit 0]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubifs_extract_file import latest_data_blocks, latest_dentries, latest_inodes, path_index, scan_nodes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    image = args.image.read_bytes()
    nodes = scan_nodes(image)
    entries = path_index(latest_dentries(nodes))
    inodes = latest_inodes(nodes)

    rows: list[dict] = []
    for path in sorted(entries):
        ino = int(entries[path]["target"])
        meta = inodes.get(ino, {})
        blocks = latest_data_blocks(nodes, ino)
        hist: dict[int, int] = defaultdict(int)
        for rec in blocks.values():
            hist[int(rec["compression"])] += 1
        rows.append({
            "path": path,
            "inode": ino,
            "size": meta.get("size", 0),
            "data_blocks": len(blocks),
            "compression": dict(sorted(hist.items())),
        })
    if args.limit:
        rows = rows[:args.limit]
    doc = {"image": str(args.image), "image_bytes": len(image), "node_count": len(nodes),
           "file_count": len(rows), "files": rows}
    if args.output:
        args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"files={len(rows)} nodes={len(nodes)}")
    for r in rows[:60]:
        print(f"{r['size']:>10d} blk={r['data_blocks']:<5d} comp={r['compression']} {r['path']}")
    if len(rows) > 60:
        print(f"... and {len(rows) - 60} more (see JSON)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
