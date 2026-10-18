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
* ``module-metadata`` -- ELF module modinfo / section / undefined-symbol metadata
* ``report``          -- assemble ``report.json`` from a run's artifacts

The lab never claims camera ABI compatibility and never authorises a load.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
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
        "config_basis": "upstream multi_v7_defconfig + vermagic reconstruction (SMP/preempt/mod_unload/ARMv7/thumb2/p2v8)",
        "camera_config_reproduced": False,
    },
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
EXPECTED_KCONFIG = {
    "CONFIG_AEABI": "y",
    "CONFIG_CPU_V7": "y",
    "CONFIG_CFG80211": "m",
    "CONFIG_MMC": "m",
    "CONFIG_WIRELESS_EXT": "y",
    "CONFIG_CFG80211_WEXT": "y",
    "CONFIG_MODVERSIONS": "n",
    "CONFIG_CC_STACKPROTECTOR_STRONG": "n",
    "CONFIG_CC_STACKPROTECTOR_REGULAR": "n",
    "CONFIG_GCC_PLUGINS": "n",
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
    wanted = list(REQUIRED_KCONFIG) + list(EXPECTED_KCONFIG)
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
    return {
        "config_path": str(config_path),
        "sha256": sha256_file(config_path),
        "vermagic_required_missing": required_missing,
        "vermagic_required_ok": not required_missing,
        "expected_mismatch": expected_mismatch,
        "expected_ok": not expected_mismatch,
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


def module_metadata(ko_path: Path, profile: str) -> dict:
    import module_abi_report

    blob = ko_path.read_bytes()
    elf = module_abi_report.report(blob)
    if profile == "baseline":
        role = "reconstructed_upstream_armv7_thumb2_single_vif"
    elif profile == "concurrent":
        role = "reconstructed_upstream_armv7_thumb2_same_channel_two_vif"
    else:
        role = "unknown_profile"
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
        report["profiles"][profile] = entry

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
    print(json.dumps({k: result[k] for k in ("vermagic_required_ok", "expected_ok", "vermagic_required_missing", "expected_mismatch")}, indent=2, sort_keys=True))
    return 0 if result["vermagic_required_ok"] else 1


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

    meta = sub.add_parser("module-metadata")
    meta.add_argument("--ko", required=True)
    meta.add_argument("--profile", required=True)
    meta.add_argument("--out")

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
        "module-metadata": _cmd_module_metadata,
        "report": _cmd_report,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
