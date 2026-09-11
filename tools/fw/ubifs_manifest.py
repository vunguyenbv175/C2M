#!/usr/bin/env python3
"""Full UBIFS filesystem manifest (read-only): every path with type, mode,
uid/gid, size, content SHA-256 (regular files) or link target (symlinks).

Compares two manifests semantically (--compare): type/mode/uid/gid/size/
sha/target/mtime must match. Volatile fields (inode numbers, journal sqnums,
ctime/atime, nlink — recomputed by any fresh mkfs) are recorded but NEVER
compared. Any semantic difference -> nonzero exit (fail-closed).

Usage:
  python3 tools/fw/ubifs_manifest.py <image.ubifs> -o manifest.json
  python3 tools/fw/ubifs_manifest.py --compare a.json b.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubifs_extract_file import (decompress_block, latest_data_blocks,
                                latest_dentries, latest_inodes, path_index,
                                scan_nodes)

COMPARE_KEYS = ("type", "mode", "uid", "gid", "size", "sha256", "target", "mtime")


def read_all_files(nodes, jobs: list[tuple[int, int]]) -> list[bytes]:
    """Bulk-read [(ino, size)] with ONE LZO helper invocation (fast path).

    Non-LZO blocks decode in-process; all LZO blocks across all files go
    through a single batch_decompress call instead of one spawn per file.
    """
    from ubifs_extract_file import decompress_block as _dec
    per_file: list[list[tuple[int, bytes]]] = []
    lzo_jobs: list[tuple[bytes, int]] = []
    lzo_pos: list[tuple[int, int, int]] = []  # (file_idx, block, usize)
    for fi, (ino, size) in enumerate(jobs):
        blocks = latest_data_blocks(nodes, ino)
        chunks: list[tuple[int, bytes]] = []
        for block, rec in sorted(blocks.items()):
            if int(rec["compression"]) == 1:
                lzo_pos.append((fi, block, int(rec["usize"])))
                lzo_jobs.append((rec["payload"], int(rec["usize"])))
            else:
                chunks.append((block, _dec(rec)))
        per_file.append(chunks)
    if lzo_jobs:
        try:
            from lzo_helper import batch_decompress
            outs = batch_decompress(lzo_jobs)
        except RuntimeError:
            # No helper binary (e.g. Linux without a local build): fall back
            # to the system liblzo2 via ctypes, one block at a time.
            from ubifs_extract_file import lzo_decompress as _lzo1
            outs = [_lzo1(p, u) for p, u in lzo_jobs]
        for (fi, block, usize), decoded in zip(lzo_pos, outs):
            if len(decoded) != usize:
                raise SystemExit(f"bulk-read: lzo size mismatch file#{fi} block {block}")
            per_file[fi].append((block, decoded))
    out = []
    for (ino, size), chunks in zip(jobs, per_file):
        buf = bytearray(size)
        for block, decoded in chunks:
            start = block * 4096
            buf[start:start + len(decoded)] = decoded
        out.append(bytes(buf[:size]))
    return out


def read_file(image_nodes_image: bytes, nodes, ino: int, size: int) -> bytes:
    return read_all_files(nodes, [(ino, size)])[0]


def build_manifest(image_path: Path) -> dict:
    image = image_path.read_bytes()
    nodes = scan_nodes(image)
    entries = path_index(latest_dentries(nodes))
    inodes = latest_inodes(nodes)
    rows = []
    reg_jobs = [(int(entries[p]["target"]), inodes[int(entries[p]["target"])]["size"])
                for p in sorted(entries)
                if inodes.get(int(entries[p]["target"])) is not None
                and ((inodes[int(entries[p]["target"])]["mode"] >> 12) & 0o17) == 0o10]
    reg_blobs = dict(zip([j[0] for j in reg_jobs], read_all_files(nodes, reg_jobs)))
    for path in sorted(entries):
        ino = int(entries[path]["target"])
        meta = inodes.get(ino)
        if meta is None:
            raise SystemExit(f"manifest: inode metadata missing for {path} (ino {ino})")
        ftype = (meta["mode"] >> 12) & 0o17
        row: dict = {"path": path, "inode": ino,
                     "type": {0o4: "dir", 0o10: "reg", 0o12: "symlink"}.get(ftype, f"UNKNOWN-{oct(ftype)}"),
                     "mode": meta["mode"] & 0o7777, "mode_oct": oct(meta["mode"] & 0o7777),
                     "uid": meta["uid"], "gid": meta["gid"],
                     "size": meta["size"], "mtime": meta["mtime"],
                     "ctime_info": meta["ctime"], "atime_info": meta["atime"]}
        if row["type"] == "reg":
            blob = reg_blobs[ino]
            row["sha256"] = hashlib.sha256(blob).hexdigest()
            hist: dict[int, int] = defaultdict(int)
            for rec in latest_data_blocks(nodes, ino).values():
                hist[int(rec["compression"])] += 1
            row["compression"] = dict(sorted(hist.items()))
        elif row["type"] == "symlink":
            rec = max((r for r in nodes if r["type"] == 0
                       and struct.unpack_from("<I", r["data"], 24)[0] == ino),
                      key=lambda r: r["sqnum"])
            dlen = struct.unpack_from("<I", rec["data"], 112)[0]
            if dlen != meta["size"] or dlen > 4096:
                raise SystemExit(f"manifest: bad symlink data_len for {path}")
            row["target"] = rec["data"][rec["len"] - dlen:rec["len"]].split(b"\0")[0].decode()
        elif row["type"] == "dir":
            pass  # no content, no target; mode/mtime are compared, applied at extract
        else:
            raise SystemExit(f"manifest: unsupported type {row['type']} at {path} "
                             f"(fail-closed: extend tooling, do not skip)")
        rows.append(row)
    return {"image": str(image_path), "image_bytes": len(image),
            "node_count": len(nodes), "entry_count": len(rows), "entries": rows}


def compare(a: dict, b: dict) -> list[str]:
    diffs = []
    ma = {r["path"]: r for r in a["entries"]}
    mb = {r["path"]: r for r in b["entries"]}
    for p in sorted(set(ma) | set(mb)):
        if p not in ma:
            diffs.append(f"ADDED {p}")
        elif p not in mb:
            diffs.append(f"REMOVED {p}")
        else:
            for k in COMPARE_KEYS:
                if ma[p].get(k) != mb[p].get(k):
                    diffs.append(f"CHANGED {p} field={k} {ma[p].get(k)!r} -> {mb[p].get(k)!r}")
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path, nargs="?")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--compare", nargs=2, metavar=("A_JSON", "B_JSON"))
    args = ap.parse_args()
    if args.compare:
        a = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        b = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        diffs = compare(a, b)
        if diffs:
            print(f"MANIFEST-DIFF: {len(diffs)} semantic differences")
            for d in diffs[:50]:
                print("  " + d)
            return 1
        print(f"MANIFEST-OK: {len(a['entries'])} entries semantically identical")
        return 0
    if args.image is None:
        ap.error("image required")
    doc = build_manifest(args.image)
    n_reg = sum(1 for r in doc["entries"] if r["type"] == "reg")
    n_dir = sum(1 for r in doc["entries"] if r["type"] == "dir")
    n_lnk = sum(1 for r in doc["entries"] if r["type"] == "symlink")
    if args.output:
        args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"manifest: {len(doc['entries'])} entries ({n_reg} reg, {n_dir} dir, {n_lnk} symlink)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
