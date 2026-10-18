#!/usr/bin/env python3
"""Offline metadata-comparison tests; no firmware fixture or device needed."""
import copy
import struct
import unittest
from elftools.common.exceptions import ELFError
from module_abi_report import compare, report


class ModuleABIReportTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            'modinfo': {'vermagic': ['4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8'], 'depends': ['cfg80211,mmc_core']},
            'elf_flags': 0x5000000, 'has_symbol_versions': False,
            'undefined_symbols': ['cfg80211_connect_result', 'kmalloc'],
            'section_bytes': {'.text': 100, '.data': 20},
        }

    def test_equal_metadata_never_establishes_load_safety(self):
        r = compare(self.base, copy.deepcopy(self.base))
        self.assertTrue(r['vermagic_equal'])
        self.assertEqual(r['undefined_added'], [])
        self.assertEqual(r['load_safety'], 'NOT_ESTABLISHED_EVEN_IF_METADATA_MATCHES')
        self.assertGreaterEqual(len(r['remaining_checks']), 4)

    def test_detects_deltas(self):
        new = copy.deepcopy(self.base)
        new['modinfo']['vermagic'] = ['4.9.228']
        new['undefined_symbols'] = ['kmalloc', 'new_export']
        new['section_bytes'] = {'.text': 150, '.bss': 10}
        new['has_symbol_versions'] = True
        r = compare(self.base, new)
        self.assertFalse(r['vermagic_equal'])
        self.assertFalse(r['symbol_version_presence_equal'])
        self.assertEqual(r['undefined_added'], ['new_export'])
        self.assertEqual(r['undefined_removed'], ['cfg80211_connect_result'])
        self.assertEqual(r['section_size_delta'], {'.text': 50, '.data': -20, '.bss': 10})

    def test_missing_fields_are_not_equal(self):
        a, b = copy.deepcopy(self.base), copy.deepcopy(self.base)
        a['modinfo'] = {}
        b['modinfo'] = {}
        r = compare(a, b)
        self.assertFalse(r['vermagic_equal'])
        self.assertFalse(r['dependencies_equal'])
        self.assertEqual(r['load_safety'], 'NOT_ESTABLISHED_EVEN_IF_METADATA_MATCHES')

    def test_valid_synthetic_module_report(self):
        names = b'\0.shstrtab\0.modinfo\0.strtab\0.symtab\0__versions\0'
        blobs = [b'', names, b'vermagic=4.9.227\0depends=\0license=GPL\0', b'\0external_symbol\0', bytes(16) + struct.pack('<IIIBBH', 1, 0, 0, 0x10, 0, 0), b'CRCSTUB!']
        offsets = []
        body = bytearray(52)
        for blob in blobs:
            while len(body) % 4:
                body.append(0)
            offsets.append(len(body))
            body.extend(blob)
        while len(body) % 4:
            body.append(0)
        shoff = len(body)
        specs = [('', 0, 0, 0), ('.shstrtab', 3, 0, 0), ('.modinfo', 1, 0, 0), ('.strtab', 3, 0, 0), ('.symtab', 2, 3, 16), ('__versions', 1, 0, 0)]
        for i, (name, kind, link, entsize) in enumerate(specs):
            ni = names.index(name.encode() + b'\0') if name else 0
            body.extend(struct.pack('<IIIIIIIIII', ni, kind, 0, 0, offsets[i], len(blobs[i]), link, 1 if i == 4 else 0, 4, entsize))
        ident = b'\x7fELF' + bytes([1, 1, 1]) + bytes(9)
        body[:52] = struct.pack('<16sHHIIIIIHHHHHH', ident, 1, 40, 1, 0, 0, shoff, 0x5000000, 52, 0, 0, 40, len(specs), 1)
        r = report(bytes(body))
        self.assertTrue(r['has_symbol_versions'])
        self.assertEqual(r['undefined_symbols'], ['external_symbol'])
        self.assertEqual(r['load_safety'], 'NOT_ESTABLISHED')
        self.assertEqual(r['modinfo']['depends'], [''])
        self.assertEqual(r['section_bytes']['__versions'], 8)

    def test_rejects_non_elf(self):
        with self.assertRaises(ELFError):
            report(b'not an ELF')


if __name__ == '__main__':
    unittest.main()
