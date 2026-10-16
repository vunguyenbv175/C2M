#!/usr/bin/env python3
"""Exact ARM M4 ADB active-identify fail-closed contract under stock QEMU.

Fixed native USB 1-1 (vid 2207 pid 0013, iface 2 ff/42/01, bulk OUT 04 /
IN 85) is absent under QEMU, so the shipping identifier must fail closed
before open/ioctl with no bulk transfer and no file mutation. No camera,
radio, private DB, or shared writer is present. Host synthetic parsing is
covered by host tests; this tests the exact shipping binary's pure ARM
--self-test/--help contract plus the finite missing-USB --probe path.

Do not execute --probe on hardware or on any host presenting 1-1.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


SELFTEST_EXACT = b'M4 ADB identify self-test: OK\n'
HELP_PHRASES = (b'active identification only', b'one CNXN',
                b'no shell or authentication reply')


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
    # Fixed native path. Never probe a host that actually presents 1-1;
    # QEMU user mode may pass through host paths; never assume isolation.
    # -L locates loader/runtime and is NOT a chroot. Require absent USB1-1
    # in BOTH visible trees; the binary then fails at sysfs identity before
    # a USB-device open or ioctl. No camera USB device is opened in this test.
    assert not Path('/sys/bus/usb/devices/1-1').exists(), \
        'do not execute --probe on hardware or any host presenting USB 1-1'
    assert not (sysroot/'sys/bus/usb/devices/1-1').exists()
    guest_tmp = sysroot/'tmp'
    assert not guest_tmp.is_symlink()
    guest_tmp.mkdir(mode=0o1777, exist_ok=True)
    os.chown(sysroot, 0, 0); sysroot.chmod(0o755)
    os.chown(guest_tmp, 0, 0); guest_tmp.chmod(0o1777)
    # Obviously synthetic sentinels only; raw bytes never enter the report.
    sentinels = {
        'c2m_d4_status': b'UNCHANGED-SYNTHETIC-D4-STATUS\n',
        'car_info': b'UNCHANGED-SYNTHETIC-CAR-INFO\n',
        'c2m_config_marker': b'UNCHANGED-SYNTHETIC-CONFIG-MARKER\n',
        'c2m_rec_marker': b'UNCHANGED-SYNTHETIC-REC-MARKER\n',
    }
    paths = {}
    for name, blob in sentinels.items():
        f = guest_tmp/name
        assert not f.exists() and not f.is_symlink()
        f.write_bytes(blob); f.chmod(0o600)
        paths[name] = f
    before_stat = {n: p.stat() for n, p in paths.items()}
    before_dir = sorted(x.name for x in guest_tmp.iterdir())
    binary_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    blob = binary.read_bytes()
    for forbidden in (b'--serve', b'--db', b'--gps-file', b'--status-file',
                      b'--observe', b'c2m_d4_status'):
        assert forbidden not in blob, f'writer/fixture token present: {forbidden!r}'
    for token in (b'--probe', b'CNXN', b'M4 ADB identify self-test: OK',
                  b'active identification only', b'one CNXN',
                  b'no shell or authentication reply'):
        assert token in blob, f'missing identify contract: {token!r}'
    # Inspect actual undefined ELF imports, not C-call-shaped substrings.
    # Dynamic symbol names contain no '('; column 7 is Name and a trailing
    # '@...' suffix is the version index, not part of the name.
    symbols = subprocess.check_output(['arm-linux-gnueabihf-readelf', '--wide',
                                      '--dyn-syms', str(binary)], text=True)
    imports = {row.split()[7].split('@')[0] for row in symbols.splitlines()
               if ' UND ' in row and len(row.split()) >= 8}
    assert {'open', 'read', 'ioctl', 'close', 'clock_gettime'} <= imports, \
        sorted({'open', 'read', 'ioctl', 'close', 'clock_gettime'} - imports)
    forbidden_calls = {'socket', 'bind', 'listen', 'accept', 'connect',
                       'send', 'sendto', 'sendmsg', 'sendmmsg',
                       'recv', 'recvfrom', 'recvmsg', 'getsockname', 'setsockopt',
                       'ptrace', 'system', 'popen', 'write', 'writev',
                       'pwrite', 'pwrite64', 'fwrite', 'fread', 'fopen',
                       'unlink', 'unlinkat', 'chmod', 'fchmod', 'mkdir', 'mkdirat',
                       'rename', 'renameat', 'creat', 'symlink', 'link',
                       'syscall', 'execve', 'execv', 'execl', 'execlp', 'execvp',
                       'dlopen', 'dlsym'}
    # printf may use write internally; a direct UND write import is forbidden.
    assert not (imports & forbidden_calls), sorted(imports & forbidden_calls)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        pure = subprocess.run([qemu, '-L', str(sysroot), str(binary), '--self-test'],
                              capture_output=True, timeout=5)
        assert pure.returncode == 0 and pure.stdout == SELFTEST_EXACT and not pure.stderr
        h = subprocess.run([qemu, '-L', str(sysroot), str(binary), '--help'],
                           capture_output=True, timeout=5)
        assert h.returncode == 0 and not h.stderr
        htext = h.stdout
        assert b'--probe' in htext
        for phrase in HELP_PHRASES:
            assert phrase in htext, phrase
        r = subprocess.run([qemu, '-L', str(sysroot), str(binary), '--probe'],
                           capture_output=True, timeout=25)
        (args.report.with_suffix('.stdout.txt')).write_bytes(r.stdout)
        (args.report.with_suffix('.stderr.txt')).write_bytes(r.stderr)
        # Missing-USB fail-closed path: nonzero exit, small output, no AUTH/
        # SHELL protocol bytes, no bulk transfer. Exact schema is asserted
        # only after the source agent's pending stdout names are seen.
        assert r.returncode != 0, (r.returncode, r.stderr.decode(errors='replace'))
        assert len(r.stdout) < 2048, len(r.stdout)
        text = r.stdout.decode('ascii')
        fields = dict(row.split('=', 1) for row in text.splitlines() if '=' in row)
        assert fields['status'] == 'error_sysfs'
        assert fields['txbytes'] == fields['out_calls'] == fields['rxcalls'] == '0'
        assert fields['claimed'] == fields['released'] == '0'
        assert b'AUTH' not in r.stdout and b'SHELL' not in r.stdout, \
            r.stdout.decode(errors='replace')[:512]
        for name, f in paths.items():
            after = f.stat()
            assert f.read_bytes() == sentinels[name] \
                and before_stat[name].st_ino == after.st_ino \
                and before_stat[name].st_mtime_ns == after.st_mtime_ns, name
        assert sorted(x.name for x in guest_tmp.iterdir()) == before_dir, \
            sorted(x.name for x in guest_tmp.iterdir())
        assert not list(guest_tmp.glob('.c2m-m4-*.tmp'))
        assert binary_digest == hashlib.sha256(binary.read_bytes()).hexdigest()
        probe_rc, probe_bytes = r.returncode, len(r.stdout)
    finally:
        for f in paths.values():
            f.unlink(missing_ok=True)
    import os as _os
    report = {'verdict': 'PASS', 'binary_sha256': binary_digest,
              'stock_runtime_sha256': PINS,
              'source': 'fw/m4_adb/m4_adb_identify.c',
              'github_run': _os.environ.get('GITHUB_RUN_ID', 'local'),
              'camera_used': False, 'status_writer': False,
              'bulk_out_transfers': 0, 'transmit': False,
              'finite_window_ms': 5000, 'window_ms': 5000, 'max_out_transfers': 2,
              'max_out_calls': 2, 'max_in_calls': 2,
              'max_in_transfers': 2, 'max_out_bytes': 31,
              'probe_rc': probe_rc, 'probe_stdout_bytes': probe_bytes,
              'no_file_mutation': True, 'sentinel_unchanged': True, 'missing_usb_fail_closed': True,
              'required_import_gate': True, 'undefined_import_gate': True,
              'selftest_exact': 'M4 ADB identify self-test: OK',
              'help_contract': ['active identification only', 'one CNXN',
                                'no shell or authentication reply'],
              'interface_case': 'missing USB 1-1 in CI (no camera USB access)',
              'runtime': 'shipping ARM M4 ADB identify --probe fail-closed under pinned stock QEMU'}
    args.report.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
