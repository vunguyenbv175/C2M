#!/usr/bin/env python3
"""Extract printable PC-relative literal strings referenced by named Thumb functions.

Designed for the position-independent ARM/Thumb patterns used by C2M binaries:
    ldr(.w) rN, [pc, #imm]
    ...
    add(.w) rN, pc
The literal is interpreted as a signed 32-bit displacement and resolved through
ELF PT_LOAD mappings. Output is evidence/candidate data, not a decompiler.
"""
from __future__ import annotations
import argparse, json, re, struct, subprocess
from pathlib import Path

NM_RE=re.compile(r'^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\w\s+(.+)$')
INS_RE=re.compile(r'^\s*([0-9a-fA-F]+):\s+([A-Za-z0-9_.]+)\s*(.*?)\s*$')
LDR_RE=re.compile(r'^(r(?:1[0-2]|[0-9])|lr), \[pc, #0x([0-9a-fA-F]+)\]$')

def run(cmd):
    return subprocess.run(cmd,text=True,capture_output=True,check=True).stdout

def loads(blob:bytes):
    if blob[:4]!=b'\x7fELF' or blob[4]!=1 or blob[5]!=1:
        raise SystemExit('ELF32 little-endian required')
    phoff=struct.unpack_from('<I',blob,28)[0]
    entsz=struct.unpack_from('<H',blob,42)[0]
    num=struct.unpack_from('<H',blob,44)[0]
    out=[]
    for i in range(num):
        o=phoff+i*entsz
        typ,off,va,_pa,fs,_ms,_fl,_al=struct.unpack_from('<IIIIIIII',blob,o)
        if typ==1 and fs: out.append((va,va+fs,off))
    return out

def file_off(maps,va):
    for lo,hi,off in maps:
        if lo<=va<hi:return off+(va-lo)
    return None

def cstring(blob,maps,va,maxlen=256):
    off=file_off(maps,va)
    if off is None:return None
    raw=blob[off:off+maxlen].split(b'\0',1)[0]
    if not raw:return None
    try:s=raw.decode('utf-8')
    except UnicodeDecodeError:return None
    if not all(ch.isprintable() or ch in '\t\r\n' for ch in s):return None
    return s

def functions(path:Path,needle:str):
    out=[]
    for line in run(['nm','-D','-S','-C',str(path)]).splitlines():
        m=NM_RE.match(line)
        if m and needle in m.group(3):
            out.append((int(m.group(1),16)&~1,int(m.group(2),16),m.group(3)))
    return out

def inspect(path:Path,start:int,size:int,blob,maps):
    text=run(['llvm-objdump','-d','--no-show-raw-insn','--triple=thumbv7-linux-gnueabihf',f'--start-address={start}',f'--stop-address={start+size}',str(path)])
    ins=[]
    for line in text.splitlines():
        m=INS_RE.match(line)
        if m:
            op=m.group(3).split('@',1)[0].strip()
            ins.append((int(m.group(1),16),m.group(2).lower(),op))
    rows=[]
    for i,(a,mn,op) in enumerate(ins):
        if not mn.startswith('ldr'):continue
        lm=LDR_RE.match(op)
        if not lm:continue
        reg,imm=lm.group(1),int(lm.group(2),16)
        lit=((a+4)&~3)+imm
        off=file_off(maps,lit)
        if off is None or off+4>len(blob):continue
        delta=struct.unpack_from('<i',blob,off)[0]
        for j in range(i+1,min(len(ins),i+7)):
            aa,mm,oo=ins[j]
            if mm.startswith('add') and re.match(rf'^{re.escape(reg)}, pc(?:$|,)',oo):
                target=(aa+4+delta)&0xffffffff
                s=cstring(blob,maps,target)
                if s:
                    rows.append({'load_addr':a,'literal_addr':lit,'add_addr':aa,'target_addr':target,'string':s})
                break
    seen=set(); uniq=[]
    for r in rows:
        k=(r['target_addr'],r['string'])
        if k not in seen:seen.add(k);uniq.append(r)
    return uniq

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('binary',type=Path)
    ap.add_argument('--contains',required=True,help='substring in demangled dynamic symbol name')
    ap.add_argument('-o','--output',type=Path)
    args=ap.parse_args()
    blob=args.binary.read_bytes(); maps=loads(blob)
    fs=functions(args.binary,args.contains)
    result={'binary':str(args.binary),'query':args.contains,'functions':[]}
    seen_funcs=set()
    for start,size,name in fs:
        key=(start,size,name)
        if key in seen_funcs:continue
        seen_funcs.add(key)
        result['functions'].append({'name':name,'start':start,'start_hex':hex(start),'size':size,'strings':inspect(args.binary,start,size,blob,maps)})
    if args.output:args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for f in result['functions']:
        print(f"{f['start_hex']} +{f['size']} {f['name']}")
        for r in f['strings']:print(f"  {hex(r['target_addr'])}: {r['string']}")

if __name__=='__main__':main()
