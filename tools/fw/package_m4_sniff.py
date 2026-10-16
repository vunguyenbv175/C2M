#!/usr/bin/env python3
"""Package only the newly built M4 usb0 observer, never an updater."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def checked_elf(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("binary must be a regular file")
    data = path.read_bytes()
    if not 512 <= len(data) <= 512 * 1024:
        raise ValueError("unexpected sniffer binary size")
    if data[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 40:
        raise ValueError("expected little-endian ELF32 ARM")
    if struct.unpack_from("<H", data, 16)[0] != 2:
        raise ValueError("expected no-PIE executable")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sniff", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refuse existing bundle output")
    blob = checked_elf(args.sniff)
    runtime = json.loads((args.evidence / "arm-m4-sniff-runtime.json").read_text())
    from prepare_ram_debug_sysroot import PINS
    if (runtime.get("verdict") != "PASS" or runtime.get("camera_used") is not False or
            runtime.get("binary_sha256") != hashlib.sha256(blob).hexdigest() or
            runtime.get("stock_runtime_sha256") != PINS or
            runtime.get("status_writer") is not False or
            runtime.get("transmit") is not False or
            runtime.get("sniff_schema") != "observer_v1"):
        raise SystemExit("Mandatory M4 sniff ARM runtime proof/pins missing")
    subprocess.run(["python3", "fw/device_minimal/check_elf.py", str(args.sniff),
                    "--allow-dynamic"], cwd=ROOT, check=True, timeout=30)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != os.environ.get("GITHUB_SHA", revision):
        raise SystemExit("workflow/source revision mismatch")
    tracked = subprocess.check_output(["git", "ls-files", "-z", "fw/m4_sniff/m4_usb_observe.c",
        "fw/m4_sniff/build_arm.sh", "fw/device_minimal/start.S",
        "fw/device_minimal/check_elf.py", "fw/d3/compat.h",
        "tools/fw/test_ram_m4_sniff_stock_qemu.py", "tools/fw/package_m4_sniff.py",
        "tests/test_m4_sniff.py",
        ".github/workflows/ram-debug-arm.yml"], cwd=ROOT).decode().split("\0")
    source_pins = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in tracked if name}
    manifest = {
        "schema": 1, "kind": "OWNER-PRIVATE-RAM-ONLY-NOT-FIRMWARE-UPDATER",
        "asset": "c2m-m4-sniff",
        "source_commit": revision, "github_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "sha256": {"c2m-m4-sniff": hashlib.sha256(blob).hexdigest()},
        "bytes": {"c2m-m4-sniff": len(blob)},
        "source_sha256": source_pins, "stock_qemu_m4_sniff": "PASS",
        "native_elf_hardware_executed": False, "camera_used": False,
        "radio_used": False, "firmware_package_created": False,
        "private_database_included": False, "keys_included": False,
        "hardware_requirements": ["owner stationary; recording/app/audio healthy",
            "bound source IP; exact UUID; pinned host key; finite SSH window",
            "fresh private RAM directory; size/hash before execution; timeout/nice; cleanup",
            "read-only observers first; never open second cardv :8080 client; never transmit"],
    }
    args.output.mkdir(parents=True)
    (args.output / "c2m-m4-sniff").write_bytes(blob)
    (args.output / "c2m-m4-sniff").chmod(0o700)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sums = "".join(f"{digest}  {name}\n" for name, digest in manifest["sha256"].items())
    sums += hashlib.sha256((args.output / "manifest.json").read_bytes()).hexdigest() + "  manifest.json\n"
    (args.output / "SHA256SUMS.txt").write_text(sums, encoding="ascii")
    if {p.name for p in args.output.iterdir()} != {"c2m-m4-sniff", "manifest.json", "SHA256SUMS.txt"}:
        raise SystemExit("Unexpected bundle member")
    print(json.dumps({"verdict": "RAM-ONLY-M4-SNIFF-BUNDLE", "source_commit": revision,
                      "sha256": manifest["sha256"], "hardware_accepted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
