#!/usr/bin/env python3
"""Compare two read-only C2M ADAS runtime captures (EN vs VI).

Usage:
  python tools/fw/compare_c2m_runtime_capture.py <capture_en_dir> <capture_vi_dir> [-o out.json] [--markdown out.md]

Compares bootargs/memmap/modules/process/allocation/ring/config-hashes.
Graceful on missing files: every absent input yields "UNKNOWN (missing file)"
instead of an exception. Never reads secret file bytes; only compares the
hash/size/mode rows recorded by capture_c2m_adas_runtime.sh.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from typing import Any

FILES = [
    "proc_cmdline.txt", "proc_meminfo.txt", "proc_iomem.txt",
    "proc_buddyinfo.txt", "proc_pagetypeinfo.txt", "proc_modules.txt",
    "lsmod.txt", "ps.txt", "ps_w.txt", "processes.tsv",
    "dev_listing.txt", "dmesg_filtered.txt", "dmesg_full.txt",
    "proc_sysvipc_shm.txt", "config_hashes.tsv", "high_value_files.tsv",
    "ports_of_interest.txt", "proc_net_tcp.txt", "MANIFEST.txt",
]

def read(p: Path) -> str | None:
    try:
        if not p.is_file():
            return None
        if p.stat().st_size > 4_000_000:
            return p.read_text(encoding="utf-8", errors="replace")[:4_000_000]
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

def norm_cmdline(s: str | None) -> dict[str, Any]:
    if s is None:
        return {"status": "UNKNOWN (missing file)"}
    toks = s.strip().split()
    out: dict[str, Any] = {"raw": s.strip()[:2000], "has_fb_reservation": "mmap_reserved=fb" in s}
    m = re.search(r"mmap_reserved=([^\s]+)", s)
    out["mmap_reserved"] = m.group(1) if m else None
    m2 = re.search(r"cma=([^\s]+)", s)
    out["cma"] = m2.group(1) if m2 else None
    m3 = re.search(r"mma_heap=([^\s]+)", s)
    out["mma_heap"] = m3.group(1) if m3 else None
    return out

def procs(tsv: str | None) -> dict[str, Any]:
    if tsv is None:
        return {"status": "UNKNOWN (missing file)"}
    rows = [line.split("\t") for line in tsv.splitlines() if line.strip()]
    def has(n: str) -> list[str]:
        n = n.lower()
        return [r[0] for r in rows if len(r) >= 2 and n in (r[1] + " " + (r[2] if len(r) > 2 else "")).lower()]
    return {
        "total": len(rows),
        "adas_pids": has("adas"),
        "cardv_pids": has("cardv"),
        "mutualism_pids": has("mutualism"),
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("en", type=Path)
    ap.add_argument("vi", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--markdown", type=Path, default=None)
    args = ap.parse_args()
    en: Path = args.en
    vi: Path = args.vi
    result: dict[str, Any] = {
        "en": str(en), "vi": str(vi),
        "deltas": {}, "missing": [], "verdict": "UNKNOWN",
    }
    for fn in FILES:
        a = read(en / fn)
        b = read(vi / fn)
        if a is None and b is None:
            result["missing"].append(fn)
            result["deltas"][fn] = "UNKNOWN (missing in both captures)"
        elif a is None or b is None:
            side = "EN" if a is None else "VI"
            result["deltas"][fn] = f"UNKNOWN ({side} missing file; no comparison)"
            result["missing"].append(fn)
        elif a == b:
            result["deltas"][fn] = "SAME"
        else:
            la = len(a.splitlines())
            lb = len(b.splitlines())
            result["deltas"][fn] = f"DIFFERENT ({la} vs {lb} lines; see per-area parsers)"
    e_cmd = norm_cmdline(read(en / "proc_cmdline.txt"))
    v_cmd = norm_cmdline(read(vi / "proc_cmdline.txt"))
    result["bootargs"] = {"en": e_cmd, "vi": v_cmd}
    result["processes"] = {"en": procs(read(en / "processes.tsv")), "vi": procs(read(vi / "processes.tsv"))}
    for key in ("proc_meminfo.txt", "proc_iomem.txt", "proc_buddyinfo.txt", "config_hashes.tsv"):
        a = read(en / key)
        b = read(vi / key)
        tag = "memmap" if "iomem" in key else ("allocation" if "meminfo" in key or "buddy" in key else "config")
        result.setdefault(tag, {})[key] = result["deltas"].get(key, "UNKNOWN")
    diff_count = sum(1 for v in result["deltas"].values() if isinstance(v, str) and v.startswith("DIFFERENT"))
    same_count = sum(1 for v in result["deltas"].values() if v == "SAME")
    unk_count = sum(1 for v in result["deltas"].values() if isinstance(v, str) and v.startswith("UNKNOWN"))
    result["summary"] = {"same": same_count, "different": diff_count, "unknown_missing": unk_count}
    if diff_count == 0 and unk_count == 0:
        result["verdict"] = "CAPTURES_IDENTICAL_ON_COMPARED_FILES"
    elif diff_count > 0:
        result["verdict"] = "DELTA_FOUND_SEE_BOOTARGS_MEMMAP_PROCESS_ALLOCATION_RING_CONFIG"
    else:
        result["verdict"] = "INCONCLUSIVE_MISSING_FILES"
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    if args.markdown:
        lines = [
            "# C2M runtime capture comparison", "",
            f"EN: `{en}`", f"VI: `{vi}`", "",
            f"Verdict: `{result['verdict']}`", "",
            f"Same: {same_count} Different: {diff_count} Unknown/missing: {unk_count}", "",
            "## Per-file deltas", "",
        ]
        for k in FILES:
            lines.append(f"- `{k}`: {result['deltas'].get(k)}")
        lines += ["", "## Bootargs", "", f"- EN fb reservation: {e_cmd.get('has_fb_reservation')} `{e_cmd.get('mmap_reserved')}`", f"- VI fb reservation: {v_cmd.get('has_fb_reservation')} `{v_cmd.get('mmap_reserved')}`", ""]
        args.markdown.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
