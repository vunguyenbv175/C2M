#!/usr/bin/env python3
"""Package ACTIVE one-public-key authorization request, never firmware or private keys."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from package_m4_adb import checked_elf
from prepare_ram_debug_sysroot import PINS
ROOT=Path(__file__).resolve().parents[2]
SOURCES=["fw/m4_adb/m4_adb_authorize.c", "fw/m4_adb/build_authorize_arm.sh",
         "fw/device_minimal/start.S", "fw/device_minimal/check_elf.py", "fw/d3/compat.h",
         "tools/fw/test_ram_m4_authorize_stock_qemu.py", "tools/fw/package_m4_authorize.py",
         "tools/fw/package_m4_adb.py", "tests/test_m4_adb_authorize.py",
         "tools/m4/adb_owner_key.py", "tools/m4/test_adb_owner_key.py",
         ".github/workflows/ram-debug-arm.yml"]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--evidence',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():raise SystemExit('Refuse existing bundle')
    blob=checked_elf(a.binary);digest=hashlib.sha256(blob).hexdigest()
    r=json.loads((a.evidence/'arm-m4-authorize-runtime.json').read_bytes())
    required={'verdict':'PASS','camera_used':False,'binary_sha256':digest,
              'stock_runtime_sha256':PINS,'window_ms':35000,'max_out_calls':4,
              'max_in_calls':4,'max_out_bytes':766,'sentinel_unchanged':True,
              'missing_usb_fail_closed':True,'undefined_import_gate':True}
    if any(r.get(k)!=v for k,v in required.items()):raise SystemExit('Missing exact authorization proof')
    rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if rev!=os.environ.get('GITHUB_SHA',rev):raise SystemExit('Source revision mismatch')
    for name in SOURCES:
        if subprocess.check_output(['git','show',rev+':'+name],cwd=ROOT)!=(ROOT/name).read_bytes():
            raise SystemExit('Source differs from revision')
    subprocess.run(['python3','fw/device_minimal/check_elf.py',str(a.binary),'--allow-dynamic'],cwd=ROOT,check=True,timeout=30)
    m={'schema':1,'kind':'OWNER-PRIVATE-RAM-STANDARD-AUTHORIZATION-REQUEST-NOT-UPDATER',
       'asset':'c2m-m4-authorize','source_commit':rev,'github_run_id':os.environ.get('GITHUB_RUN_ID','local'),
       'sha256':{'c2m-m4-authorize':digest},'bytes':{'c2m-m4-authorize':len(blob)},
       'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in SOURCES},
       'stock_qemu_m4_authorize':'PASS','window_ms':35000,'max_out_calls':4,'max_in_calls':4,
       'max_out_bytes':766,'one_cnxn_then_one_public_key':True,'usb_interface':2,'vid_pid':'2207:0013',
       'private_keys_included':False,'public_keys_included':False,'shell_commands':False,
       'authentication_bypass':False,'ui_permission_request':True,'ui_sign_injection':False,
       'camera_used':False,'radio_used':False,'firmware_package_created':False,'hardware_accepted':False}
    a.output.mkdir(parents=True)
    (a.output/'c2m-m4-authorize').write_bytes(blob);(a.output/'c2m-m4-authorize').chmod(0o700)
    (a.output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    md=hashlib.sha256((a.output/'manifest.json').read_bytes()).hexdigest()
    (a.output/'SHA256SUMS.txt').write_text(f'{digest}  c2m-m4-authorize\n{md}  manifest.json\n',encoding='ascii')
    print(json.dumps({'verdict':'M4-STANDARD-AUTH-REQUEST-BUNDLE','source_commit':rev,'sha256':digest,'hardware_accepted':False}))


if __name__=='__main__':main()
