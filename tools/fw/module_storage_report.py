#!/usr/bin/env python3
"""Allocated-object storage accounting for a public-source ARM kernel module.

Offline, metadata-only helper for the RTL8821CS public-source lab. It reads a
single ELF32 little-endian ARM relocatable object (``ARM32 ET_REL``, e.g. a
``.ko`` built from public source by the lab) and reports which ``STT_OBJECT``
symbols land in allocated, writable sections (``.bss``/``.data`` and their
split variants) plus ``COMMON`` (tentative-definition) symbols. This lets the
module's effective writable/``.bss`` footprint be compared against the stock
module's ``.bss`` without shipping any raw module bytes.

Design constraints, all enforced here:

* the only required input is one public-source module blob; a build ``.cmd``
  file (also public source) may optionally be read **as text** to record the
  compiler and flags. It is never executed and never shell-evaluated,
* only names, sizes, bindings, section names and section offsets are emitted;
  raw section/symbol data bytes are never emitted,
* object byte totals are reported three separate ways so aliases/overlaps are
  never double counted: the naive sum of ``st_size``, the named interval union
  per section, and the section-size padding. ``COMMON`` sizes are reported as a
  name-size total only: they have no linker-assigned offset yet, so the total
  may be *compared with* a stock ``.bss`` effective footprint but must not be
  equated with a finalized linker layout,
* the symbol tables are bounded (<= ``OBJECT_TABLE_LIMIT`` entries and
  <= ``JSON_BYTE_LIMIT``-byte JSON) so a pathological object cannot produce an
  unbounded evidence file.

It never loads a module, never touches a device and never claims ABI or load
safety.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile

SHF_WRITE = 0x1
SHF_ALLOC = 0x2
_SHT_NOBITS = "SHT_NOBITS"
_OBJECT_TYPE = "STT_OBJECT"

# Hard bounds so one pathological object can never produce an unbounded table.
OBJECT_TABLE_LIMIT = 8192
JSON_BYTE_LIMIT = 2 * 1024 * 1024
_CMD_FLAG_LIMIT = 512


def interval_union(intervals) -> int:
    """Total length covered by ``[(offset, size), ...]`` with aliases merged.

    Overlapping or identical spans are counted once; touching spans merge
    without leaving a gap. Zero/negative-size spans contribute nothing.
    """
    spans = sorted((offset, offset + size) for offset, size in intervals if size > 0)
    if not spans:
        return 0
    total = 0
    cur_lo, cur_hi = spans[0]
    for lo, hi in spans[1:]:
        if lo > cur_hi:
            total += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
        elif hi > cur_hi:
            cur_hi = hi
    total += cur_hi - cur_lo
    return total


def parse_build_cmd(cmd_path) -> dict:
    """Read a public kbuild ``.cmd`` file as text and extract compiler + flags.

    The file content is tokenised with :mod:`shlex` only; it is NEVER executed
    or handed to a shell. Returns a small bounded provenance record.
    """
    path = Path(cmd_path)
    entry: dict = {"path": str(path), "present": path.is_file(), "executed": False, "shell_evaluated": False}
    if not entry["present"]:
        return entry
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        entry["error"] = str(exc)
        return entry
    command = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("cmd_") and ":=" in stripped:
            command = stripped.split(":=", 1)[1].strip()
            break
    entry["command_found"] = command is not None
    if command is None:
        return entry
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        entry["parse_error"] = str(exc)
        entry["token_count"] = 0
        return entry
    entry["token_count"] = len(tokens)
    entry["cc"] = tokens[0] if tokens else None
    entry["flags"] = tokens[1:1 + _CMD_FLAG_LIMIT]
    entry["flags_truncated"] = len(tokens) - 1 > _CMD_FLAG_LIMIT
    return entry


def _writable_sections(elf) -> list[dict]:
    groups = []
    for index, section in enumerate(elf.iter_sections()):
        if not section.name:
            continue
        flags = int(section["sh_flags"])
        if (flags & SHF_ALLOC) and (flags & SHF_WRITE):
            groups.append({
                "index": index,
                "name": section.name,
                "type": section["sh_type"],
                "size": int(section["sh_size"]),
                "flags": flags,
            })
    return groups


def _json_text(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True)


def report(blob: bytes, *, profile: str | None = None, cmd_path=None) -> dict:
    """Build the bounded storage-accounting report for one ARM32 ``ET_REL`` blob."""
    elf = ELFFile(io.BytesIO(blob))
    if elf.elfclass != 32 or not elf.little_endian or elf["e_machine"] != "EM_ARM" or elf["e_type"] != "ET_REL":
        raise ValueError("requires ELF32 little-endian ARM relocatable module (ARM32 ET_REL)")

    groups = _writable_sections(elf)
    group_by_index = {group["index"]: group for group in groups}

    symtab = elf.get_section_by_name(".symtab")
    if symtab is None:
        raise ValueError("module lacks symbol table (.symtab)")

    objects: list[dict] = []
    common: list[dict] = []
    for symbol in symtab.iter_symbols():
        if not symbol.name:
            continue
        info = symbol["st_info"]
        if info["type"] != _OBJECT_TYPE:
            continue
        bind = info["bind"]
        value = int(symbol["st_value"])
        size = int(symbol["st_size"])
        shndx = symbol["st_shndx"]
        if shndx == "SHN_COMMON":
            common.append({
                "name": symbol.name,
                "section": "COMMON",
                "section_type": "COMMON",
                "size": size,
                "bind": bind,
                "type": "OBJECT",
                "value": value,
                "alignment": value,
                "common": True,
            })
            continue
        if isinstance(shndx, int) and shndx in group_by_index:
            group = group_by_index[shndx]
            objects.append({
                "name": symbol.name,
                "section": group["name"],
                "section_type": group["type"],
                "size": size,
                "bind": bind,
                "type": "OBJECT",
                "value": value,
                "common": False,
            })

    objects.sort(key=lambda item: (-item["size"], item["name"]))
    common.sort(key=lambda item: (-item["size"], item["name"]))

    section_accounting = []
    agg = {
        "nobits_object_byte_sum": 0,
        "nobits_named_union_bytes": 0,
        "nobits_padding_bytes": 0,
        "nobits_alias_overlap_bytes": 0,
        "progbits_object_byte_sum": 0,
        "progbits_named_union_bytes": 0,
    }
    for group in groups:
        intervals = [(item["value"], item["size"]) for item in objects if item["section"] == group["name"]]
        byte_sum = sum(size for _value, size in intervals)
        union = interval_union(intervals)
        padding = max(0, group["size"] - union)
        out_of_bounds = sum(1 for offset, size in intervals if size > 0 and offset + size > group["size"])
        section_accounting.append({
            "name": group["name"],
            "type": group["type"],
            "size": group["size"],
            "symbol_count": len(intervals),
            "object_byte_sum": byte_sum,
            "named_union_bytes": union,
            "padding_bytes": padding,
            "alias_overlap_bytes": byte_sum - union,
            "out_of_bounds_symbols": out_of_bounds,
        })
        if group["type"] == _SHT_NOBITS:
            agg["nobits_object_byte_sum"] += byte_sum
            agg["nobits_named_union_bytes"] += union
            agg["nobits_padding_bytes"] += padding
            agg["nobits_alias_overlap_bytes"] += byte_sum - union
        else:
            agg["progbits_object_byte_sum"] += byte_sum
            agg["progbits_named_union_bytes"] += union

    common_total = sum(item["size"] for item in common)
    bss = next((group["size"] for group in groups if group["name"] == ".bss"), 0)
    summary = {
        "object_symbol_count": len(objects),
        "object_byte_sum": sum(item["size"] for item in objects),
        "common_symbol_count": len(common),
        "common_total_bytes": common_total,
        "common_alignments": sorted({item["alignment"] for item in common}),
        "writable_section_count": len(groups),
        "bss_section_bytes": bss,
        **agg,
        "common_plus_nobits_union_bytes": common_total + agg["nobits_named_union_bytes"],
    }

    listed_objects = objects[:OBJECT_TABLE_LIMIT]
    listed_common = common[:OBJECT_TABLE_LIMIT]
    bounds = {
        "object_table_limit": OBJECT_TABLE_LIMIT,
        "json_byte_limit": JSON_BYTE_LIMIT,
        "object_symbols_total": len(objects),
        "object_symbols_listed": len(listed_objects),
        "common_symbols_total": len(common),
        "common_symbols_listed": len(listed_common),
        "truncated": len(objects) > len(listed_objects) or len(common) > len(listed_common),
    }

    result: dict = {
        "status": "parsed",
        "profile": profile,
        "module_input": "public-source build output only; no private payload",
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        "elf": {"class": 32, "little_endian": True, "machine": "EM_ARM", "type": "ET_REL"},
        "writable_sections": [
            {"name": group["name"], "type": group["type"], "size": group["size"]} for group in groups
        ],
        "objects": listed_objects,
        "common": listed_common,
        "section_accounting": section_accounting,
        "summary": summary,
        "bounds": bounds,
        "compiler": parse_build_cmd(cmd_path) if cmd_path is not None else None,
        "load_safety": "NOT_ESTABLISHED",
        "notes": [
            "selected STT_OBJECT symbols are only those in allocated+writable sections (.bss/.data and splits) or COMMON",
            "objects and common tables are sorted by descending st_size then name (top globals first)",
            "object_byte_sum is the naive sum of st_size and double-counts aliases and overlapping spans; use named_union_bytes",
            "named_union_bytes merges [st_value, st_value+st_size) offsets per section; padding_bytes = section size - named_union_bytes",
            "COMMON symbols have no linker offset yet: st_value is the alignment and common_total_bytes is a name-size total",
            "common_total_bytes + the NOBITS named union may be compared with the stock .bss effective footprint as research evidence only; it must not be equated with a finalized linker layout",
            "no raw section or symbol data bytes are emitted; only names/sizes/bindings/section offsets",
            "matching storage totals is NOT an ABI or load-safety result",
            "load_safety NOT_ESTABLISHED: an offline public-source module is never authorized to load",
        ],
    }

    # Enforce the JSON bound on exactly the serialised form the CLI writes.
    while len(_json_text(result).encode("utf-8")) > JSON_BYTE_LIMIT and (listed_objects or listed_common):
        if listed_objects and len(listed_objects) >= len(listed_common):
            listed_objects = listed_objects[: max(0, len(listed_objects) - max(1, len(listed_objects) // 10))]
        else:
            listed_common = listed_common[: max(0, len(listed_common) - max(1, len(listed_common) // 10))]
        result["objects"] = listed_objects
        result["common"] = listed_common
        bounds["object_symbols_listed"] = len(listed_objects)
        bounds["common_symbols_listed"] = len(listed_common)
        bounds["truncated"] = True
    return result


def _summary(result: dict) -> dict:
    return {
        "status": result["status"],
        "profile": result.get("profile"),
        "sha256": result["sha256"],
        "bytes": result["bytes"],
        "load_safety": result["load_safety"],
        "bounds": result["bounds"],
        "compiler": result.get("compiler"),
        **result["summary"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ko", type=Path, help="public-source-built ARM32 ET_REL module")
    parser.add_argument("--profile")
    parser.add_argument("--cmd", type=Path, help="optional kbuild .cmd read as text; never executed")
    parser.add_argument("--out", type=Path, help="write the full JSON report here")
    args = parser.parse_args(argv)

    try:
        blob = args.ko.read_bytes()
    except OSError as exc:
        print(json.dumps({"status": "error", "error": str(exc), "path": str(args.ko)}, indent=2, sort_keys=True))
        return 2
    try:
        result = report(blob, profile=args.profile, cmd_path=args.cmd)
    except (ValueError, ELFError) as exc:
        print(json.dumps({"status": "error", "error": str(exc), "path": str(args.ko)}, indent=2, sort_keys=True))
        return 1
    text = _json_text(result) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps(_summary(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
