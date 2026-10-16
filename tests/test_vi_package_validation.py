#!/usr/bin/env python3
"""VI base-profile validation tests (full-VI D5 variant gates).

Portable synthetic checks always run (no vendor firmware needed):
  - EN default pins are unchanged;
  - VI pins are hardcoded from the exact trusted VI TAR extraction
    (never caller-supplied);
  - no arbitrary protected-hash override flags exist on either tool;
  - --base-profile defaults to en; --base-tar/--en-tar are exclusive;
  - synthetic packages cannot self-bless under either profile.

Read-only real-VI check (skipped when the VI TAR is absent):
  - verifies the local VI TAR SHA-256 pin first (trust gate);
  - derives a VI contract into a PRIVATE temp dir only (never docs/,
    because package_contract output embeds vendor upgrade_script_text
    and raw tail bytes);
  - `validate --deep --base-profile vi` must be VALID;
  - `validate --deep` with the default en profile must be INVALID
    (profiles cannot cross-bless).

Run: python3 tests/test_vi_package_validation.py
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

import validate_firmware as VF

VI_TAR_REL = Path("firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar")

EN_CARDV = "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c"
EN_ADAS = "0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043"
VI_CARDV = "56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23"
VI_ADAS = "997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1"
VI_TAR = "f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa"


def sha256_bytes(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()


def build_synthetic(tmp: Path) -> tuple[Path, Path]:
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
    tar_path = tmp / "synth_vi.tar"
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as t:
        for name, data in [
            ("SigmastarUpgradeSD_SSC8838G.bin", inner),
            ("sysVer.txt", b"sysVer 20230920185743\nend\n"),
            ("minieye_firmware.md5", (hashlib.md5(inner).hexdigest() + "  SigmastarUpgradeSD_SSC8838G.bin\n").encode()),
            ("adas_upgrade.sh", b"#!/bin/sh\necho hi\n"),
        ]:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mode = 0o775 if name.endswith(".sh") else 0o664
            ti.mtime = 1695060000
            t.addfile(ti, io.BytesIO(data))
    contract = {
        "source_tar_sha256": sha256_bytes(tar_path.read_bytes()),
        "outer_order": ["SigmastarUpgradeSD_SSC8838G.bin", "sysVer.txt",
                        "minieye_firmware.md5", "adas_upgrade.sh"],
        "outer_members": [],
        "sysVer_txt": "sysVer 20230920185743\nend\n",
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
    contract_path = tmp / "synth_contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    return tar_path, contract_path


def run_validator(tar: Path, contract: Path, tmp: Path, name: str,
                  extra: list[str] | None = None, timeout: int = 120) -> tuple[int, dict]:
    rj, rm = tmp / f"{name}.json", tmp / f"{name}.md"
    cmd = [sys.executable, "tools/fw/validate_firmware.py", "--tar", str(tar),
           "--contract", str(contract), "--report-json", str(rj),
           "--report-md", str(rm)]
    if extra:
        cmd += extra
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    doc = json.loads(rj.read_text()) if rj.exists() else {}
    return r.returncode, doc


def main() -> int:
    fails: list[str] = []

    # 1. EN default pins unchanged (backward compatible).
    if VF.PROTECTED != {"cardv_sha256": EN_CARDV, "adas_sha256": EN_ADAS}:
        fails.append("legacy PROTECTED is not the exact EN baseline")
    if VF.PROTECTED_EN != VF.PROTECTED:
        fails.append("PROTECTED_EN diverged from legacy PROTECTED")

    # 2. VI pins hardcoded from the trusted VI TAR extraction.
    if VF.VI_TAR_SHA256 != VI_TAR:
        fails.append("VI_TAR_SHA256 pin mismatch")
    if VF.PROTECTED_VI != {"cardv_sha256": VI_CARDV, "adas_sha256": VI_ADAS}:
        fails.append("PROTECTED_VI is not the extraction-derived VI pins")
    if VF.PROTECTED_VI == VF.PROTECTED_EN:
        fails.append("VI pins equal EN pins (profiles would cross-bless)")

    # 3. Pure profile selection; unknown profiles fail closed.
    try:
        if VF.protected_for_profile("en") != VF.PROTECTED_EN:
            fails.append("protected_for_profile('en') mismatch")
        if VF.protected_for_profile("vi") != VF.PROTECTED_VI:
            fails.append("protected_for_profile('vi') mismatch")
        try:
            VF.protected_for_profile("evil")
            fails.append("protected_for_profile accepted an unknown profile")
        except ValueError:
            pass
    except Exception as exc:
        fails.append(f"protected_for_profile raised unexpectedly: {exc}")

    # 4. No arbitrary hash-override flags; --base-profile exists on both tools.
    for tool in ("tools/fw/validate_firmware.py", "tools/fw/build_candidates.py"):
        r = subprocess.run([sys.executable, tool, "--help"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        out = r.stdout + r.stderr
        if "--base-profile" not in out:
            fails.append(f"{tool}: --base-profile missing from --help")
        for bad in ("--cardv-sha", "--adas-sha", "--protected", "--override"):
            if bad in out:
                fails.append(f"{tool}: forbidden override flag present: {bad}")
    help_bc = subprocess.run([sys.executable, "tools/fw/build_candidates.py", "--help"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
    if "--base-tar" not in help_bc or "--en-tar" not in help_bc:
        fails.append("build_candidates: --base-tar/--en-tar pair missing")

    # 5. --en-tar and --base-tar are mutually exclusive (fast argparse fail).
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        r = subprocess.run(
            [sys.executable, "tools/fw/build_candidates.py",
             "--en-tar", "a.tar", "--base-tar", "b.tar",
             "--workdir", str(tmp / "wd")],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            fails.append("--en-tar + --base-tar together did not fail")

    # 6. Synthetic packages cannot self-bless under either profile.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tar, contract = build_synthetic(tmp)
        for profile, extra in (("en", []), ("vi", ["--base-profile", "vi"])):
            rc, doc = run_validator(tar, contract, tmp, f"synth_{profile}", extra)
            if not (rc != 0 and doc.get("verdict") == "INCOMPLETE_EVIDENCE"):
                fails.append(f"synthetic {profile} w/o --deep: want "
                             f"INCOMPLETE_EVIDENCE, got {doc.get('verdict')} rc={rc}")
        # With --deep the synthetic payloads are not real cardv/adas, so
        # protected rows must FAIL under both profiles (no self-bless).
        for profile, extra in (("en", ["--deep"]), ("vi", ["--deep", "--base-profile", "vi"])):
            rc, doc = run_validator(tar, contract, tmp, f"synth_deep_{profile}", extra)
            if doc.get("verdict") == "VALID":
                fails.append(f"synthetic {profile} --deep unexpectedly VALID")
            prot_fails = [c for c in doc.get("checks", [])
                          if c["check"].startswith("protected.") and c["result"] == "FAIL"]
            if not prot_fails:
                fails.append(f"synthetic {profile} --deep: no protected FAIL rows")

    # 7. Read-only real-VI check (skipped when the VI TAR is absent).
    vi_tar = ROOT / VI_TAR_REL
    if not vi_tar.is_file():
        print("SKIP: real-VI deep check (VI TAR absent)")
    else:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            actual = sha256_bytes(vi_tar.read_bytes())
            if actual != VI_TAR:
                fails.append(f"local VI TAR pin mismatch: got {actual[:16]}…")
            else:
                # Private VI contract only (embeds vendor script/tail bytes).
                vc_json, vc_md = tmp / "vi_contract.json", tmp / "vi_contract.md"
                r = subprocess.run(
                    [sys.executable, "tools/fw/package_contract.py",
                     "--tar", str(VI_TAR_REL),
                     "--out-json", str(vc_json), "--out-md", str(vc_md)],
                    cwd=ROOT, capture_output=True, text=True, timeout=180)
                if r.returncode != 0:
                    fails.append(f"private VI contract derivation failed: {r.stderr[-500:]}")
                else:
                    rc, doc = run_validator(vi_tar, vc_json, tmp, "vi_real_vi",
                                            ["--deep", "--base-profile", "vi"], timeout=300)
                    if not (rc == 0 and doc.get("verdict") == "VALID"):
                        fails.append(f"real VI --deep --base-profile vi: want VALID, "
                                     f"got {doc.get('verdict')} rc={rc}")
                    elif doc.get("base_profile") != "vi":
                        fails.append("real VI report missing base_profile=vi")
                    elif doc.get("protected_golden", {}).get("adas_sha256") != VI_ADAS:
                        fails.append("real VI report protected_golden mismatch")
                    # Default en profile must NOT bless the VI image.
                    rc2, doc2 = run_validator(vi_tar, vc_json, tmp, "vi_real_en",
                                              ["--deep"], timeout=300)
                    if doc2.get("verdict") == "VALID":
                        fails.append("real VI image VALID under default en profile "
                                     "(cross-bless)")
                    if not [c for c in doc2.get("checks", [])
                            if c["check"].startswith("protected.") and c["result"] == "FAIL"]:
                        fails.append("real VI under en profile: no protected FAIL rows")
        if list((ROOT / "docs" / "firmware").glob("VI_PACKAGE_CONTRACT*")):
            fails.append("VI contract leaked into docs/firmware (must stay in build/work)")

    if fails:
        print("VI-PACKAGE-VALIDATION FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("vi package validation: OK (synthetic gates + hardcoded pins, "
          "real-VI checked when present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
