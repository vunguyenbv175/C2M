#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from libflow_protocol import decode_ws_binary

def safe(v):
    if isinstance(v,bytes):return {"_bytes_hex":v.hex(),"_len":len(v)}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,list):return [safe(x) for x in v]
    return v

def main():
    ap=argparse.ArgumentParser(description='Decode one C2M libflow WebSocket binary frame.')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--file',type=Path)
    g.add_argument('--hex')
    args=ap.parse_args()
    data=args.file.read_bytes() if args.file else bytes.fromhex(args.hex)
    r=decode_ws_binary(data)
    print(json.dumps({'outer':safe(r.outer),'inner':safe(r.inner),'warnings':r.warnings},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
