#!/usr/bin/env python3
"""Inspect stock C2M model blobs (read-only, no decryption beyond header stats).

Usage:
  python3 tools/reverse/c2m/inspect_stock_model.py build/fw_bin_en/adas [--m0 HEX --model-txt params/model.txt]
  python3 tools/reverse/c2m/inspect_stock_model.py <d0.bin> <v_a.bin> ...

For adas input: uses built-in EN offsets/sizes (verified SHAs) unless --m0/--model-txt
decrypt path is added later. For raw blob inputs: reports size/sha/entropy/header/magic/strings.
Does NOT attempt AES payload decrypt (key handling out of scope for research harness).
"""
from __future__ import annotations
import argparse, hashlib, math, re
from collections import Counter
from pathlib import Path

EN_MODELS = [
    ("d0", 0x1747fe, 0x2b9000, "0b5533eea7af01c3075b517a36a9238c7d91c82dec5fc7c34c87307da725d4f9"),
    ("v_a", 0x431994, 0x1ea000, "342db12adb9bbeaf83595fbb7178bd2ba6b5de06f14c8fb476c4d52cad23142a"),
    ("v_t", 0x61d75c, 0x40000, "f63b18df7b5d0c6e22241fc743e51ef8a5e27750503e481fabc509143108d0cf"),
    ("p_r", 0x661b44, 0x189000, "fb5795ec70b7d2cfdf06ce61a1fb627e18b4008d811ca1c73ddf7b9ca47239a9"),
    ("road", 0x7ee408, 0x2fe000, "4bc0e6f262e919beeba7f384da4a8347b39943066a05963355b46e404f704914"),
    ("tl", 0xaf14bc, 0x25000, "ce2da36309acab718205d63b566c45489a3683adfa412e815670abf00d424753"),
]

def entropy(b: bytes) -> float:
    c = Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())

def report_blob(name: str, blob: bytes, exp_sha: str | None = None):
    sha = hashlib.sha256(blob).hexdigest()
    ent = entropy(blob) if blob else 0.0
    hdr = blob[:64].hex() if len(blob) >= 64 else blob.hex()
    hstrs = [m.group().decode(errors="replace") for m in re.finditer(rb'[ -~]{4,}', blob[:4096])]
    alln = sum(1 for _ in re.finditer(rb'[ -~]{5,}', blob))
    magics = {}
    for mg in [b"ONNX", b"TFL3", b"IPU", b"MSTAR", b"SSTAR", b"NCNN", b"caffe"]:
        if mg in blob[:256]:
            magics[mg.decode()] = True
    print(f"{name}: size={len(blob)} sha={sha} match={sha==exp_sha if exp_sha else 'n/a'}")
    print(f"  entropy={ent:.3f} header64={hdr}")
    print(f"  header_strs={hstrs[:10]} total_printable_runs={alln} magics={list(magics) or 'none'}")
    return {"name": name, "size": len(blob), "sha256": sha, "match": (sha == exp_sha if exp_sha else None),
            "entropy": round(ent, 3), "header64": hdr, "magics": list(magics)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    args = ap.parse_args()
    for p in args.inputs:
        data = p.read_bytes()
        if len(data) > 6_000_000 and data[:4] == b"\x7fELF":
            print(f"== adas {p} ({len(data)} B) — carving 6 known EN blobs")
            for name, off, sz, exp in EN_MODELS:
                blob = data[off:off+sz]
                report_blob(name, blob, exp)
        else:
            report_blob(p.name, data)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
