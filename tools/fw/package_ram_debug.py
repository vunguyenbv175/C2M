#!/usr/bin/env python3
"""Package only newly built owner-private RAM diagnostics, never an updater."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ("c2m-signs", "c2m-nlprobe", "c2m-gps-probe")


def checked_elf(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("binary must be a regular file")
    data = path.read_bytes()
    if not 52 <= len(data) <= 4 * 1024 * 1024:
        raise ValueError("unexpected diagnostic binary size")
    if data[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", data, 18)[0] != 40:
        raise ValueError("expected little-endian ELF32 ARM")
    if struct.unpack_from("<H", data, 16)[0] != 2:
        raise ValueError("expected no-PIE executable")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--d4", required=True, type=Path)
    parser.add_argument("--nlprobe", required=True, type=Path)
    parser.add_argument("--gps-probe", required=True, type=Path)
    parser.add_argument("--d4-shadow", type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refuse existing bundle output")
    paths = [args.d4, args.nlprobe, args.gps_probe]
    names = list(EXPECTED)
    if args.d4_shadow is not None:
        paths.append(args.d4_shadow)
        names.append("c2m-d4-shadow")
    binaries = {name: checked_elf(path) for name, path in zip(names, paths)}
    runtime = json.loads((args.evidence / "arm-d4-producer-runtime.json").read_text())
    from prepare_ram_debug_sysroot import PINS
    if (runtime.get("verdict") != "PASS" or runtime.get("camera_used") is not False or
            runtime.get("binary_sha256") != hashlib.sha256(binaries["c2m-signs"]).hexdigest() or
            runtime.get("stock_runtime_sha256") != PINS):
        raise SystemExit("Mandatory actual ARM producer runtime proof/pins missing")
    shadow_runtime = None
    if args.d4_shadow is not None:
        shadow_runtime = json.loads((args.evidence / "arm-d4-shadow-runtime.json").read_text())
        if (shadow_runtime.get("verdict") != "PASS" or
                shadow_runtime.get("binary_sha256") != hashlib.sha256(binaries["c2m-d4-shadow"]).hexdigest() or
                shadow_runtime.get("stock_runtime_sha256") != PINS or
                shadow_runtime.get("status_writer") is not False or
                shadow_runtime.get("finite_samples") != 10 or
                shadow_runtime.get("camera_used") is not False):
            raise SystemExit("Mandatory exact shadow ARM runtime proof/pins missing")
    for path in paths:
        subprocess.run(["python3", "fw/device_minimal/check_elf.py", str(path),
                        "--allow-dynamic"], cwd=ROOT, check=True, timeout=30)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if revision != os.environ.get("GITHUB_SHA", revision):
        raise SystemExit("workflow/source revision mismatch")
    tracked = subprocess.check_output(["git", "ls-files", "-z", "fw/d3/gps_snapshot.c",
        "fw/d3/gps_snapshot.h", "fw/d3/compat.h", "fw/device_minimal/start.S",
        "fw/device_minimal/check_elf.py", "fw/d4", "fw/warner/db.c",
        "fw/warner/db.h", "fw/warner/warner.c", "fw/warner/warner.h", "tools/wifi",
        "tools/gps", "tools/fw/prepare_ram_debug_sysroot.py",
        "tools/fw/carve_upgrade.py", "tools/fw/extract_rootfs_cpio.py",
        "tools/fw/test_ram_d4_stock_qemu.py", "tools/fw/test_ram_shadow_stock_qemu.py",
        "tools/fw/package_ram_debug.py",
        ".github/workflows/ram-debug-arm.yml"], cwd=ROOT).decode().split("\0")
    source_pins = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in tracked if name}
    manifest = {
        "schema": 1, "kind": "OWNER-PRIVATE-RAM-ONLY-NOT-FIRMWARE-UPDATER",
        "source_commit": revision, "github_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "sha256": {name: hashlib.sha256(blob).hexdigest() for name, blob in binaries.items()},
        "bytes": {name: len(blob) for name, blob in binaries.items()},
        "source_sha256": source_pins, "stock_qemu_d4_producer": "PASS",
        "stock_qemu_d4_shadow": "PASS" if shadow_runtime is not None else "NOT-INCLUDED",
        "native_elf_hardware_executed": False, "camera_used": False,
        "radio_used": False, "firmware_package_created": False,
        "private_database_included": False, "keys_included": False,
        "hardware_requirements": ["owner stationary; recording/app/audio healthy",
            "bound source IP; exact UUID; pinned host key; finite SSH window",
            "fresh private RAM directory; size/hash before execution; timeout/nice; cleanup",
            "read-only observers first; do not replace installed D4 producer without separate plan"],
    }
    args.output.mkdir(parents=True)
    for name, blob in binaries.items():
        (args.output / name).write_bytes(blob)
        (args.output / name).chmod(0o700)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sums = "".join(f"{digest}  {name}\n" for name, digest in manifest["sha256"].items())
    sums += hashlib.sha256((args.output / "manifest.json").read_bytes()).hexdigest() + "  manifest.json\n"
    (args.output / "SHA256SUMS.txt").write_text(sums, encoding="ascii")
    if {p.name for p in args.output.iterdir()} != set(names) | {"manifest.json", "SHA256SUMS.txt"}:
        raise SystemExit("Unexpected bundle member")
    print(json.dumps({"verdict": "RAM-ONLY-BUNDLE", "source_commit": revision,
                      "sha256": manifest["sha256"], "hardware_accepted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
