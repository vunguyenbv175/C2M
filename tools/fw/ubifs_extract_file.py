#!/usr/bin/env python3
"""Minimal read-only UBIFS single-file extractor for C2M firmware analysis.

This intentionally implements only the on-flash node types needed to reconstruct
regular files from the C2M customer UBIFS images. It does not mount, repair or
modify the image.

Supported data compression:
  0 = none
  1 = LZO1X (via system liblzo2)
  2 = zlib
  3 = zstd (optional Python zstandard package)

Typical pipeline:
  python3 tools/fw/carve_upgrade.py firmware.tar -o carved/
  python3 tools/fw/ubifs_extract_file.py carved/customer.bin /minieye/adas/adas -o adas
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import struct
import zlib
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

UBIFS_MAGIC = b"1\x18\x10\x06"  # little-endian 0x06101831
COMMON_HDR_SIZE = 24
DENT_NODE_MIN = 56
INO_NODE_MIN = 160
DATA_NODE_MIN = 48
KEY_BLOCK_MASK = 0x1FFFFFFF

_lzo = None


def lzo_decompress(src: bytes, out_len: int) -> bytes:
    global _lzo
    if _lzo is None:
        name = ctypes.util.find_library("lzo2")
        if not name:
            # Fall back to the local batch helper (single-block path used only
            # when batch extraction is unavailable, e.g. unit probes).
            from lzo_helper import batch_decompress
            return batch_decompress([(src, out_len)])[0]
        _lzo = ctypes.CDLL(name)
        _lzo = ctypes.CDLL(name)
        _lzo.lzo1x_decompress_safe.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
        ]
        _lzo.lzo1x_decompress_safe.restype = ctypes.c_int
    out = ctypes.create_string_buffer(out_len)
    olen = ctypes.c_size_t(out_len)
    inp = ctypes.create_string_buffer(src)
    rc = _lzo.lzo1x_decompress_safe(inp, len(src), out, ctypes.byref(olen), None)
    if rc != 0:
        raise RuntimeError(f"lzo1x_decompress_safe failed rc={rc}")
    return out.raw[: olen.value]


def scan_nodes(image: bytes) -> list[dict[str, Any]]:
    pos = 0
    nodes: list[dict[str, Any]] = []
    while True:
        off = image.find(UBIFS_MAGIC, pos)
        if off < 0:
            break
        pos = off + 1
        if off + COMMON_HDR_SIZE > len(image):
            continue
        magic, _crc, sqnum, nlen, ntype, group_type = struct.unpack_from("<IIQIBB", image, off)
        if magic != 0x06101831 or nlen < COMMON_HDR_SIZE or nlen > 1_000_000:
            continue
        if off + nlen > len(image):
            continue
        nodes.append(
            {
                "offset": off,
                "sqnum": sqnum,
                "len": nlen,
                "type": ntype,
                "group_type": group_type,
                "data": image[off : off + nlen],
            }
        )
    return nodes


def latest_dentries(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[int, int, str], dict[str, Any]] = {}
    for rec in nodes:
        node = rec["data"]
        if rec["type"] != 2 or len(node) < DENT_NODE_MIN:
            continue
        key0, key1 = struct.unpack_from("<II", node, 24)
        target = struct.unpack_from("<Q", node, 40)[0]
        dtype = node[49]
        name_len = struct.unpack_from("<H", node, 50)[0]
        if name_len > 255 or DENT_NODE_MIN + name_len > len(node):
            continue
        name = node[56 : 56 + name_len].decode("utf-8", "surrogateescape")
        key = (key0, key1, name)
        row = {
            "parent": key0,
            "target": target,
            "dtype": dtype,
            "name": name,
            "sqnum": rec["sqnum"],
            "offset": rec["offset"],
        }
        if key not in best or row["sqnum"] > best[key]["sqnum"]:
            best[key] = row
    return list(best.values())


def path_index(dentries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    children: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in dentries:
        if row["target"]:
            children[row["parent"]].append(row)
    inode_path = {1: "/"}
    result: dict[str, dict[str, Any]] = {}
    todo = deque([1])
    while todo:
        parent = todo.popleft()
        base = inode_path[parent]
        for row in children.get(parent, []):
            full = (base.rstrip("/") + "/" + row["name"]) if base != "/" else "/" + row["name"]
            result[full] = row
            ino = int(row["target"])
            if ino not in inode_path:
                inode_path[ino] = full
                todo.append(ino)
    return result


def latest_inodes(nodes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    # Vendor INO layout (SigmaStar 4.9 kernel), mapped EMPIRICALLY against EN
    # customer.es (3+ inodes incl. 11 MB adas: size/mode exact):
    #   ch[24] key[8]@24 creat-ish@32[8] creat@40[8] size@48[8]
    #   t56[8] t64[8] mtime@72[8] (all factory-Aug-2023; kernel-order analogy:
    #   atime@56 ctime@64 mtime@72; only mtime is rebuild-meaningful, ctime/
    #   atime are INFO because a fresh UBIFS can never preserve them)
    #   nsec-ish@76,80,84,88[4] nlink@92 uid@96 gid@100 mode@104 flags@108
    # NOTE this is +8 vs mainline ubifs-media.h (size@40/mode@96 there):
    # the vendor tree carries 8 extra bytes before size. Verified:
    #   /wifi/rcInsDriver.sh -> size 933, mode 0o100755
    #   /minieye             -> size 800, mode 0o040755 (dir)
    #   /minieye/adas/adas   -> size 11636008, mode 0o100775
    # (A prior revision read size@48/mode@100(=flags) — size was right by
    # luck of contiguous blocks, mode was wrong. Now both are proven.)
    best: dict[int, dict[str, Any]] = {}
    for rec in nodes:
        node = rec["data"]
        if rec["type"] != 0 or len(node) < INO_NODE_MIN:
            continue
        ino = struct.unpack_from("<I", node, 24)[0]
        row = {
            "size": struct.unpack_from("<Q", node, 48)[0],
            "mode": struct.unpack_from("<I", node, 104)[0],
            "uid": struct.unpack_from("<I", node, 96)[0],
            "gid": struct.unpack_from("<I", node, 100)[0],
            "nlink": struct.unpack_from("<I", node, 92)[0],
            "flags": struct.unpack_from("<I", node, 108)[0],
            "atime": struct.unpack_from("<Q", node, 56)[0],
            "ctime": struct.unpack_from("<Q", node, 64)[0],
            "mtime": struct.unpack_from("<Q", node, 72)[0],
            "sqnum": rec["sqnum"],
            "offset": rec["offset"],
        }
        if ino not in best or row["sqnum"] > best[ino]["sqnum"]:
            best[ino] = row
    return best


def latest_data_blocks(nodes: list[dict[str, Any]], inode: int) -> dict[int, dict[str, Any]]:
    best: dict[int, dict[str, Any]] = {}
    for rec in nodes:
        node = rec["data"]
        if rec["type"] != 1 or len(node) < DATA_NODE_MIN:
            continue
        key0, key1 = struct.unpack_from("<II", node, 24)
        if key0 != inode or (key1 >> 29) != 1:
            continue
        block = key1 & KEY_BLOCK_MASK
        row = {
            "sqnum": rec["sqnum"],
            "usize": struct.unpack_from("<I", node, 40)[0],
            "compression": struct.unpack_from("<H", node, 44)[0],
            "payload": node[48:],
            "offset": rec["offset"],
        }
        if block not in best or row["sqnum"] > best[block]["sqnum"]:
            best[block] = row
    return best


def decompress_block(rec: dict[str, Any]) -> bytes:
    src = rec["payload"]
    expected = int(rec["usize"])
    ctype = int(rec["compression"])
    if ctype == 0:
        out = src
    elif ctype == 1:
        out = lzo_decompress(src, expected)
    elif ctype == 2:
        out = zlib.decompress(src)
    elif ctype == 3:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise RuntimeError("zstd block encountered; install Python package zstandard") from exc
        out = zstd.ZstdDecompressor().decompress(src, max_output_size=expected)
    else:
        raise RuntimeError(f"unsupported UBIFS compression type {ctype}")
    if len(out) != expected:
        raise RuntimeError(f"decompressed size mismatch: {len(out)} != {expected}")
    return out


def extract(image_path: Path, target: str) -> tuple[bytes, dict[str, Any]]:
    image = image_path.read_bytes()
    nodes = scan_nodes(image)
    entries = path_index(latest_dentries(nodes))
    if target not in entries:
        close = [p for p in sorted(entries) if target.lower().split("/")[-1] in p.lower()]
        hint = "\n".join(close[:20])
        raise FileNotFoundError(f"{target!r} not found in UBIFS image" + (f"; candidates:\n{hint}" if hint else ""))
    inode = int(entries[target]["target"])
    meta = latest_inodes(nodes).get(inode)
    if not meta:
        raise RuntimeError(f"inode metadata missing for {inode}")
    blocks = latest_data_blocks(nodes, inode)
    if not blocks and meta["size"]:
        raise RuntimeError(f"no data blocks found for inode {inode}")
    output = bytearray(int(meta["size"]))
    cstats: dict[int, int] = defaultdict(int)
    lzo_jobs: list[tuple[int, dict[str, Any]]] = []
    for block, rec in sorted(blocks.items()):
        cstats[int(rec["compression"])] += 1
        if int(rec["compression"]) == 1:
            lzo_jobs.append((block, rec))
    if lzo_jobs:
        # One helper process for all LZO blocks (fast path; same bytes as
        # per-block decompress_block). Falls back to system liblzo2 where
        # no helper binary exists (e.g. Linux runners with liblzo2-dev).
        try:
            from lzo_helper import batch_decompress
            outs = batch_decompress([(r["payload"], int(r["usize"])) for _, r in lzo_jobs])
        except RuntimeError:
            outs = [lzo_decompress(r["payload"], int(r["usize"])) for _, r in lzo_jobs]
        for (block, rec), decoded in zip(lzo_jobs, outs):
            if len(decoded) != int(rec["usize"]):
                raise RuntimeError(f"lzo size mismatch block {block}")
            start = block * 4096
            output[start:start + len(decoded)] = decoded
    for block, rec in sorted(blocks.items()):
        if int(rec["compression"]) == 1:
            continue
        decoded = decompress_block(rec)
        start = block * 4096
        output[start:start + len(decoded)] = decoded
    blob = bytes(output)
    report = {
        "image": str(image_path),
        "target": target,
        "inode": inode,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "node_count": len(nodes),
        "data_block_count": len(blocks),
        "compression_block_counts": dict(sorted(cstats.items())),
    }
    return blob, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path, help="raw UBIFS image")
    ap.add_argument("target", help="absolute path inside UBIFS, e.g. /minieye/adas/adas")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, help="optional JSON extraction report")
    args = ap.parse_args()
    blob, report = extract(args.image, args.target)
    args.output.write_bytes(blob)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
