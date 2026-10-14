#!/usr/bin/env python3
"""Execute verbatim D shell in isolated host paths; no cam/SD/config access."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'fw/tsr/tsr_profile_boot.sh'
SHELL = os.environ.get('C2M_TSR_TEST_SHELL') or shutil.which('sh')


def sh_path(path):
    value = Path(path).as_posix()
    return '/' + value[0].lower() + value[2:] if len(value) > 2 and value[1] == ':' else value


@unittest.skipUnless(SHELL, 'requires sh')
class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='d-tsr-')
        self.root = Path(self.temp.name)
        self.cfg = self.root / 'config'
        self.cfg.mkdir()
        text = SCRIPT.read_bytes().decode('ascii')
        text = text.replace('/customer/minieye/config', sh_path(self.cfg))
        text = text.replace('/tmp/c2m_tsr_status.txt', sh_path(self.root / 'status.txt'))
        text = text.replace('/tmp/c2m_tsr_work', sh_path(self.root / 'work'))
        self.script = self.root / 'script.sh'
        self.script.write_bytes(text.encode('ascii'))
        self.original = (b'# --enable_tsr=false stays a comment\n'
                         b'--enable_vehicle=true\n--enable_tsr=false\n'
                         b'--unchanged=private-test\n')

    def tearDown(self):
        self.temp.cleanup()

    def seed(self, decoded=None):
        self.cfg.joinpath('adas.flag').write_bytes(base64.encodebytes(decoded or self.original))
        self.cfg.joinpath('adas_de.flag').write_bytes(b'unchanged decoded source until stock run.sh\n')

    def run_script(self, expected):
        run = subprocess.run([SHELL, sh_path(self.script)], capture_output=True, text=True, timeout=int(os.environ.get('C2M_TSR_TEST_TIMEOUT', '20')))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        status = (self.root / 'status.txt').read_text()
        self.assertIn('status=' + expected + '\n', status)
        return status

    def test_applies_with_original_backup_and_idempotency(self):
        self.seed()
        original = (self.cfg / 'adas.flag').read_bytes()
        decoded_before = (self.cfg / 'adas_de.flag').read_bytes()
        self.run_script('APPLIED_WAIT_STOCK_REDECODE')
        decoded = base64.b64decode((self.cfg / 'adas.flag').read_bytes())
        self.assertIn(b'--enable_tsr=true\n', decoded)
        self.assertIn(b'--tsrw_interval=5\n', decoded)
        self.assertIn(b'--tsrw_sli_over_min_ratio=10\n', decoded)
        self.assertIn(b'--tsrw_sli_over_min_thresh=5\n', decoded)
        self.assertIn(b'--tsrw_sli_host_speed_min_thresh=20\n', decoded)
        self.assertIn(b'# --enable_tsr=false stays a comment\n', decoded)
        self.assertIn(b'--unchanged=private-test\n', decoded)
        self.assertEqual((self.cfg / 'adas_de.flag').read_bytes(), decoded_before)
        self.assertEqual((self.cfg / '.c2m-tsr-pre-d/adas.flag').read_bytes(), original)
        snapshot = (self.cfg / 'adas.flag').read_bytes()
        self.run_script('ALREADY_APPLIED')
        self.assertEqual((self.cfg / 'adas.flag').read_bytes(), snapshot)
        self.assertEqual((self.cfg / '.c2m-tsr-pre-d/adas.flag').read_bytes(), original)

    def test_missing_final_lf_no_write_or_backup(self):
        for payload in (b'--enable_tsr=false\n--unrelated=stock',
                        b'--enable_tsr=false\n# unrelated comment',
                        b'--enable_tsr=false'):
            with self.subTest(payload=payload):
                self.seed(payload)
                encoded = (self.cfg / 'adas.flag').read_bytes()
                decoded = (self.cfg / 'adas_de.flag').read_bytes()
                self.run_script('MISSING_FINAL_LF')
                self.assertEqual((self.cfg / 'adas.flag').read_bytes(), encoded)
                self.assertEqual((self.cfg / 'adas_de.flag').read_bytes(), decoded)
                self.assertFalse((self.cfg / '.c2m-tsr-pre-d').exists())
                self.assertFalse((self.cfg / '.c2m-tsr-adas.flag.new').exists())
                self.assertFalse((self.root / 'work').exists())

    def test_invalid_base64_no_write(self):
        self.cfg.joinpath('adas.flag').write_bytes(b'not-valid-%base64')
        self.run_script('DECODE_FAILED')
        self.assertEqual((self.cfg / 'adas.flag').read_bytes(), b'not-valid-%base64')
        self.assertFalse((self.cfg / '.c2m-tsr-pre-d').exists())

    def test_duplicate_inline_comment_and_crlf_block(self):
        payloads = [self.original + b'--enable_tsr=true\n',
                    self.original.replace(b'--enable_tsr=false\n', b'--enable_tsr=false # active\n')]
        # Git/MSYS base64 text I/O normalizes CRLF, unlike Linux/target. The
        # CRLF negative case is mandatory on the Linux CI/stock-BusyBox test.
        if os.name != 'nt':
            payloads.append(self.original.replace(b'\n', b'\r\n'))
        for payload in payloads:
            with self.subTest(payload=payload):
                self.seed(payload)
                original = (self.cfg / 'adas.flag').read_bytes()
                self.run_script('CONFIG_SHAPE_BLOCK')
                self.assertEqual((self.cfg / 'adas.flag').read_bytes(), original)

    def test_disable_and_missing_source(self):
        self.run_script('NO_ENCODED_FLAG')
        self.seed()
        snapshot = (self.cfg / 'adas.flag').read_bytes()
        self.cfg.joinpath('.c2m-tsr-disabled').write_bytes(b'owner-disabled\n')
        self.run_script('DISABLED_BY_OWNER_MARKER')
        self.assertEqual((self.cfg / 'adas.flag').read_bytes(), snapshot)

    def test_incomplete_backup_and_stage_refuse(self):
        self.seed()
        snapshot = (self.cfg / 'adas.flag').read_bytes()
        backup = self.cfg / '.c2m-tsr-pre-d'
        backup.mkdir()
        self.run_script('BACKUP_INCOMPLETE')
        self.assertEqual((self.cfg / 'adas.flag').read_bytes(), snapshot)
        backup.rmdir()
        stage = self.cfg / '.c2m-tsr-adas.flag.new'
        stage.write_bytes(b'unknown stage')
        self.run_script('STAGE_PATH_EXISTS')
        self.assertEqual(stage.read_bytes(), b'unknown stage')
        self.assertEqual((self.cfg / 'adas.flag').read_bytes(), snapshot)

    def test_hook_and_manifest(self):
        tree = self.root / 'tree'
        (tree / 'wifi').mkdir(parents=True)
        hook = b'#!/bin/sh\nexit 0\n'
        (tree / 'wifi/rcInsDriver.sh').write_bytes(hook)
        manifest = {'entries': [{'path': '/wifi/rcInsDriver.sh', 'type': 'reg',
                                'sha256': hashlib.sha256(hook).hexdigest(), 'size': len(hook)}]}
        stock = self.root / 'stock.json'; stock.write_text(json.dumps(manifest))
        idle = self.root / 'idle'; idle.write_bytes(b'test-arm-placeholder')
        mutation = self.root / 'mutation.json'
        run = subprocess.run([sys.executable, str(ROOT / 'tools/fw/mutate_customer.py'),
                              '--tree', str(tree), '--manifest', str(stock), '--idle-bin', str(idle),
                              '--tsr-experiment', '--out-manifest', str(mutation)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        record = json.loads(mutation.read_text())
        self.assertTrue(record['tsr_experiment']); self.assertFalse(record['tsr_patch'])
        self.assertEqual((tree / 'c2m/tsr_profile_boot.sh').read_bytes(), SCRIPT.read_bytes())
        self.assertIn('/c2m/tsr_profile_boot.sh', [r['path'] for r in record['added']])
        modified = (tree / 'wifi/rcInsDriver.sh').read_text()
        self.assertLess(modified.index('tsr_profile_boot.sh'), modified.index('( _c2m_n=0'))
        self.assertIn('tsr-profile-D.txt', modified)
        syntax = subprocess.run([SHELL, '-n', sh_path(tree / 'wifi/rcInsDriver.sh')], capture_output=True)
        self.assertEqual(syntax.returncode, 0)


if __name__ == '__main__':
    unittest.main()
