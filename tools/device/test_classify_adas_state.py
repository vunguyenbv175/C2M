#!/usr/bin/env python3
"""Synthetic smoke tests for classify_adas_state.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
from classify_adas_state import classify


def write(root: Path, name: str, text: str):
    p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')


def case_absent(root: Path):
    write(root,'processes.tsv','10\tcardv\t/bootconfig/bin/cardv\n')
    r=classify(root)
    assert r['classification']['class']=='A', r


def case_crash(root: Path):
    write(root,'processes.tsv','10\tcardv\t/bootconfig/bin/cardv\n')
    write(root,'dmesg.txt','adas[123]: segmentation fault\n')
    r=classify(root)
    assert r['classification']['class']=='B', r


def case_healthy_snapshot(root: Path):
    write(root,'processes.tsv','10\tcardv\t/bootconfig/bin/cardv\n20\tadas\t/customer/minieye/adas/adas\n')
    # /proc/net/tcp local 0.0.0.0:26012 in hex (659C)
    write(root,'proc_net_tcp.txt','  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n   0: 00000000:659C 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 111\n')
    r=classify(root)
    assert r['classification']['class']=='OK', r
    assert r['ports']['26012_screenservice'] is True


def case_output_candidate(root: Path):
    write(root,'processes.tsv','10\tcardv\t/bootconfig/bin/cardv\n20\tadas\t/customer/minieye/adas/adas\n')
    r=classify(root)
    assert r['classification']['class']=='UNKNOWN', r
    assert any(x['class']=='F' for x in r['candidates']), r


def run_one(fn):
    with TemporaryDirectory() as td:
        fn(Path(td))


def main():
    for fn in (case_absent,case_crash,case_healthy_snapshot,case_output_candidate):
        run_one(fn)
        print('OK',fn.__name__)

if __name__=='__main__': main()
