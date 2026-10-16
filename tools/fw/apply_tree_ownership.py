#!/usr/bin/env python3
"""Apply per-manifest uid/gid ownership to an extracted customer tree.

Replaces the legacy uniform ``chown -R 1001:1001`` (which broke VI images
carrying a 1000/1001 mixture). Every stock manifest entry keeps its own
recorded uid/gid; mutation-added entries use their recorded uid/gid or the
1001:1001 fallback for legacy records without ownership fields; mutation
``replaced`` entries that were absent from the stock image (e.g. the
md5sum-listed but image-absent tlr wav) infer uid/gid from a unanimous
same-directory stock sibling, else from the parent stock directory.

Root policy: new stock manifests always carry "/" recorded from UBIFS
root inode 1 (VI: 1000:1000 0755; never guessed). The host tree root (which
mkfs.ubifs -r turns into the image root) takes that exact uid/gid. A legacy
manifest without "/" (synthetic fixtures only) falls back to 1001:1001 and
is never used for VI.

Fail-closed: all paths/uids/gids/modes and every tree leaf (type + no
symlink ancestors) are preflighted BEFORE any chown. Any violation exits
nonzero with zero chowns. Never chmods (mode preserved). Never follows
symlinks: ``os.chown(..., follow_symlinks=False)`` + ``os.lstat`` only.

Usage:
  python3 tools/fw/apply_tree_ownership.py --tree <dir> \\
      --stock-manifest <stock.json> [--mut-manifest <mut.json>]
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

FALLBACK_UID = 1001
FALLBACK_GID = 1001
VALID_TYPES = ("dir", "reg", "symlink")
ABSENT = "(absent-in-image)"
MAX_ID = 0xFFFFFFFF


def _fail(msg: str) -> str:
    return f"OWNERSHIP-FAIL: {msg}"


def check_image_path(p) -> str | None:
    """Return error string when *p* is not a valid absolute POSIX image path."""
    if not isinstance(p, str) or not p:
        return "path must be a non-empty string"
    if "\0" in p or "\n" in p or "\r" in p:
        return f"bad path {p!r}: control characters"
    if "\\" in p or ":" in p:
        return f"bad path {p!r}: backslash/colon forbidden"
    if not p.startswith("/"):
        return f"bad path {p!r}: must be absolute"
    if p != "/" and p.endswith("/"):
        return f"bad path {p!r}: trailing slash"
    if len(p) > 4096:
        return f"bad path {p!r}: too long"
    if p == "/":
        return None
    parts = p.split("/")[1:]
    for part in parts:
        if part in ("", ".", ".."):
            return f"bad path {p!r}: empty/dot traversal"
    return None


def check_id(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= MAX_ID


def check_mode(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 0o7777


def load_stock_manifest(path: Path) -> tuple[dict | None, str | None]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, _fail(f"cannot read stock manifest: {exc}")
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        return None, _fail("stock manifest needs entries list")
    stock: dict[str, dict] = {}
    for i, r in enumerate(doc["entries"]):
        if not isinstance(r, dict):
            return None, _fail(f"stock entry #{i} not an object")
        p = r.get("path")
        err = check_image_path(p)
        if err is not None:
            return None, _fail(f"stock entry #{i}: {err}")
        if p in stock:
            return None, _fail(f"duplicate stock path {p!r}")
        t = r.get("type")
        if t not in VALID_TYPES:
            return None, _fail(f"stock {p}: bad type {t!r}")
        if not check_mode(r.get("mode")):
            return None, _fail(f"stock {p}: bad mode {r.get('mode')!r}")
        if not check_id(r.get("uid")) or not check_id(r.get("gid")):
            return None, _fail(f"stock {p}: bad uid/gid "
                               f"{r.get('uid')!r}/{r.get('gid')!r}")
        stock[p] = r
    return stock, None


def load_mut_manifest(path: Path | None) -> tuple[dict | None, str | None]:
    if path is None:
        return {"added": {}, "replaced_absent": []}, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, _fail(f"cannot read mut manifest: {exc}")
    if not isinstance(doc, dict):
        return None, _fail("mut manifest must be an object")
    raw_added = doc.get("added", [])
    raw_replaced = doc.get("replaced", {})
    if not isinstance(raw_added, list):
        return None, _fail("mut added must be a list")
    if not isinstance(raw_replaced, dict):
        return None, _fail("mut replaced must be an object")
    added: dict[str, dict] = {}
    for i, r in enumerate(raw_added):
        if not isinstance(r, dict):
            return None, _fail(f"mut added #{i} not an object")
        p = r.get("path")
        err = check_image_path(p)
        if err is not None:
            return None, _fail(f"mut added #{i}: {err}")
        if p in added:
            return None, _fail(f"duplicate mut added path {p!r}")
        if r.get("type") not in VALID_TYPES:
            return None, _fail(f"mut added {p}: bad type {r.get('type')!r}")
        if not check_mode(r.get("mode")):
            return None, _fail(f"mut added {p}: bad mode {r.get('mode')!r}")
        uid, gid = r.get("uid"), r.get("gid")
        if ("uid" in r) != ("gid" in r):
            return None, _fail(f"mut added {p}: uid/gid must pair")
        if "uid" in r and (not check_id(uid) or not check_id(gid)):
            return None, _fail(f"mut added {p}: bad uid/gid {uid!r}/{gid!r}")
        added[p] = r
    replaced_absent: list[str] = []
    for p, exp in raw_replaced.items():
        err = check_image_path(p)
        if err is not None:
            return None, _fail(f"mut replaced {p!r}: {err}")
        if not isinstance(exp, dict):
            return None, _fail(f"mut replaced {p}: bad record")
        old = exp.get("old_sha256")
        if old == ABSENT:
            if p in replaced_absent:
                return None, _fail(f"duplicate mut replaced path {p!r}")
            replaced_absent.append(p)
        elif not isinstance(old, str):
            return None, _fail(f"mut replaced {p}: bad old_sha256")
    return {"added": added, "replaced_absent": replaced_absent,
            "replaced_raw": raw_replaced}, None


def parent_image_path(p: str) -> str:
    if p == "/":
        return "/"
    parent = p.rsplit("/", 1)[0]
    return parent if parent else "/"


def infer_absent_uid_gid(img_path: str,
                         stock: dict[str, dict]) -> tuple[tuple[int, int] | None, str | None]:
    parent = parent_image_path(img_path)
    sibs = [r for q, r in stock.items()
            if q != img_path and parent_image_path(q) == parent
            and r.get("type") == "reg"]
    if sibs:
        pairs = {(r["uid"], r["gid"]) for r in sibs}
        if len(pairs) != 1:
            return None, _fail(f"replaced-absent {img_path}: ambiguous "
                               f"sibling uid/gid {sorted(pairs)}")
        return next(iter(pairs)), None
    prec = stock.get(parent)
    if prec is not None and check_id(prec.get("uid")) and check_id(prec.get("gid")):
        return (prec["uid"], prec["gid"]), None
    return None, _fail(f"replaced-absent {img_path}: no sibling or parent stock "
                       f"uid/gid to infer")


def host_for(tree: Path, img_path: str) -> Path:
    if img_path == "/":
        return tree
    return tree / img_path.lstrip("/")


def expected_type_ok(st, expected: str) -> bool:
    if expected == "dir":
        return stat.S_ISDIR(st.st_mode)
    if expected == "reg":
        return stat.S_ISREG(st.st_mode)
    if expected == "symlink":
        return stat.S_ISLNK(st.st_mode)
    return False


def preflight(tree: Path, stock: dict[str, dict],
              mut: dict) -> tuple[list[tuple[str, Path, int, int]] | None, str | None]:
    """Validate everything; return plan [(img, host, uid, gid)] or error.

    No chown is performed here. Callers must not write on error.
    """
    # Tree root itself: must exist, be a real dir, never a symlink.
    try:
        tst = os.lstat(tree)
    except OSError as exc:
        return None, _fail(f"tree missing: {exc}")
    if stat.S_ISLNK(tst.st_mode):
        return None, _fail("tree root must not be a symlink")
    if not stat.S_ISDIR(tst.st_mode):
        return None, _fail("tree root must be a directory")

    added: dict[str, dict] = mut["added"]
    replaced_absent: list[str] = mut["replaced_absent"]

    # Overlap rules: added must be new vs stock; absent must be new vs both.
    for p in added:
        if p == "/":
            return None, _fail("mut added must not be /")
        if p in stock:
            return None, _fail(f"mut added {p} collides with stock")
    for p in replaced_absent:
        if p == "/":
            return None, _fail("mut replaced-absent must not be /")
        if p in stock:
            return None, _fail(f"mut replaced-absent {p} collides with stock")
        if p in added:
            return None, _fail(f"mut replaced-absent {p} collides with added")

    # Resolve ownership for every target first (validates ids/modes already
    # checked at load; infers absent).
    targets: list[tuple[str, str, int, int]] = []  # (img, type, uid, gid)
    has_root_record = "/" in stock
    if has_root_record:
        r = stock["/"]
        if r.get("type") != "dir":
            return None, _fail("stock / must be dir")
        targets.append(("/", "dir", r["uid"], r["gid"]))
    else:
        targets.append(("/", "dir", FALLBACK_UID, FALLBACK_GID))
    for p in sorted(stock):
        if p == "/":
            continue
        r = stock[p]
        targets.append((p, r["type"], r["uid"], r["gid"]))
    for p in sorted(added):
        r = added[p]
        if "uid" in r:
            targets.append((p, r["type"], r["uid"], r["gid"]))
        else:
            targets.append((p, r["type"], FALLBACK_UID, FALLBACK_GID))
    for p in sorted(replaced_absent):
        pair, err = infer_absent_uid_gid(p, stock)
        if err is not None:
            return None, err
        targets.append((p, "reg", pair[0], pair[1]))

    # Validate tree leaves + no symlink ancestors (lstat only, never follow).
    plan: list[tuple[str, Path, int, int]] = []
    for img, etype, uid, gid in targets:
        host = host_for(tree, img)
        # Ancestors from tree root through parent of leaf must be real dirs.
        if img == "/":
            rel_parts: list[str] = []
        else:
            rel_parts = img.lstrip("/").split("/")
        # Check tree root already done; check each intermediate dir.
        cur = tree
        for depth, part in enumerate(rel_parts[:-1] if rel_parts else []):
            cur = cur / part
            try:
                ast = os.lstat(cur)
            except OSError:
                return None, _fail(f"missing ancestor {cur} for {img}")
            if stat.S_ISLNK(ast.st_mode):
                return None, _fail(f"symlink ancestor {cur} for {img}")
            if not stat.S_ISDIR(ast.st_mode):
                return None, _fail(f"non-dir ancestor {cur} for {img}")
        try:
            lst = os.lstat(host)
        except OSError:
            return None, _fail(f"missing tree path for {img} ({host})")
        if img != "/" and stat.S_ISLNK(lst.st_mode):
            if etype != "symlink":
                return None, _fail(f"unexpected symlink at {img}")
        elif stat.S_ISLNK(lst.st_mode):
            if etype != "symlink":
                return None, _fail(f"unexpected symlink at {img}")
        if not expected_type_ok(lst, etype):
            return None, _fail(f"type mismatch at {img}: want {etype}")
        plan.append((img, host, uid, gid))
    return plan, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--stock-manifest", type=Path, required=True)
    ap.add_argument("--mut-manifest", type=Path, default=None)
    args = ap.parse_args(argv)

    tree = args.tree
    stock, err = load_stock_manifest(args.stock_manifest)
    if err is not None:
        print(err, file=sys.stderr)
        return 1
    assert stock is not None
    mut, err = load_mut_manifest(args.mut_manifest)
    if err is not None:
        print(err, file=sys.stderr)
        return 1
    assert mut is not None
    plan, err = preflight(tree, stock, mut)
    if err is not None:
        print(err, file=sys.stderr)
        return 1
    assert plan is not None

    n_stock = sum(1 for img, _, _, _ in plan if img in stock and img != "/")
    n_added = sum(1 for img, _, _, _ in plan if img in mut["added"])
    n_absent = len(mut["replaced_absent"])
    # All validation passed: now (and only now) perform ownership writes.
    try:
        for _img, host, uid, gid in plan:
            os.chown(host, uid, gid, follow_symlinks=False)
    except OSError as exc:
        print(_fail(f"chown failed: {exc}"), file=sys.stderr)
        return 1
    n_root = 1
    print(f"OWNERSHIP-OK: {len(plan)} paths (root={n_root} "
          f"stock={n_stock} added={n_added} inferred={n_absent})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
