#!/usr/bin/env python3
"""Read-only subscriber for the stock C2M ADAS ScreenService.

Do not use against a vehicle in motion during early validation. This sends only
libflow subscribe frames and never injects ADAS state.
"""
from __future__ import annotations
import argparse,json
import websocket
from libflow_protocol import pack_subscription,decode_ws_binary

def clean(v):
    if isinstance(v,bytes):return f"<bytes:{len(v)}>"
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,list):return [clean(x) for x in v]
    return v

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('host')
    ap.add_argument('--port',type=int,default=26012)
    ap.add_argument('--path',default='/')
    ap.add_argument('--source',default='c2m-re')
    ap.add_argument('--topics',default='vehicle,ped,lane')
    ap.add_argument('--timeout',type=float,default=10.0)
    args=ap.parse_args()
    url=f"ws://{args.host}:{args.port}{args.path}"
    ws=websocket.create_connection(url,timeout=args.timeout)
    try:
        for topic in [x.strip() for x in args.topics.split(',') if x.strip()]:
            ws.send(pack_subscription(args.source,topic),opcode=websocket.ABNF.OPCODE_BINARY)
            print(f"subscribed request: {topic}")
        while True:
            opcode,payload=ws.recv_data(control_frame=True)
            if opcode==websocket.ABNF.OPCODE_BINARY:
                r=decode_ws_binary(payload)
                print(json.dumps({'outer':clean(r.outer),'inner':clean(r.inner),'warnings':r.warnings},ensure_ascii=False))
            elif opcode==websocket.ABNF.OPCODE_TEXT:
                print('text:',payload.decode() if isinstance(payload,bytes) else payload)
            elif opcode==websocket.ABNF.OPCODE_CLOSE:
                break
    finally:
        ws.close()
if __name__=='__main__':main()
