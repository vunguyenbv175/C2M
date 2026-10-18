#!/usr/bin/env python3
"""Compare ARM kernel-module ABI metadata offline; NEVER a load-safety verdict.

Requires pyelftools. Does not load modules, contact a device or modify inputs.
Only modinfo allowlisted fields, undefined symbol names and section sizes output.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile


def report(blob: bytes) -> dict:
    elf = ELFFile(io.BytesIO(blob))
    if elf.elfclass != 32 or not elf.little_endian or elf['e_machine'] != 'EM_ARM' or elf['e_type'] != 'ET_REL':
        raise ValueError('requires ELF32 little-endian ARM relocatable module')
    info: dict[str, list[str]] = {}
    section = elf.get_section_by_name('.modinfo')
    if section is None:
        raise ValueError('module lacks .modinfo')
    for item in section.data().split(b'\0'):
        if b'=' not in item:
            continue
        key, value = item.split(b'=', 1)
        if key in (b'vermagic', b'version', b'depends', b'license', b'srcversion', b'name'):
            info.setdefault(key.decode('ascii'), []).append(value.decode('ascii', errors='replace'))
    syms = elf.get_section_by_name('.symtab')
    if syms is None:
        raise ValueError('module lacks symbol table')
    undefined = sorted({sym.name for sym in syms.iter_symbols() if sym.name and sym['st_shndx'] == 'SHN_UNDEF'})
    sections = {name: int(sec['sh_size']) for name in ('.text', '.rodata', '.data', '.bss', '__versions', '.ARM.attributes') if (sec := elf.get_section_by_name(name)) is not None}
    return {
        'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob),
        'elf_flags': int(elf['e_flags']), 'modinfo': info,
        'section_bytes': sections, 'has_symbol_versions': '__versions' in sections,
        'undefined_symbols': undefined, 'undefined_symbol_count': len(undefined),
        'load_safety': 'NOT_ESTABLISHED',
    }


def compare(baseline: dict, candidate: dict) -> dict:
    old, new = set(baseline['undefined_symbols']), set(candidate['undefined_symbols'])
    return {
        'vermagic_equal': bool(baseline['modinfo'].get('vermagic')) and bool(candidate['modinfo'].get('vermagic')) and baseline['modinfo']['vermagic'] == candidate['modinfo']['vermagic'],
        'elf_flags_equal': baseline['elf_flags'] == candidate['elf_flags'],
        'symbol_version_presence_equal': baseline['has_symbol_versions'] == candidate['has_symbol_versions'],
        'undefined_added': sorted(new - old), 'undefined_removed': sorted(old - new),
        'dependencies_equal': 'depends' in baseline['modinfo'] and 'depends' in candidate['modinfo'] and baseline['modinfo']['depends'] == candidate['modinfo']['depends'],
        'section_size_delta': {k: candidate['section_bytes'].get(k, 0) - baseline['section_bytes'].get(k, 0) for k in sorted(set(baseline['section_bytes']) | set(candidate['section_bytes']))},
        'load_safety': 'NOT_ESTABLISHED_EVEN_IF_METADATA_MATCHES',
        'remaining_checks': ['matching kernel generated headers/config and vendor structure layout', 'kernel export compatibility, including GPL-only symbols', 'target instruction attributes and toolchain', 'AP-independent recovery and explicitly reviewed hardware test'],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path)
    p.add_argument('--candidate', type=Path)
    args = p.parse_args()
    baseline = report(args.baseline.read_bytes())
    out = {'baseline': baseline}
    if args.candidate:
        candidate = report(args.candidate.read_bytes())
        out.update(candidate=candidate, comparison=compare(baseline, candidate))
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
