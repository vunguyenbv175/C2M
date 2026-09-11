#!/usr/bin/env python3
"""Recover nav live-key table consumers via absolute-pointer scan (XL-proven method).

Usage: python recover_nav_key_table.py <app-image.bin> [--json]
Finds the NUL-delimited bare-key set (unix/nav/spd/...) then scans the image
for LE32 words pointing at each key. On XL-S3 this yields IROM consumer
clusters (settings key table + literal pools); on classic ESP32 the same scan
yields nothing (Xtensa literal method differs) - a method-validity signal, NOT
proof of absence. See PROMAX_LIVE_VALUE_PARSER_V1.md.
"""
import struct, sys, json, re
KEYS = [b"\x00unix\x00", b"\x00nav\x00", b"\x00spd\x00", b"\x00lim\x00", b"\x00trn\x00",
        b"\x00dst\x00", b"\x00exit\x00", b"\x00eta\x00", b"\x00rmin\x00", b"\x00rkm\x00",
        b"\x00avg\x00", b"\x00alrs\x00", b"\x00hi\x00"]
def main():
    d = open(sys.argv[1], "rb").read()
    out = []
    for k in KEYS:
        offs = [m.start() for m in re.finditer(re.escape(k), d)]
        refs = 0
        for o in offs:
            refs += sum(1 for i in range(0, len(d) - 3, 4)
                        if struct.unpack_from("<I", d, i)[0] == o)
        out.append({"key": repr(k), "defs": [hex(o) for o in offs], "abs_refs": refs})
        print(f"{k!r} defs={[hex(o) for o in offs]} abs_refs={refs}")
    print("NOTE: abs_refs counts file-offset (not VA) matches; use v4_xref.py VA math for the real XL result.")
    if "--json" in sys.argv: print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
