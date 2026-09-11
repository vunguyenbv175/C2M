#!/usr/bin/env python3
"""Compare same-name ARM Thumb function call sequences in two ELF files.

Resolves exact internal FUNC targets and ARM PLT stubs to relocation symbol names.
Unresolved indirect/register and symbolized targets are retained but should be
reviewed as lower-confidence evidence.
"""
from __future__ import annotations
import argparse,json,re,subprocess,shutil
from pathlib import Path
INSN_RE=re.compile(r'^\s*([0-9a-fA-F]+):\s+([A-Za-z0-9_.]+|<unknown>)\s*(.*?)\s*$')
TARGET_NUM=re.compile(r'^(?:0x)?([0-9a-fA-F]+)')

def run(cmd): return subprocess.run(cmd,text=True,capture_output=True,check=True).stdout

def funcs(p):
    o=run(['readelf','-Ws',str(p)]); d={}; by={}
    for line in o.splitlines():
        c=line.split()
        if len(c)<8 or not c[0].endswith(':') or c[3]!='FUNC': continue
        try: v=int(c[1],16); sz=int(c[2]); int(c[6])
        except: continue
        if sz<=0: continue
        a=v&~1; n=c[7]
        if n not in d or sz>d[n]['size']: d[n]={'addr':a,'size':sz}; by[a]=n
    return d,by

def pltmap(p):
    obj=shutil.which('llvm-objdump')
    if not obj: raise SystemExit('llvm-objdump required')
    po=run([obj,'-d','-j','.plt','--no-show-raw-insn','--triple=armv7-linux-gnueabihf',str(p)])
    starts=[]
    for line in po.splitlines():
        m=re.match(r'\s*([0-9a-fA-F]+):\s+add\s+r12, pc',line)
        if m: starts.append(int(m.group(1),16))
    ro=run(['readelf','-rW',str(p)]); rel=[]; active=False
    for line in ro.splitlines():
        if "Relocation section '.rel.plt'" in line: active=True; continue
        if active and line.startswith('Relocation section'): break
        if active and 'R_ARM_JUMP_SLOT' in line:
            c=line.split(); rel.append(c[-1].split('@')[0])
    if len(starts)!=len(rel): raise SystemExit(f'PLT/rel count mismatch {len(starts)} != {len(rel)}')
    return dict(zip(starts,rel))

def disasm(p):
    obj=shutil.which('llvm-objdump')
    if not obj: raise SystemExit('llvm-objdump required')
    o=run([obj,'-d','--no-show-raw-insn','--triple=thumbv7-linux-gnueabihf',str(p)])
    a=[]
    for line in o.splitlines():
        m=INSN_RE.match(line)
        if m:a.append((int(m.group(1),16),m.group(2).lower(),m.group(3)))
    return a

def calls_by_func(p):
    fs,by=funcs(p); pm=pltmap(p); ins=disasm(p); out={}; i=0
    for name,f in sorted(fs.items(), key=lambda kv:kv[1]['addr']):
        lo,hi=f['addr'],f['addr']+f['size']
        while i<len(ins) and ins[i][0]<lo:i+=1
        j=i; cs=[]
        while j<len(ins) and ins[j][0]<hi:
            adr,mn,op=ins[j]
            if adr>=lo and mn in ('bl','blx'):
                mt=TARGET_NUM.match(op.strip())
                if mt:
                    t=int(mt.group(1),16)
                    if t in pm: callee='PLT:'+pm[t]
                    elif t in by: callee='FUNC:'+by[t]
                    elif lo<=t<hi: callee='LOCAL'
                    else:
                        am=re.search(r'<([^>]+)>',op)
                        callee='SYM:'+am.group(1).split('+')[0] if am else 'ADDR'
                else: callee='INDIRECT:'+re.sub(r'\s+',' ',op.strip())
                cs.append({'offset':adr-lo,'mnemonic':mn,'callee':callee})
            j+=1
        out[name]={'addr':lo,'size':f['size'],'calls':cs}
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('left',type=Path);ap.add_argument('right',type=Path);ap.add_argument('-o','--output',type=Path);args=ap.parse_args()
    a,b=calls_by_func(args.left),calls_by_func(args.right); common=sorted(set(a)&set(b)); changed=[]; same=0
    for n in common:
        sa=[(x['mnemonic'],x['callee']) for x in a[n]['calls']]; sb=[(x['mnemonic'],x['callee']) for x in b[n]['calls']]
        if sa==sb:same+=1
        else:changed.append({'name':n,'left_size':a[n]['size'],'right_size':b[n]['size'],'left_calls':a[n]['calls'],'right_calls':b[n]['calls']})
    result={'left':str(args.left),'right':str(args.right),'common_functions':len(common),'same_call_sequence':same,'changed_call_sequence':len(changed),'changed':changed}
    if args.output:args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('common_functions','same_call_sequence','changed_call_sequence')},indent=2))
if __name__=='__main__':main()
