#!/usr/bin/env python3
"""Report bytes appended beyond normal ELF file structures.

Supports ELF32/ELF64 and either byte order using only the Python standard library.
The overlay start is the maximum of section-header-table end, program-header-table
end, and all *file-backed* section/segment ends. SHT_NOBITS (for example .bss)
is explicitly excluded because it occupies memory but no bytes in the file.
"""
from __future__ import annotations
import argparse, hashlib, json, math, struct
from pathlib import Path

def entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = [0] * 256
    for x in buf:
        counts[x] += 1
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)

def unpack(fmt, data, off):
    return struct.unpack_from(fmt, data, off)

def report(path: Path):
    d = path.read_bytes()
    if d[:4] != b"\x7fELF":
        raise ValueError(f"{path}: not ELF")
    cls, enc = d[4], d[5]
    endian = "<" if enc == 1 else ">" if enc == 2 else None
    if endian is None or cls not in (1, 2):
        raise ValueError("unsupported ELF class/encoding")
    if cls == 1:
        e_phoff = unpack(endian + "I", d, 28)[0]
        e_shoff = unpack(endian + "I", d, 32)[0]
        e_phentsize = unpack(endian + "H", d, 42)[0]
        e_phnum = unpack(endian + "H", d, 44)[0]
        e_shentsize = unpack(endian + "H", d, 46)[0]
        e_shnum = unpack(endian + "H", d, 48)[0]
        ph_fmt = endian + "IIIIIIII"
        sh_fmt = endian + "IIIIIIIIII"
        ph_offset_i, ph_filesz_i = 1, 4
        sh_type_i, sh_offset_i, sh_size_i = 1, 4, 5
    else:
        e_phoff = unpack(endian + "Q", d, 32)[0]
        e_shoff = unpack(endian + "Q", d, 40)[0]
        e_phentsize = unpack(endian + "H", d, 54)[0]
        e_phnum = unpack(endian + "H", d, 56)[0]
        e_shentsize = unpack(endian + "H", d, 58)[0]
        e_shnum = unpack(endian + "H", d, 60)[0]
        ph_fmt = endian + "IIQQQQQQ"
        sh_fmt = endian + "IIQQQQIIQQ"
        ph_offset_i, ph_filesz_i = 2, 5
        sh_type_i, sh_offset_i, sh_size_i = 1, 4, 5

    candidates = [0]
    if e_phoff and e_phentsize and e_phnum:
        candidates.append(e_phoff + e_phentsize * e_phnum)
    if e_shoff and e_shentsize and e_shnum:
        candidates.append(e_shoff + e_shentsize * e_shnum)
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + struct.calcsize(ph_fmt) <= len(d):
            vals = unpack(ph_fmt, d, off)
            candidates.append(vals[ph_offset_i] + vals[ph_filesz_i])
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if off + struct.calcsize(sh_fmt) <= len(d):
            vals = unpack(sh_fmt, d, off)
            # SHT_NOBITS == 8: memory-only; sh_offset + sh_size is not a
            # meaningful file-backed end (this is typically .bss).
            if vals[sh_type_i] != 8:
                candidates.append(vals[sh_offset_i] + vals[sh_size_i])

    start = max(x for x in candidates if x <= len(d))
    ov = d[start:]
    return {
        "path": str(path),
        "file_size": len(d),
        "elf_class": 32 if cls == 1 else 64,
        "byte_order": "little" if enc == 1 else "big",
        "overlay_start": start,
        "overlay_start_hex": hex(start),
        "overlay_size": len(ov),
        "overlay_sha256": hashlib.sha256(ov).hexdigest(),
        "overlay_entropy_bits_per_byte": round(entropy(ov), 6),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    result = [report(p) for p in args.files]
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)

if __name__ == "__main__":
    main()
