#!/usr/bin/env python3
"""Fail-closed optional shadow packaging tests; no ARM runtime or private data."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import package_ram_debug as package
from test_package_ram_debug import header
from prepare_ram_debug_sysroot import PINS


class ShadowPackageGate(unittest.TestCase):
    def test_no_shadow_binary_without_exact_runtime_proof(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix='c2m-shadow-package-') as name:
            root=Path(name); evidence=root/'evidence';evidence.mkdir()
            binaries=[]
            for n in ('d4','nlprobe','gps','shadow'):
                p=root/n;p.write_bytes(header());binaries.append(p)
            digest=hashlib.sha256(binaries[0].read_bytes()).hexdigest()
            (evidence/'arm-d4-producer-runtime.json').write_text(json.dumps({
                'verdict':'PASS','camera_used':False,'binary_sha256':digest,
                'stock_runtime_sha256':PINS}))
            args=['package_ram_debug.py','--output',str(root/'out'),
                '--d4',str(binaries[0]),'--nlprobe',str(binaries[1]),
                '--gps-probe',str(binaries[2]),'--d4-shadow',str(binaries[3]),
                '--evidence',str(evidence)]
            for mutation in ({'status_writer':True},{'camera_used':True},
                             {'binary_sha256':'0'*64},{'stock_runtime_sha256':{}},
                             {'verdict':'FAIL'}, {'finite_samples':9},
                             {'shadow_schema':'observer_v1'}, {'shadow_schema':None},
                             {'same_poll_diagnostics_checked':False},
                             {'same_poll_diagnostics_checked':None}):
                report={'verdict':'PASS','camera_used':False,'status_writer':False,
                        'finite_samples':10,'binary_sha256':digest,'stock_runtime_sha256':PINS,
                        'shadow_schema':'observer_v2','same_poll_diagnostics_checked':True}
                report.update(mutation)
                (evidence/'arm-d4-shadow-runtime.json').write_text(json.dumps(report))
                with self.subTest(mutation=mutation), patch('sys.argv',args):
                    with self.assertRaisesRegex(SystemExit,'shadow ARM runtime proof'):
                        package.main()
                    self.assertFalse((root/'out').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
