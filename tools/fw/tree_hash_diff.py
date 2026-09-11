#!/usr/bin/env python3
"""SHA-256 recursive directory diff with stable machine-readable output."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

def hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def collect(root: Path):
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path)
    ap.add_argument("--json", dest="json_path", type=Path)
    ap.add_argument("--csv", dest="csv_path", type=Path)
    args = ap.parse_args()

    a, b = collect(args.left), collect(args.right)
    rows = []
    counts = {"same": 0, "different": 0, "left_only": 0, "right_only": 0}
    for rel in sorted(set(a) | set(b)):
        pa, pb = a.get(rel), b.get(rel)
        if pa and pb:
            ha, hb = hash_file(pa), hash_file(pb)
            st = "same" if ha == hb else "different"
            row = {"path": rel, "status": st, "left_size": pa.stat().st_size, "right_size": pb.stat().st_size, "left_sha256": ha, "right_sha256": hb}
        elif pa:
            st = "left_only"
            row = {"path": rel, "status": st, "left_size": pa.stat().st_size, "right_size": None, "left_sha256": hash_file(pa), "right_sha256": None}
        else:
            st = "right_only"
            row = {"path": rel, "status": st, "left_size": None, "right_size": pb.stat().st_size, "left_sha256": None, "right_sha256": hash_file(pb)}
        counts[st] += 1
        rows.append(row)

    result = {"left": str(args.left), "right": str(args.right), "counts": counts, "files": rows}
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.csv_path:
        args.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["path", "status", "left_size", "right_size", "left_sha256", "right_sha256"])
            w.writeheader()
            w.writerows(rows)
    print(json.dumps({"counts": counts, "changed": [r["path"] for r in rows if r["status"] != "same"]}, indent=2))

if __name__ == "__main__":
    main()
