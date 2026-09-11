#!/usr/bin/env python3
"""Extract the appended C2M ADAS --key=value flag block and compare builds."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
START=b'--switch_file='
FLAG_RE=re.compile(rb'--([A-Za-z0-9_]+)=')

def extract(p:Path):
    d=p.read_bytes(); s=d.rfind(START)
    if s<0: raise SystemExit(f'{p}: flag block start not found')
    tail=d[s:]; ms=list(FLAG_RE.finditer(tail)); out=[]
    for i,m in enumerate(ms):
        end=ms[i+1].start() if i+1<len(ms) else len(tail)
        raw=tail[m.start():end]; cut=len(raw)
        for sep in (b'\0',b'\n',b'\r'):
            j=raw.find(sep)
            if j>=0: cut=min(cut,j)
        raw=raw[:cut]
        while raw and not (32<=raw[-1]<=126): raw=raw[:-1]
        txt=raw.decode('ascii','replace'); key,val=txt[2:].split('=',1)
        out.append({'key':key,'value':val,'file_offset':s+m.start(),'file_offset_hex':hex(s+m.start())})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('left',type=Path);ap.add_argument('right',type=Path,nargs='?');ap.add_argument('-o','--output',type=Path);args=ap.parse_args()
    A=extract(args.left); result={'left':str(args.left),'left_flags':A}
    if args.right:
        B=extract(args.right); da={x['key']:x for x in A};db={x['key']:x for x in B};diff=[]
        for k in sorted(set(da)|set(db)):
            av=da.get(k,{}).get('value');bv=db.get(k,{}).get('value')
            if av!=bv:diff.append({'key':k,'left':av,'right':bv})
        result.update({'right':str(args.right),'right_flags':B,'same_keys':set(da)==set(db),'differences':diff})
    text=json.dumps(result,indent=2)
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(json.dumps({'left_count':len(A),'right_count':len(result.get('right_flags',[])) if args.right else None,'difference_count':len(result.get('differences',[])) if args.right else None,'differences':result.get('differences',[])},indent=2))
if __name__=='__main__':main()
