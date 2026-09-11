#!/usr/bin/env python3
"""Recover and compare the stock cardv -> raw_adas CRingBuf contract.

Requires `readelf` and `llvm-objdump`. The tool is read-only and works on
extracted `bootconfig/bin/cardv` ELF files.

It maps ARM PLT stubs back to .rel.plt symbols, locates calls to the CRingBuf
constructor / RequestWriteFrame / CommitWrite, resolves nearby PC-relative
constructor string arguments, and reports normalized instruction-prefix
similarity for the two high-value producer helpers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any

CTOR = "_ZN8CRingBufC1EPKcS1_iibb"
REQUEST = "_ZN8CRingBuf17RequestWriteFrameEj9__FRAME_E18__CRB_WRITE_MODE_E"
COMMIT = "_ZN8CRingBuf11CommitWriteEjPiS0_"
SEND = "_Z4sendP8CRingBufR10StreamPack"
SEND_FRAME = "_Z28adas_minieye_send_frame_taskPv"


def run(*argv: str) -> str:
    return subprocess.check_output(argv, text=True, errors="replace")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_relplt(path: Path) -> dict[int, str]:
    text = run("readelf", "-r", "--wide", str(path))
    out: dict[int, str] = {}
    active = False
    for line in text.splitlines():
        if "Relocation section '.rel.plt'" in line:
            active = True
            continue
        if active and line.startswith("Relocation section "):
            break
        if active:
            m = re.match(r"([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+R_ARM_JUMP_SLOT\s+[0-9a-fA-F]+\s+(.+)", line)
            if m:
                out[int(m.group(1), 16)] = m.group(2).split()[0]
    return out


def arm_rot_imm(text: str) -> int:
    vals = re.findall(r"#(0x[0-9a-fA-F]+|\d+)", text)
    if not vals:
        raise ValueError(f"no immediate in {text!r}")
    value = int(vals[0], 0)
    if len(vals) > 1 and value <= 0xFF:
        rotate = int(vals[1], 0) * 2
        if rotate:
            value = ((value >> rotate) | (value << (32 - rotate))) & 0xFFFFFFFF
    return value


def parse_plt(path: Path) -> dict[str, int]:
    rel = parse_relplt(path)
    text = run("llvm-objdump", "-d", "--triple=armv7-linux-gnueabihf", "--section=.plt", str(path))
    ins = []
    for line in text.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+(.+)$", line)
        if m:
            ins.append((int(m.group(1), 16), m.group(2).strip()))
    out: dict[str, int] = {}
    for i in range(len(ins) - 2):
        a, s1 = ins[i]
        a2, s2 = ins[i + 1]
        a3, s3 = ins[i + 2]
        if (a2, a3) != (a + 4, a + 8):
            continue
        if not s1.startswith("add\tr12, pc,"):
            continue
        if not s2.startswith("add\tr12, r12,"):
            continue
        if not s3.startswith("ldr\tpc, [r12, #"):
            continue
        target = (a + 8 + arm_rot_imm(s1) + arm_rot_imm(s2) + arm_rot_imm(s3)) & 0xFFFFFFFF
        if target in rel:
            out[rel[target]] = a
    return out


def elf32_load_segments(path: Path) -> list[tuple[int, int, int]]:
    b = path.read_bytes()
    if b[:4] != b"\x7fELF" or b[4] != 1 or b[5] != 1:
        raise ValueError("expected little-endian ELF32")
    phoff = struct.unpack_from("<I", b, 28)[0]
    entsz = struct.unpack_from("<H", b, 42)[0]
    num = struct.unpack_from("<H", b, 44)[0]
    segs = []
    for i in range(num):
        off = phoff + i * entsz
        p_type, p_offset, p_vaddr, _paddr, p_filesz, _memsz, _flags, _align = struct.unpack_from("<IIIIIIII", b, off)
        if p_type == 1 and p_filesz:
            segs.append((p_vaddr, p_offset, p_filesz))
    return segs


def vaddr_to_offset(path: Path, addr: int) -> int:
    for vaddr, off, size in elf32_load_segments(path):
        if vaddr <= addr < vaddr + size:
            return off + (addr - vaddr)
    raise ValueError(f"vaddr not file-backed: {addr:#x}")


def cstring_at_vaddr(path: Path, addr: int, limit: int = 256) -> str:
    data = path.read_bytes()
    off = vaddr_to_offset(path, addr)
    raw = data[off : off + limit].split(b"\0", 1)[0]
    return raw.decode("utf-8", errors="replace")


def disasm(path: Path, symbol: str) -> list[dict[str, Any]]:
    text = run("llvm-objdump", "-d", "--triple=thumbv7-linux-gnueabihf", f"--disassemble-symbols={symbol}", str(path))
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]+):\s+(?:[0-9a-fA-F]{4}(?:\s+[0-9a-fA-F]{4})?\s+)+(.+)$", line)
        if m:
            out.append({"addr": int(m.group(1), 16), "text": m.group(2).strip(), "raw_line": line})
    return out


def normalize_instruction(text: str) -> str:
    x = re.sub(r"\s+@.*$", "", text)
    x = re.sub(r"0x[0-9a-fA-F]+\s+(<[^>]+>)", r"\1", x)
    return x.strip()


def calls_to(dis: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    needle = f"0x{target:x}"
    return [x for x in dis if (x["text"].startswith("bl") or x["text"].startswith("blx")) and needle in x["text"]]


def resolve_ctor_string_args(path: Path, dis: list[dict[str, Any]], call_addr: int) -> dict[str, Any]:
    idx = next(i for i, x in enumerate(dis) if x["addr"] == call_addr)
    window = dis[max(0, idx - 32) : idx]
    result = {}
    for reg in ("r1", "r2"):
        # Find closest PC-relative literal load and a subsequent add reg,pc before call.
        candidate = None
        for j, x in enumerate(window):
            if re.search(rf"ldr(?:\.w)?\s+{reg}, \[pc,", x["text"]):
                cm = re.search(r"@\s+0x([0-9a-fA-F]+)", x["text"])
                if cm:
                    candidate = (j, int(cm.group(1), 16))
        if candidate is None:
            continue
        j, literal_addr = candidate
        add = next((x for x in window[j + 1 :] if re.match(rf"add\s+{reg}, pc$", normalize_instruction(x["text"]))), None)
        if add is None:
            continue
        data = path.read_bytes()
        literal_off = vaddr_to_offset(path, literal_addr)
        rel = struct.unpack_from("<i", data, literal_off)[0]
        # Thumb PC for ADD using PC is current instruction address + 4.
        target = (add["addr"] + 4 + rel) & 0xFFFFFFFF
        result[reg] = {"literal_vaddr": hex(literal_addr), "relative_value": rel, "target_vaddr": hex(target), "string": cstring_at_vaddr(path, target)}
    return result


def report(path: Path) -> dict[str, Any]:
    plt = parse_plt(path)
    missing = [s for s in (CTOR, REQUEST, COMMIT) if s not in plt]
    if missing:
        raise ValueError(f"missing PLT mappings: {missing}")
    sf = disasm(path, SEND_FRAME)
    send = disasm(path, SEND)
    ctor_calls = calls_to(sf, plt[CTOR])
    req_calls = calls_to(send, plt[REQUEST])
    commit_calls = calls_to(send, plt[COMMIT])
    strings = {}
    data = path.read_bytes()
    for key in (b"raw_adas\0", b"fortest\0"):
        off = data.find(key)
        strings[key[:-1].decode()] = {"file_offset": off, "file_offset_hex": hex(off) if off >= 0 else None}
    ctor_args = resolve_ctor_string_args(path, sf, ctor_calls[0]["addr"]) if ctor_calls else {}
    return {
        "binary": str(path),
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "plt": {"CRingBuf_ctor": hex(plt[CTOR]), "RequestWriteFrame": hex(plt[REQUEST]), "CommitWrite": hex(plt[COMMIT])},
        "string_locations": strings,
        "send_frame_task": {
            "instruction_records_in_symbol": len(sf),
            "ctor_calls": [{"addr": hex(x["addr"]), "text": x["text"]} for x in ctor_calls],
            "ctor_pc_relative_string_args": ctor_args,
            "normalized": [normalize_instruction(x["text"]) for x in sf],
            "addresses": [x["addr"] for x in sf],
        },
        "send_helper": {
            "instruction_records_in_symbol": len(send),
            "request_calls": [{"addr": hex(x["addr"]), "text": x["text"]} for x in req_calls],
            "commit_calls": [{"addr": hex(x["addr"]), "text": x["text"]} for x in commit_calls],
            "normalized": [normalize_instruction(x["text"]) for x in send],
            "addresses": [x["addr"] for x in send],
        },
    }


def equal_prefix(a: list[str], b: list[str]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def compact(r: dict[str, Any]) -> dict[str, Any]:
    # Keep machine output useful without repeating hundreds of instruction strings.
    return {
        "binary": r["binary"], "sha256": r["sha256"], "size": r["size"], "plt": r["plt"],
        "string_locations": r["string_locations"],
        "send_frame_task": {k: v for k, v in r["send_frame_task"].items() if k not in ("normalized", "addresses")},
        "send_helper": {k: v for k, v in r["send_helper"].items() if k not in ("normalized", "addresses")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path, nargs="?")
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    left = report(args.left)
    result: dict[str, Any] = {"left": compact(left)}
    if args.right:
        right = report(args.right)
        sf_prefix = equal_prefix(left["send_frame_task"]["normalized"], right["send_frame_task"]["normalized"])
        send_prefix = equal_prefix(left["send_helper"]["normalized"], right["send_helper"]["normalized"])
        result["right"] = compact(right)
        result["comparison"] = {
            "send_frame_equal_normalized_prefix_instructions": sf_prefix,
            "send_frame_left_first_mismatch_vaddr": hex(left["send_frame_task"]["addresses"][sf_prefix]) if sf_prefix < len(left["send_frame_task"]["addresses"]) else None,
            "send_frame_right_first_mismatch_vaddr": hex(right["send_frame_task"]["addresses"][sf_prefix]) if sf_prefix < len(right["send_frame_task"]["addresses"]) else None,
            "send_helper_equal_normalized_prefix_instructions": send_prefix,
            "send_helper_left_first_mismatch_vaddr": hex(left["send_helper"]["addresses"][send_prefix]) if send_prefix < len(left["send_helper"]["addresses"]) else None,
            "send_helper_right_first_mismatch_vaddr": hex(right["send_helper"]["addresses"][send_prefix]) if send_prefix < len(right["send_helper"]["addresses"]) else None,
            "constructor_string_args_equal": left["send_frame_task"]["ctor_pc_relative_string_args"] and right["send_frame_task"]["ctor_pc_relative_string_args"] and {k:v.get("string") for k,v in left["send_frame_task"]["ctor_pc_relative_string_args"].items()} == {k:v.get("string") for k,v in right["send_frame_task"]["ctor_pc_relative_string_args"].items()},
            "request_call_count_equal": len(left["send_helper"]["request_calls"]) == len(right["send_helper"]["request_calls"]),
            "commit_call_count_equal": len(left["send_helper"]["commit_calls"]) == len(right["send_helper"]["commit_calls"]),
        }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
