#!/usr/bin/env python3
"""Candidate-E oneed_cust audio mutator (fail-closed).

Replaces explicit /audio/*.wav assets inside an EXTRACTED oneed_cust tree with
format-checked Vietnamese donor bytes (RIFF/WAVE PCM16 mono 24 kHz, <=1MB,
same encoding gate as the ADAS wav swaps), preserving mode/ownership metadata
(the rebuild driver applies manifest ownership on Linux).

Only these wavs may change; no file is added, removed or renamed. All specs
are validated BEFORE any write; any violation exits nonzero with zero writes.

The emitted mutation manifest has kind=oneed and the same 'replaced' record
shape consumed by tools/fw/verify_b_manifest.py (hook-less kind; see
verify_b_manifest kind handling).

Usage:
  python3 tools/fw/mutate_oneed.py --tree <oneed-tree> --manifest <stock.json> \\
      --audio-replacements <list.json> --out-manifest <mutation.json> \\
      [--expect-count N]

audio-replacements JSON: list of {"path": "/audio/X.wav", "file": "<local wav>"}
"""
from __future__ import annotations

import argparse
import hashlib
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutate_customer import check_wav, has_symlink  # noqa: E402

AUDIO_PREFIX = "/audio/"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="stock oneed_cust manifest JSON (base integrity gate)")
    ap.add_argument("--audio-replacements", type=Path, required=True,
                    help="JSON list of {path (image-absolute), file (local wav)}")
    ap.add_argument("--out-manifest", type=Path, required=True)
    ap.add_argument("--expect-count", type=int, default=None)
    args = ap.parse_args()

    if has_symlink(args.tree) or not args.tree.is_dir():
        print("MUTATE-FAIL: tree must be a nonsymlink directory")
        return 1
    try:
        stock = {r["path"]: r for r in
                 json.loads(args.manifest.read_text(encoding="utf-8"))["entries"]}
    except Exception as exc:  # noqa: BLE001
        print(f"MUTATE-FAIL: bad stock manifest: {exc}")
        return 1
    try:
        specs = json.loads(args.audio_replacements.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"MUTATE-FAIL: bad audio replacements JSON: {exc}")
        return 1
    if not isinstance(specs, list) or not specs:
        print("MUTATE-FAIL: audio replacements must be a non-empty list")
        return 1
    if args.expect_count is not None and len(specs) != args.expect_count:
        print(f"MUTATE-FAIL: expected {args.expect_count} replacements, got {len(specs)}")
        return 1

    writes: list[tuple[Path, bytes]] = []
    replaced: dict[str, dict] = {}
    seen: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) != {"path", "file"}:
            print("MUTATE-FAIL: each spec must be exactly {path, file}")
            return 1
        img_path, src = spec["path"], Path(spec["file"])
        if (not isinstance(img_path, str)
                or not img_path.startswith(AUDIO_PREFIX)
                or not img_path.endswith(".wav")
                or ".." in img_path.split("/") or "\\" in img_path
                or img_path.count("/") != 2):
            print(f"MUTATE-FAIL: invalid oneed audio target path {img_path!r}")
            return 1
        if img_path in seen:
            print(f"MUTATE-FAIL: duplicate audio target: {img_path}")
            return 1
        seen.add(img_path)
        row = stock.get(img_path)
        if row is None or row.get("type") != "reg":
            print(f"MUTATE-FAIL: {img_path} not a stock regular file")
            return 1
        target = args.tree / img_path.lstrip("/")
        if has_symlink(target) or not target.is_file():
            print(f"MUTATE-FAIL: tree target missing/nonregular: {img_path}")
            return 1
        try:
            wav = src.read_bytes()
        except Exception as exc:  # noqa: BLE001
            print(f"MUTATE-FAIL: cannot read audio input {src}: {exc}")
            return 1
        try:
            check_wav(wav, img_path)
        except ValueError as exc:
            print(f"MUTATE-FAIL: {exc}")
            return 1
        old_bytes = target.read_bytes()
        old_sha = hashlib.sha256(old_bytes).hexdigest()
        if old_sha != row.get("sha256") or len(old_bytes) != row.get("size"):
            print(f"MUTATE-FAIL: tree {img_path} != stock manifest")
            return 1
        if wav == old_bytes:
            print(f"MUTATE-FAIL: replacement identical to current bytes: {img_path}")
            return 1
        writes.append((target, wav))
        replaced[img_path] = {"old_sha256": old_sha, "old_size": len(old_bytes),
                              "new_sha256": hashlib.sha256(wav).hexdigest(),
                              "new_size": len(wav)}

    # Validation complete; apply the exactly-recorded byte swaps only.
    for target, data in writes:
        target.write_bytes(data)

    doc = {"kind": "oneed",
           "added": [],
           "modified": [],
           "replaced": replaced}
    if args.out_manifest.exists():
        print("MUTATE-FAIL: out-manifest already exists (never overwrite)")
        return 1
    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"replaced": len(replaced),
                      "paths": sorted(replaced)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
