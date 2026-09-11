#!/usr/bin/env python3
"""Find nav-state key cross-references: handshake JSON vs live bare-key table.

Usage: python find_nav_state_xrefs.py <firmware.bin> [--json]
Distinguishes the handshake block (quoted keys in dev/want) from the live
bare-key table (NUL-delimited unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/hi
+ false/null + JSON escape table). A second quoted occurrence would signal a
parser/dispatch site; its absence is itself evidence (hashed/numeric/binary path
or no string-keyed dispatch).
"""
import re, sys, json
QUOTED = [b'"nav"', b'"spd"', b'"lim"', b'"trn"', b'"dst"', b'"exit"', b'"st"', b'"eta"',
          b'"rmin"', b'"rkm"', b'"avg"', b'"avgL"', b'"alrs"', b'"lan"']
BARE = [b"\x00unix\x00", b"\x00nav\x00", b"\x00spd\x00", b"\x00lim\x00", b"\x00trn\x00",
        b"\x00dst\x00", b"\x00exit\x00", b"\x00eta\x00", b"\x00rmin\x00", b"\x00rkm\x00",
        b"\x00avg\x00", b"\x00alrs\x00", b"\x00hi\x00", b"Overflow ######"]
def main():
    p = sys.argv[1]; d = open(p, "rb").read()
    out = {"image": p, "quoted": [], "bare": [], "verdict": ""}
    for k in QUOTED:
        offs = [m.start() for m in re.finditer(re.escape(k), d)]
        out["quoted"].append({"key": k.decode(), "count": len(offs), "offsets": [f"0x(o:X)" for o in offs[:4]]})
        print(f"Q {k.decode():8s} x{len(offs)} {[hex(o) for o in offs[:4]]}")
    for k in BARE:
        offs = [m.start() for m in re.finditer(re.escape(k), d)]
        out["bare"].append({"key": repr(k), "count": len(offs), "offsets": [hex(o) for o in offs[:4]]})
        print(f"B {k!r} x{len(offs)} {[hex(o) for o in offs[:4]]}")
    q2 = sum(1 for q in out["quoted"] if q["count"] > 1 and q["key"] != '"eta"')
    # eta x2 is want+can inside ONE handshake JSON, not a second site
    b = sum(1 for x in out["bare"] if x["count"] > 0)
    out["verdict"] = f"quoted-second-sites={q2} bare-keys-present={b}; " + \
        ("live bare table present" if b > 5 else "no live bare table")
    print(out["verdict"])
    if "--json" in sys.argv: print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
