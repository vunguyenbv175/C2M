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
# Directory size/mtime are rebuild artifacts (entry count and build clock),
# not content identity: a directory gaining an allowlisted file (e.g. the
# previously absent tlr wav) legitimately changes both. Compare only
# identity metadata for dirs, full KEYS for everything else.
DIR_KEYS = ("type", "mode", "uid", "gid")


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
    replaced = mut.get("replaced", {})
    hook = mut["hook"]
    new_hook_sha = next(m["new_sha256"] for m in mut["modified"] if m["path"] == hook)
    bad: list[str] = []
    for p, s in stock.items():
        if p == hook:
            continue
        if p in replaced:
            # Authorized content swap (e.g. wav assets + md5sum.txt): the
            # rebuilt image must carry EXACTLY the recorded bytes.
            a = actual.get(p)
            exp = replaced[p]
            if a is None:
                bad.append(f"REPLACED-MISSING {p}")
            elif a.get("sha256") != exp["new_sha256"] or a.get("size") != exp["new_size"]:
                bad.append(f"REPLACED-MISMATCH {p}: got sha {a.get('sha256')} "
                           f"size {a.get('size')}, want {exp['new_sha256']} {exp['new_size']}")
            continue
        a = actual.get(p)
        if a is None:
            bad.append(f"REMOVED {p}")
            continue
        for k in (DIR_KEYS if s.get("type") == "dir" else KEYS):
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
    allowed_new = {p for p, r in replaced.items()
                   if r.get("old_sha256") == "(absent-in-image)"}
    for p in sorted(allowed_new):
        a = actual.get(p)
        exp = replaced[p]
        if a is None:
            bad.append(f"ADDED-MISSING {p}")
        elif a.get("sha256") != exp["new_sha256"] or a.get("size") != exp["new_size"]:
            bad.append(f"ADDED-MISMATCH {p}")
    extra = set(actual) - set(stock) - set(added) - allowed_new
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
