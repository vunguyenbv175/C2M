#!/usr/bin/env python3
"""Parse Espressif ESP image headers + partition table (pure python, no deps).

Usage:
  python parse_esp_image.py <firmware.bin> [--json]
  python parse_esp_image.py --all <dir> [--json]

Proves chip family from image header chip_id field at header+12, never from
product naming. Chip IDs (ESP-IDF esp_image_spi_app.c / esptool):
  0=ESP32, 2=ESP32-S2, 5=ESP32-C3, 9=ESP32-S3, 12=ESP32-C2, 13=ESP32-C6, 16=ESP32-H2
Flash size byte (header+3): 0x20=4MB, 0x2F=4MB(C3 variant encoding), 0x3F=16MB, 0x4F=16MB(S3)
Partition magic: 0x50AA, 32B entries at flash 0x8000.
"""
import struct, sys, os, json, hashlib

CHIP_MAP = {0:"ESP32",2:"ESP32-S2",5:"ESP32-C3",9:"ESP32-S3",12:"ESP32-C2",13:"ESP32-C6",16:"ESP32-H2"}
FLASH_MAP = {0x20:"4MB",0x21:"2MB",0x22:"1MB",0x23:"8MB",0x24:"16MB",0x2F:"4MB(C3-enc)",0x3F:"16MB",0x4F:"16MB(S3-enc)"}

def parse_header(d, off):
    if off+24 > len(d):
        return {"offset":off,"error":"short"}
    magic=d[off]
    if magic!=0xE9:
        return {"offset":hex(off),"magic":hex(magic),"valid":False}
    segs=d[off+1]; fm=d[off+2]; fs=d[off+3]
    entry=struct.unpack_from("<I",d,off+4)[0]
    chip=struct.unpack_from("<H",d,off+12)[0]
    return {"offset":hex(off),"valid":True,"magic":"0xe9","segments":segs,
      "flash_mode":hex(fm),"flash_size_byte":hex(fs),
      "flash_size_decoded":FLASH_MAP.get(fs,"UNKNOWN"),
      "entry":hex(entry),"chip_id":chip,
      "chip_decoded":CHIP_MAP.get(chip,f"UNKNOWN({chip})")}

def parse_partitions(d, base=0x8000, maxn=16):
    parts=[]
    for i in range(maxn):
        e=d[base+i*32:base+(i+1)*32]
        if len(e)<32: break
        if e==b"\xFF"*32:
            parts.append({"index":i,"erased":True}); continue
        magic=struct.unpack("<H",e[0:2])[0]
        if magic!=0x50AA:
            parts.append({"index":i,"magic":hex(magic),"valid":False,"raw":e[:16].hex()})
            break
        typ=e[2]; sub=e[3]
        foff=struct.unpack("<I",e[4:8])[0]; size=struct.unpack("<I",e[8:12])[0]
        name=e[12:28].split(b"\x00")[0].decode(errors="replace")
        flags=struct.unpack("<I",e[28:32])[0]
        parts.append({"index":i,"valid":True,"type":hex(typ),"subtype":hex(sub),
          "offset":hex(foff),"offset_int":foff,"size":hex(size),"size_int":size,"name":name,"flags":hex(flags)})
    return parts

def analyze(path):
    d=open(path,"rb").read()
    out={"image":os.path.basename(path),"path":path,"size":len(d),
      "sha256":hashlib.sha256(d).hexdigest()}
    hdrs=[]
    for off in (0,0x1000,0x10000):
        if off < len(d) and d[off]==0xE9:
            hdrs.append(parse_header(d,off))
    out["headers"]=hdrs
    # partition table candidate at 0x8000
    if len(d)>0x8000+32 and d[0x8000:0x8002]==b"\xAA\x50":
        out["partitions"]=parse_partitions(d,0x8000)
    else:
        out["partitions"]=[]
        out["partition_note"]="no 0x50AA at 0x8000 (OTA app-only dump or erased)"
    # sdk/toolchain hints (offsets, not proof of chip alone)
    hints={}
    for n in (b"esp-idf v",b"v4.4.",b"v5.3.",b"xtensa",b"riscv",b"esp32c3",b"esp32s3",b"NimBLE",b"nimble",b"Bluedroid",b"Arduino"):
        i=d.find(n)
        if i>=0: hints[n.decode()]={"offset":hex(i),"count":d.count(n)}
    out["sdk_hints"]=hints
    return out

def main():
    args=[a for a in sys.argv[1:] if not a.startswith("--")]
    asjson="--json" in sys.argv
    results=[]
    if "--all" in sys.argv:
        root=args[0] if args else "."
        for dp,_,fns in os.walk(root):
            for fn in sorted(fns):
                if fn.endswith(".bin"):
                    results.append(analyze(os.path.join(dp,fn)))
    else:
        for a in args:
            results.append(analyze(a))
    if asjson or "--all" in sys.argv:
        print(json.dumps(results,indent=2))
    else:
        for r in results:
            print(f"== {r['path']} size={r['size']} sha256={r['sha256'][:16]}..")
            for h in r["headers"]: print("  HDR",h)
            for p in r["partitions"]: print("  PART",p)
            print("  HINTS",{k:v["offset"] for k,v in r["sdk_hints"].items()})
if __name__=="__main__": main()
