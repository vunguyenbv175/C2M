#!/usr/bin/env python3
"""Observer for stock cardv JSON; NOT non-interfering on this single-client server.

WARNING: EN cardv uses one global g_wsi. A second WS client overwrites it;
closing the observer clears it regardless of the native M4's connection.
Never run with M4 attached. A no-send observer can still steal its stream.
"""
from __future__ import annotations
import argparse
import websocket

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--confirm-m4-disconnected', action='store_true', required=True,
                    help='Required: M4 is physically disconnected; a second client can steal its stream')
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
