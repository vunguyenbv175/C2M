#!/usr/bin/env python3
"""Fail-closed, version-only repacker for the four-file SD package.

The only allowed edits are one 14-byte U-Boot sysVer token, sysVer.txt, and
its regenerated inner-image MD5 sidecar. Every loaded payload (including
customer), load command, padding byte, UNKNOWN footer byte and adas script
must remain identical. This is host-byte evidence, not device/FLASH proof.

Library: reversion_package(members, old_version, new_version) -> (members, proof).
CLI pins are a required JSON object mapping all four exact names to SHA-256.
The output directory may be absent or empty; the report must be outside both
package directories. Existing files are never overwritten. No TAR/build/SD
or device operations are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import package_contract

INNER = package_contract.INNER
MEMBERS = (INNER, "sysVer.txt", "minieye_firmware.md5", "adas_upgrade.sh")
TOKEN_RE = re.compile(r"[0-9]{14}")
SYSVER_RE = re.compile(rb"^[ \t]*sysVer\b[^\n]*$", re.M)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokens(old_version: str, new_version: str) -> tuple[bytes, bytes]:
    for label, value in (("old", old_version), ("new", new_version)):
        if not isinstance(value, str) or TOKEN_RE.fullmatch(value) is None:
            raise ValueError(f"{label} version must be exactly 14 ASCII digits")
    if old_version == new_version:
        raise ValueError("old and new versions must differ")
    return old_version.encode("ascii"), new_version.encode("ascii")


def _members(members: dict[str, bytes]) -> None:
    if not isinstance(members, dict) or set(members) != set(MEMBERS):
        raise ValueError("package must contain exactly the four SD member names")
    if any(not isinstance(members[name], bytes) for name in MEMBERS):
        raise ValueError("all package members must be bytes")


def _sysver(token: bytes) -> bytes:
    return b"sysVer " + token + b"\nend\n"


def _md5_file(inner: bytes) -> bytes:
    return (hashlib.md5(inner).hexdigest() + "  " + INNER + "\n").encode("ascii")


def _number(text: str) -> int:
    return int(text, 16 if text.lower().startswith("0x") else 10)


def _inspect_inner(inner: bytes, token: bytes) -> dict:
    marker = package_contract.END_MARKER
    marker_start = inner.find(marker)
    if marker_start < 0 or (marker_start and inner[marker_start - 1] != 10):
        raise ValueError("inner script must end with a standalone END_MARKER")
    script_end = marker_start + len(marker)
    script = inner[:script_end]
    try:
        text = script.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("inner script must be ASCII text") from exc
    if any(byte not in (9, 10) and not 32 <= byte <= 126 for byte in script):
        raise ValueError("inner script contains CRLF or other control bytes")
    versions = list(SYSVER_RE.finditer(script))
    if len(versions) != 1 or versions[0].group() != b"sysVer " + token:
        raise ValueError("script must contain exactly one exact sysVer OLD/NEW line")
    token_offset = versions[0].start() + len(b"sysVer ")
    trailer_nl = inner[script_end:script_end + 1] == b"\n"
    script_bytes = script_end + int(trailer_nl)

    sections = list(package_contract.SECTION_RE.finditer(text))
    names = [section.group(1) for section in sections]
    if len(names) != len(set(names)):
        raise ValueError("duplicate File Partition section")
    fatloads = list(package_contract.FATLOAD_RE.finditer(text))
    # The shared regex is permissive. Do not silently ignore unsupported or
    # partially matched commands, or let its whitespace match cross lines.
    words = list(re.finditer(r"\bfatload\b", text, re.I))
    if not fatloads or [m.start() for m in words] != [m.start() for m in fatloads]:
        raise ValueError("missing or unsupported fatload command")
    for match in fatloads:
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        line = text[line_start:line_end].strip(" \t")
        if "\n" in match.group() or line != match.group():
            raise ValueError("fatload must be a complete single-line command")

    loads = []
    for index, section in enumerate(sections):
        start = section.end()
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        section_loads = [m for m in fatloads if start <= m.start() < end]
        for load_index, match in enumerate(section_loads):
            size, offset = (_number(match.group(1)), _number(match.group(2)))
            stop = offset + size
            if size <= 0 or not script_bytes <= offset < stop <= len(inner):
                raise ValueError("fatload range is empty, in the script, or outside the image")
            if offset < token_offset + 14 and stop > token_offset:
                raise ValueError("fatload range overlaps the version token")
            loads.append({
                "section": section.group(1), "load_index": load_index,
                "offset": offset, "size": size, "end": stop,
                "command": match.group(), "command_offset": match.start(),
                "sha256": _sha256(inner[offset:stop]),
            })
    if len(loads) != len(fatloads):
        raise ValueError("every fatload must belong to a File Partition section")
    ordered = sorted(loads, key=lambda row: row["offset"])
    if any(a["end"] > b["offset"] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("overlapping fatload payload ranges")
    first_offset = ordered[0]["offset"]
    if any(byte != 0xFF for byte in inner[script_bytes:first_offset]):
        raise ValueError("script must be followed only by optional LF and FF head padding")

    regions = [("head_padding", script_bytes, first_offset)]
    for a, b in zip(ordered, ordered[1:]):
        if a["end"] < b["offset"]:
            regions.append(("inter_payload_gap", a["end"], b["offset"]))
    regions.append(("unknown_footer", ordered[-1]["end"], len(inner)))
    return {
        "script_end": script_end, "script_bytes": script_bytes,
        "script_trailer_newline": trailer_nl, "token_offset": token_offset,
        "loads": loads, "regions": regions,
    }


def _inspect_package(members: dict[str, bytes], token: bytes) -> dict:
    _members(members)
    if members["sysVer.txt"] != _sysver(token):
        raise ValueError("sysVer.txt must exactly match the requested version and LF format")
    if members["minieye_firmware.md5"] != _md5_file(members[INNER]):
        raise ValueError("minieye_firmware.md5 is not the exact fresh inner-image MD5 line")
    return _inspect_inner(members[INNER], token)


def verify_pins(members: dict[str, bytes], pins: dict[str, str]) -> dict[str, str]:
    """Require a complete source SHA-256 map; return verified snapshot hashes."""
    _members(members)
    if not isinstance(pins, dict) or set(pins) != set(MEMBERS):
        raise ValueError("pins must map exactly the four SD member names to SHA-256")
    hashes = {name: _sha256(members[name]) for name in MEMBERS}
    for name in MEMBERS:
        value = pins[name]
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
            raise ValueError(f"invalid SHA-256 pin for {name}")
        if value.lower() != hashes[name]:
            raise ValueError(f"source SHA-256 pin mismatch: {name}")
    return hashes


def prove_version_only(source: dict[str, bytes], output: dict[str, bytes],
                       old_version: str, new_version: str) -> dict:
    """Fail unless every byte and load meets the version-only allowlist."""
    old, new = _tokens(old_version, new_version)
    before = _inspect_package(source, old)
    after = _inspect_package(output, new)
    original, revised = source[INNER], output[INNER]
    token_offset = before["token_offset"]
    stop = token_offset + 14
    if len(original) != len(revised):
        raise ValueError("inner image length changed")
    if before["token_offset"] != after["token_offset"]:
        raise ValueError("script token offset changed")
    if original[:token_offset] != revised[:token_offset] or original[stop:] != revised[stop:]:
        raise ValueError("inner bytes changed outside the 14-byte version token span")
    if original[token_offset:stop] != old or revised[token_offset:stop] != new:
        raise ValueError("inner token span does not match the requested versions")
    for key in ("script_end", "script_bytes", "script_trailer_newline", "regions"):
        if before[key] != after[key]:
            raise ValueError(f"inner layout changed: {key}")
    normalized = (revised[:token_offset] + old + revised[stop:after["script_bytes"]])
    if normalized != original[:before["script_bytes"]]:
        raise ValueError("script is not exactly identical after token normalization")
    if source["adas_upgrade.sh"] != output["adas_upgrade.sh"]:
        raise ValueError("adas_upgrade.sh changed")
    if before["loads"] != after["loads"]:
        raise ValueError("load command, partition offset, length or SHA-256 changed")

    load_proofs = []
    for a, b in zip(before["loads"], after["loads"]):
        if original[a["offset"]:a["end"]] != revised[b["offset"]:b["end"]]:
            raise ValueError("partition payload bytes changed")
        load_proofs.append({
            "section": a["section"], "load_index": a["load_index"],
            "offset": a["offset"], "size": a["size"], "end": a["end"],
            "command": a["command"], "command_offset": a["command_offset"],
            "source_sha256": a["sha256"], "output_sha256": b["sha256"],
            "unchanged": True,
        })
    region_proofs = []
    for kind, start, end in before["regions"]:
        a, b = original[start:end], revised[start:end]
        if a != b:
            raise ValueError(f"{kind} bytes changed")
        region_proofs.append({
            "kind": kind, "offset": start, "size": end - start, "end": end,
            "source_sha256": _sha256(a), "output_sha256": _sha256(b),
            "unchanged": True,
        })
    return {
        "verdict": "ALLOWLIST-OK", "host_byte_proof_only": True,
        "device_tested": False, "flash_proven": False,
        "old_version": old_version, "new_version": new_version,
        "source_sha256": {name: _sha256(source[name]) for name in MEMBERS},
        "output_sha256": {name: _sha256(output[name]) for name in MEMBERS},
        "new_md5": hashlib.md5(revised).hexdigest(), "inner_size": len(revised),
        "token_offset": token_offset, "token_span": [token_offset, stop],
        "changed_inner_byte_offsets": [index for index in range(token_offset, stop)
                                       if original[index] != revised[index]],
        "script_end": before["script_end"],
        "script_trailer_newline": before["script_trailer_newline"],
        "normalized_script_sha256": _sha256(normalized),
        "allowed_edits": ["inner 14-byte sysVer token", "sysVer.txt", "minieye_firmware.md5"],
        "proof": {
            "inner_equal_outside_token_span": True,
            "script_exact_after_token_normalization": True,
            "all_load_commands_offsets_sizes_and_payloads_identical": True,
            "padding_and_unknown_footer_identical": True,
            "adas_upgrade_sh_identical": True,
        },
        "loads": load_proofs, "preserved_regions": region_proofs,
    }


def reversion_package(source: dict[str, bytes], old_version: str,
                      new_version: str) -> tuple[dict[str, bytes], dict]:
    """Pure function: validate, change only the token/sidecars, and prove it."""
    old, new = _tokens(old_version, new_version)
    layout = _inspect_package(source, old)
    offset = layout["token_offset"]
    inner = source[INNER][:offset] + new + source[INNER][offset + 14:]
    output = dict(source)
    output[INNER] = inner
    output["sysVer.txt"] = _sysver(new)
    output["minieye_firmware.md5"] = _md5_file(inner)
    return output, prove_version_only(source, output, old_version, new_version)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON pin key: {key}")
        result[key] = value
    return result


def _empty_output(path: Path) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("output directory must be new or empty; refusing overwrite")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--pins", type=Path, required=True, help="required source SHA-256 JSON map")
    ap.add_argument("--old-version", required=True)
    ap.add_argument("--new-version", required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        _tokens(args.old_version, args.new_version)
        source_dir = args.source_dir.resolve(strict=True)
        if args.out_dir.is_symlink() or args.report.is_symlink():
            raise ValueError("output directory/report may not be symlinks")
        out_dir = args.out_dir.resolve()
        report_path = args.report.resolve()
        if (out_dir.is_relative_to(source_dir) or source_dir.is_relative_to(out_dir)):
            raise ValueError("source/output directories alias or overlap")
        if report_path.is_relative_to(source_dir) or report_path.is_relative_to(out_dir):
            raise ValueError("report must be outside both package directories")
        _empty_output(out_dir)
        if report_path.exists():
            raise ValueError("report already exists; refusing overwrite")
        if not source_dir.is_dir() or {p.name for p in source_dir.iterdir()} != set(MEMBERS):
            raise ValueError("source directory must contain exactly the four SD files")
        source = {}
        for name in MEMBERS:
            path = source_dir / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"source member is not a regular non-symlink file: {name}")
            source[name] = path.read_bytes()
        pins = json.loads(args.pins.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_json_object)
        verified = verify_pins(source, pins)
        output, report = reversion_package(source, args.old_version, args.new_version)
        # All pins, inputs, proof and destination checks pass before any writes.
        out_dir.mkdir(parents=True, exist_ok=True)
        _empty_output(out_dir)
        for name in MEMBERS:
            with (out_dir / name).open("xb") as stream:
                stream.write(output[name])
        readback = {}
        if {p.name for p in out_dir.iterdir()} != set(MEMBERS):
            raise ValueError("output directory changed during write")
        for name in MEMBERS:
            data = (out_dir / name).read_bytes()
            if data != output[name]:
                raise ValueError(f"output read-back bytes differ: {name}")
            readback[name] = _sha256(data)
        if readback != report["output_sha256"]:
            raise ValueError("output read-back SHA-256 mismatch")
        report.update({
            "source_dir": str(source_dir), "out_dir": str(out_dir),
            "pins_path": str(args.pins.resolve()), "verified_source_pins": verified,
            "readback_sha256": readback, "readback_verified": True,
        })
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 1
    print(f"ALLOWLIST-OK: wrote four SD payload files to {out_dir}")
    print(f"Host-only byte evidence: {report_path}; not device-tested or FLASH-proven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
