#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path


def parse_int(s: str) -> int:
    return int(s, 0)


def main():
    ap=argparse.ArgumentParser(description='Map exact-byte anchor alignment between two appended payloads.')
    ap.add_argument('left',type=Path)
    ap.add_argument('right',type=Path)
    ap.add_argument('--start',type=parse_int,required=True,help='file offset where payload starts, e.g. 0x1755e4')
    ap.add_argument('--stride',type=parse_int,default=0x1000)
    ap.add_argument('--anchor',type=parse_int,default=64)
    ap.add_argument('--window',type=parse_int,default=0x20000,help='search radius around predicted location')
    ap.add_argument('-o','--output',type=Path)
    args=ap.parse_args()
    A=args.left.read_bytes(); B=args.right.read_bytes(); start=args.start
    rows=[]; last_delta=0
    for off in range(start, max(start,len(A)-args.anchor), args.stride):
        sig=A[off:off+args.anchor]
        if len(sig)<args.anchor: break
        pred=off+last_delta
        lo=max(start,pred-args.window); hi=min(len(B),pred+args.window+args.anchor)
        positions=[]; pos=B.find(sig,lo,hi)
        while pos>=0:
            positions.append(pos)
            pos=B.find(sig,pos+1,hi)
            if len(positions)>8: break
        if not positions:
            # Fallback to a global exact search. Accept only a unique occurrence to avoid repeated padding/data.
            gp=B.find(sig,start)
            if gp>=0 and B.find(sig,gp+1)<0:
                positions=[gp]
            else:
                rows.append({'left_offset':off,'matched':False})
                continue
        # Prefer location closest to prediction; this filters repeated padding/data.
        pos=min(positions,key=lambda p: abs(p-pred))
        delta=pos-off; last_delta=delta
        rows.append({'left_offset':off,'right_offset':pos,'delta':delta,'matched':True,'candidate_count':len(positions)})
    matched=[r for r in rows if r.get('matched')]
    hist=Counter(r['delta'] for r in matched)
    runs=[]; cur=None
    for r in rows:
        d=r.get('delta') if r.get('matched') else None
        if cur is None or d!=cur['delta']:
            if cur: runs.append(cur)
            cur={'delta':d,'first_left_offset':r['left_offset'],'last_left_offset':r['left_offset'],'anchors':1}
        else:
            cur['last_left_offset']=r['left_offset']; cur['anchors']+=1
    if cur: runs.append(cur)
    result={
        'left':str(args.left),'right':str(args.right),'start':start,'start_hex':hex(start),
        'stride':args.stride,'anchor_size':args.anchor,'search_radius':args.window,
        'left_payload_size':len(A)-start,'right_payload_size':len(B)-start,
        'payload_size_delta':len(B)-len(A),
        'matched_anchors':len(matched),'total_anchors':len(rows),
        'top_deltas':[{'delta':d,'delta_hex':hex(d),'anchors':n} for d,n in hist.most_common(20)],
        'runs':[{**r,'delta_hex':None if r['delta'] is None else hex(r['delta'])} for r in runs],
        'anchors':[{**r, **({'left_hex':hex(r['left_offset'])} if 'left_offset' in r else {}), **({'right_hex':hex(r['right_offset']),'delta_hex':hex(r['delta'])} if r.get('matched') else {})} for r in rows]
    }
    if args.output: args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['start_hex','left_payload_size','right_payload_size','payload_size_delta','matched_anchors','total_anchors','top_deltas']},indent=2))

if __name__=='__main__': main()
