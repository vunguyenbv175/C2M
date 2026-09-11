#!/usr/bin/env python3
"""Rank M4 transport candidates from two C2M baseline captures.

Expected usage compares M4 disconnected (left) with M4 connected (right).
No packet injection is performed; this is offline analysis only.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

SOCK_RE=re.compile(r"socket:\[(\d+)\]")

def read(p: Path) -> str:
    try: return p.read_text(encoding='utf-8',errors='replace')
    except Exception: return ''

def lines(p: Path): return {x for x in read(p).splitlines() if x.strip()}

def net_ifaces(root: Path):
    d=root/'sys_class_net'
    if not d.is_dir(): return {}
    out={}
    for p in d.iterdir():
        if not p.is_dir(): continue
        out[p.name]={f:read(p/f).strip() for f in ('address','operstate','carrier','mtu','speed','type','device_link.txt') if (p/f).exists()}
    return out

def usb_devices(root: Path):
    d=root/'usb'; out={}
    if not d.is_dir(): return out
    for p in d.iterdir():
        if not p.is_dir(): continue
        vals={}
        for f in ('idVendor','idProduct','manufacturer','product','serial','bDeviceClass','bInterfaceClass','bInterfaceSubClass','bInterfaceProtocol','driver_link.txt'):
            if (p/f).exists(): vals[f]=read(p/f).strip()
        if vals: out[p.name]=vals
    return out

def arp(root: Path):
    out=[]
    for ln in read(root/'proc_net_arp.txt').splitlines()[1:]:
        parts=ln.split()
        if len(parts)>=6: out.append({'ip':parts[0],'hw_type':parts[1],'flags':parts[2],'mac':parts[3],'mask':parts[4],'iface':parts[5]})
    return out

def processes(root: Path):
    out={}
    for ln in read(root/'processes.tsv').splitlines():
        p=ln.split('\t',2)
        if len(p)>=2: out[p[0]]={'pid':p[0],'comm':p[1],'cmd':p[2] if len(p)>2 else ''}
    return out

def socket_owners(root: Path):
    owners={}
    for d in root.glob('proc_*'):
        if not d.is_dir(): continue
        m=re.match(r'proc_(\d+)_(.*)',d.name)
        if not m: continue
        pid,comm=m.group(1),m.group(2)
        for ln in read(d/'fd.txt').splitlines():
            sm=SOCK_RE.search(ln)
            if sm: owners.setdefault(sm.group(1),[]).append({'pid':pid,'comm':comm,'fd_line':ln})
    return owners

def decode_proc_net(path: Path, proto: str, owners: dict):
    rows=[]
    for ln in read(path).splitlines()[1:]:
        p=ln.split()
        if len(p)<10: continue
        try:
            _,lport_hex=p[1].split(':'); _,rport_hex=p[2].split(':')
            inode=p[9]
            rows.append({'proto':proto,'local_port':int(lport_hex,16),'remote_port':int(rport_hex,16),'state_hex':p[3],'inode':inode,'owners':owners.get(inode,[])})
        except Exception: pass
    return rows

def sockets(root: Path):
    own=socket_owners(root); rows=[]
    for fn,proto in [('proc_net_tcp.txt','tcp'),('proc_net_tcp6.txt','tcp6'),('proc_net_udp.txt','udp'),('proc_net_udp6.txt','udp6')]:
        rows += decode_proc_net(root/fn,proto,own)
    return rows

def sock_key(x): return (x['proto'],x['local_port'],x['remote_port'],tuple(sorted((o['comm'],o['pid']) for o in x['owners'])))

def summarize(left: Path,right: Path):
    li,ri=net_ifaces(left),net_ifaces(right)
    lu,ru=usb_devices(left),usb_devices(right)
    la,ra=arp(left),arp(right)
    lp,rp=processes(left),processes(right)
    ls,rs=sockets(left),sockets(right)
    new_if={k:v for k,v in ri.items() if k not in li}
    changed_if={k:{'left':li[k],'right':ri[k]} for k in sorted(set(li)&set(ri)) if li[k]!=ri[k]}
    new_usb={k:v for k,v in ru.items() if k not in lu}
    new_arp=[x for x in ra if x not in la]
    new_proc=[v for pid,v in rp.items() if pid not in lp and not any(v['comm']==q['comm'] and v['cmd']==q['cmd'] for q in lp.values())]
    lkeys={sock_key(x) for x in ls}; new_sock=[x for x in rs if sock_key(x) not in lkeys]
    input_left=lines(left/'proc_input_devices.txt'); input_right=lines(right/'proc_input_devices.txt')
    new_input=sorted(input_right-input_left)
    evidence=[]
    for name,v in new_if.items(): evidence.append({'score':100,'kind':'new_network_interface','subject':name,'details':v})
    for name,v in new_usb.items(): evidence.append({'score':100,'kind':'new_usb_device','subject':name,'details':v})
    for x in new_arp: evidence.append({'score':80,'kind':'new_arp_peer','subject':x['ip'],'details':x})
    for x in new_sock:
        score=90 if x['local_port'] in (26012,8080) or x['remote_port'] in (26012,8080) else 55
        if any(o['comm'] in ('adas','cardv') or 'adas' in o['comm'].lower() or 'cardv' in o['comm'].lower() for o in x['owners']): score+=10
        evidence.append({'score':min(score,100),'kind':'new_socket','subject':f"{x['proto']} {x['local_port']}->{x['remote_port']}",'details':x})
    if new_input: evidence.append({'score':45,'kind':'input_device_delta','subject':'/proc/bus/input/devices','details':new_input})
    for x in new_proc: evidence.append({'score':35,'kind':'new_process','subject':x['comm'],'details':x})
    for name,v in changed_if.items():
        if v['left'].get('operstate')!=v['right'].get('operstate') or v['left'].get('carrier')!=v['right'].get('carrier'):
            evidence.append({'score':70,'kind':'interface_state_change','subject':name,'details':v})
    evidence.sort(key=lambda x:(-x['score'],x['kind'],x['subject']))
    return {'left':str(left),'right':str(right),'assumption':'left=M4_off, right=M4_on','new_interfaces':new_if,'changed_interfaces':changed_if,'new_usb_devices':new_usb,'new_arp_peers':new_arp,'new_sockets':new_sock,'new_processes':new_proc,'new_input_lines':new_input,'ranked_evidence':evidence}

def markdown(r):
    out=['# M4 transport discovery','',f"Left: `{r['left']}`",f"Right: `{r['right']}`",'', '## Ranked evidence','']
    if not r['ranked_evidence']: out.append('No transport-specific delta detected.')
    for e in r['ranked_evidence']:
        out.append(f"- **{e['score']:03d}** `{e['kind']}` — `{e['subject']}`")
    out += ['', '## Interpretation', '', 'A new USB device + new network interface + new peer/socket on the M4-connected capture is strong evidence for USB-network transport. A socket owned by `adas`/`cardv`, especially involving 26012 or 8080, should be captured next with tcpdump. Absence of such evidence does not prove a non-USB transport; inspect input/device-node and process-FD deltas.','']
    return '\n'.join(out)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('m4_off',type=Path); ap.add_argument('m4_on',type=Path)
    ap.add_argument('-o','--output',type=Path); ap.add_argument('--markdown',type=Path)
    a=ap.parse_args(); r=summarize(a.m4_off,a.m4_on); txt=json.dumps(r,indent=2)
    if a.output: a.output.write_text(txt,encoding='utf-8')
    if a.markdown: a.markdown.write_text(markdown(r),encoding='utf-8')
    print(txt)
if __name__=='__main__': main()
