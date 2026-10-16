#!/usr/bin/env python3
"""Exact ARM shadow finite read-only no-database contract under stock QEMU.

Production target constants stay fixed. Runtime uses a private QEMU library
prefix with root-owned sticky prefix/tmp (not a path-check bypass). No private
DB, camera, radio or shared D4 writer is present. DB/GPS success fixtures are
additionally exercised by host shadow harness tests; this tests the exact
shipping observer binary's finite failure path and nonmutation guarantee.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', required=True, type=Path)
    p.add_argument('--sysroot', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    from prepare_ram_debug_sysroot import PINS, LINKS
    binary, sysroot = args.binary.resolve(), args.sysroot.resolve()
    for n, digest in PINS.items():
        f = sysroot/'lib'/n
        assert f.is_file() and not f.is_symlink() and hashlib.sha256(f.read_bytes()).hexdigest() == digest
    for n, target in LINKS.items():
        f = sysroot/'lib'/n
        assert f.is_symlink() and os.readlink(f) == target
    qemu = shutil.which('qemu-arm-static')
    assert qemu and os.geteuid() == 0
    # Run in a throwaway user of QEMU's prefix, no real camera files. The
    # shipping shadow has no path overrides and must terminate naturally.
    guest_tmp=sysroot/'tmp'
    assert not guest_tmp.is_symlink()
    guest_tmp.mkdir(mode=0o1777,exist_ok=True)
    os.chown(sysroot,0,0);sysroot.chmod(0o755)
    os.chown(guest_tmp,0,0);guest_tmp.chmod(0o1777)
    status=guest_tmp/'c2m_d4_status'
    assert not status.exists() and not status.is_symlink()
    sentinel=b'UNCHANGED-SYNTHETIC-D4-STATUS\n'
    status.write_bytes(sentinel);status.chmod(0o600)
    before=status.stat()
    binary_digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    try:
        r=subprocess.run([qemu,'-L',str(sysroot),str(binary),'--observe'],capture_output=True,timeout=20)
        (args.report.with_suffix('.stdout.txt')).write_bytes(r.stdout)
        (args.report.with_suffix('.stderr.txt')).write_bytes(r.stderr)
        assert r.returncode==0,(r.returncode,r.stderr.decode(errors='replace'))
        assert not r.stderr,r.stderr.decode(errors='replace')
        text=r.stdout.decode('ascii')
        assert len(r.stdout)<8192
        assert 'd4_shadow=observer_v2' in text
        assert 'db_valid=0 db_count=0' in text
        rows=[x for x in text.splitlines() if x.startswith('sample=')]
        assert len(rows)==10,len(rows)
        assert 'summary samples=10 ' in text and 'status_writes=0' in text
        assert 'completion=complete' in text
        assert 'delivery_sim=observer_simulation_not_production_delivery' in text
        assert all('state=no_database' in row and 'gps_fresh=0' in row and 'active=0' in row for row in rows)
        assert [int(row.split(' ', 1)[0].split('=')[1]) for row in rows] == list(range(1, 11))
        for i, row in enumerate(rows):
            fields = dict(part.split('=', 1) for part in row.split())
            assert set(fields) == {'sample', 'state', 'gps_fresh', 'active', 'code',
                'distance_m', 'event_id', 'sequence', 'gps_result', 'poll_dt_ms',
                'utc_step', 'freshness_reason', 'delivery_sim'}
            assert fields['gps_result'] == 'io_error'
            assert fields['freshness_reason'] == 'no_sample'
            assert fields['utc_step'] == 'unavailable'
            assert fields['poll_dt_ms'].isdigit() and int(fields['poll_dt_ms']) <= 30000
            if i == 0:
                assert fields['poll_dt_ms'] == '0'
        for private in ('latitude=', 'longitude=', 'speed_kmh=', 'course_deg=', 'UTC=', 'record_id='):
            assert private not in text
        after=status.stat()
        assert status.read_bytes()==sentinel and before.st_ino==after.st_ino and before.st_mtime_ns==after.st_mtime_ns
        assert not list(guest_tmp.glob('.c2m-d4-*.tmp'))
        assert binary_digest==hashlib.sha256(binary.read_bytes()).hexdigest()
    finally:
        status.unlink(missing_ok=True)
    report={'verdict':'PASS','binary_sha256':binary_digest,'stock_runtime_sha256':PINS,
            'camera_used':False,'status_writer':False,'finite_samples':10,
            'runtime':'shipping ARM shadow --observe under pinned stock QEMU',
            'database_case':'missing expected fixed private DB (no private DB in CI)',
            'status_sentinel_unchanged':True,'target_hardware_accepted':False,
            'shadow_schema':'observer_v2','same_poll_diagnostics_checked':True}
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':
    main()
