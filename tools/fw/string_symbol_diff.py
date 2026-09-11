#!/usr/bin/env python3
"""Compare printable strings and, when available, ELF symbols of two binaries."""
from __future__ import annotations
import argparse, json, re, shutil, subprocess
from pathlib import Path

def strings(path: Path, minimum=4):
    data = path.read_bytes()
    pat = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    return {m.group().decode("ascii", "replace") for m in pat.finditer(data)}

def symbols(path: Path):
    exe = shutil.which("readelf")
    if not exe:
        return None
    cp = subprocess.run([exe, "-Ws", str(path)], text=True, capture_output=True, check=False)
    if cp.returncode:
        return None
    out = set()
    for line in cp.stdout.splitlines():
        cols = line.split()
        if len(cols) >= 8 and cols[0].rstrip(":").isdigit():
            out.add(cols[-1])
    return out

def delta(a, b):
    return {"left_only": sorted(a - b), "right_only": sorted(b - a), "common_count": len(a & b), "left_count": len(a), "right_count": len(b)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path)
    ap.add_argument("--min-string", type=int, default=4)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    sa, sb = strings(args.left, args.min_string), strings(args.right, args.min_string)
    result = {"left": str(args.left), "right": str(args.right), "strings": delta(sa, sb)}
    ya, yb = symbols(args.left), symbols(args.right)
    result["symbols"] = delta(ya, yb) if ya is not None and yb is not None else {"available": False}
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)

if __name__ == "__main__":
    main()
