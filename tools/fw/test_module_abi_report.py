#!/usr/bin/env python3
"""Offline metadata-comparison tests; no firmware fixture or device needed."""
import copy
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

    def test_rejects_non_elf(self):
        with self.assertRaises(ELFError):
            report(b'not an ELF')


if __name__ == '__main__':
    unittest.main()
