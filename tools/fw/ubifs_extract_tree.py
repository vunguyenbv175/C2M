#!/usr/bin/env python3
"""Extract a full UBIFS image to a directory tree (read-only source).

Preserves: regular-file bytes + mode + mtime, directory modes + mtimes,
symlink targets, uid/gid NUMBERS in a sidecar (ventura: chown needs root;
the rebuild driver applies them where permitted and records the rest).

Symlink fallback: on platforms without symlink privilege (e.g. Windows),
writes the target into `<name>.SYMLINK-TARGET.txt` + records a fallback in
report.json. The Linux rebuild driver REFUSES trees with fallbacks
(fail-closed); this path exists for host inspection only.

Usage:
  python3 tools/fw/ubifs_extract_tree.py <image.ubifs> <outdir> [--report report.json]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubifs_manifest import build_manifest, read_all_files  # noqa: E402
from ubifs_extract_file import scan_nodes  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--manifest", type=Path,
                    help="reuse manifest JSON (skips rebuild; must match image)")
    args = ap.parse_args()

    if args.manifest:
        doc = json.loads(args.manifest.read_text(encoding="utf-8"))
    else:
        doc = build_manifest(args.image)
    image = args.image.read_bytes()
    nodes = scan_nodes(image)
    blobs = {}
    reg_jobs = [(r["inode"], r["size"]) for r in doc["entries"] if r["type"] == "reg"]
    for (ino, _size), blob in zip(reg_jobs, read_all_files(nodes, reg_jobs)):
        blobs[ino] = blob
    fallbacks = []
    for row in doc["entries"]:
        dest = args.outdir / row["path"].lstrip("/")
        if row["type"] == "dir":
            dest.mkdir(parents=True, exist_ok=True)
        elif row["type"] == "reg":
            dest.parent.mkdir(parents=True, exist_ok=True)
            ino = row["inode"]
            dest.write_bytes(blobs[ino])
        elif row["type"] == "symlink":
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink() or dest.exists():
                dest.unlink() if dest.is_symlink() else None
            try:
                if dest.exists() and not dest.is_symlink():
                    raise RuntimeError("non-symlink blocks symlink path")
                os.symlink(row["target"], dest)
            except (OSError, RuntimeError) as e:
                fb = dest.with_name(dest.name + ".SYMLINK-TARGET.txt")
                fb.write_text(row["target"], encoding="utf-8")
                fallbacks.append({"path": row["path"], "target": row["target"],
                                  "reason": str(e)})
                continue
        if row["type"] != "symlink":
            os.chmod(dest, row["mode"])
            os.utime(dest, (row["mtime"], row["mtime"]))
    # directory mtimes after all children are placed
    for row in sorted(doc["entries"], key=lambda r: -len(r["path"])):
        if row["type"] == "dir":
            os.utime(args.outdir / row["path"].lstrip("/"),
                     (row["mtime"], row["mtime"]))
    report = {"image": str(args.image), "entries": len(doc["entries"]),
              "symlink_fallbacks": fallbacks}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"tree: {len(doc['entries'])} entries -> {args.outdir} "
          f"(symlink fallbacks: {len(fallbacks)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
