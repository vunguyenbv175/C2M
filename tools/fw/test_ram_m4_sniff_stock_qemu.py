#!/usr/bin/env python3
"""Exact ARM M4 usb0 observer finite no-transmit contract under stock QEMU.

No camera, radio, private DB, or shared writer is present. QEMU has no usb0,
so the shipping observer must take the finite iface_unavailable path without
mutating any sentinel file. Host synthetic parsing is covered by host tests;
this tests the exact shipping binary's finite failure path and nonmutation.
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
    # QEMU user-mode uses host interfaces. Never accidentally sniff a host
    # usb0 on the mandatory no-interface fixture path.
    assert not Path('/sys/class/net/usb0').exists(), 'Fixture host unexpectedly has usb0'
    guest_tmp = sysroot/'tmp'
    assert not guest_tmp.is_symlink()
    guest_tmp.mkdir(mode=0o1777, exist_ok=True)
    os.chown(sysroot, 0, 0); sysroot.chmod(0o755)
    os.chown(guest_tmp, 0, 0); guest_tmp.chmod(0o1777)
    status = guest_tmp/'c2m_d4_status'
    assert not status.exists() and not status.is_symlink()
    sentinel = b'UNCHANGED-SYNTHETIC-D4-STATUS\n'
    status.write_bytes(sentinel); status.chmod(0o600)
    before = status.stat()
    binary_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    blob = binary.read_bytes()
    for forbidden in (b'--serve', b'--db', b'--gps-file', b'--status-file', b'c2m_d4_status'):
        assert forbidden not in blob, f'writer/fixture token present: {forbidden!r}'
    # Inspect actual undefined ELF imports, not C-call-shaped substrings.
    # Dynamic symbol names contain no '('; the old byte grep was not a gate.
    symbols = subprocess.check_output(['arm-linux-gnueabihf-readelf', '--wide',
                                      '--dyn-syms', str(binary)], text=True)
    # Column 7 is Name; a trailing '(version-index)' is NOT the symbol name.
    imports = {row.split()[7].split('@')[0] for row in symbols.splitlines()
               if ' UND ' in row and len(row.split()) >= 8}
    assert {'socket', 'bind', 'recvfrom', 'poll'} <= imports, 'Unparsed/missing capture imports'
    forbidden_calls = {'send', 'sendto', 'sendmsg', 'sendmmsg', 'connect', 'write',
                       'writev', 'pwrite', 'pwrite64', 'ioctl', 'setsockopt',
                       'system', 'popen', 'fopen', 'open', 'openat', 'creat',
                       'syscall', 'execve', 'execv', 'execl', 'dlopen', 'dlsym'}
    assert not (imports & forbidden_calls), sorted(imports & forbidden_calls)
    for token in (b'm4_sniff=observer_v4', b'iface_fixed=', b'usb0',
                  b'payload_hex_fixed=', b'payload_len=', b'payload_hex=',
                  b'observer_simulation_not_production_delivery',
                  b'status_writes=0', b'transmit_bytes=0'):
        assert token in blob, f'missing observer contract: {token!r}'
    assert b'm4_sniff=observer_v1' not in blob, 'stale observer schema present'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        pure = subprocess.run([qemu, '-L', str(sysroot), str(binary), '--self-test'],
                              capture_output=True, timeout=5)
        assert pure.returncode == 0 and pure.stdout == b'M4 USB observe self-test: OK\n' and not pure.stderr
        r = subprocess.run([qemu, '-L', str(sysroot), str(binary), '--observe'],
                           capture_output=True, timeout=25)
        (args.report.with_suffix('.stdout.txt')).write_bytes(r.stdout)
        (args.report.with_suffix('.stderr.txt')).write_bytes(r.stderr)
        assert r.returncode == 0, (r.returncode, r.stderr.decode(errors='replace'))
        assert not r.stderr, r.stderr.decode(errors='replace')
        text = r.stdout.decode('ascii')
        assert len(r.stdout) < 65536
        assert 'm4_sniff=observer_v4' in text
        assert 'iface_fixed=usb0' in text
        assert 'payload_hex_fixed=1536' in text
        assert 'monotonic_bound_ms=12000' in text and 'record_budget=61440' in text
        assert 'status_writes=0' in text and 'transmit_bytes=0' in text
        assert 'delivery_sim=observer_simulation_not_production_delivery' in text
        assert 'summary packets=0 ' in text
        assert 'data_packets=0' in text
        assert 'completion=iface_unavailable' in text
        assert 'iface_present=0' in text
        for private in ('latitude=', 'longitude=', 'speed_kmh=', 'R.420', 'c2m_d4_status'):
            assert private not in text
        after = status.stat()
        assert status.read_bytes() == sentinel and before.st_ino == after.st_ino \
            and before.st_mtime_ns == after.st_mtime_ns
        assert not list(guest_tmp.glob('.c2m-m4-*.tmp'))
        assert binary_digest == hashlib.sha256(binary.read_bytes()).hexdigest()
    finally:
        status.unlink(missing_ok=True)
    report = {'verdict': 'PASS', 'binary_sha256': binary_digest, 'stock_runtime_sha256': PINS,
              'camera_used': False, 'status_writer': False, 'transmit': False,
              'finite_packets': 4096, 'finite_records': 48, 'window_ms': 12000, 'runtime': 'shipping ARM M4 sniff --observe under pinned stock QEMU',
              'interface_case': 'missing usb0 in CI (no private capture)',
              'status_sentinel_unchanged': True, 'target_hardware_accepted': False,
              'sniff_schema': 'observer_v4',
              'undefined_import_no_transmit_gate': True,
              'record_budget_bytes': 61440,
              'bounded_tcp_payloads_not_reassembled_stream': True}
    args.report.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
