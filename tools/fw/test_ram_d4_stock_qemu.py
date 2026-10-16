#!/usr/bin/env python3
"""Exercise the exact updated ARM D4 producer under pinned stock userspace.

Synthetic DB/GPS paths only; no camera, UART, radio, private DB or real route.
The production binary runs in fixture mode, not with camera default paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time


def gps(second: int, raw: int) -> bytes:
    record = bytearray(0x1C0)
    fields = {0: 8, 4: 126, 8: 9, 12: 16, 16: 0, 20: 0,
              24: second, 28: raw, 32: 1, 36: 3}
    for offset, value in fields.items():
        struct.pack_into("<I", record, offset, value)
    for offset, value in {0x40: 1000.0, 0x48: 10600.0,
                          0x58: 36.0, 0x60: 90.0}.items():
        struct.pack_into("<d", record, offset, value)
    return bytes(0x330) + record


def db() -> bytes:
    row = struct.pack("<ddf", 10.0, 106.0013, 90.0)
    row += b"R.420\0".ljust(16, b"\0") + b"synthetic".ljust(64, b"\0")
    return b"C2MSDB01" + struct.pack("<I", 1) + row


def read_status(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except FileNotFoundError:
        return {}
    if len(lines) != 11 or any("=" not in row for row in lines):
        raise AssertionError("invalid producer status framing")
    rows = dict(row.split("=", 1) for row in lines)
    if len(rows) != 11:
        raise AssertionError("duplicate status keys")
    return rows


def wait_status(path: Path, predicate, timeout: float = 5) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = read_status(path)
        if status and predicate(status):
            return status
        time.sleep(0.05)
    raise AssertionError("expected synthetic producer state not reached: " +
                         json.dumps(read_status(path), sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--sysroot", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "posix":
        raise SystemExit("Linux/QEMU required; do not silently skip this gate")
    binary, sysroot = args.binary.resolve(), args.sysroot.resolve()
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise SystemExit("target must be an already ABI-gated ARM ELF")
    from prepare_ram_debug_sysroot import PINS, LINKS
    for name, expected in PINS.items():
        path = sysroot / "lib" / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit("stock runtime pin failed")
    for name, target in LINKS.items():
        path = sysroot / "lib" / name
        if not path.is_symlink() or os.readlink(path) != target:
            raise SystemExit("stock runtime symlink pin failed")
    binary_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
    qemu = shutil.which("qemu-arm-static")
    if not qemu:
        raise SystemExit("qemu-arm-static required")
    if os.geteuid() != 0:
        raise SystemExit("Run this synthetic QEMU fixture gate with sudo; /tmp trust policy requires root")
    # QEMU -L maps open("/") to the prefix; subsequent descriptor-relative
    # openat(dirfd, "tmp") cannot fall back to the host /tmp. Put fixtures
    # under an actual root-owned sticky prefix/tmp, not a symlink, without
    # weakening the production descriptor/owner checks to suit the host.
    os.chown(sysroot, 0, 0)
    sysroot.chmod(0o755)
    guest_tmp = sysroot / "tmp"
    if guest_tmp.is_symlink():
        raise SystemExit("QEMU fixture /tmp must not be a symlink")
    guest_tmp.mkdir(mode=0o1777, exist_ok=True)
    os.chown(guest_tmp, 0, 0)
    guest_tmp.chmod(0o1777)
    if guest_tmp.stat().st_uid != 0:
        raise SystemExit("QEMU fixture /tmp must be root owned")
    observations = []
    with tempfile.TemporaryDirectory(prefix="c2m-d4-arm-fixture-", dir=guest_tmp) as name:
        root = Path(name)
        root.chmod(0o700)
        guest_root = Path("/tmp") / root.name
        database, source, status = root / "synthetic.bin", root / "car_info", root / "status"
        database.write_bytes(db())
        database.chmod(0o600)

        def update(second, raw):
            temporary = root / "gps.next"
            temporary.write_bytes(gps(second, raw))
            temporary.chmod(0o600)
            os.replace(temporary, source)

        update(0, 100)
        command = [qemu, "-strace", "-L", str(sysroot), str(binary), "--serve",
                   "--db", str(guest_root / database.name), "--gps-file", str(guest_root / source.name),
                   "--status-file", str(guest_root / status.name)]
        trace_path = args.report.with_suffix(".strace.txt")
        trace = trace_path.open("wb")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=trace)
        try:
            wait_status(status, lambda s: s["state"] == "warming_up")
            observations.append("raw100_valid_warming_up")
            time.sleep(1)
            update(1, 200)
            ready = wait_status(status, lambda s: s["gps_fresh"] == "1")
            assert ready["state"] == "ready" and ready["active"] == "1"
            observations.append("advancing_second_raw200_ready_synthetic_advisory")
            # Repeated UTC second with rapidly changing fraction must still age
            # out. Use real monotonic elapsed time, not file mtime as freshness.
            deadline = time.monotonic() + 3.4
            raw = 300
            while time.monotonic() < deadline:
                update(1, raw)
                raw = 999 if raw != 999 else 300
                time.sleep(0.3)
            wait_status(status, lambda s: s["state"] == "stale" and s["gps_fresh"] == "0")
            observations.append("subsecond_only_churn_stale_no_active_advisory")
            # Invalid raw1000 cannot bypass decode, even on advancing UTC.
            update(2, 1000)
            baseline = int(read_status(status)["sequence"])
            invalid = wait_status(status, lambda s: int(s["sequence"]) > baseline and s["gps_fresh"] == "0")
            assert invalid["active"] == "0"
            observations.append("raw1000_invalid_fail_closed")
            update(3, 300)
            baseline = int(invalid["sequence"])
            wait_status(status, lambda s: int(s["sequence"]) > baseline and s["gps_fresh"] == "0")
            time.sleep(1)
            update(4, 999)
            wait_status(status, lambda s: s["gps_fresh"] == "1" and s["state"] == "ready")
            observations.append("valid300_then999_two_seconds_reacquire")
            if process.poll() is not None:
                raise AssertionError("producer exited unexpectedly")
        finally:
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)
                raise AssertionError("bounded SIGTERM did not stop producer")
            finally:
                trace.close()
                # Trace contains only synthetic fixture paths/data; no private
                # database, keys, firmware content or live camera coordinates.
                print(trace_path.read_text(errors="replace")[-24000:])
        assert process.returncode == 0, process.returncode
        assert not stdout, "unexpected producer output"
        stopped = read_status(status)
        assert stopped["state"] == "disabled" and stopped["active"] == "0"
        observations.append("SIGTERM_disabled_status_clean_exit")
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == binary_sha256
    report = {"verdict": "PASS", "runtime": "exact ARM ELF plus stock loader/glibc under QEMU",
              "binary_sha256": binary_sha256, "stock_runtime_sha256": PINS,
              "fixtures": "synthetic only", "checks": observations,
              "camera_used": False, "radio_used": False, "private_database_used": False,
              "target_device_accepted": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
