#!/usr/bin/env python3
"""Diff two directories produced by collect_baseline.sh.

This is a host-side tool. It emphasizes evidence relevant to EN-vs-VI ADAS and
M4 connected-vs-disconnected comparisons while also reporting generic file diffs.
"""
from __future__ import annotations
import argparse, difflib, hashlib, json
from pathlib import Path

TEXT_FOCUS = [
    'proc_cmdline.txt','proc_modules.txt','processes.tsv','netstat_anp.txt','ss_lntup.txt',
    'ifconfig_a.txt','ip_addr.txt','ip_link.txt','ip_route.txt','ip_neigh.txt',
    'proc_net_arp.txt','proc_net_dev.txt','proc_net_tcp.txt','proc_net_udp.txt','proc_net_unix.txt',
    'proc_sysvipc_shm.txt','proc_sysvipc_msg.txt','dmesg.txt','ports_of_interest.txt','high_value_files.tsv'
]

def sha(p: Path) -> str:
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def files(root: Path):
    return {str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()}

def small_text(p: Path, limit=2_000_000):
    if p.stat().st_size > limit: return None
    try: return p.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception: return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('left',type=Path); ap.add_argument('right',type=Path)
    ap.add_argument('-o','--output',type=Path)
    ap.add_argument('--diff-dir',type=Path)
    args=ap.parse_args(); a=files(args.left); b=files(args.right)
    names=sorted(set(a)|set(b)); rows=[]
    if args.diff_dir: args.diff_dir.mkdir(parents=True,exist_ok=True)
    for n in names:
        if n not in a: rows.append({'path':n,'status':'right_only'}); continue
        if n not in b: rows.append({'path':n,'status':'left_only'}); continue
        ha,hb=sha(a[n]),sha(b[n])
        if ha==hb: continue
        row={'path':n,'status':'different','left_size':a[n].stat().st_size,'right_size':b[n].stat().st_size,'left_sha256':ha,'right_sha256':hb}
        if n in TEXT_FOCUS or n.startswith('sys_class_net/') or n.startswith('usb/') or n.startswith('proc_'):
            la,lb=small_text(a[n]),small_text(b[n])
            if la is not None and lb is not None:
                d='\n'.join(difflib.unified_diff(la,lb,fromfile=f'left/{n}',tofile=f'right/{n}',lineterm=''))
                row['unified_diff']=d
                if args.diff_dir and d:
                    out=args.diff_dir/(n.replace('/','__')+'.diff'); out.write_text(d+'\n',encoding='utf-8')
        rows.append(row)
    result={'left':str(args.left),'right':str(args.right),'different_count':sum(r['status']=='different' for r in rows),'left_only_count':sum(r['status']=='left_only' for r in rows),'right_only_count':sum(r['status']=='right_only' for r in rows),'changes':rows}
    text=json.dumps(result,indent=2)
    if args.output: args.output.write_text(text,encoding='utf-8')
    print(text)
if __name__=='__main__': main()
