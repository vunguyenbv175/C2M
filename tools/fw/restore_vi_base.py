#!/usr/bin/env python3
"""Rejoin private, bounded original-VI input parts; never a firmware mutation."""
from pathlib import Path
import argparse
import hashlib

VI_SHA='f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa'
VI_BYTES=58122240
PART_BYTES=4*1024*1024


def restore(vault: Path, output: Path):
    if output.exists() or output.is_symlink():raise ValueError('Output must not exist')
    original=vault/'V2023.09.20.1_C2M_U_FR_WIFI_VI.tar'
    if original.is_file() and not original.is_symlink():
        data=original.read_bytes()
    else:
        folder=vault/'assets/vi-base-parts'
        if folder.is_symlink() or not folder.is_dir():raise ValueError('Private VI input absent')
        expected={f'part-{i:02d}.bin' for i in range((VI_BYTES+PART_BYTES-1)//PART_BYTES)}
        if {p.name for p in folder.iterdir()} != expected|{'manifest.json'}:
            raise ValueError('VI input incomplete/unexpected files')
        # Independent whole-archive pin, never trust hashes supplied by manifest.
        chunks=[]
        for i,name in enumerate(sorted(expected)):
            p=folder/name
            if p.is_symlink() or not p.is_file():raise ValueError('VI part not regular')
            n=min(PART_BYTES,VI_BYTES-i*PART_BYTES)
            if p.stat().st_size!=n:raise ValueError('VI part size mismatch')
            chunks.append(p.read_bytes())
        data=b''.join(chunks)
    if len(data)!=VI_BYTES or hashlib.sha256(data).hexdigest()!=VI_SHA:
        raise ValueError('Independent original VI pin mismatch')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(data)
    print('PRIVATE_ORIGINAL_VI_REASSEMBLY_PIN_PASS; NO_DEVICE')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vault',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();restore(a.vault,a.output)
