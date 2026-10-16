#!/usr/bin/env python3
"""Synthetic negative tests of private VI input reassembly, no vendor input."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
import restore_vi_base as R


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.vault=self.root/'vault';self.parts=self.vault/'assets/vi-base-parts';self.parts.mkdir(parents=True)
        self.data=b'synthetic-only-input';self.out=self.root/'output.tar'
        self.parts.joinpath('manifest.json').write_text('{}')
        for i,o in enumerate(range(0,len(self.data),7)):
            self.parts.joinpath(f'part-{i:02d}.bin').write_bytes(self.data[o:o+7])
        self.p=patch.multiple(R,VI_BYTES=len(self.data),PART_BYTES=7,VI_SHA=hashlib.sha256(self.data).hexdigest());self.p.start();self.addCleanup(self.p.stop)

    def test_exact_synthetic_reassembly_and_no_overwrite(self):
        R.restore(self.vault,self.out);self.assertEqual(self.out.read_bytes(),self.data)
        with self.assertRaises(ValueError):R.restore(self.vault,self.out)

    def test_missing_extra_or_size_fail_before_output(self):
        for mode in ('missing','extra','size'):
            path=self.parts/'part-00.bin';old=path.read_bytes()
            if mode=='missing':path.unlink()
            elif mode=='extra':self.parts.joinpath('extra').write_bytes(b'x')
            else:path.write_bytes(old+b'x')
            with self.assertRaises(ValueError):R.restore(self.vault,self.out)
            self.assertFalse(self.out.exists())
            path.write_bytes(old);self.parts.joinpath('extra').unlink(missing_ok=True)

    def test_correct_size_wrong_bytes_cannot_self_bless(self):
        p=self.parts/'part-00.bin';p.write_bytes(b'X'*7)
        self.parts.joinpath('manifest.json').write_text(json.dumps({'sha256':hashlib.sha256(b'X'*len(self.data)).hexdigest()}))
        with self.assertRaises(ValueError):R.restore(self.vault,self.out)
        self.assertFalse(self.out.exists())

    def test_bad_whole_archive_rejected(self):
        self.vault.joinpath('V2023.09.20.1_C2M_U_FR_WIFI_VI.tar').write_bytes(b'X'*len(self.data))
        with self.assertRaises(ValueError):R.restore(self.vault,self.out)
        self.assertFalse(self.out.exists())


if __name__=='__main__':unittest.main()
