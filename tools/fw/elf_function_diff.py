#!/usr/bin/env python3
"""Byte-hash same-named ELF functions and report implementation changes.

ARM Thumb FUNC symbols encode Thumb state in bit 0 of st_value. Clear that bit
before mapping virtual addresses to file offsets. Raw hashes still over-report
semantic changes when branch/literal addresses move; use callgraph/semantic diff
as a second pass.
"""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, subprocess
from pathlib import Path

def run(*args):
    exe=shutil.which('readelf')
    if not exe: raise SystemExit('readelf is required')
    return subprocess.run([exe,*args],text=True,capture_output=True,check=True).stdout

def sections(path: Path):
    txt=run('-SW',str(path)); out={}
    rx=re.compile(r'^\s*\[\s*(\d+)\]\s+(\S*)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\b')
    for line in txt.splitlines():
        m=rx.match(line)
        if m:
            idx=int(m.group(1)); out[idx]={'name':m.group(2),'type':m.group(3),'addr':int(m.group(4),16),'offset':int(m.group(5),16),'size':int(m.group(6),16)}
    return out

def funcs(path: Path):
    secs=sections(path); data=path.read_bytes(); txt=run('-Ws',str(path)); out={}
    for line in txt.splitlines():
        cols=line.split()
        if len(cols)<8 or not cols[0].endswith(':') or cols[3] != 'FUNC': continue
        try: value=int(cols[1],16); size=int(cols[2]); ndx=int(cols[6])
        except ValueError: continue
        if size <= 0 or ndx not in secs: continue
        sec=secs[ndx]; code_value=(value & ~1) if (value & 1) else value; rel=code_value-sec['addr']; off=sec['offset']+rel
        if rel<0 or off<0 or off+size>len(data): continue
        blob=data[off:off+size]; name=cols[7]
        item={'value':value,'value_hex':hex(value),'code_value':code_value,'code_value_hex':hex(code_value),'thumb':bool(value & 1),'size':size,'section':sec['name'],'file_offset':off,'file_offset_hex':hex(off),'sha256':hashlib.sha256(blob).hexdigest()}
        prev=out.get(name)
        if prev is None or size>prev['size']: out[name]=item
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('left',type=Path); ap.add_argument('right',type=Path); ap.add_argument('-o','--output',type=Path); args=ap.parse_args()
    a,b=funcs(args.left),funcs(args.right); common=sorted(set(a)&set(b)); changed=[]; same=[]
    for n in common:
        (same if a[n]['sha256']==b[n]['sha256'] else changed).append({'name':n,'left':a[n],'right':b[n]})
    result={'left':str(args.left),'right':str(args.right),'left_functions':len(a),'right_functions':len(b),'common_functions':len(common),'same_bytecode':len(same),'changed_bytecode':len(changed),'left_only':sorted(set(a)-set(b)),'right_only':sorted(set(b)-set(a)),'changed':changed}
    text=json.dumps(result,indent=2)
    if args.output: args.output.write_text(text,encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('left_functions','right_functions','common_functions','same_bytecode','changed_bytecode')},indent=2))
if __name__=='__main__': main()
