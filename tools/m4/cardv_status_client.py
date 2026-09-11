#!/usr/bin/env python3
"""Passive client for cardv's stock JSON WebSocket server on port 8080."""
from __future__ import annotations
import argparse
import websocket

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('host')
    ap.add_argument('--port',type=int,default=8080)
    ap.add_argument('--path',default='/')
    ap.add_argument('--timeout',type=float,default=10.0)
    args=ap.parse_args()
    url=f"ws://{args.host}:{args.port}{args.path}"
    ws=websocket.create_connection(url,timeout=args.timeout,subprotocols=['minieye-websocket'])
    try:
        while True:
            msg=ws.recv()
            if msg is None:break
            print(msg)
    finally:ws.close()
if __name__=='__main__':main()
