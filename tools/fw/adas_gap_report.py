#!/usr/bin/env python3
"""Analyze interstitial regions around embedded C2M ADAS model blobs.

Inputs are one or two stock `adas` executables. Model offsets/sizes may be
provided by JSON emitted from `adas_m0_directory.py`; if omitted, this script
imports that sibling tool and decrypts `--m0` directly.

The report is read-only and intended for good/bad differential analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

DEFAULT_TAIL_MARKER = b"--switch_file="


def entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = [0] * 256
    for b in buf:
        counts[b] += 1
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def sha256(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()


def block_stats(buf: bytes, block: int = 16) -> dict[str, Any]:
    blocks = [buf[i : i + block] for i in range(0, len(buf) - block + 1, block)]
    unique = len(set(blocks))
    total = len(blocks)
    return {
        "block_size": block,
        "full_blocks": total,
        "unique_blocks": unique,
        "repeated_blocks": total - unique,
        "unique_ratio": round(unique / total, 6) if total else 1.0,
    }


def ascii_ratio(buf: bytes) -> float:
    if not buf:
        return 0.0
    printable = sum(1 for b in buf if b in (9, 10, 13) or 32 <= b <= 126)
    return printable / len(buf)


def zero_ratio(buf: bytes) -> float:
    return (buf.count(0) / len(buf)) if buf else 0.0


def common_prefix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def common_suffix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def aligned_equal_ratio(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b))
    if not n:
        return 1.0 if len(a) == len(b) else 0.0
    return sum(x == y for x, y in zip(a[:n], b[:n])) / n


def block_jaccard(a: bytes, b: bytes, block: int = 16) -> float:
    sa = {a[i : i + block] for i in range(0, len(a) - block + 1, block)}
    sb = {b[i : i + block] for i in range(0, len(b) - block + 1, block)}
    if not sa and not sb:
        return 1.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def true_elf_end(binary: Path) -> int:
    try:
        from elf_overlay_report import report as elf_report
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from elf_overlay_report import report as elf_report
    return int(elf_report(binary)["overlay_start"])


def load_directory_json(path: Path) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    records = obj.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected top-level records list")
    return records


def decrypt_directory(binary: Path, model_txt: Path | None) -> list[dict[str, Any]]:
    try:
        from adas_m0_directory import report as m0_report
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from adas_m0_directory import report as m0_report
    return m0_report(binary, model_txt, "de091ce6cb35733540c86656fa1692e8")["records"]


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, rec in enumerate(records):
        name = str(rec.get("name", f"model_{i}"))
        off = int(rec["offset"] if "offset" in rec else int(rec["offset_hex"], 0))
        size = int(rec["size"] if "size" in rec else int(rec["size_hex"], 0))
        out.append({"name": name, "offset": off, "size": size, "end": off + size})
    out.sort(key=lambda r: r["offset"])
    for prev, cur in zip(out, out[1:]):
        if prev["end"] > cur["offset"]:
            raise ValueError(f"model overlap: {prev['name']} -> {cur['name']}")
    return out


def region_metrics(name: str, start: int, end: int, data: bytes) -> dict[str, Any]:
    if start < 0 or end < start or end > len(data):
        raise ValueError(f"invalid gap {name}: {start:#x}..{end:#x} for size {len(data):#x}")
    buf = data[start:end]
    return {
        "name": name,
        "start": start,
        "start_hex": hex(start),
        "end": end,
        "end_hex": hex(end),
        "size": len(buf),
        "size_hex": hex(len(buf)),
        "sha256": sha256(buf),
        "entropy_bits_per_byte": round(entropy(buf), 6),
        "ascii_ratio": round(ascii_ratio(buf), 6),
        "zero_ratio": round(zero_ratio(buf), 6),
        "head16_hex": buf[:16].hex(),
        "tail16_hex": buf[-16:].hex() if buf else "",
        "block16": block_stats(buf, 16),
        "block32": block_stats(buf, 32),
    }


def single_report(binary: Path, records: list[dict[str, Any]], tail_marker: bytes) -> dict[str, Any]:
    data = binary.read_bytes()
    records = normalize_records(records)
    elf_end = true_elf_end(binary)
    tail_start = data.rfind(tail_marker)
    if tail_start < 0:
        raise ValueError(f"{binary}: tail marker {tail_marker!r} not found")
    if not records:
        raise ValueError("model directory is empty")

    gaps = []
    cursor = elf_end
    for rec in records:
        gaps.append(region_metrics(f"before_{rec['name']}", cursor, rec["offset"], data))
        cursor = rec["end"]
    gaps.append(region_metrics("before_flags", cursor, tail_start, data))

    return {
        "binary": str(binary),
        "file_size": len(data),
        "file_sha256": sha256(data),
        "elf_end": elf_end,
        "elf_end_hex": hex(elf_end),
        "tail_start": tail_start,
        "tail_start_hex": hex(tail_start),
        "tail_size": len(data) - tail_start,
        "models": records,
        "gaps": gaps,
        "gap_total": sum(g["size"] for g in gaps),
    }


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    lg = {g["name"]: g for g in left["gaps"]}
    rg = {g["name"]: g for g in right["gaps"]}
    rows = []
    ldata = Path(left["binary"]).read_bytes()
    rdata = Path(right["binary"]).read_bytes()
    for name in [g["name"] for g in left["gaps"]]:
        if name not in rg:
            continue
        a, b = lg[name], rg[name]
        abuf = ldata[a["start"] : a["end"]]
        bbuf = rdata[b["start"] : b["end"]]
        rows.append({
            "name": name,
            "left_size": a["size"],
            "right_size": b["size"],
            "size_delta": b["size"] - a["size"],
            "size_delta_hex": hex(b["size"] - a["size"]) if b["size"] >= a["size"] else f"-0x{a['size']-b['size']:x}",
            "identical": abuf == bbuf,
            "common_prefix": common_prefix(abuf, bbuf),
            "common_suffix": common_suffix(abuf, bbuf),
            "aligned_equal_ratio": round(aligned_equal_ratio(abuf, bbuf), 6),
            "block16_jaccard": round(block_jaccard(abuf, bbuf, 16), 6),
            "left_entropy": a["entropy_bits_per_byte"],
            "right_entropy": b["entropy_bits_per_byte"],
        })
    return {
        "left": left["binary"],
        "right": right["binary"],
        "file_size_delta": right["file_size"] - left["file_size"],
        "gap_total_delta": right["gap_total"] - left["gap_total"],
        "gaps": rows,
    }


def markdown(rep: dict[str, Any]) -> str:
    lines = ["# ADAS interstitial gap report", ""]
    if "comparison" not in rep:
        reps = [("binary", rep)]
    else:
        reps = [("left", rep["left_report"]), ("right", rep["right_report"])]
    for label, r in reps:
        lines += [f"## {label}: `{r['binary']}`", "", "| Gap | Size | Entropy | ASCII | Zero | SHA-256 |", "|---|---:|---:|---:|---:|---|"]
        for g in r["gaps"]:
            lines.append(f"| `{g['name']}` | {g['size']} | {g['entropy_bits_per_byte']:.6f} | {g['ascii_ratio']:.4f} | {g['zero_ratio']:.4f} | `{g['sha256']}` |")
        lines.append("")
    if "comparison" in rep:
        c = rep["comparison"]
        lines += ["## Comparison", "", "| Gap | EN/left | VI/right | Delta | Prefix | Suffix | Equal@offset | 16B Jaccard |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for g in c["gaps"]:
            lines.append(f"| `{g['name']}` | {g['left_size']} | {g['right_size']} | {g['size_delta']:+d} | {g['common_prefix']} | {g['common_suffix']} | {g['aligned_equal_ratio']:.4f} | {g['block16_jaccard']:.4f} |")
        lines += ["", f"Total gap delta: **{c['gap_total_delta']:+d} bytes**", f"File-size delta: **{c['file_size_delta']:+d} bytes**", ""]
    return "\n".join(lines)


def parse_marker(s: str) -> bytes:
    return s.encode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path, nargs="?")
    ap.add_argument("--left-directory-json", type=Path)
    ap.add_argument("--right-directory-json", type=Path)
    ap.add_argument("--left-model-txt", type=Path)
    ap.add_argument("--right-model-txt", type=Path)
    ap.add_argument("--tail-marker", default="--switch_file=")
    ap.add_argument("-o", "--output", type=Path, help="write JSON report")
    ap.add_argument("--markdown", type=Path, help="also write Markdown summary")
    args = ap.parse_args()

    lrec = load_directory_json(args.left_directory_json) if args.left_directory_json else decrypt_directory(args.left, args.left_model_txt)
    left = single_report(args.left, lrec, parse_marker(args.tail_marker))

    if args.right:
        rrec = load_directory_json(args.right_directory_json) if args.right_directory_json else decrypt_directory(args.right, args.right_model_txt)
        right = single_report(args.right, rrec, parse_marker(args.tail_marker))
        result = {"left_report": left, "right_report": right, "comparison": compare(left, right)}
    else:
        result = left

    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(result), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
