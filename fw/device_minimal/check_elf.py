#!/usr/bin/env python3
"""Strong ELF compatibility gate for the minimal ARM device binary.

Verifies (all measured from the file bytes, no readelf needed):
  - ELF32, little-endian, ET_EXEC, EM_ARM, EI_OSABI SYSV(0)/Linux(3);
  - e_flags: EABI v5 (0x05000000) + hard-float (EF_ARM_ABI_FLOAT_HARD 0x400),
    soft-float bit clear;
  - .ARM.attributes: CPU_arch=10 (v7), profile 'A', FP_arch=4 (VFPv3-D16),
    VFP_args=1, and NO Advanced_SIMD tag (no NEON);
  - static build (default): NO PT_INTERP, NO PT_DYNAMIC, NO DT_NEEDED,
    NO GLIBC version needs. NOTE on tag 12: Ubuntu's static libc objects
    (libc.a/crt*.o, built with the distro default FPU) carry
    Advanced_SIMD_arch, which the linker merges into the final binary even
    when our TU is NEON-free. Use --object + --allow-libc-simd to prove our
    TU clean (strict .o gate incl. tag-12 absence) while recording the
    inherited tag on the final link (FP_arch/VFP_args still enforced);
  - dynamic build (--allow-dynamic only): PT_INTERP must be
    /lib/ld-linux-armhf.so.3, NEEDED subset of the minimal allowlist,
    max GLIBC_* need <= --max-glibc (default 2.30, the stock baseline).

Exit 0 only if every applicable check passes. Prints all measured values.
"""
from __future__ import annotations
import argparse
import struct
import sys
from pathlib import Path

TAG_NAMES = {5: "CPU_name", 6: "CPU_arch", 7: "CPU_arch_profile",
             8: "ARM_ISA_use", 9: "THUMB_ISA_use", 10: "FP_arch",
             12: "Advanced_SIMD_arch", 18: "ABI_PCS_wchar_t",
             28: "ABI_VFP_args", 34: "CPU_unaligned_access"}
INTERP_WANT = b"/lib/ld-linux-armhf.so.3"
NEEDED_ALLOW = {"libc.so.6", "libm.so.6", "libgcc_s.so.1"}

EF_ARM_EABI_VER5 = 0x05000000
EF_ARM_ABI_FLOAT_HARD = 0x00000400
EF_ARM_ABI_FLOAT_SOFT = 0x00000200


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
        raise ValueError("unterminated string")
    return data[pos:end].decode("ascii", "replace"), end + 1


def parse_elf(path: Path) -> dict:
    d = path.read_bytes()
    if d[:4] != b"\x7fELF":
        raise SystemExit(f"{path}: not ELF")
    e = {"class": d[4], "data": d[5], "osabi": d[7]}
    (e["type"], e["machine"], _ver, _entry, e["phoff"], e["shoff"],
     e["flags"], _eh, _phent, e["phnum"], _shent, e["shnum"],
     e["shstrndx"]) = struct.unpack_from("<HHIIIIIHHHHHH", d, 16)
    e["phdrs"] = [struct.unpack_from("<IIIIIIII", d, e["phoff"] + i * 32)
                  for i in range(e["phnum"])]
    secs = [struct.unpack_from("<IIIIIIIIII", d, e["shoff"] + i * 40)
            for i in range(e["shnum"])]
    sh = secs[e["shstrndx"]]
    shstr = d[sh[4]:sh[4] + sh[5]]
    e["sections"] = {}
    for f in secs:
        end = shstr.find(b"\x00", f[0])
        e["sections"][shstr[f[0]:end].decode("ascii", "replace")] = f
    e["raw"] = d
    return e


def vaddr_to_offset(phdrs, vaddr: int) -> int | None:
    for (pt, off, va, _pa, fsz, _msz, _fl, _al) in phdrs:
        if pt == 1 and va <= vaddr < va + fsz:
            return off + (vaddr - va)
    return None


def cstr_at(d: bytes, off: int) -> str:
    end = d.find(b"\x00", off)
    return d[off:end].decode("ascii", "replace")


def decode_attrs(blob: bytes) -> dict[int, object]:
    if blob[:1] != b"A":
        raise ValueError("bad attribute magic")
    pos = 5
    vendor, pos = ntbs(blob, pos)
    if vendor != "aeabi":
        raise ValueError(f"vendor {vendor!r}")
    out: dict[int, object] = {}
    while pos < len(blob):
        tag, pos = uleb(blob, pos)
        if tag == 1:
            _size, pos = struct.unpack_from("<I", blob, pos)[0], pos + 4
            continue
        if tag == 5:
            s, pos = ntbs(blob, pos)
            out[tag] = s
        else:
            v, pos = uleb(blob, pos)
            out[tag] = v
    return out


