#!/usr/bin/env python3
"""Scan Xtensa IROM for `entry a1, N` function prologues (validated pattern).

Pattern `36 (N>>3)<<4|1 00` verified 6/6 via rz-asm before use
(`entry a1,0x40` = 36 81 00 at classic entry+8). a1-only census undercounts
(true total higher: other base regs), so treat counts as lower bounds.
Usage: python find_entry_prologues.py <bin> <hex-start> <hex-len>
"""
import sys
def scan(d, start, ln):
    out = []
    for o in range(start, start + ln - 2):
        b0, b1, b2 = d[o], d[o + 1], d[o + 2]
        if b0 == 0x36 and (b1 & 0x0F) == 0x01 and b2 == 0x00:
            size = (b1 >> 4) << 3
            if 0x10 <= size <= 0x78:
                out.append((o, size))
    return out
if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    hits = scan(d, int(sys.argv[2], 16), int(sys.argv[3], 16))
    print(f"entry-a1 candidates: {len(hits)}")
    for o, s in hits[:20]:
        print(f"  file 0x{o:X} framesize 0x{s:X}")
