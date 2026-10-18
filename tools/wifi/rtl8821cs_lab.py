#!/usr/bin/env python3
"""Offline public-source build-lab helpers for the RTL8821CS SDIO driver.

Deterministic and side-effect free except for the files explicitly requested on
the command line. Never contacts a device, never downloads anything, never
reads or writes firmware. Supports ``tools/wifi/build_rtl8821cs_lab.sh``:

* ``manifest``        -- machine-readable provenance pins
* ``env``             -- shell ``KEY=VALUE`` exports for the orchestrator
* ``verify-file``     -- strict SHA-256 check of one downloaded artifact
* ``check-driver``    -- verify pinned source file hashes after extraction
* ``config-state``    -- read a reconstructed kernel ``.config`` and report flags
* ``config-sticky``   -- report whether the iteration-2 forced choices stuck
* ``layout-probe``    -- compile-only struct-layout probe metadata + arch scan
* ``memzero-scan``   -- per-object ``__memzero``/``memset`` attribution in a driver build tree
* ``memzero-probe``  -- parse compile-only codegen variant objects into a flag table
* ``module-metadata`` -- ELF module modinfo / section / undefined-symbol metadata
* ``module-storage``  -- allocated/COMMON object-symbol storage accounting (bounded)
* ``report``          -- assemble ``report.json`` from a run's artifacts

The lab never claims camera ABI compatibility and never authorises a load.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FW_DIR = REPO_ROOT / "tools" / "fw"
if str(FW_DIR) not in sys.path:
    sys.path.insert(0, str(FW_DIR))

# --------------------------------------------------------------------------
# Pins. These are the single source of truth for the shell orchestrator.
# The kernel SHA-256 was looked up independently in the PGP-signed upstream
# release checksum file (https://cdn.kernel.org/.../v4.x/sha256sums.asc) and is
# pinned here before any fetch; it is never derived from the fetched tarball.
# The HTTPS checksum is verified; the OpenPGP signature itself is NOT verified
# in this lab.
# --------------------------------------------------------------------------
PINS = {
    "kernel": {
        "version": "4.9.227",
        "url": "https://cdn.kernel.org/pub/linux/kernel/v4.x/linux-4.9.227.tar.xz",
        "sha256": "38c485b411a14e825f8a66a5c2e64f1480397325a5f692b4929f68d228070c5f",
        "sums_url": "https://cdn.kernel.org/pub/linux/kernel/v4.x/sha256sums.asc",
        "sums_signature_verified": False,
        "sha256_source": "upstream cdn.kernel.org v4.x sha256sums.asc (HTTPS), looked up independently of any fetch",
        "extracted_dir": "linux-4.9.227",
    },
    "driver": {
        "repo": "https://github.com/leavs/rtl8821cs",
        "commit": "d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2",
        "url": "https://codeload.github.com/leavs/rtl8821cs/tar.gz/d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2",
        "archive_sha256": "f7f6cdf34260f55bbca7ad0e3ce5959f4f8ee41dead30d1ee52ae1255c85347e",
        "extracted_dir": "rtl8821cs-d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2",
        "version_string": "v5.14.2-28-g6011b0372.20220328",
        "files": {
            "include/rtw_version.h": "aae92ac00973d72e56b7b03023c2aa1184e1e0a53b914e0995be00ca6dc39e53",
            "Makefile": "dbe35f90f5fb7a14c91e595db8cf12249d64493bdb069da0016d92be6e940b5d",
            "include/drv_conf.h": "997eea79909bbcb520493441e803fe5df97ed36ea8b935610c46e6c8a734efce",
            "include/autoconf.h": "7470f2b517425fc27955e607b215242ea3796d105d0d1e172102152a139aa6d6",
        },
    },
    "profiles": ["baseline", "concurrent"],
    "claim": {
        "camera_abi_claim": "NOT_CAMERA_ABI",
        "load_authorized": False,
        "load_policy": "NO_LOAD_EVER_FROM_THIS_LAB",
        "config_basis": "upstream multi_v7_defconfig + vermagic reconstruction + iteration-2 inferred debug/lock/stackprotector/ipv6 deltas (NOT a camera config)",
        "camera_config_reproduced": False,
    },
}

# --------------------------------------------------------------------------
# Iteration 2 hypothesis. These config deltas and the prediction are INFERRED
# research choices, NOT a reproduction of any camera configuration. A matching
# undefined-symbol set is evidence about the reconstructed config only; it is
# never an ABI-success or load-safety claim.
# --------------------------------------------------------------------------
ITERATION = 5

HYPOTHESIS = {
    "label": "iteration5-memzero-attribution",
    "statement": (
        "The extra __memzero undefined reference (the stock module has memset only) "
        "can be attributed to exact driver translation units, and its emission is "
        "controlled by specific target codegen flag choices in the pinned host "
        "cross toolchain; no Kconfig or driver source changes in this iteration."
    ),
    "config_changes": [],
    "prediction": (
        "constant-zero memset emits __memzero under the lab target flags; the "
        "variant table shows which flag choices remove it; object attribution "
        "localizes every reference in both profiles"
    ),
    "camera_debug_lock_alloc_state": "inferred_not_proven",
    "abi_success_claim": False,
    "evidence_goal": (
        "object-level attribution (which .o files reference __memzero and/or memset) plus a "
        "compile-only codegen variant table isolating toolchain flag effects; the stock "
        "WEXT/layout difference, vendor ABI, recovery and any live test remain unresolved"
    ),
    "config_changed_since_iteration2": False,
    "target_codegen_changed_since_iteration3": "-fcommon replaced by -fno-common (iteration 4; unchanged)",
    "build_change_since_iteration4": "none: iteration 5 adds metadata evidence only",
    "iteration5_scope": "attribution + flag-variant measurement; no codegen/config change, no load",
}

# Explicitly forced iteration-2 choices. ``config_state`` reports any that
# olddefconfig silently changed (unmet dependency or dropped symbol).
STICKY_KCONFIG = {
    "CONFIG_DEBUG_KERNEL": "y",
    "CONFIG_DEBUG_SPINLOCK": "y",
    "CONFIG_DEBUG_MUTEXES": "y",
    "CONFIG_DEBUG_LOCK_ALLOC": "n",
    "CONFIG_PROVE_LOCKING": "n",
    "CONFIG_CC_STACKPROTECTOR_REGULAR": "y",
    "CONFIG_CC_STACKPROTECTOR_STRONG": "n",
    "CONFIG_CC_STACKPROTECTOR_NONE": "n",
    "CONFIG_IPV6": "n",
}

# Kernel flags that must hold for the reconstructed config to carry the same
# vermagic tokens as the stock module. These are required (the run is marked
# "failed" if any is unmet).
REQUIRED_KCONFIG = {
    "CONFIG_MODULES": "y",
    "CONFIG_SMP": "y",
    "CONFIG_PREEMPT": "y",
    "CONFIG_MODULE_UNLOAD": "y",
    "CONFIG_THUMB2_KERNEL": "y",
    "CONFIG_ARM_PATCH_PHYS_VIRT": "y",
    "CONFIG_LOCALVERSION": "",
}

# Flags expected of the reconstructed config. Unmet entries are reported as
# warnings, not hard failures (the module still builds with undefined symbols).
# The debug/lock/stackprotector/ipv6 entries below are the iteration-2
# hypothesis (see HYPOTHESIS); they were inferred, not read from a camera.
EXPECTED_KCONFIG = {
    "CONFIG_AEABI": "y",
    "CONFIG_CPU_V7": "y",
    "CONFIG_CFG80211": "m",
    "CONFIG_MMC": "m",
    # Linux 4.9 net/wireless/Kconfig selects WEXT_CORE via CFG80211_WEXT;
    # promptless WIRELESS_EXT is independent and may legitimately remain n.
    "CONFIG_CFG80211_WEXT": "y",
    "CONFIG_WEXT_CORE": "y",
    "CONFIG_WEXT_PROC": "y",
    "CONFIG_PROC_FS": "y",
    "CONFIG_MODVERSIONS": "n",
    "CONFIG_GCC_PLUGINS": "n",
    "CONFIG_DEBUG_KERNEL": "y",
    "CONFIG_DEBUG_SPINLOCK": "y",
    "CONFIG_DEBUG_MUTEXES": "y",
    "CONFIG_DEBUG_LOCK_ALLOC": "n",
    "CONFIG_PROVE_LOCKING": "n",
    "CONFIG_CC_STACKPROTECTOR": "y",
    "CONFIG_CC_STACKPROTECTOR_REGULAR": "y",
    "CONFIG_CC_STACKPROTECTOR_STRONG": "n",
    "CONFIG_CC_STACKPROTECTOR_NONE": "n",
    "CONFIG_IPV6": "n",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOT_SET_RE = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_kconfig(text: str) -> dict:
    """Parse a ``.config`` into ``{"CONFIG_X": "y"|"m"|"n"|"<string>"}``."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _NOT_SET_RE.match(line)
        if match:
            out[match.group(1)] = "n"
            continue
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("CONFIG_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        out[key] = value
    return out


def config_state(config_path: Path) -> dict:
    observed_all = parse_kconfig(config_path.read_text(encoding="utf-8", errors="replace"))
    wanted = list(dict.fromkeys(list(REQUIRED_KCONFIG) + list(EXPECTED_KCONFIG) + list(STICKY_KCONFIG)))
    observed = {symbol: observed_all.get(symbol, "n") for symbol in wanted}
    required_missing = [
        f"{symbol} (want {want!r}, saw {observed[symbol]!r})"
        for symbol, want in REQUIRED_KCONFIG.items()
        if observed[symbol] != want
    ]
    expected_mismatch = [
        f"{symbol} (want {want!r}, saw {observed[symbol]!r})"
        for symbol, want in EXPECTED_KCONFIG.items()
        if observed[symbol] != want
    ]
    # The iteration-2 choices were forced through scripts/config; olddefconfig
    # can silently revert a symbol whose dependency is unmet. Report those.
    sticky_mismatch = [
        f"{symbol} (forced {want!r}, saw {observed[symbol]!r})"
        for symbol, want in STICKY_KCONFIG.items()
        if observed[symbol] != want
    ]
    return {
        "config_path": str(config_path),
        "sha256": sha256_file(config_path),
        "iteration": ITERATION,
        "vermagic_required_missing": required_missing,
        "vermagic_required_ok": not required_missing,
        "expected_mismatch": expected_mismatch,
        "expected_ok": not expected_mismatch,
        "sticky_mismatch": sticky_mismatch,
        "sticky_ok": not sticky_mismatch,
        "observed": observed,
    }


def check_driver(driver_dir: Path) -> dict:
    results = {}
    all_match = True
    for rel, expected in PINS["driver"]["files"].items():
        target = driver_dir / rel
        if not target.is_file():
            results[rel] = {"present": False, "expected": expected}
            all_match = False
            continue
        actual = sha256_file(target)
        match = actual == expected
        all_match = all_match and match
        results[rel] = {"present": True, "sha256": actual, "expected": expected, "match": match}
    return {
        "driver_dir": str(driver_dir),
        "commit": PINS["driver"]["commit"],
        "version_string": PINS["driver"]["version_string"],
        "files": results,
        "all_match": all_match,
    }


# --------------------------------------------------------------------------
# Compile-only layout probe. The probe is a relocatable ELF32 ARM object whose
# global char arrays encode sizeof()/offsetof() values as symbol sizes. Only
# ``probe.o`` is requested from kbuild, so no module is linked and no
# modpost/MODULE_LICENSE step runs.
# --------------------------------------------------------------------------
_ELF_MACHINE = {0: "NONE", 3: "I386", 40: "ARM", 62: "X86_64"}
_ELF_TYPE = {1: "ET_REL", 2: "ET_EXEC", 3: "ET_DYN", 4: "ET_CORE"}
_SHT_SYMTAB = 2
_SHN_UNDEF = 0
_SIZEOF_PREFIX = "c2m_probe_sizeof_"
_OFFSETOF_PREFIX = "c2m_probe_offsetof_"


def parse_elf32(blob: bytes) -> dict:
    """Dependency-free ELF32 little-endian reader for relocatable objects."""
    if len(blob) < 52 or blob[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    if blob[4] != 1:
        raise ValueError("not ELFCLASS32")
    if blob[5] != 1:
        raise ValueError("not little-endian")
    header = struct.unpack_from("<HHIIIIIHHHHHH", blob, 16)
    e_type, e_machine = header[0], header[1]
    e_shoff, e_shentsize, e_shnum, e_shstrndx = header[5], header[10], header[11], header[12]
    if e_shoff == 0 or e_shnum == 0 or e_shentsize < 40:
        raise ValueError("ELF has no section header table")
    sections = []
    for index in range(e_shnum):
        off = e_shoff + index * e_shentsize
        if off + 40 > len(blob):
            raise ValueError("section header table out of bounds")
        (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size,
         sh_link, sh_info, sh_addralign, sh_entsize) = struct.unpack_from("<IIIIIIIIII", blob, off)
        sections.append({
            "index": index, "sh_name": sh_name, "type": sh_type, "flags": sh_flags,
            "addr": sh_addr, "offset": sh_offset, "size": sh_size, "link": sh_link,
            "info": sh_info, "addralign": sh_addralign, "entsize": sh_entsize, "name": "",
        })
    if e_shstrndx >= len(sections):
        raise ValueError("invalid e_shstrndx")
    shstr = sections[e_shstrndx]
    shstrtab = blob[shstr["offset"]:shstr["offset"] + shstr["size"]]

    def _name(base: bytes, name_off: int) -> str:
        if name_off < 0 or name_off >= len(base):
            return ""
        end = base.find(b"\0", name_off)
        if end < 0:
            end = len(base)
        return base[name_off:end].decode("utf-8", errors="replace")

    for section in sections:
        section["name"] = _name(shstrtab, section["sh_name"])

    symbols = []
    symtab = next((s for s in sections if s["type"] == _SHT_SYMTAB), None)
    if symtab is not None:
        linked = sections[symtab["link"]] if 0 <= symtab["link"] < len(sections) else {"offset": 0, "size": 0}
        strtab = blob[linked["offset"]:linked["offset"] + linked["size"]]
        entsize = symtab["entsize"] or 16
        for index in range(symtab["size"] // entsize):
            off = symtab["offset"] + index * entsize
            if off + 16 > len(blob):
                break
            st_name, st_value, st_size, st_info, st_other, st_shndx = struct.unpack_from("<IIIBBH", blob, off)
            symbols.append({
                "name": _name(strtab, st_name),
                "value": st_value,
                "size": st_size,
                "info": st_info,
                "other": st_other,
                "shndx": st_shndx,
                "global": bool(st_info & 0x10),
                "undefined": st_shndx == _SHN_UNDEF,
            })
    return {
        "class": 32,
        "little_endian": True,
        "type": _ELF_TYPE.get(e_type, f"e_type={e_type}"),
        "machine": _ELF_MACHINE.get(e_machine, f"e_machine={e_machine}"),
        "sections": {s["name"]: {"type": s["type"], "size": s["size"]} for s in sections if s["name"]},
        "symbols": symbols,
    }


def layout_probe_bytes(blob: bytes, object_name: str = "probe.o") -> dict:
    parsed = parse_elf32(blob)
    sizes: dict[str, int] = {}
    offsets: dict[str, int] = {}
    for symbol in parsed["symbols"]:
        name = symbol["name"]
        if name.startswith(_SIZEOF_PREFIX):
            sizes[name[len(_SIZEOF_PREFIX):]] = symbol["size"]
        elif name.startswith(_OFFSETOF_PREFIX):
            offsets[name[len(_OFFSETOF_PREFIX):]] = symbol["size"]
    undefined = sorted({s["name"] for s in parsed["symbols"] if s["undefined"] and s["name"]})
    return {
        "status": "parsed",
        "object": object_name,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        "elf": {
            "class": parsed["class"],
            "little_endian": parsed["little_endian"],
            "type": parsed["type"],
            "machine": parsed["machine"],
        },
        "struct_sizes": dict(sorted(sizes.items())),
        "struct_offsets": dict(sorted(offsets.items())),
        "undefined_symbols": undefined,
        "undefined_symbol_count": len(undefined),
        "memset_related_undefined": [s for s in undefined if s in ("memset", "__memzero", "memcpy", "memmove")],
        "load_safety": "NOT_ESTABLISHED",
        "notes": [
            "compile-only probe: only probe.o is produced, so no modpost/MODULE_LICENSE step runs and no .ko exists",
            "array symbol sizes encode sizeof()/offsetof() under the reconstructed config",
            "these layouts do NOT prove vendor-camera struct layout or loading safety",
        ],
    }


# The __memzero export is decided from BOTH files: memzero.S alone cannot show
# whether the symbol is exported, and absence in these files is not a
# kernel-wide proof. This mirrors the iteration-2 correction that the parent
# found v4.9.227 arch/arm/kernel/armksyms.c does carry EXPORT_SYMBOL(__memzero).
MEMZERO_SCAN_FILES = ("arch/arm/kernel/armksyms.c", "arch/arm/lib/memzero.S")


def memzero_export(ksrc: Path) -> dict:
    files = {}
    combined = hashlib.sha256()
    for rel in MEMZERO_SCAN_FILES:
        target = ksrc / rel
        entry = {"path": rel, "present": target.is_file()}
        if entry["present"]:
            text = target.read_text(encoding="utf-8", errors="replace")
            digest = sha256_file(target)
            export_lines = [ln.strip() for ln in text.splitlines() if "__memzero" in ln and "EXPORT_SYMBOL" in ln]
            entry.update(
                sha256=digest,
                bytes=target.stat().st_size,
                mentions_memzero="__memzero" in text,
                export_symbol_lines=export_lines,
                exports_memzero=bool(export_lines),
            )
            combined.update(rel.encode("utf-8"))
            combined.update(digest.encode("ascii"))
        files[rel] = entry
    scanned = [entry for entry in files.values() if entry["present"]]
    if any(entry.get("exports_memzero") for entry in files.values()):
        verdict = "exported"
    elif len(scanned) == len(MEMZERO_SCAN_FILES):
        verdict = "not_exported_in_scanned_files"
    else:
        verdict = "unknown_partial_scan"
    return {
        "kernel_source": str(ksrc),
        "files": files,
        "arch_string_sha256": combined.hexdigest(),
        "arch_string_source": "sha256 over scanned arch/arm relpaths plus each file sha256",
        "memzero_export_verdict": verdict,
        "scope_note": (
            "verdict covers only the scanned files; __memzero absent from a module undefined set is a "
            "source/codegen delta and is not by itself a load hazard"
        ),
    }


def memzero_attribution(objects_dir: Path, profile: str | None = None,
                        limit: int = 400) -> dict:
    """Object-level __memzero / memset attribution across one driver build tree.

    Pure metadata: every regular ``*.o`` under ``objects_dir`` is parsed as
    ELF32 and only undefined-symbol names are used. Objects are never linked
    into a module here and nothing is executed or loaded.
    """
    candidates = sorted(p for p in objects_dir.rglob("*.o") if p.is_file()) \
        if objects_dir.is_dir() else []
    scanned = 0
    unparseable: list[str] = []
    memzero_objects: list[dict] = []
    memset_objects = 0
    for path in candidates:
        relative = str(path.relative_to(objects_dir)).replace("\\", "/")
        try:
            parsed = parse_elf32(path.read_bytes())
        except Exception:  # noqa: BLE001 - record honestly, never fake evidence
            unparseable.append(relative)
            continue
        scanned += 1
        undefined = {s["name"] for s in parsed["symbols"] if s["undefined"] and s["name"]}
        if "memset" in undefined:
            memset_objects += 1
        if "__memzero" in undefined:
            memzero_objects.append({
                "object": relative,
                "undefined_symbol_count": len(undefined),
            })
    return {
        "probe": "memzero-object-attribution",
        "profile": profile,
        "objects_dir": str(objects_dir),
        "objects_seen": len(candidates),
        "objects_scanned": scanned,
        "unparseable_count": len(unparseable),
        "unparseable_objects": unparseable[:limit],
        "objects_with_memset_count": memset_objects,
        "objects_with_memzero_count": len(memzero_objects),
        "objects_with_memzero": memzero_objects[:limit],
        "truncated": len(memzero_objects) > limit,
        "load_safety": "NOT_ESTABLISHED",
        "notes": [
            "public-source compile metadata only; no module was built from these objects in this step",
            "attribution localizes the extra __memzero reference; it does not by itself explain the stock build difference",
        ],
    }


def memzero_probe(probe_dir: Path) -> dict:
    """Parse compile-only codegen variant objects into a flag -> symbol table.

    ``probe_dir`` holds one ``<variant>.o`` per flag set plus an optional
    ``flags.tsv`` (name TAB flags, written by the shell as the single source of
    truth) and an optional ``toolchain.txt``. Parse failures are reported as
    such; nothing is linked or loaded.
    """
    flags: dict[str, str] = {}
    flags_file = probe_dir / "flags.tsv"
    if flags_file.is_file():
        for raw in flags_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            parts = raw.split("\t", 1)
            flags[parts[0]] = parts[1] if len(parts) > 1 else ""
    toolchain = None
    toolchain_file = probe_dir / "toolchain.txt"
    if toolchain_file.is_file():
        toolchain = toolchain_file.read_text(encoding="utf-8", errors="replace").strip()
    variants: dict[str, dict] = {}
    for path in sorted(probe_dir.glob("*.o")):
        entry = {
            "object": path.name,
            "flags": flags.get(path.stem),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        try:
            parsed = parse_elf32(path.read_bytes())
            undefined = sorted({s["name"] for s in parsed["symbols"] if s["undefined"] and s["name"]})
            entry.update(
                status="parsed",
                undefined_symbols=undefined,
                undefined_symbol_count=len(undefined),
                has_memzero="__memzero" in undefined,
                has_memset="memset" in undefined,
            )
        except Exception as exc:  # noqa: BLE001 - surface parse failure honestly
            entry.update(status="unparseable", error=str(exc),
                         has_memzero=None, has_memset=None)
        variants[path.stem] = entry
    return {
        "probe": "memzero-codegen-variant-table",
        "variants": variants,
        "variant_count": len(variants),
        "toolchain": toolchain,
        "load_safety": "NOT_ESTABLISHED",
        "notes": [
            "variant flags are a reduced subset of the kbuild command line; they isolate flag effects, not a byte-exact kbuild reproduction",
            "compile-only objects: never linked into a module and never loaded",
        ],
    }


def layout_probe(obj_path: Path, ksrc: Path | None = None) -> dict:
    result = {"probe_iteration": ITERATION, "hypothesis_label": HYPOTHESIS["label"]}
    if obj_path.is_file():
        try:
            obj = layout_probe_bytes(obj_path.read_bytes(), obj_path.name)
            obj["path"] = str(obj_path)
        except Exception as exc:  # noqa: BLE001 - surface the parse failure honestly
            obj = {"status": "unparseable", "path": str(obj_path), "error": str(exc)}
        result["object"] = obj
    else:
        result["object"] = {"status": "missing", "path": str(obj_path)}
    if ksrc is not None:
        result["source_scan"] = memzero_export(ksrc)
    return result


def _profile_role(profile: str) -> str:
    if profile == "baseline":
        return "reconstructed_upstream_armv7_thumb2_single_vif"
    if profile == "concurrent":
        return "reconstructed_upstream_armv7_thumb2_same_channel_two_vif"
    return "unknown_profile"


def module_metadata(ko_path: Path, profile: str) -> dict:
    import module_abi_report

    blob = ko_path.read_bytes()
    elf = module_abi_report.report(blob)
    role = _profile_role(profile)
    return {
        "profile": profile,
        "role": role,
        "camera_abi_claim": "NOT_CAMERA_ABI",
        "load_authorized": False,
        "load_policy": "NO_LOAD_EVER_FROM_THIS_LAB",
        "kernel": {
            "version": PINS["kernel"]["version"],
            "source": "upstream kernel.org tarball",
            "config": PINS["claim"]["config_basis"],
            "config_reproduced_from_camera": False,
        },
        "driver": {
            "commit": PINS["driver"]["commit"],
            "version_string": PINS["driver"]["version_string"],
        },
        "source_pins": dict(PINS["driver"]["files"]),
        "elf": elf,
        "notes": [
            "vermagic equality or symbol agreement would NOT prove vendor-camera struct layout or loading safety",
            "built with the host distribution cross compiler, not the vendor gcc-9.1.0 toolchain",
            "module bytes stay in the ephemeral runner scratch dir; only this metadata is retained",
        ],
    }


def module_storage(ko_path: Path, profile: str, cmd_path: Path | None = None) -> dict:
    """Bounded allocated/COMMON object accounting for one public-source .ko.

    Delegates to ``tools/fw/module_storage_report`` so the same bounded helper is
    exercised by the standalone tests. Only names/sizes/bindings/offsets are
    reported; the module blob and any build ``.cmd`` are read, never executed.
    """
    import module_storage_report

    blob = ko_path.read_bytes()
    result = module_storage_report.report(blob, profile=profile, cmd_path=cmd_path)
    result["role"] = _profile_role(profile)
    result["camera_abi_claim"] = "NOT_CAMERA_ABI"
    result["load_policy"] = "NO_LOAD_EVER_FROM_THIS_LAB"
    result["notes"] = list(result.get("notes", [])) + [
        "role/label is metadata only; the producing config is the reconstructed iteration-2 config (unchanged)",
    ]
    return result


def _read_steps(step_file: Path) -> list:
    steps = []
    if not step_file.is_file():
        return steps
    for raw in step_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        name = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        detail = parts[2] if len(parts) > 2 else ""
        steps.append({"step": name, "status": status, "detail": detail})
    return steps


def build_report(out_dir: Path, exit_code: int) -> dict:
    steps = _read_steps(out_dir / "steps.tsv")
    report = {
        "lab": "rtl8821cs-offline-public-source",
        "iteration": ITERATION,
        "iteration_label": HYPOTHESIS["label"],
        "load_safety": "NOT_ESTABLISHED",
        "generated_by": "tools/wifi/build_rtl8821cs_lab.sh",
        "exit_code": exit_code,
        "identity": {
            "purpose": "offline public-source build research only",
            "kernel": {
                "version": PINS["kernel"]["version"],
                "url": PINS["kernel"]["url"],
                "sha256": PINS["kernel"]["sha256"],
                "sha256_source": PINS["kernel"]["sha256_source"],
                "sums_url": PINS["kernel"]["sums_url"],
                "sums_signature_verified": PINS["kernel"]["sums_signature_verified"],
            },
            "driver": {
                "repo": PINS["driver"]["repo"],
                "commit": PINS["driver"]["commit"],
                "url": PINS["driver"]["url"],
                "archive_sha256": PINS["driver"]["archive_sha256"],
                "version_string": PINS["driver"]["version_string"],
            },
            **PINS["claim"],
        },
        "steps": steps,
        "profiles": {},
        "warnings": [],
        "artifacts": {},
    }

    driver_verify = out_dir / "driver-verify.json"
    if driver_verify.is_file():
        report["driver_verify"] = json.loads(driver_verify.read_text(encoding="utf-8"))

    kernel_config = out_dir / "kernel-config.json"
    if kernel_config.is_file():
        state = json.loads(kernel_config.read_text(encoding="utf-8"))
        report["kernel_config"] = state
        report["warnings"].extend(state.get("expected_mismatch", []))
        if not state.get("vermagic_required_ok", False):
            report["warnings"].append("reconstructed config is missing required vermagic flags")
        report["hypothesis"] = {
            **HYPOTHESIS,
            "config_choices_forced": dict(STICKY_KCONFIG),
            "config_choices_ok": state.get("sticky_ok"),
            "config_choices_mismatch": state.get("sticky_mismatch", []),
        }
        for item in state.get("sticky_mismatch", []):
            report["warnings"].append(f"config choice did not stick after olddefconfig: {item}")

    toolchain = out_dir / "toolchain.txt"
    if toolchain.is_file():
        report["artifacts"]["toolchain.txt"] = {
            "sha256": sha256_file(toolchain),
            "bytes": toolchain.stat().st_size,
        }

    for profile in PINS["profiles"]:
        meta = out_dir / f"{profile}.metadata.json"
        log = out_dir / f"build-{profile}.log"
        entry: dict = {"status": "absent"}
        if log.is_file():
            entry["build_log_bytes"] = log.stat().st_size
        if meta.is_file():
            entry["status"] = "built"
            entry["metadata"] = json.loads(meta.read_text(encoding="utf-8"))
        storage = out_dir / f"{profile}.storage.json"
        if storage.is_file():
            # Reference the full bounded artifact; attach only the safe summary
            # so report.json stays small.
            entry["storage_artifact"] = storage.name
            try:
                data = json.loads(storage.read_text(encoding="utf-8"))
                entry["storage_summary"] = {
                    "sha256": data.get("sha256"),
                    "bytes": data.get("bytes"),
                    "load_safety": data.get("load_safety"),
                    "bounds": data.get("bounds"),
                    "compiler": data.get("compiler"),
                    "summary": data.get("summary"),
                }
            except (OSError, ValueError) as exc:
                entry["storage_summary_error"] = str(exc)
        attribution = out_dir / f"{profile}.memzero-attribution.json"
        if attribution.is_file():
            # Reference the full bounded artifact; attach only the safe summary.
            entry["memzero_artifact"] = attribution.name
            try:
                data = json.loads(attribution.read_text(encoding="utf-8"))
                entry["memzero_summary"] = {
                    "objects_scanned": data.get("objects_scanned"),
                    "objects_with_memzero_count": data.get("objects_with_memzero_count"),
                    "objects_with_memset_count": data.get("objects_with_memset_count"),
                    "load_safety": data.get("load_safety"),
                }
            except (OSError, ValueError) as exc:
                entry["memzero_summary_error"] = str(exc)
        report["profiles"][profile] = entry

    layout = out_dir / "layout-probe.json"
    if layout.is_file():
        report["layout_probe"] = json.loads(layout.read_text(encoding="utf-8"))
    memzero_table = out_dir / "memzero-probe.json"
    if memzero_table.is_file():
        try:
            data = json.loads(memzero_table.read_text(encoding="utf-8"))
            report["memzero_probe"] = {
                "variant_count": data.get("variant_count"),
                "toolchain": data.get("toolchain"),
                "variants": {
                    name: {
                        "flags": item.get("flags"),
                        "status": item.get("status"),
                        "has_memzero": item.get("has_memzero"),
                        "has_memset": item.get("has_memset"),
                    }
                    for name, item in data.get("variants", {}).items()
                },
            }
        except (OSError, ValueError) as exc:
            report["memzero_probe_error"] = str(exc)
    if "hypothesis" not in report:
        report["hypothesis"] = {**HYPOTHESIS, "config_choices_forced": dict(STICKY_KCONFIG), "config_choices_ok": None, "config_choices_mismatch": []}

    failed = [s for s in steps if s["status"] == "fail"]
    report["failed_steps"] = [s["step"] for s in failed]
    report["status"] = "failed" if (failed or exit_code != 0) else "ok"
    return report


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_env(_args) -> int:
    driver = PINS["driver"]
    kernel = PINS["kernel"]
    assignments = {
        "C2M_KERNEL_VERSION": kernel["version"],
        "C2M_KERNEL_URL": kernel["url"],
        "C2M_KERNEL_SHA256": kernel["sha256"],
        "C2M_KERNEL_DIR": kernel["extracted_dir"],
        "C2M_DRIVER_COMMIT": driver["commit"],
        "C2M_DRIVER_URL": driver["url"],
        "C2M_DRIVER_ARCHIVE_SHA256": driver["archive_sha256"],
        "C2M_DRIVER_DIR": driver["extracted_dir"],
        "C2M_DRIVER_VERSION": driver["version_string"],
    }
    for key, value in assignments.items():
        print(f"{key}={value}")
    return 0


def _cmd_manifest(_args) -> int:
    print(json.dumps(PINS, indent=2, sort_keys=True))
    return 0


def _cmd_verify_file(args) -> int:
    target = Path(args.path)
    result = {"path": str(target), "expected": args.expected}
    if not target.is_file():
        result.update(present=False, match=False)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    actual = sha256_file(target)
    result.update(present=True, sha256=actual, bytes=target.stat().st_size, match=actual == args.expected)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["match"] else 1


def _cmd_check_driver(args) -> int:
    result = check_driver(Path(args.driver_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_match"] else 1


def _cmd_config_state(args) -> int:
    result = config_state(Path(args.config))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_keys = ("vermagic_required_ok", "expected_ok", "sticky_ok", "vermagic_required_missing", "expected_mismatch", "sticky_mismatch")
    print(json.dumps({k: result[k] for k in summary_keys}, indent=2, sort_keys=True))
    return 0 if result["vermagic_required_ok"] else 1


def _cmd_config_sticky(args) -> int:
    state = config_state(Path(args.config))
    print(json.dumps({"sticky_ok": state["sticky_ok"], "sticky_mismatch": state["sticky_mismatch"]}, indent=2, sort_keys=True))
    return 0 if state["sticky_ok"] else 1


def _cmd_layout_probe(args) -> int:
    result = layout_probe(Path(args.obj), Path(args.ksrc) if args.ksrc else None)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    obj = result["object"]
    summary = {
        "object_status": obj.get("status"),
        "struct_sizes": obj.get("struct_sizes"),
        "struct_offsets": obj.get("struct_offsets"),
        "undefined_symbol_count": obj.get("undefined_symbol_count"),
        "memset_related_undefined": obj.get("memset_related_undefined"),
        "memzero_export_verdict": result.get("source_scan", {}).get("memzero_export_verdict"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if obj.get("status") == "parsed" else 1


def _cmd_module_metadata(args) -> int:
    result = module_metadata(Path(args.ko), args.profile)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "profile": result["profile"],
        "sha256": result["elf"]["sha256"],
        "bytes": result["elf"]["bytes"],
        "vermagic": result["elf"]["modinfo"].get("vermagic"),
        "undefined_symbol_count": result["elf"]["undefined_symbol_count"],
        "has_symbol_versions": result["elf"]["has_symbol_versions"],
        "load_safety": result["elf"]["load_safety"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_module_storage(args) -> int:
    cmd_path = Path(args.cmd) if getattr(args, "cmd", None) else None
    try:
        result = module_storage(Path(args.ko), args.profile, cmd_path)
    except Exception as exc:  # noqa: BLE001 - surface parse failure honestly, never fake evidence
        print(json.dumps({"status": "error", "profile": args.profile, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    common_count = result["summary"]["common_symbol_count"]
    result["target_common_gate"] = {
        "passed": common_count == 0,
        "count": common_count,
        "reason": "Linux 4.9 simplify_symbols rejects non-LTO SHN_COMMON; no load attempted",
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "status": result["status"],
        "profile": result["profile"],
        "sha256": result["sha256"],
        "bytes": result["bytes"],
        "bounds": result["bounds"],
        "load_safety": result["load_safety"],
        **result["summary"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if common_count == 0 else 1


def _cmd_memzero_scan(args) -> int:
    result = memzero_attribution(Path(args.objects_dir), getattr(args, "profile", None),
                                 getattr(args, "limit", 400))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "profile": result["profile"],
        "objects_scanned": result["objects_scanned"],
        "objects_with_memzero_count": result["objects_with_memzero_count"],
        "objects_with_memset_count": result["objects_with_memset_count"],
        "objects_with_memzero": [item["object"] for item in result["objects_with_memzero"]][:20],
        "unparseable_count": result["unparseable_count"],
        "load_safety": result["load_safety"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_memzero_probe(args) -> int:
    result = memzero_probe(Path(args.dir))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        name: {
            "flags": item["flags"],
            "status": item["status"],
            "has_memzero": item["has_memzero"],
            "has_memset": item["has_memset"],
        }
        for name, item in result["variants"].items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_report(args) -> int:
    report = build_report(Path(args.out), args.exit_code)
    target = Path(args.out) / "report.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), "status": report["status"], "failed_steps": report["failed_steps"]}, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("env")
    sub.add_parser("manifest")

    verify = sub.add_parser("verify-file")
    verify.add_argument("path")
    verify.add_argument("expected")

    driver = sub.add_parser("check-driver")
    driver.add_argument("driver_dir")

    config = sub.add_parser("config-state")
    config.add_argument("config")
    config.add_argument("--out")

    sticky = sub.add_parser("config-sticky")
    sticky.add_argument("config")

    probe = sub.add_parser("layout-probe")
    probe.add_argument("--obj", required=True)
    probe.add_argument("--ksrc")
    probe.add_argument("--out")

    meta = sub.add_parser("module-metadata")
    meta.add_argument("--ko", required=True)
    meta.add_argument("--profile", required=True)
    meta.add_argument("--out")

    storage = sub.add_parser("module-storage")
    storage.add_argument("--ko", required=True)
    storage.add_argument("--profile", required=True)
    storage.add_argument("--cmd")
    storage.add_argument("--out")

    mzscan = sub.add_parser("memzero-scan")
    mzscan.add_argument("--objects-dir", required=True)
    mzscan.add_argument("--profile")
    mzscan.add_argument("--limit", type=int, default=400)
    mzscan.add_argument("--out")

    mzprobe = sub.add_parser("memzero-probe")
    mzprobe.add_argument("--dir", required=True)
    mzprobe.add_argument("--out")

    report = sub.add_parser("report")
    report.add_argument("--out", required=True)
    report.add_argument("--exit-code", type=int, default=0)

    args = parser.parse_args(argv)
    handlers = {
        "env": _cmd_env,
        "manifest": _cmd_manifest,
        "verify-file": _cmd_verify_file,
        "check-driver": _cmd_check_driver,
        "config-state": _cmd_config_state,
        "config-sticky": _cmd_config_sticky,
        "layout-probe": _cmd_layout_probe,
        "module-metadata": _cmd_module_metadata,
        "module-storage": _cmd_module_storage,
        "memzero-scan": _cmd_memzero_scan,
        "memzero-probe": _cmd_memzero_probe,
        "report": _cmd_report,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
