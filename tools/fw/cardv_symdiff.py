#!/usr/bin/env python3
"""Gate A cardv ELF symbol diff from ORIGINAL binaries (readelf only, no LLVM).

Re-derives: total symbols, EN-only / VI-only names, same-name size changes.
Outputs JSON + prints the security-relevant rows (GPS/screen/ringbuf).
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

ROW = re.compile(r"^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s*(.*)$")


def dynsym(path: Path) -> dict[str, dict]:
    try:
        out = subprocess.run(["readelf", "--dyn-syms", "-W", str(path)],
                             capture_output=True, text=True, check=True).stdout
    except FileNotFoundError as e:
        raise SystemExit("readelf not found on PATH (install binutils/WinLibs)") from e
    syms: dict[str, dict] = {}
    for line in out.splitlines():
        m = ROW.match(line)
        if m:
            syms[m.group(5).strip()] = {"value": m.group(1), "size": int(m.group(2)),
                                        "type": m.group(3), "bind": m.group(4)}
    return syms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=Path, default=Path("build/fw_bin_en/cardv"))
    ap.add_argument("--vi", type=Path, default=Path("build/fw_bin_vi/cardv"))
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/reverse/EVIDENCE_CARDV_SYMDIFF.json"))
    args = ap.parse_args()
    en, vi = dynsym(args.en), dynsym(args.vi)
    se, sv = set(en), set(vi)
    common = se & sv
    changed = sorted((n, en[n]["size"], vi[n]["size"]) for n in common if en[n]["size"] != vi[n]["size"])
    doc = {"en_symbols": len(en), "vi_symbols": len(vi), "common": len(common),
           "en_only": sorted(se - sv), "vi_only": sorted(sv - se),
           "size_changed": [{"name": n, "en_size": a, "vi_size": b} for n, a, b in changed]}
    args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"EN={len(en)} VI={len(vi)} common={len(common)}")
    print("EN-only:", sorted(se - sv))
    print("VI-only:", sorted(sv - se))
    print(f"size-changed: {len(changed)}")
    for n, a, b in changed:
        print(f"  {a} -> {b}  {n}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
