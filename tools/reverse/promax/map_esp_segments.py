#!/usr/bin/env python3
"""Map ESP image segments to virtual addresses using esptool (preferred) or pure-python fallback.

Usage:
  python map_esp_segments.py <app-image.bin> [--json]
  python map_esp_segments.py <merged-flash.bin> --flash-offset 0x10000 --len 0x3D0000

Prefers `esptool image-info` when installed; otherwise parses the 24B v1/v2
header + 8B segment headers in pure python. Prints esptool-equivalent table:
seg / length / load VA / file offset / memory type + flashVA mapping formula.

C2M provenance: written for ProMax V4 static analysis (classic ESP32 +
XL ESP32-S3 OTA). No firmware modified.
"""
import struct, sys, json, subprocess, shutil, os
MEM = {(0x3F400020, 0x4000000): "DROM", (0x3FF80000, 0x100000): "DRAM",
       (0x40080000, 0x100000): "IRAM", (0x400D0020, 0x400000): "IROM",
       (0x3C000000, 0x1000000): "S3-DROM", (0x42000000, 0x1000000): "S3-IROM",
       (0x3FCA0000, 0x100000): "S3-DRAM", (0x40370000, 0x100000): "S3-IRAM"}
def memtype(va):
    for (b, ln), n in MEM.items():
        if b <= va < b + ln: return n
    return "UNKNOWN"
def pure_map(path):
    d = open(path, "rb").read()
    if d[0] != 0xE9: return {"error": f"bad magic 0x{d[0]:02X} (merged flash? use --flash-offset)"}
    segs = d[1]; entry = struct.unpack_from("<I", d, 4)[0]
    chip = struct.unpack_from("<H", d, 12)[0]
    out = {"image": path, "size": len(d), "segments": segs, "entry": hex(entry), "chip": chip, "map": []}
    pos = 24
    for i in range(segs):
        va, ln = struct.unpack_from("<II", d, pos); pos += 8
        out["map"].append({"seg": i, "load": hex(va), "len": hex(ln), "fileoff": hex(pos),
                           "mem": memtype(va)})
        pos += ln
    return out
def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    path = a[0]
    if "--flash-offset" in sys.argv:
        fo = int(sys.argv[sys.argv.index("--flash-offset") + 1], 0)
        ln = int(sys.argv[sys.argv.index("--len") + 1], 0)
        d = open(path, "rb").read()[fo:fo + ln]
        tmp = os.environ.get("TEMP", ".") + "/_mapseg_tmp.bin"
        open(tmp, "wb").write(d); path = tmp
    if shutil.which("esptool"):
        r = subprocess.run(["esptool", "image-info", path], capture_output=True, text=True)
        print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
    print(json.dumps(pure_map(path), indent=2))
if __name__ == "__main__": main()
