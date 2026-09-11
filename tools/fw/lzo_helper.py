#!/usr/bin/env python3
"""LZO1X block decompression via local helper binary (no system liblzo2 needed).

Helper: build/lzo_blockdec.exe (compiled from upstream LZO minilzo at tool
time; see docs/reverse/UBIFS_EXTRACTION_V1.md). Set C2M_LZO_HELPER to override.
Batch protocol over one subprocess: [u32le comp_len][u32le out_len][bytes] ...
"""
from __future__ import annotations
import os
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def helper_path() -> Path | None:
    env = os.environ.get("C2M_LZO_HELPER")
    if env:
        p = Path(env)
        return p if p.is_file() else None
    for cand in (ROOT / "build" / "lzo_blockdec.exe", ROOT / "build" / "lzo_blockdec"):
        if cand.is_file():
            return cand
    return None


def batch_decompress(blocks: list[tuple[bytes, int]]) -> list[bytes]:
    """Decompress [(payload, usize)] via one helper process. Order preserved."""
    helper = helper_path()
    if helper is None:
        raise RuntimeError(
            "LZO helper not found. Build it: gcc -O2 -o build/lzo_blockdec[.exe] "
            "build/lzo_blockdec.c <minilzo.c> -I <minilzo-dir> -I <lzo-include/lzo> "
            "(see docs/reverse/UBIFS_EXTRACTION_V1.md)")
    stdin = b"".join(struct.pack("<II", len(p), u) + p for p, u in blocks)
    proc = subprocess.run([str(helper)], input=stdin, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"lzo helper failed rc={proc.returncode}: {proc.stderr.decode()[:500]}")
    out, pos = [], 0
    for _, u in blocks:
        out.append(proc.stdout[pos:pos + u])
        pos += u
    if pos != len(proc.stdout):
        raise RuntimeError(f"lzo helper byte mismatch {pos} != {len(proc.stdout)}")
    return out
