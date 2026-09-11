#!/usr/bin/env python3
"""Recover BLE setup structures referencing 8a7e/FFF UUIDs via absolute-pointer scan.

Usage: python recover_gatt_db.py <app-image.bin> <drom-load-hex> <drom-fileoff-hex> <drom-len-hex> [--json]
Scans IRAM/IROM/DRAM segments (esptool layout) for LE32 words pointing into the
DROM string ranges of 8a7e0001/2/3 + FFF0. Prints file offset + segment + target
string for each hit. Honest ceiling without an Xtensa disassembler: finds
DATA xrefs (setup structs, literal pools) but cannot label service-vs-char or
callbacks. See PROMAX_8A7E_GATT_REVERSE_V2.md for V4 results.
"""
import struct, sys, json, re
def main():
    path = sys.argv[1]
    d = open(path, "rb").read()
    needles = [b"8a7e0001", b"8a7e0002", b"8a7e0003", b"FFF0", b"VIETMAP_HUD"]
    table = {}
    for n in needles:
        offs = [m.start() for m in re.finditer(re.escape(n), d)]
        table[n.decode()] = offs
        print(f"{n.decode():12s} x{len(offs)} {[hex(o) for o in offs[:6]]}")
    # caller supplies DROM mapping; here just report string offsets so a
    # Ghidra run can break on them. Pointer scan needs segment table (see
    # map_esp_segments.py + V4 v4_xref.py for the worked XL example).
    if "--json" in sys.argv:
        print(json.dumps({k: [hex(o) for o in v] for k, v in table.items()}, indent=2))
if __name__ == "__main__": main()
