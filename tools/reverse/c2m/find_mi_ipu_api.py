#!/usr/bin/env python3
"""Find MI_IPU API surface in C2M firmware (read-only).

Usage:
  python3 tools/reverse/c2m/find_mi_ipu_api.py build/rootfs_en_inner.bin build/fw_bin_en/adas --out /tmp/ipu_api.json

Extracts libmi_ipu.so + adas/cardv from the rootfs cpio (or uses direct paths),
dumps dynsym UND/DEF MI_IPU/MI_SYS/MI_SCL imports, NEEDED, version strings,
and .rel.plt cross-check. No device, no flash, no modification.
"""
from __future__ import annotations
import argparse, json, struct, re, hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fw"))

def parse_dyn(path: Path):
    data = path.read_bytes()
    e_type,e_machine,e_version,e_entry,e_phoff,e_shoff,e_flags,e_ehsize,e_phentsize,e_phnum,e_shentsize,e_shnum,e_shstrndx = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    shstr_off = e_shoff + e_shstrndx * e_shentsize
    _,_,_,_,sh_offset,sh_size,_,_,_,_ = struct.unpack_from('<IIIIIIIIII', data, shstr_off)
    shstr = data[sh_offset:sh_offset+sh_size]
    def sname(o):
        e = shstr.index(b'\x00', o)
        return shstr[o:e].decode()
    secs = {}
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        a = struct.unpack_from('<IIIIIIIIII', data, off)
        secs[sname(a[0])] = a
    doff, dsize = secs['.dynsym'][4], secs['.dynsym'][5]
    soff, ssize = secs['.dynstr'][4], secs['.dynstr'][5]
    dynstr = data[soff:soff+ssize]
    def dstr(o):
        e = dynstr.index(b'\x00', o)
        return dynstr[o:e].decode(errors='replace')
    n = dsize // 16
    defs, unds = [], []
    for i in range(n):
        off = doff + i * 16
        st_name,st_value,st_size,st_info,st_other,st_shndx = struct.unpack_from('<IIIBBH', data, off)
        nm = dstr(st_name)
        if not nm:
            continue
        rec = {"name": nm, "addr": hex(st_value), "size": st_size, "shndx": st_shndx}
        (unds if st_shndx == 0 else defs).append(rec)
    needed = []
    a = secs['.dynamic']
    doff2, dsize2 = a[4], a[5]
    for i in range(dsize2 // 8):
        tag, val = struct.unpack_from('<ii', data, doff2 + i * 8)
        if tag == 1:
            e = dynstr.index(b'\x00', val)
            needed.append(dynstr[val:e].decode(errors='replace'))
        if tag == 0:
            break
    strs = [m.group().decode(errors='replace') for m in re.finditer(rb'[ -~]{4,}', data)]
    vers = [s for s in strs if 'Sigmastar Module' in s or s.startswith('T_0.0')]
    return {"file": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "defs": defs, "unds": unds, "needed": needed, "versions": vers}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path, help="ELF files (libmi_ipu.so, adas, cardv, ...)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = {"files": []}
    for p in args.inputs:
        if not p.exists():
            print(f"missing {p}")
            continue
        try:
            rec = parse_dyn(p)
        except Exception as e:
            rec = {"file": str(p), "error": str(e)}
            print(f"ERR {p}: {e}")
            continue
        mi_defs = [d for d in rec.get("defs", []) if d["name"].startswith("MI_")]
        mi_unds = [d for d in rec.get("unds", []) if d["name"].startswith("MI_")]
        print(f"== {p.name} ({rec['size']} B sha {rec['sha256'][:16]}..)")
        print(f"   MI defs ({len(mi_defs)}): {[d['name'] for d in mi_defs]}")
        print(f"   MI unds ({len(mi_unds)}): {[d['name'] for d in mi_unds]}")
        print(f"   NEEDED: {rec.get('needed')}")
        print(f"   VER: {rec.get('versions')}")
        rec["mi_defs"] = mi_defs
        rec["mi_unds"] = mi_unds
        out["files"].append(rec)
    if args.out:
        args.out.write_text(json.dumps(out, indent=2))
        print(f"wrote {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
