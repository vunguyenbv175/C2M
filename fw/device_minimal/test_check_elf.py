#!/usr/bin/env python3
"""Host unit tests for the ARM ELF gate (no toolchain / firmware needed).

Locks the evidence interpretation with the exact measured stock
.ARM.attributes block (51 bytes of ABI metadata, not a vendor binary):
cardv + adas both carry these semantics at their own .ARM.attributes
section (see tools/fw/arm_attributes.py output). Also exercises the
TU-proof paths (--object / --allow-libc-simd) with hand-assembled ET_REL /
ET_EXEC fixtures so the CI-only branches are proven locally too.
"""
from __future__ import annotations
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "fw" / "device_minimal"))

from check_elf import decode_attrs, ver_tuple  # noqa: E402

# Exact measured stock attribute block (cardv file offset 0x12ae41, len 0x33).
STOCK_ATTR_HEX = ("41320000006165616269000128000000"
                  "05372d4100060a0741080109020a041204"
                  "1301140115011703180119011a021c012201")

# (tag, value) rows of the stock block, in order (tag 5 = CPU_name "7-A").
STOCK_ROWS: list[tuple[int, object]] = [
    (5, "7-A"), (6, 10), (7, 65), (8, 1), (9, 2), (10, 4), (18, 4),
    (19, 1), (20, 1), (21, 1), (23, 3), (24, 1), (25, 1), (26, 2),
    (28, 1), (34, 1),
]


def uleb(v: int) -> bytes:
    assert 0 <= v < 128
    return bytes([v])


def encode_attr(rows: list[tuple[int, object]]) -> bytes:
    body = b""
    for tag, val in rows:
        body += uleb(tag)
        if tag == 5:
            assert isinstance(val, str)
            body += val.encode() + b"\x00"
        else:
            assert isinstance(val, int)
            body += uleb(val)
    sub = uleb(1) + struct.pack("<I", 5 + len(body)) + body
    rest = b"aeabi\x00" + sub
    # NOTE: stock section-length field = len(rest)+4, i.e. it counts its own
    # 4 length bytes (GNU quirk, measured on cardv/adas). Reproduce exactly.
    return b"A" + struct.pack("<I", len(rest) + 4) + rest


def make_elf(etype: int, attr: bytes) -> bytes:
    shstr = b"\x00.ARM.attributes\x00.shstrtab\x00"
    ehsize, shentsize, shnum = 52, 40, 3
    shoff = ehsize
    attr_off = shoff + shentsize * shnum
    str_off = attr_off + len(attr)
    hdr = (b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
           + struct.pack("<HHIIIIIHHHHHH", etype, 0x28, 1, 0, 0, shoff,
                         0x5000400, ehsize, 0, 0, shentsize, shnum, 2))
    null = b"\x00" * 40
    s_attr = struct.pack("<IIIIIIIIII", 1, 0x70000003, 0, 0, attr_off,
                         len(attr), 0, 0, 1, 0)
    s_str = struct.pack("<IIIIIIIIII", 18, 3, 0, 0, str_off, len(shstr),
                        0, 0, 1, 0)
    return hdr + null + s_attr + s_str + attr + shstr


def run_gate(*argv: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "fw/device_minimal/check_elf.py", *argv],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    # 1. exact-bytes lock: our encoder reproduces the measured stock block.
    assert encode_attr(STOCK_ROWS).hex() == STOCK_ATTR_HEX
    attrs = decode_attrs(bytes.fromhex(STOCK_ATTR_HEX))
    assert attrs.get(5) == "7-A", attrs
    assert attrs.get(6) == 10, attrs          # v7
    assert attrs.get(7) == 65, attrs           # 'A' profile
    assert attrs.get(8) == 1, attrs            # ARM ISA
    assert attrs.get(9) == 2, attrs            # Thumb-2
    assert attrs.get(10) == 4, attrs           # VFPv3-D16 (NOT NEON)
    assert 12 not in attrs, attrs              # no Advanced_SIMD tag
    assert attrs.get(28) == 1, attrs           # VFP args = hard-float ABI
    assert ver_tuple("GLIBC_2.29") < ver_tuple("2.30")
    assert ver_tuple("GLIBC_2.30") <= ver_tuple("2.30")
    assert ver_tuple("GLIBC_2.31") > ver_tuple("2.30")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        obj = tmp / "tu.o"
        obj.write_bytes(make_elf(1, encode_attr(STOCK_ROWS)))
        simd_rows = STOCK_ROWS + [(12, 1)]  # inherited-tag shape (final link)
        linked = tmp / "final"
        linked.write_bytes(make_elf(2, encode_attr(simd_rows)))
        clean = tmp / "clean"
        clean.write_bytes(make_elf(2, encode_attr(STOCK_ROWS)))

        # 2. TU object parses; strict TU rows pass on it.
        rc, out = run_gate(str(clean), "--object", str(obj), "--allow-libc-simd")
        assert rc == 0, out
        assert "tu.no_simd" in out and "TU Advanced_SIMD tag absent" in out, out
        # 3. inherited SIMD tag on final link: FAILS without the TU proof flag...
        rc, out = run_gate(str(linked), "--object", str(obj))
        assert rc != 0 and "attr.no_simd" in out, out
        # ...and PASSES with it, recording provenance.
        rc, out = run_gate(str(linked), "--object", str(obj), "--allow-libc-simd")
        assert rc == 0 and "INHERITED" in out, out
        # 4. a NEON-claiming TU itself can never pass.
        bad_obj = tmp / "bad.o"
        bad_obj.write_bytes(make_elf(1, encode_attr(simd_rows)))
        rc, out = run_gate(str(linked), "--object", str(bad_obj), "--allow-libc-simd")
        assert rc != 0 and "tu.no_simd" in out, out

    print("check_elf unit: OK (stock attrs = v7-A/VFPv3-D16/VFP-args no-SIMD; "
          "TU-proof + inherited-tag paths proven)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
