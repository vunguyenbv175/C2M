#!/usr/bin/env python3
"""Disassemble Xtensa windows via rizin rz-asm (no Ghidra/Java needed).

Usage: python xtensa_dis.py <bin> <hex-vaddr> <hex-fileoff> <hex-len>
Proven on ProMax classic ESP32 entry (0x40083764) and XL-S3 IROM functions.
Requires Rizin (winget: Rizin.Rizin) for rz-asm.exe with xtensa support.
Pure offline analysis; never modifies the image.
"""
import subprocess, sys, shutil
def dis(binpath, vaddr, foff, ln, rz="rz-asm"):
    d = open(binpath, "rb").read()[foff:foff + ln]
    exe = shutil.which(rz) or r"C:\Program Files\Rizin\bin\rz-asm.exe"
    r = subprocess.run([exe, "-a", "xtensa", "-b", "32", "-o", hex(vaddr), "-d", d.hex()],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or "") + (r.stderr or "")
if __name__ == "__main__":
    print(dis(sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4], 16)))
