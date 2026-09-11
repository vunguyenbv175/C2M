#!/usr/bin/env python3
"""Diff two ESP firmware images: size/sha/headers/string-set/version-string deltas.

Usage: python diff_esp_firmware.py <old.bin> <new.bin> [--json]
Highlights added/removed strings matching protocol vocabulary so version-to-version
protocol handler additions (lane/road/camera/UUID/adapter) can be isolated without
disassembling the whole image.
"""
import hashlib,sys,json,re
VOCAB=[b"lane",b"roundabout",b"camera",b"speed_limit",b"VIETMAP",b"8a7e",b"FFF",b"IMG_START",b"DTBK",b"want",b"proto",b"adapter",b"pong",b"ping",b"dev",b"nav",b"spd",b"lim",b"trn",b"dst",b"alrs",b"lan",b"Guition",b"Waveshare",b"NimBLE",b"Bluedroid",b"kimdung",b"openai",b"192.168"]
def strset(d,minl=4):
    out=set(); cur=b""
    for b in d:
        if 32<=b<127: cur+=bytes((b,))
        else:
            if len(cur)>=minl: out.add(cur)
            cur=b""
    if len(cur)>=minl: out.add(cur)
    return out
def main():
    a,b=sys.argv[1],sys.argv[2]
    da=open(a,"rb").read(); db=open(b,"rb").read()
    info={"a":{"path":a,"size":len(da),"sha256":hashlib.sha256(da).hexdigest()},
          "b":{"path":b,"size":len(db),"sha256":hashlib.sha256(db).hexdigest()},
          "size_delta":len(db)-len(da)}
    sa=strset(da); sb=strset(db)
    info["strings_added"]=sorted(x.decode(errors="replace")[:160] for x in (sb-sa) if any(v.lower() in x.lower() for v in VOCAB))[:200]
    info["strings_removed"]=sorted(x.decode(errors="replace")[:160] for x in (sa-sb) if any(v.lower() in x.lower() for v in VOCAB))[:200]
    info["added_count"]=len(sb-sa); info["removed_count"]=len(sa-sb)
    for x in info["strings_added"][:60]: print("+",x)
    for x in info["strings_removed"][:60]: print("-",x)
    print(f"size {len(da)}->{len(db)} delta {info['size_delta']} added_str {info['added_count']} removed {info['removed_count']}")
    if "--json" in sys.argv: print(json.dumps(info,indent=2))
if __name__=="__main__": main()
