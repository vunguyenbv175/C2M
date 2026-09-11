#!/usr/bin/env python3
"""Local CI mirror (Windows-friendly): header self-containment + cmake + all py tests.

Usage: python3 tools/ci/local_ci.py  (needs g++ + cmake on PATH after WinLibs install)
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
failed: list[str] = []


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
    headers = sorted(ROOT.glob("include/**/*.hpp"))
    print(f"headers: {len(headers)}")
    if shutil.which("g++"):
        for h in headers:
            run(["g++", "-std=c++17", "-fsyntax-only", "-I", "include", "-x", "c++", str(h)],
                f"header {h.relative_to(ROOT)}")
    else:
        print("SKIP header checks (no g++)")
    if shutil.which("cmake"):
        run(["cmake", "-S", ".", "-B", "build/host-ci", "-G", "MinGW Makefiles"], "cmake-configure")
        run(["cmake", "--build", "build/host-ci"], "cmake-build")
        run(["ctest", "--test-dir", "build/host-ci", "--output-on-failure"], "ctest")
    else:
        print("SKIP cmake (not installed)")
    py = sys.executable
    for t in ["tools/m4/test_protocol.py", "tools/m4/test_normalize_adas.py",
              "tools/m4/test_m4_policy.py", "tools/m4/test_real_data_path.py",
              "tools/road/test_road.py"]:
        run([py, t], t)
    run([py, "tools/m4/make_fixture.py"], "make_fixture")
    print("FAILED:", failed if failed else "none")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
