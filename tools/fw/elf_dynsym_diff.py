#!/usr/bin/env python3
"""Compare ELF symbol value/size/type between two binaries using readelf."""
from __future__ import annotations
import argparse, json, shutil, subprocess
from pathlib import Path

def load(path: Path):
    exe = shutil.which("readelf")
    if not exe:
        raise SystemExit("readelf is required")
    cp = subprocess.run([exe, "-Ws", str(path)], text=True, capture_output=True, check=True)
    out = {}
    for line in cp.stdout.splitlines():
        cols = line.split()
        if len(cols) < 8 or not cols[0].endswith(":"):
            continue
        try:
            int(cols[0][:-1]); value = int(cols[1], 16); size = int(cols[2])
        except ValueError:
            continue
        name = cols[7]
        item = {"value": value, "value_hex": hex(value), "size": size, "type": cols[3], "bind": cols[4], "vis": cols[5], "ndx": cols[6]}
        prev = out.get(name)
        if prev is None or (prev["ndx"] == "UND" and item["ndx"] != "UND") or item["size"] > prev["size"]:
            out[name] = item
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    a, b = load(args.left), load(args.right)
    common = sorted(set(a) & set(b))
    rows = []
    for name in common:
        la, rb = a[name], b[name]
        changes = {k: (la[k], rb[k]) for k in ("value", "size", "type", "bind", "vis", "ndx") if la[k] != rb[k]}
        if changes:
            rows.append({"name": name, "left": la, "right": rb, "changes": changes})
    result = {"left": str(args.left), "right": str(args.right), "left_symbols": len(a), "right_symbols": len(b), "common_symbols": len(common), "left_only": sorted(set(a) - set(b)), "right_only": sorted(set(b) - set(a)), "changed_common": rows}
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"left_symbols": len(a), "right_symbols": len(b), "common_symbols": len(common), "left_only": len(result["left_only"]), "right_only": len(result["right_only"]), "changed_common": len(rows)}, indent=2))

if __name__ == "__main__":
    main()
