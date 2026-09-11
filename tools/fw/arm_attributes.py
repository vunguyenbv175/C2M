#!/usr/bin/env python3
"""Decode `.ARM.attributes` (ARM IHI 0045 / aeabi) from an ARM ELF.

Reads section headers (no readelf needed), extracts the `aeabi` vendor
subsection, and prints tag=value rows with names. Used to ground the
TARGET_ABI FPU claim in measured bytes (NOT inference).

Usage:
  python3 tools/fw/arm_attributes.py build/fw_bin_en/cardv
  python3 tools/fw/arm_attributes.py build/fw_bin_en/adas
"""
from __future__ import annotations
import struct
import sys
from pathlib import Path

TAG_NAMES = {
    4: "CPU_raw_name", 5: "CPU_name", 6: "CPU_arch", 7: "CPU_arch_profile",
    8: "ARM_ISA_use", 9: "THUMB_ISA_use", 10: "FP_arch", 11: "WMMX_arch",
    12: "Advanced_SIMD_arch", 13: "PCS_config", 14: "ABI_PCS_R9_use",
    15: "ABI_PCS_RW_data", 16: "ABI_PCS_RO_data", 17: "ABI_PCS_GOT_use",
    18: "ABI_PCS_wchar_t", 19: "ABI_FP_rounding", 20: "ABI_FP_denormal",
    21: "ABI_FP_exceptions", 22: "ABI_FP_user_exceptions",
    23: "ABI_FP_number_model", 24: "ABI_align_needed",
    25: "ABI_align_preserved", 26: "ABI_enum_size", 27: "ABI_HardFP_use",
    28: "ABI_VFP_args", 29: "ABI_WMMX_args", 30: "ABI_optimization_goals",
    31: "ABI_FP_optimization_goals", 32: "compatibility",
    34: "CPU_unaligned_access", 36: "FP_HP_extension",
    38: "ABI_FP_16bit_format", 42: "MPextension_use", 44: "DIV_use",
}
STR_TAGS = {4, 5}
CPU_ARCH = {0: "pre-v4", 1: "v4", 2: "v4T", 3: "v5T", 4: "v5TE", 5: "v5TEJ",
            6: "v6", 7: "v6KZ", 8: "v6T2", 9: "v6K", 10: "v7", 11: "v7E-M",
            12: "v8", 13: "v6-M", 14: "v6S-M", 15: "v7E-M(v8?)"}
FP_ARCH = {0: "none", 1: "VFPv1", 2: "VFPv2", 3: "VFPv3", 4: "VFPv3-D16",
           5: "VFPv4", 6: "VFPv4-D16", 7: "ARMv8-FP", 8: "ARMv8-FP16"}


def uleb(data: bytes, pos: int) -> tuple[int, int]:
    out = shift = 0
    while True:
        b = data[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return out, pos


def ntbs(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end < 0:
        raise ValueError("unterminated string in attributes")
    return data[pos:end].decode("ascii", "replace"), end + 1


def find_attr_section(data: bytes) -> bytes:
    e_shoff = struct.unpack_from("<I", data, 32)[0]
    e_shnum = struct.unpack_from("<H", data, 48)[0]
    e_shstrndx = struct.unpack_from("<H", data, 50)[0]
    secs = []
    for i in range(e_shnum):
        f = struct.unpack_from("<IIIIIIIIII", data, e_shoff + i * 40)
        secs.append(f)
    sh = secs[e_shstrndx]
    shstr = data[sh[4]:sh[4] + sh[5]]
    for f in secs:
        end = shstr.find(b"\x00", f[0])
        if shstr[f[0]:end] == b".ARM.attributes":
            return data[f[4]:f[4] + f[5]]
    raise SystemExit("no .ARM.attributes section")


def decode(blob: bytes) -> list[tuple[int, object]]:
    if blob[:1] != b"A":
        raise ValueError(f"bad attributes magic {blob[:1]!r}")
    pos = 5  # 'A' + uint32 section length
    vendor, pos = ntbs(blob, pos)
    if vendor != "aeabi":
        raise ValueError(f"unexpected vendor {vendor!r}")
    rows: list[tuple[int, object]] = []
    while pos < len(blob):
        tag, pos = uleb(blob, pos)
        if tag == 1:  # FileAttributes subsection: uint32 size, then attributes
            size, pos = struct.unpack_from("<I", blob, pos)[0], pos + 4
            rows.append((1, f"file-attributes(size={size})"))
            continue
        if tag in STR_TAGS:
            s, pos = ntbs(blob, pos)
            rows.append((tag, s))
        else:
            v, pos = uleb(blob, pos)
            rows.append((tag, v))
    return rows


def main() -> int:
    for arg in sys.argv[1:]:
        data = Path(arg).read_bytes()
        if data[:4] != b"\x7fELF":
            raise SystemExit(f"{arg}: not ELF")
        e_flags = struct.unpack_from("<I", data, 36)[0]
        print(f"== {arg}  e_flags={hex(e_flags)} EI_OSABI={data[7]}")
        for tag, val in decode(find_attr_section(data)):
            name = TAG_NAMES.get(tag, f"Tag{tag}")
            extra = ""
            if tag == 6 and isinstance(val, int):
                extra = f" ({CPU_ARCH.get(val, '?')})"
            if tag == 10 and isinstance(val, int):
                extra = f" ({FP_ARCH.get(val, '?')})"
            if tag == 7 and isinstance(val, int):
                extra = f" ({chr(val)!r})" if 32 <= val < 127 else ""
            print(f"  tag {tag:3d} {name:22s} = {val!r}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
