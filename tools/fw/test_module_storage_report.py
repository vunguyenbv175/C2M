#!/usr/bin/env python3
"""Offline tests for the allocated-object storage accounting helper.

Synthetic ELF32 little-endian ARM relocatable objects only: no firmware, no
cross toolchain, no device. The tests pin the alias/overlap/common-alignment
accounting and the bounded-table contract.
"""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from elftools.common.exceptions import ELFError

import module_storage_report as msr

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_NOBITS = 8
SHF_WRITE = 0x1
SHF_ALLOC = 0x2
STB_LOCAL = 0
STB_GLOBAL = 1
STT_OBJECT = 1
STT_FUNC = 2
SHN_COMMON = 0xFFF2


def build_elf(sections, symbols, *, machine=40, elf_type=1, elf_class=1, endian="<"):
    """Minimal but valid ELF32 object builder.

    ``sections`` is ``[(name, sh_type, sh_flags, size, payload), ...]`` for the
    user sections (index 1..N). ``symbols`` is
    ``[(name, value, size, bind, stype, shndx), ...]``.
    """
    shstr = bytearray(b"\0")

    def shname(name):
        if not name:
            return 0
        key = name.encode("ascii")
        found = shstr.find(key + b"\0")
        if found >= 0:
            return found
        offset = len(shstr)
        shstr.extend(key + b"\0")
        return offset

    strtab = bytearray(b"\0")
    symtab = bytearray(16)  # leading null symbol
    for name, value, size, bind, stype, shndx in symbols:
        name_off = len(strtab)
        strtab.extend(name.encode("ascii") + b"\0")
        symtab.extend(struct.pack(endian + "IIIBBH", name_off, value, size, (bind << 4) | stype, 0, shndx))

    # Register every section name (including the internal tables) before
    # snapshotting the .shstrtab payload.
    section_names = [shname(name) for name, *_rest in sections]
    shstr_index = 1 + len(sections)
    strtab_index = shstr_index + 1
    symtab_index = strtab_index + 1
    internal_names = [shname(".shstrtab"), shname(".strtab"), shname(".symtab")]
    shstr_payload = bytes(shstr)

    specs = [(0, SHT_NULL, 0, 0, b"")]
    for (name, sh_type, sh_flags, size, payload), name_off in zip(sections, section_names):
        specs.append((name_off, sh_type, sh_flags, size, payload))
    specs.append((internal_names[0], SHT_STRTAB, 0, len(shstr_payload), shstr_payload))
    specs.append((internal_names[1], SHT_STRTAB, 0, len(strtab), bytes(strtab)))
    specs.append((internal_names[2], SHT_SYMTAB, 0, len(symtab), bytes(symtab)))

    count = len(specs)
    shoff = 52
    # Section data lives after the header and the whole section-header table.
    cursor = shoff + count * 40
    offsets = {}
    payloads = []
    for index, (_name, sh_type, _flags, _size, payload) in enumerate(specs):
        if payload and sh_type != SHT_NOBITS:
            offsets[index] = cursor
            cursor += len(payload)
            payloads.append(payload)

    shdrs = []
    for index, (name_off, sh_type, sh_flags, size, _payload) in enumerate(specs):
        link = strtab_index if index == symtab_index else 0
        info = 1 if index == symtab_index else 0
        align = 4 if index in (symtab_index, strtab_index, shstr_index) else 1
        entsize = 16 if index == symtab_index else 0
        shdrs.append(struct.pack(
            endian + "IIIIIIIIII",
            name_off, sh_type, sh_flags, 0, offsets.get(index, 0), size, link, info, align, entsize,
        ))

    ident = bytearray(b"\x7fELF")
    ident.append(elf_class)
    ident.append(1 if endian == "<" else 2)
    ident.append(1)
    ident.extend(b"\0" * 9)
    ehdr = struct.pack(
        endian + "16sHHIIIIIHHHHHH",
        bytes(ident), elf_type, machine, 1, 0, 0, shoff, 0, 52, 0, 0, 40, count, shstr_index,
    )
    return bytes(ehdr) + b"".join(shdrs) + b"".join(payloads)


def bss_and_data(symbols, bss_size=0, data=b""):
    return [
        (".bss", SHT_NOBITS, SHF_ALLOC | SHF_WRITE, bss_size, b""),
        (".data", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE, len(data), data),
    ], symbols


