#!/usr/bin/env python3
"""Verify a mutated (Candidate-B) customer manifest against stock + mutation.

Checks (fail-closed, nonzero exit on any violation):
  1. every stock path except the hook is semantically identical
     (type/mode/uid/gid/size/sha/target/mtime);
  2. each ADDED path exists with identical mode/size/sha (mtime INFO only —
     build-time by nature);
  3. the hook's sha equals the mutation record's new_sha256 (mtime INFO);
  4. no other added/removed paths exist.

Usage:
  python3 tools/fw/verify_b_manifest.py --stock stock.json --mut mut.json \\
      --actual actual.json [--out report.json]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

KEYS = ("type", "mode", "uid", "gid", "size", "sha256", "target", "mtime")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--mut", type=Path, required=True)
    ap.add_argument("--actual", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    stock = {r["path"]: r for r in json.loads(args.stock.read_text(encoding="utf-8"))["entries"]}
    actual = {r["path"]: r for r in json.loads(args.actual.read_text(encoding="utf-8"))["entries"]}
    mut = json.loads(args.mut.read_text(encoding="utf-8"))
    added = {a["path"]: a for a in mut["added"]}
    hook = mut["hook"]
    new_hook_sha = next(m["new_sha256"] for m in mut["modified"] if m["path"] == hook)
    bad: list[str] = []
    for p, s in stock.items():
        if p == hook:
            continue
        a = actual.get(p)
        if a is None:
            bad.append(f"REMOVED {p}")
            continue
        for k in KEYS:
            if s.get(k) != a.get(k):
                bad.append(f"CHANGED {p} {k}: {s.get(k)!r} -> {a.get(k)!r}")
    for p, a in added.items():
        r = actual.get(p)
        if r is None:
            bad.append(f"MISSING-ADDED {p}")
            continue
        if a.get("type") == "dir":
            # Directories carry no content hash: enforce identity metadata.
            for k in ("type", "mode", "uid", "gid"):
                if r.get(k) != a.get(k):
                    bad.append(f"ADDED-DIR-MISMATCH {p} {k}: {a.get(k)!r} -> {r.get(k)!r}")
            continue
        for k in ("type", "mode", "size", "sha256"):
            if r.get(k) != a.get(k):
                bad.append(f"ADDED-MISMATCH {p} {k}: {a.get(k)!r} -> {r.get(k)!r}")
    h = actual.get(hook)
    if h is None:
        bad.append(f"HOOK-MISSING {hook}")
    elif h.get("sha256") != new_hook_sha:
        bad.append(f"HOOK-SHA {hook}: {h.get('sha256')} != {new_hook_sha}")
    extra = set(actual) - set(stock) - set(added)
    if extra:
        bad.append(f"UNEXPECTED-PATHS {sorted(extra)}")
    doc = {"verdict": "OK" if not bad else "BLOCK", "violations": bad,
           "checked": len(stock), "added": sorted(added), "hook": hook}
    if args.out:
        args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
