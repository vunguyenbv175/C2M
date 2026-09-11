#!/usr/bin/env python3
"""Local CI mirror (Windows-friendly): header self-containment + cmake + all py tests.

Usage:
  python3 tools/ci/local_ci.py [--strict] [--evidence]
  --strict: missing g++/cmake is a FAILURE (default: SKIP with warning).
  --evidence: also regenerate firmware evidence (needs TARs in firmware/original/
    plus build/ extraction inputs) and diff vs committed canonical JSON.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
failed: list[str] = []
STRICT = False


def run(cmd: list[str], what: str):
    print(f"### {what}: {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        failed.append(what)
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
    else:
        print(f"OK {what}")


def main() -> int:
    global STRICT
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--evidence", action="store_true")
    args = ap.parse_args()
    STRICT = args.strict

    headers = sorted(ROOT.glob("include/**/*.hpp"))
    print(f"headers: {len(headers)}")
    if shutil.which("g++"):
        for h in headers:
            run(["g++", "-std=c++17", "-fsyntax-only", "-I", "include", "-x", "c++", str(h)],
                f"header {h.relative_to(ROOT)}")
    elif STRICT:
        failed.append("toolchain-g++-missing(strict)")
        print("FAIL: g++ missing in --strict mode")
    else:
        print("SKIP header checks (no g++; use --strict to fail)")
    if shutil.which("cmake"):
        run(["cmake", "-S", ".", "-B", "build/host-ci", "-G", "MinGW Makefiles"], "cmake-configure")
        run(["cmake", "--build", "build/host-ci"], "cmake-build")
        run(["ctest", "--test-dir", "build/host-ci", "--output-on-failure"], "ctest")
    elif STRICT:
        failed.append("toolchain-cmake-missing(strict)")
        print("FAIL: cmake missing in --strict mode")
    else:
        print("SKIP cmake (not installed; use --strict to fail)")
    py = sys.executable
    for t in ["tools/m4/test_protocol.py", "tools/m4/test_normalize_adas.py",
              "tools/m4/test_m4_policy.py", "tools/m4/test_real_data_path.py",
              "tools/road/test_road.py", "tests/test_firmware_pipeline.py",
              "fw/device_minimal/test_check_elf.py", "tests/test_candidate_b.py"]:
        run([py, t], t)
    run([py, "tools/m4/make_fixture.py"], "make_fixture")
    if args.evidence:
        run([py, "tools/fw/stock_adas_schema_v2.py"], "evidence-regen")
        r = subprocess.run(["git", "diff", "--exit-code",
                            "docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json"],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            failed.append("evidence-drift")
            print("evidence JSON drifted vs canonical — review required")
        else:
            print("OK evidence-no-drift")
    print("FAILED:", failed if failed else "none")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
