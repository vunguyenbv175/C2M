#!/usr/bin/env python3
"""Host tests for the offline firmware pipeline (synthetic fixtures only).

No vendor firmware needed. Covers WS2/WS3 negative gates:
  - validator VALID-path is NOT asserted here on synthetic data (protected
    deep evidence unavailable by design -> INCOMPLETE_EVIDENCE);
  - every corruption fixture MUST yield INVALID (rc != 0);
  - repack --replace-payload MUST fail closed.

Run: python3 tests/test_firmware_pipeline.py
"""
from __future__ import annotations
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "fw"))


def sha256_bytes(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()


def build_synthetic(tmp: Path) -> tuple[Path, Path]:
    """Minimal package mirroring the EN layout (script + 2 payloads + FF pad + tail)."""
    payload_a = b"A" * 1024
    payload_b = b"B" * 2048
    script = (
        "\n# File Partition: cis.es\n"
        f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(len(payload_a))} 0x4000\n"
        "# File Partition: kernel.es\n"
        f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(len(payload_b))} 0x5000\n"
        "% <- this is end of script symbol"
    ).encode()
    script_end = len(script)
    total = 0x5000 + len(payload_b) + 24
    inner = bytearray(total)
    inner[:] = b"\xff" * total
    inner[:script_end] = script
    inner[script_end] = 0x0A
    inner[0x4000:0x4000 + len(payload_a)] = payload_a
    inner[0x5000:0x5000 + len(payload_b)] = payload_b
    tail = b"12345678\n# File Partitio"
    inner[0x5000 + len(payload_b):] = tail
    inner = bytes(inner)
    tar_path = tmp / "synth.tar"
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as t:
        for name, data in [
            ("SigmastarUpgradeSD_SSC8838G.bin", inner),
            ("sysVer.txt", b"sysVer 20230803193750\nend\n"),
            ("minieye_firmware.md5", (hashlib.md5(inner).hexdigest() + "  SigmastarUpgradeSD_SSC8838G.bin\n").encode()),
            ("adas_upgrade.sh", b"#!/bin/sh\necho hi\n"),
        ]:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mode = 0o775 if name.endswith(".sh") else 0o664
            ti.mtime = 1691062673
            t.addfile(ti, io.BytesIO(data))
    # minimal contract matching validator expectations
    contract = {
        "source_tar_sha256": sha256_bytes(tar_path.read_bytes()),
        "outer_order": ["SigmastarUpgradeSD_SSC8838G.bin", "sysVer.txt",
                        "minieye_firmware.md5", "adas_upgrade.sh"],
        "outer_members": [],
        "sysVer_txt": "sysVer 20230803193750\nend\n",
        "adas_upgrade_sh_sha256": sha256_bytes(b"#!/bin/sh\necho hi\n"),
        "upgrade_script_end": script_end,
        "upgrade_script_sha256": sha256_bytes(script),
        "loads": [
            {"section": "cis.es", "load_index": 0, "offset": 0x4000,
             "end": 0x4000 + len(payload_a), "size": len(payload_a),
             "offset_hex": hex(0x4000), "size_hex": hex(len(payload_a)),
             "sha256": sha256_bytes(payload_a), "within_image": True},
            {"section": "kernel.es", "load_index": 0, "offset": 0x5000,
             "end": 0x5000 + len(payload_b), "size": len(payload_b),
             "offset_hex": hex(0x5000), "size_hex": hex(len(payload_b)),
             "sha256": sha256_bytes(payload_b), "within_image": True},
        ],
        "inter_payload_gaps": [
            {"range": [script_end + 1, 0x4000]},
            {"range": [0x4000 + len(payload_a), 0x5000]},
        ],
        "tail_unknown": {"offset": 0x5000 + len(payload_b),
                         "len": len(tail), "hex": tail.hex()},
        "accounting": {"total": total, "check": True},
    }
    with tarfile.open(tar_path, "r") as tf:
        for m in tf.getmembers():
            blob = tf.extractfile(m).read()
            contract["outer_members"].append(
                {"name": m.name, "size": len(blob), "sha256": sha256_bytes(blob)})
    contract_path = tmp / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    return tar_path, contract_path


def run_validator(tar: Path, contract: Path, tmp: Path, extra: list[str] | None = None) -> tuple[int, dict]:
    rj, rm = tmp / "v.json", tmp / "v.md"
    cmd = [sys.executable, "tools/fw/validate_firmware.py", "--tar", str(tar),
           "--contract", str(contract), "--report-json", str(rj), "--report-md", str(rm)]
    if extra:
        cmd += extra
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    doc = json.loads(rj.read_text()) if rj.exists() else {}
    return r.returncode, doc


