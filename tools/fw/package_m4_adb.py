#!/usr/bin/env python3
"""Package owner-private ACTIVE one-CNXN USB identification, NOT a passive sniffer.
No shell/auth response/UI control/updater. Hardware execution separately gated.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["fw/m4_adb/m4_adb_identify.c", "fw/m4_adb/build_arm.sh",
           "fw/device_minimal/start.S", "fw/device_minimal/check_elf.py", "fw/d3/compat.h",
           "tools/fw/test_ram_m4_adb_stock_qemu.py", "tools/fw/package_m4_adb.py",
           "tests/test_m4_adb.py", ".github/workflows/ram-debug-arm.yml"]


def checked_elf(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("binary must be a regular file")
    data = path.read_bytes()
    if not 512 <= len(data) <= 512 * 1024:
        raise ValueError("unexpected identifier size")
    if data[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 40:
        raise ValueError("expected little-endian ELF32 ARM")
    if struct.unpack_from("<H", data, 16)[0] != 2:
        raise ValueError("expected no-PIE executable")
    return data


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--binary", required=True, type=Path)
    p.add_argument("--evidence", required=True, type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("Refuse existing bundle output")
    blob = checked_elf(a.binary)
    digest = hashlib.sha256(blob).hexdigest()
    r = json.loads((a.evidence / "arm-m4-adb-runtime.json").read_text())
    from prepare_ram_debug_sysroot import PINS
    required = {"verdict": "PASS", "camera_used": False, "binary_sha256": digest,
                "stock_runtime_sha256": PINS, "window_ms": 5000, "max_out_calls": 2,
                "max_in_calls": 2, "max_out_bytes": 31, "sentinel_unchanged": True,
                "missing_usb_fail_closed": True, "undefined_import_gate": True}
    if any(r.get(k) != v for k, v in required.items()):
        raise SystemExit("Mandatory exact M4 ADB runtime proof missing")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != os.environ.get("GITHUB_SHA", revision):
        raise SystemExit("workflow/source revision mismatch")
    for name in SOURCES:
        expected = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT)
        if expected != (ROOT / name).read_bytes():
            raise SystemExit("Source differs from checked-in workflow revision")
    subprocess.run(["python3", "fw/device_minimal/check_elf.py", str(a.binary), "--allow-dynamic"],
                   cwd=ROOT, check=True, timeout=30)
    manifest = {"schema": 1, "kind": "OWNER-PRIVATE-RAM-ACTIVE-IDENTIFICATION-NOT-UPDATER",
                "asset": "c2m-m4-adb", "source_commit": revision,
                "github_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
                "sha256": {"c2m-m4-adb": digest}, "bytes": {"c2m-m4-adb": len(blob)},
                "source_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in SOURCES},
                "stock_qemu_m4_adb": "PASS", "window_ms": 5000,
                "max_out_calls": 2, "max_in_calls": 2, "max_out_bytes": 31,
                "usb_interface": 2, "vid_pid": "2207:0013", "active_cnxn_only": True,
                "authentication_reply": False, "shell_commands": False,
                "keys_included": False, "radio_used": False, "camera_used": False,
                "firmware_package_created": False, "native_elf_hardware_executed": False,
                "ui_change": False, "hardware_accepted": False}
    a.output.mkdir(parents=True)
    (a.output / "c2m-m4-adb").write_bytes(blob)
    (a.output / "c2m-m4-adb").chmod(0o700)
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    mdigest = hashlib.sha256((a.output / "manifest.json").read_bytes()).hexdigest()
    (a.output / "SHA256SUMS.txt").write_text(
        f"{digest}  c2m-m4-adb\n{mdigest}  manifest.json\n", encoding="ascii")
    assert {x.name for x in a.output.iterdir()} == {"c2m-m4-adb", "manifest.json", "SHA256SUMS.txt"}
    print(json.dumps({"verdict": "M4-ACTIVE-IDENTIFICATION-BUNDLE", "sha256": digest,
                      "source_commit": revision, "hardware_accepted": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