class StorageReportTests(unittest.TestCase):
    def test_shared_offset_alias_is_not_double_counted(self):
        sections, symbols = bss_and_data([
            ("g_alpha", 0, 32, STB_GLOBAL, STT_OBJECT, 1),
            ("g_alpha_alias", 0, 32, STB_GLOBAL, STT_OBJECT, 1),
        ], bss_size=64)
        result = msr.report(build_elf(sections, symbols), profile="baseline")
        bss = next(item for item in result["section_accounting"] if item["name"] == ".bss")
        self.assertEqual(bss["symbol_count"], 2)
        self.assertEqual(bss["object_byte_sum"], 64)
        self.assertEqual(bss["named_union_bytes"], 32)
        self.assertEqual(bss["alias_overlap_bytes"], 32)
        self.assertEqual(bss["padding_bytes"], 32)

    def test_overlapping_spans_are_unioned(self):
        sections, symbols = bss_and_data([
            ("g_first", 0, 24, STB_GLOBAL, STT_OBJECT, 1),
            ("g_second", 8, 24, STB_GLOBAL, STT_OBJECT, 1),
        ], bss_size=40)
        result = msr.report(build_elf(sections, symbols))
        bss = next(item for item in result["section_accounting"] if item["name"] == ".bss")
        self.assertEqual(bss["object_byte_sum"], 48)
        self.assertEqual(bss["named_union_bytes"], 32)
        self.assertEqual(bss["alias_overlap_bytes"], 16)
        self.assertEqual(bss["padding_bytes"], 8)

    def test_common_alignment_and_total(self):
        sections, symbols = bss_and_data([
            ("g_common4", 4, 16, STB_GLOBAL, STT_OBJECT, SHN_COMMON),
            ("g_common32", 32, 64, STB_GLOBAL, STT_OBJECT, SHN_COMMON),
            ("g_common4b", 4, 8, STB_GLOBAL, STT_OBJECT, SHN_COMMON),
            ("g_bss", 0, 16, STB_LOCAL, STT_OBJECT, 1),
        ], bss_size=16)
        result = msr.report(build_elf(sections, symbols), profile="concurrent")
        summary = result["summary"]
        self.assertEqual(summary["common_symbol_count"], 3)
        self.assertEqual(summary["common_total_bytes"], 88)
        self.assertEqual(summary["common_alignments"], [4, 32])
        self.assertEqual({item["alignment"] for item in result["common"]}, {4, 32})
        self.assertEqual(result["common"][0]["name"], "g_common32")
        self.assertEqual(result["common"][0]["section"], "COMMON")
        self.assertTrue(all(item["common"] for item in result["common"]))
        self.assertEqual(summary["object_symbol_count"], 1)
        self.assertEqual(result["profile"], "concurrent")

    def test_selects_only_allocated_writable_objects(self):
        sections = [
            (".bss", SHT_NOBITS, SHF_ALLOC | SHF_WRITE, 32, b""),
            (".data", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE, 16, bytes(16)),
            (".rodata", SHT_PROGBITS, SHF_ALLOC, 16, bytes(16)),
            (".text", SHT_PROGBITS, SHF_ALLOC, 16, bytes(16)),
        ]
        symbols = [
            ("g_bss", 0, 16, STB_GLOBAL, STT_OBJECT, 1),
            ("g_data", 0, 16, STB_GLOBAL, STT_OBJECT, 2),
            ("g_rodata", 0, 16, STB_GLOBAL, STT_OBJECT, 3),
            ("some_func", 0, 16, STB_GLOBAL, STT_FUNC, 4),
            ("g_undef", 0, 0, STB_GLOBAL, STT_OBJECT, 0),
        ]
        result = msr.report(build_elf(sections, symbols))
        self.assertEqual([item["name"] for item in result["objects"]], ["g_bss", "g_data"])
        self.assertEqual(result["summary"]["object_byte_sum"], 32)
        self.assertEqual({item["name"] for item in result["writable_sections"]}, {".bss", ".data"})
        self.assertEqual(result["summary"]["bss_section_bytes"], 32)

    def test_no_bss_padding_when_named_coverage_matches(self):
        sections, symbols = bss_and_data([
            ("g_a", 0, 16, STB_GLOBAL, STT_OBJECT, 1),
            ("g_b", 16, 16, STB_GLOBAL, STT_OBJECT, 1),
        ], bss_size=32)
        result = msr.report(build_elf(sections, symbols))
        bss = next(item for item in result["section_accounting"] if item["name"] == ".bss")
        self.assertEqual(bss["named_union_bytes"], 32)
        self.assertEqual(bss["padding_bytes"], 0)
        self.assertEqual(bss["alias_overlap_bytes"], 0)

    def test_report_metadata_and_no_raw_bytes(self):
        sections, symbols = bss_and_data([("g_x", 0, 8, STB_GLOBAL, STT_OBJECT, 1)], bss_size=8)
        blob = build_elf(sections, symbols)
        result = msr.report(blob)
        self.assertEqual(result["status"], "parsed")
        self.assertEqual(result["bytes"], len(blob))
        self.assertEqual(result["elf"]["machine"], "EM_ARM")
        self.assertEqual(result["elf"]["type"], "ET_REL")
        self.assertEqual(result["load_safety"], "NOT_ESTABLISHED")
        self.assertNotIn(blob, json.dumps(result).encode("utf-8"))

    def test_object_table_is_bounded(self):
        sections, symbols = bss_and_data([
            (f"g_{index:05d}", index * 4, 4, STB_GLOBAL, STT_OBJECT, 1) for index in range(50)
        ], bss_size=200)
        original = msr.OBJECT_TABLE_LIMIT
        msr.OBJECT_TABLE_LIMIT = 10
        try:
            result = msr.report(build_elf(sections, symbols))
        finally:
            msr.OBJECT_TABLE_LIMIT = original
        self.assertEqual(len(result["objects"]), 10)
        self.assertEqual(result["bounds"]["object_symbols_total"], 50)
        self.assertEqual(result["bounds"]["object_symbols_listed"], 10)
        self.assertTrue(result["bounds"]["truncated"])
        # The summary still covers every selected symbol.
        self.assertEqual(result["summary"]["object_symbol_count"], 50)
        self.assertEqual(result["summary"]["object_byte_sum"], 200)

    def test_json_output_is_bounded(self):
        sections, symbols = bss_and_data([
            (f"g_{index:05d}", index * 4, 4, STB_GLOBAL, STT_OBJECT, 1) for index in range(60)
        ], bss_size=240)
        original = msr.JSON_BYTE_LIMIT
        # Above the report's fixed overhead but far below 60 entries.
        msr.JSON_BYTE_LIMIT = 4000
        try:
            result = msr.report(build_elf(sections, symbols))
            text = json.dumps(result, indent=2, sort_keys=True)
        finally:
            msr.JSON_BYTE_LIMIT = original
        self.assertLessEqual(len(text.encode("utf-8")), 4000)
        self.assertTrue(result["bounds"]["truncated"])
        self.assertLess(len(result["objects"]), 60)

    def test_rejects_non_elf(self):
        with self.assertRaises(ELFError):
            msr.report(b"not an elf")

    def test_rejects_wrong_class_machine_and_type(self):
        sections, symbols = bss_and_data([("g_x", 0, 4, STB_GLOBAL, STT_OBJECT, 1)], bss_size=4)
        with self.assertRaises(ValueError):
            msr.report(build_elf(sections, symbols, machine=62))
        with self.assertRaises(ValueError):
            msr.report(build_elf(sections, symbols, elf_class=2))
        with self.assertRaises(ValueError):
            msr.report(build_elf(sections, symbols, elf_type=2))


