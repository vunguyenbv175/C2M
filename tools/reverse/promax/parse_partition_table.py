#!/usr/bin/env python3
"""Parse ESP32 partition table at given flash offset (default 0x8000).

Usage: python parse_partition_table.py <firmware.bin> [offset]
Output: human + JSON. Validates 0x50AA magic, 32B entries, AAA.../FFFF terminator.
Type 0x00=app, 0x01=data. Subtypes: app factory=0x00, ota_0..15=0x10.., data ota=0x00,
phy=0x01, nvs=0x02, coredump=0x03, spiffs/littlefs/fat=0x82 (label distinguishes).
"""
import struct,sys,json
def parse(path,base=0x8000):
    d=open(path,"rb").read()
    parts=[]
    for i in range(16):
        e=d[base+i*32:base+(i+1)*32]
        if e==b"\xFF"*32:
            parts.append({"index":i,"erased":True}); continue
        magic=struct.unpack("<H",e[:2])[0]
        if magic!=0x50AA:
            parts.append({"index":i,"valid":False,"magic":hex(magic)}); break
        typ,sub=e[2],e[3]
        foff,sz=struct.unpack("<II",e[4:12])
        name=e[12:28].split(b"\x00")[0].decode(errors="replace")
        flags=struct.unpack("<I",e[28:32])[0]
        parts.append({"index":i,"valid":True,"type":f"0x{typ:02x}","subtype":f"0x{sub:02x}",
          "offset":f"0x{foff:x}","size":f"0x{sz:x}","size_dec":sz,"name":name,"flags":f"0x{flags:x}"})
    return parts
if __name__=="__main__":
    p=sys.argv[1]; base=int(sys.argv[2],0) if len(sys.argv)>2 else 0x8000
    r=parse(p,base)
    for x in r: print(x)
    print(json.dumps(r,indent=2))