def glibc_needs(e: dict) -> list[str]:
    d = e["raw"]
    if ".gnu.version_r" not in e["sections"] or ".dynstr" not in e["sections"]:
        return []
    vr, ds = e["sections"][".gnu.version_r"], e["sections"][".dynstr"]
    off, end = vr[4], vr[4] + vr[5]
    found: set[str] = set()
    while off < end:
        vn_ver, vn_cnt, _f, vn_aux, vn_next = struct.unpack_from("<HHIII", d, off)
        if vn_ver == 0:
            break
        a = off + vn_aux
        for _ in range(vn_cnt):
            _h, _fl, _o, name, nxt = struct.unpack_from("<IHHII", d, a)
            s = cstr_at(d, ds[4] + name)
            if s.startswith("GLIBC_"):
                found.add(s)
            a += nxt if nxt else 16
            if not nxt:
                break
        if not vn_next:
            break
        off += vn_next
    return sorted(found)


def dynamic_needed(e: dict) -> tuple[list[str], int | None]:
    """Return (NEEDED names, strtab file offset or None)."""
    d = e["raw"]
    dyn = next(((o, v, f) for (pt, o, v, _p, f, _m, _fl, _a) in e["phdrs"]
                if pt == 2), None)
    if dyn is None:
        return [], None
    doff = vaddr_to_offset(e["phdrs"], dyn[1])
    if doff is None:
        raise SystemExit("cannot map PT_DYNAMIC to file offset")
    needed_offs: list[int] = []
    strtab = None
    for i in range(dyn[2] // 8):
        tag, val = struct.unpack_from("<iI", d, doff + i * 8)
        if tag == 1:
            needed_offs.append(val)
        elif tag == 5:
            strtab = vaddr_to_offset(e["phdrs"], val)
    if strtab is None:
        raise SystemExit("no DT_STRTAB in PT_DYNAMIC")
    return [cstr_at(d, strtab + o) for o in needed_offs], strtab


def ver_tuple(s: str) -> tuple[int, ...]:
    num = s.split("_", 1)[1] if "_" in s else s
    return tuple(int(x) for x in num.split("."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", type=Path)
    ap.add_argument("--allow-dynamic", action="store_true")
    ap.add_argument("--max-glibc", default="2.30")
    ap.add_argument("--object", type=Path, default=None,
                    help="also strictly gate our compiled TU (.o): same arch/FPU "
                         "checks INCLUDING tag-12 absence")
    ap.add_argument("--allow-libc-simd", action="store_true",
                    help="permit Advanced_SIMD tag on the FINAL static binary only "
                         "when --object is given and passes (provenance: Ubuntu "
                         "static libc objects merge the tag at link time)")
    args = ap.parse_args()
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            fails.append(name)

    e = parse_elf(args.elf)
    d = e["raw"]
    check("elf.magic", True, "7f454c46")
    check("elf.class32", e["class"] == 1, f"EI_CLASS={e['class']} (want 1)")
    check("elf.le", e["data"] == 1, f"EI_DATA={e['data']} (want 1)")
    check("elf.exec", e["type"] == 2, f"e_type={hex(e['type'])} (want 0x2)")
    check("elf.arm", e["machine"] == 0x28, f"e_machine={hex(e['machine'])} (want 0x28)")
    check("elf.osabi", e["osabi"] in (0, 3), f"EI_OSABI={e['osabi']} (want 0 SYSV or 3 Linux)")
    fl = e["flags"]
    check("elf.eabi5", fl & 0xFF000000 == EF_ARM_EABI_VER5,
          f"e_flags={hex(fl)} top-byte want 0x05")
    check("elf.hardfloat", bool(fl & EF_ARM_ABI_FLOAT_HARD) and not fl & EF_ARM_ABI_FLOAT_SOFT,
          f"e_flags={hex(fl)} HARD bit set, SOFT bit clear")

    if ".ARM.attributes" not in e["sections"]:
        check("attr.present", False, "missing .ARM.attributes section")
        attrs: dict[int, object] = {}
    else:
        f = e["sections"][".ARM.attributes"]
        attrs = decode_attrs(d[f[4]:f[4] + f[5]])
        check("attr.present", True,
              ", ".join(f"{TAG_NAMES.get(t, t)}={v!r}" for t, v in sorted(attrs.items())
                        if t in TAG_NAMES))
    check("attr.cpu_arch_v7", attrs.get(6) == 10, f"CPU_arch={attrs.get(6)!r} (want 10=v7)")
    check("attr.profile_A", attrs.get(7) == 65, f"profile={attrs.get(7)!r} (want 65='A')")
    check("attr.fp_vfpv3d16", attrs.get(10) == 4, f"FP_arch={attrs.get(10)!r} (want 4=VFPv3-D16)")
    simd_ok = 12 not in attrs
    if simd_ok:
        check("attr.no_simd", True, "Advanced_SIMD tag absent (no NEON)")
    elif args.allow_libc_simd and args.object is not None:
        check("attr.no_simd", True,
              f"Advanced_SIMD_arch={attrs.get(12)!r} INHERITED (see tu.* rows: our TU "
              "proven NEON-free; tag merged from Ubuntu static libc objects)")
    else:
        check("attr.no_simd", False,
              "Advanced_SIMD tag present (no NEON evidence; use --object + "
              "--allow-libc-simd only with a passing TU proof)")
    check("attr.vfp_args", attrs.get(28) == 1, f"VFP_args={attrs.get(28)!r} (want 1=hard)")
    check("attr.align8", attrs.get(24) == 1 and attrs.get(25) == 1,
          f"align8_needed={attrs.get(24)!r} align8_preserved={attrs.get(25)!r} (want 1/1)")

    gnustack = e["sections"].get(".note.GNU-stack")
    if gnustack is None:
        check("stack.note", False, "missing .note.GNU-stack (link warns: executable stack?)")
    else:
        check("stack.note", not (gnustack[2] & 0x4),
              f".note.GNU-stack flags={hex(gnustack[2])} (SHF_EXECINSTR must be clear)")

    if args.object is not None:
        o = parse_elf(args.object)
        od = o["raw"]
        check("tu.type", o["type"] == 1, f"{args.object.name}: e_type={hex(o['type'])} (want 0x1 ET_REL)")
        check("tu.arm", o["machine"] == 0x28, f"e_machine={hex(o['machine'])}")
        if ".ARM.attributes" not in o["sections"]:
            check("tu.attr", False, "missing .ARM.attributes in TU object")
        else:
            f = o["sections"][".ARM.attributes"]
            oa = decode_attrs(od[f[4]:f[4] + f[5]])
            check("tu.attr", True,
                  ", ".join(f"{TAG_NAMES.get(t, t)}={v!r}" for t, v in sorted(oa.items())
                            if t in TAG_NAMES))
            check("tu.no_simd", 12 not in oa,
                  f"TU Advanced_SIMD tag absent (got {oa.get(12)!r})" if 12 in oa
                  else "TU Advanced_SIMD tag absent (our code is NEON-free)")
            check("tu.fp_vfpv3d16", oa.get(10) == 4, f"TU FP_arch={oa.get(10)!r} (want 4)")
            check("tu.vfp_args", oa.get(28) == 1, f"TU VFP_args={oa.get(28)!r} (want 1)")

    has_interp = any(pt == 3 for (pt, *_r) in e["phdrs"])
    has_dynamic = any(pt == 2 for (pt, *_r) in e["phdrs"])
    if not args.allow_dynamic:
        check("static.no_interp", not has_interp, "no PT_INTERP (static)")
        check("static.no_dynamic", not has_dynamic, "no PT_DYNAMIC (static)")
        check("static.no_verneed", ".gnu.version_r" not in e["sections"],
              "no .gnu.version_r section (static)")
    else:
        interp = b""
        for (pt, off, _v, _p, fsz, _m, _fl, _a) in e["phdrs"]:
            if pt == 3:
                interp = d[off:off + fsz].rstrip(b"\x00")
        check("dyn.interp", interp == INTERP_WANT.rstrip(b"\x00") or interp + b"\x00" == INTERP_WANT,
              f"PT_INTERP={interp!r} (want {INTERP_WANT!r})")
        needed, _st = dynamic_needed(e)
        check("dyn.needed", set(needed) <= NEEDED_ALLOW,
              f"NEEDED={needed} (allow={sorted(NEEDED_ALLOW)})")
        needs = glibc_needs(e)
        worst = max([ver_tuple(v) for v in needs], default=(0,))
        cap = tuple(int(x) for x in args.max_glibc.split("."))
        worst_s = max(needs, key=ver_tuple) if needs else None
        check("dyn.glibc", not worst or worst <= cap,
              f"max GLIBC need={worst_s} (cap {args.max_glibc})")

    if fails:
        print(f"ELF-GATE: FAIL ({len(fails)}: {fails})")
        return 1
    mode = "static" if not args.allow_dynamic else "dynamic"
    if args.object is not None:
        mode += "+tu-proof"
    print(f"ELF-GATE: OK ({args.elf.name}, {mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