class BuildCmdTests(unittest.TestCase):
    def test_parses_cc_and_flags_without_shell_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = Path(tmp) / "8821cs.o.cmd"
            cmd.write_text(
                "cmd_/tmp/8821cs.o := arm-linux-gnueabi-gcc -Werror -fcommon -o x.o x.c\n"
                "deps_/tmp/8821cs.o := x.c y.h\n",
                encoding="utf-8",
            )
            entry = msr.parse_build_cmd(cmd)
        self.assertTrue(entry["present"])
        self.assertTrue(entry["command_found"])
        self.assertFalse(entry["executed"])
        self.assertFalse(entry["shell_evaluated"])
        self.assertEqual(entry["cc"], "arm-linux-gnueabi-gcc")
        self.assertIn("-fcommon", entry["flags"])
        self.assertEqual(entry["token_count"], 6)

    def test_missing_cmd_is_reported_not_raised(self):
        entry = msr.parse_build_cmd(Path("does-not-exist.cmd"))
        self.assertFalse(entry["present"])
        self.assertFalse(entry["executed"])

    def test_report_includes_compiler_context(self):
        sections, symbols = bss_and_data([("g_x", 0, 4, STB_GLOBAL, STT_OBJECT, 1)], bss_size=4)
        with tempfile.TemporaryDirectory() as tmp:
            cmd = Path(tmp) / "m.cmd"
            cmd.write_text("cmd_m.o := cc -O2 -fcommon\n", encoding="utf-8")
            result = msr.report(build_elf(sections, symbols), cmd_path=cmd)
        self.assertEqual(result["compiler"]["cc"], "cc")
        self.assertIn("-fcommon", result["compiler"]["flags"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
