#!/usr/bin/env python3
"""D3 host-only mutation guard. No firmware, camera or SD access."""
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

class D3MutationTest(unittest.TestCase):
    def test_manifest_and_reachable_background_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root / 'tree'; (tree / 'wifi').mkdir(parents=True)
            hook = b'#!/bin/sh\nexit 0\n'
            (tree / 'wifi/rcInsDriver.sh').write_bytes(hook)
            stock = root / 'stock.json'
            stock.write_text(json.dumps({'entries': [{'path': '/wifi/rcInsDriver.sh',
                'type': 'reg', 'size': len(hook), 'sha256': hashlib.sha256(hook).hexdigest()}]}))
            idle = root / 'idle'; idle.write_bytes(b'test-placeholder')
            services = root / 'services'; services.mkdir()
            for name in ['boot.sh', 'connectivity_probe.sh']:
                (services / name).write_bytes((ROOT / 'fw/d3' / name).read_bytes())
            elf = bytearray(52); elf[:6] = b'\x7fELF\x01\x01'; elf[18] = 40
            for name in ['c2m-web', 'c2m-wifi', 'wpa_supplicant']: (services / name).write_bytes(elf)
            mutation = root / 'mutation.json'
            cmd = [sys.executable, str(ROOT / 'tools/fw/mutate_customer.py'),
                   '--tree', str(tree), '--manifest', str(stock), '--idle-bin', str(idle),
                   '--tsr-experiment', '--d3-services-dir', str(services),
                   '--out-manifest', str(mutation)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            doc = json.loads(mutation.read_text())
            self.assertTrue(doc['d3_services'])
            added = {r['path'] for r in doc['added']}
            self.assertEqual(added, {'/c2m', '/c2m/c2m-idle', '/c2m/tsr_profile_boot.sh',
                '/c2m/boot.sh', '/c2m/connectivity_probe.sh', '/c2m/c2m-web', '/c2m/c2m-wifi',
                '/c2m/wpa_supplicant'})
            # The next-flash Bluetooth probe must be the exact reviewed source,
            # not an older bundled report/probe silently left in the image.
            self.assertEqual((tree / 'c2m/connectivity_probe.sh').read_bytes(),
                             (ROOT / 'fw/d3/connectivity_probe.sh').read_bytes())
            boot = (tree / 'c2m/boot.sh').read_text()
            self.assertIn('/bin/sh /customer/c2m/connectivity_probe.sh', boot)
            self.assertIn('$_run/bluetooth.txt', boot)
            self.assertIn('$_log/bluetooth-D3.txt', boot)
            text = (tree / 'wifi/rcInsDriver.sh').read_text()
            self.assertEqual(text.count('/bin/sh /customer/c2m/boot.sh'), 1)
            self.assertLess(text.index('tsr_profile_boot.sh'), text.index('( _c2m_n=0'))
            self.assertLess(text.index('/customer/c2m/c2m-idle >'), text.index('/customer/c2m/boot.sh'))
            # Hardcoded stock exit 0 is preserved; only bare exit/$? uses saved rc.
            self.assertTrue(text.endswith('exit 0\n'))
            self.assertIn('_c2m_rc=$?', text)
            shell = shutil.which('sh')
            if shell:
                path = (tree / 'wifi/rcInsDriver.sh').as_posix()
                if os.name == 'nt': path = '/' + path[0].lower() + path[2:]
                syntax = subprocess.run([shell, '-n', path], capture_output=True, text=True)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
            # Existing modified hook must not be mutated again.
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)

    def test_deploy_sources_are_lf_and_no_stock_wifi_switch(self):
        for name in ['boot.sh', 'connectivity_probe.sh']:
            data = (ROOT / 'fw/d3' / name).read_bytes()
            self.assertNotIn(b'\r', data)
            self.assertTrue(data.startswith(b'#!/bin/sh\n'))
        boot = (ROOT / 'fw/d3/boot.sh').read_text()
        for unsafe in ['killall ', 'nvconf ', 'sta.sh ', 'ap.sh ', 'insmod ', '/dev/tty']:
            self.assertNotIn(unsafe, boot)
        self.assertIn('/customer/minieye/config/.c2m-d3', boot)
        self.assertNotIn('--bind 0.0.0.0', boot)

if __name__ == '__main__':
    unittest.main()
