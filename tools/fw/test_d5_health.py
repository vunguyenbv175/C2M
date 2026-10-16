#!/usr/bin/env python3
"""Synthetic D5 health install/parse tests; no real camera/device access."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import unittest

from test_d4_mutation import D4MutationTest, ROOT, digest


class D5HealthMutation(D4MutationTest):
    # Reuse stock synthetic fixture utilities without rerunning inherited D4 tests.
    def test_health_install_exact_no_boot_launch(self):
        f = self.fixture()
        r = self.run_mutation(f, extra=['--d5-health'])
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        m = json.loads(f['out'].read_bytes())
        source = ROOT/'fw/d5/health.sh'
        self.assertTrue(m['d5_health'])
        self.assertEqual((f['tree']/'c2m/health.sh').read_bytes(), source.read_bytes())
        row = next(x for x in m['added'] if x['path']=='/c2m/health.sh')
        self.assertEqual(row['sha256'], digest(source.read_bytes()))
        self.assertEqual((row['mode'], row['uid'], row['gid']), (0o755,1001,1001))
        self.assertNotIn('health.sh', (f['tree']/'wifi/rcInsDriver.sh').read_text())
        self.assert_blocked(f, extra=['--d5-health'])

    def test_health_requires_d4(self):
        self.assert_blocked(self.fixture(), omit={'--d4-services-dir','--d4-database','--d4-database-sha256'}, extra=['--d5-health'])

    def test_collision_blocked_before_mutation(self):
        f=self.fixture();(f['tree']/'c2m').mkdir();(f['tree']/'c2m/health.sh').write_bytes(b'owner-work')
        self.assert_blocked(f, extra=['--d5-health'])


class HealthPure(unittest.TestCase):
    def test_source_is_passive_and_bounded(self):
        text=(ROOT/'fw/d5/health.sh').read_text()
        for forbidden in ('/dev/', '8080/', 'wget ', 'curl ', 'nc ', 'kill ', 'reboot', 'mount ', 'sysctl ', '/tmp/car_info', 'authorized_keys', 'cat /customer'):
            self.assertNotIn(forbidden,text)
        self.assertNotIn('\r',(ROOT/'fw/d5/health.sh').read_bytes().decode())
        self.assertNotIn(' > ',text)
        self.assertIn('snapshot_not_continuity=1',text)
        self.assertIn('recording_growth_and_gps_fix=not_tested',text)

    def test_kernel_table_synthetic(self):
        # Parse EXACT embedded awk without executing the health script or /proc reads.
        text=(ROOT/'fw/d5/health.sh').read_text()
        program=text.split("awk 'BEGIN",1)[1].split("' /proc/net/tcp",1)[0]
        program='BEGIN'+program
        awk=shutil.which('awk')
        self.assertIsNotNone(awk)
        fake='''  1: 7B20A8C0:1F90 8120A8C0:C001 01 0 0 0
  2: 7B20A8C0:5DCC 8120A8C0:C002 01 0 0 0
  3: 7B20A8C0:659C 8120A8C0:C003 01 0 0 0
  4: 7B20A8C0:1F90 8120A8C0:C004 0A 0 0 0
  5: 0100007F:659C 8120A8C0:C005 01 0 0 0
'''
        r=subprocess.run([awk,program],input=fake,text=True,capture_output=True,check=True,timeout=5)
        self.assertEqual(r.stdout,'m4_8080_established=1\nm4_24012_established=1\nm4_26012_established=1\n')


if __name__=='__main__':
    # Do not collect imported superclass or duplicate its full suite here.
    suite=unittest.TestSuite()
    for cls,names in ((D5HealthMutation,['test_health_install_exact_no_boot_launch','test_health_requires_d4','test_collision_blocked_before_mutation']),
                      (HealthPure,['test_source_is_passive_and_bounded','test_kernel_table_synthetic'])):
        suite.addTests(cls(name) for name in names)
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