def mutate_tar_member(src: Path, dst: Path, member: str, new_data: bytes | None):
    """Replace (or drop with None) one member, keep the rest identical."""
    with tarfile.open(src, "r") as tf:
        members = tf.getmembers()
        blobs = {m.name: tf.extractfile(m).read() for m in members}
    if new_data is None:
        blobs.pop(member, None)
    else:
        blobs[member] = new_data
    with tarfile.open(dst, "w", format=tarfile.USTAR_FORMAT) as t:
        for m in members:
            if m.name not in blobs:
                continue
            ti = tarfile.TarInfo(m.name)
            ti.size = len(blobs[m.name])
            ti.mode = m.mode
            ti.mtime = m.mtime
            t.addfile(ti, io.BytesIO(blobs[m.name]))


def main() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tar, contract = build_synthetic(tmp)

        # 0. clean synthetic package: package-layer OK -> INCOMPLETE_EVIDENCE (no --deep)
        rc, doc = run_validator(tar, contract, tmp)
        if not (rc != 0 and doc.get("verdict") == "INCOMPLETE_EVIDENCE"):
            fails.append(f"clean synthetic: want INCOMPLETE_EVIDENCE rc!=0, got {doc.get('verdict')} rc={rc}")

        # 1. wrong MD5
        with tarfile.open(tar, "r") as tf:
            inner = tf.extractfile("SigmastarUpgradeSD_SSC8838G.bin").read()
        bad_md5 = b"0" * 32 + b"  SigmastarUpgradeSD_SSC8838G.bin\n"
        t1 = tmp / "bad_md5.tar"
        mutate_tar_member(tar, t1, "minieye_firmware.md5", bad_md5)
        rc, doc = run_validator(t1, contract, tmp)
        if not (rc != 0 and doc.get("verdict") == "INVALID"):
            fails.append("wrong-MD5 not INVALID")

        # 2. truncated upgrade image
        t2 = tmp / "trunc.tar"
        mutate_tar_member(tar, t2, "SigmastarUpgradeSD_SSC8838G.bin", inner[:0x4800])
        rc, doc = run_validator(t2, contract, tmp)
        if not (rc != 0 and doc.get("verdict") == "INVALID"):
            fails.append("truncated-image not INVALID")

        # 3. modified payload
        mod = bytearray(inner)
        mod[0x4000] ^= 0xFF
        t3 = tmp / "modpay.tar"
        mutate_tar_member(tar, t3, "SigmastarUpgradeSD_SSC8838G.bin", bytes(mod))
        rc, doc = run_validator(t3, contract, tmp)
        if not (rc != 0 and doc.get("verdict") == "INVALID"):
            fails.append("modified-payload not INVALID")

        # 4. invalid offset/length (tampered contract claims oversized load)
        c4 = json.loads(contract.read_text())
        c4["loads"][1]["end"] = 0x5000 + 2048 + 5000
        c4["loads"][1]["size"] = 2048 + 5000
        c4p = tmp / "contract_badlen.json"
        c4p.write_text(json.dumps(c4))
        rc, doc = run_validator(tar, c4p, tmp)
        if not (rc != 0 and doc.get("verdict") == "INVALID"):
            fails.append("invalid-offset/length not INVALID")

        # 5. missing TAR member
        t5 = tmp / "missing.tar"
        mutate_tar_member(tar, t5, "sysVer.txt", None)
        rc, doc = run_validator(t5, contract, tmp)
        if not (rc != 0 and doc.get("verdict") == "INVALID"):
            fails.append("missing-member not INVALID")

        # 6. protected-component modification proxy: payload flip must already be
        # INVALID (covered by #3); here assert the flip is caught at payload-sha row
        rc, doc = run_validator(t3, contract, tmp)
        badrows = [r for r in doc.get("checks", [])
                   if r["result"] == "FAIL" and "payload" in r["check"]]
        if not badrows:
            fails.append("payload-mod not attributed to payload-sha row")

        # 7. repack fail-closed on --replace-payload
        r = subprocess.run(
            [sys.executable, "tools/fw/repack_firmware.py", "--tar", str(tar),
             "--contract", str(contract), "--out", str(tmp / "x.tar"),
             "--report", str(tmp / "x.json"),
             "--replace-payload", "customer.es=/tmp/evil.bin"],
            cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("--replace-payload did not fail closed")

    if fails:
        print("FIRMWARE-PIPELINE TEST FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("firmware pipeline (synthetic): OK (6 corruptions INVALID + fail-closed override)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
