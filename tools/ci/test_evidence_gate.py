#!/usr/bin/env python3
"""Negative gate tests for tools/ci/verify_evidence.py (review R1-new acceptance).

Each induced failure MUST return nonzero:
  1. missing EN TAR
  2. wrong EN SHA (tampered copy)
  3. LZO extraction failure (truncated customer image via tampered TAR)
  4. schema generator failure (staged build missing inputs)
  5. modified canonical JSON (drift)

Slow/local-only: needs the real 55MB TARs + LZO route. NOT part of product CI.
Usage: python3 tools/ci/test_evidence_gate.py
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TMP = ROOT / "build" / "gate_neg"
EN_TAR = ROOT / "firmware" / "original" / "V2023.08.03.1_C2M_U_FR_WIFI_EN.tar"
VI_TAR = ROOT / "firmware" / "original" / "V2023.09.20.1_C2M_U_FR_WIFI_VI.tar"
INNER = "SigmastarUpgradeSD_SSC8838G.bin"


def run_verify(en_tar: Path, vi_tar: Path, canon: Path, tag: str) -> int:
    wd = TMP / f"wd_{tag}"
    od = TMP / f"out_{tag}"
    shutil.rmtree(wd, ignore_errors=True)
    shutil.rmtree(od, ignore_errors=True)
    r = subprocess.run(
        [sys.executable, "tools/ci/verify_evidence.py", "--en-tar", str(en_tar),
         "--vi-tar", str(vi_tar), "--workdir", str(wd), "--out-dir", str(od),
         "--canonical-dir", str(canon)],
        cwd=ROOT, capture_output=True, text=True)
    print(f"[{tag}] rc={r.returncode}")
    tail = (r.stdout + r.stderr)[-800:]
    if r.returncode == 0:
        print(tail)
    return r.returncode


def tamper_tar_byte(src: Path, dst: Path, offset: int = 6000000):
    data = bytearray(src.read_bytes())
    data[offset] ^= 0xFF
    dst.write_bytes(data)


def main() -> int:
    if not EN_TAR.is_file() or not VI_TAR.is_file():
        print("SKIP: original TARs absent (gate tests need firmware/original/)")
        return 0
    TMP.mkdir(parents=True, exist_ok=True)
    fails = []

    # 1. missing EN TAR
    rc = run_verify(TMP / "nope.tar", VI_TAR, ROOT / "docs" / "reverse", "missing-tar")
    fails += [] if rc != 0 else ["missing-tar returned 0"]

    # 2. wrong EN SHA
    bad_en = TMP / "en_badsha.tar"
    tamper_tar_byte(EN_TAR, bad_en)
    rc = run_verify(bad_en, VI_TAR, ROOT / "docs" / "reverse", "bad-sha")
    fails += [] if rc != 0 else ["bad-sha returned 0"]

    # 3. extraction failure: valid TAR container, truncated inner image
    trunc = TMP / "en_trunc.tar"
    with tarfile.open(EN_TAR, "r") as tin:
        member = tin.getmember(INNER)
        f = tin.extractfile(member)
        assert f is not None
        blob = f.read(len_trunc := 30_000_000)
    with tarfile.open(trunc, "w") as tout:
        import io
        ti = tarfile.TarInfo(INNER)
        ti.size = len(blob)
        tout.addfile(ti, io.BytesIO(blob))
    rc = run_verify(trunc, VI_TAR, ROOT / "docs" / "reverse", "trunc-image")
    fails += [] if rc != 0 else ["trunc-image returned 0"]

    # 4. generator failure: point verifier at empty staged inputs is internal;
    # direct equivalent: schema generator with missing build-dir must fail.
    r = subprocess.run(
        [sys.executable, "tools/fw/stock_adas_schema_v2.py", "--build-dir",
         str(TMP / "empty_build"), "-o", str(TMP / "x.json")],
        cwd=ROOT, capture_output=True, text=True)
    print(f"[gen-fail] rc={r.returncode}")
    fails += [] if r.returncode != 0 else ["generator with missing inputs returned 0"]

    # 5. drift: tampered canonical copy must trip the verifier (needs full chain;
    # reuse the happy-path out-dir by running verify once against real canon
    # only if fast... instead: tamper canon + run full chain).
    tamper_canon = TMP / "canon_tampered"
    shutil.rmtree(tamper_canon, ignore_errors=True)
    shutil.copytree(ROOT / "docs" / "reverse", tamper_canon)
    p = tamper_canon / "EVIDENCE_STOCK_ADAS_SCHEMA.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["fields"][0]["verdict"] = "TOTALLY-MADE-UP"
    p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    rc = run_verify(EN_TAR, VI_TAR, tamper_canon, "drift")
    fails += [] if rc != 0 else ["drift returned 0"]

    if fails:
        print("GATE-TEST FAILURES:", fails)
        return 1
    print("evidence gate negatives: OK (all 5 induced failures returned nonzero)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
