#!/usr/bin/env python3
"""Host behavioral tests for c2m-idle SD diagnostics (no ARM toolchain needed).

Compiles fw/device_minimal/c2m_idle.c with the host C compiler, overriding
paths/timing via -D macros, then runs the daemon briefly and asserts:
  1. stdout prints the version; /tmp-equivalent marker file has exact bytes.
  2. diag dir gains boot.seq + boot-<i>.log with START (version/pid/boot-id/
     uptime/marker) and at least one HEARTBEAT; second run increments seq.
  3. per-file byte cap is honored (tiny cap override -> small file, daemon
     still alive and printing).
  4. fail-safe: unwritable diag dir (a regular file) -> daemon still prints
     version + writes marker (diag silently disabled, stock loop unaffected).
Fail-closed: missing compiler or any assertion failure exits nonzero.
Run: python3 fw/device_minimal/test_sdlog.py
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "fw" / "device_minimal" / "c2m_idle.c"
VER = "test-sdlog-1"


def need_cc() -> str:
    for c in ("gcc", "cc"):
        if shutil.which(c):
            return c
    print("FAIL: no host C compiler (gcc/cc) for sdlog behavioral test")
    return ""


def build(tmp: Path, cc: str, tag: str, extra: list[str]) -> Path:
    out = tmp / f"idle_{tag}{'.exe' if os.name == 'nt' else ''}"
    diag = tmp / f"diag_{tag}"
    mk = tmp / f"marker_{tag}"
    bootid = tmp / f"bootid_{tag}"
    uptime = tmp / f"uptime_{tag}"
    bootid.write_text("abcdef12-3456-7890-abcd-ef1234567890\n")
    uptime.write_text("100.25 50.10\n")
    defs = [
        f'-DC2M_IDLE_VERSION="{VER}"',
        f'-DC2M_DIAG_DIR="{diag.as_posix()}"',
        f'-DC2M_MARKER_PATH="{mk.as_posix()}"',
        f'-DC2M_BOOTID_PATH="{bootid.as_posix()}"',
        f'-DC2M_UPTIME_PATH="{uptime.as_posix()}"',
        "-DC2M_SLEEP_SEC=1",
        "-DC2M_BEAT_EVERY=2",
        *extra,
    ]
    r = subprocess.run([cc, "-O2", "-Wall", "-Wextra", str(SRC), "-o", str(out), *defs],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"compile failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    return out


def run_brief(exe: Path, secs: float) -> str:
    p = subprocess.Popen([str(exe)], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    try:
        p.wait(timeout=secs)
        out = p.stdout.read() if p.stdout else ""
    except subprocess.TimeoutExpired:
        p.terminate()
        try:
            out, _ = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
    return out or ""


def main() -> int:
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = ""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
        if not ok:
            fails.append(name)

    cc = need_cc()
    if not cc:
        return 1
    assert SRC.is_file(), "c2m_idle.c missing"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1+2. normal run: version, marker, START + heartbeat, seq ring.
        exe = build(tmp, cc, "a", [])
        out = run_brief(exe, 6.0)
        diag = tmp / "diag_a"
        mk = tmp / "marker_a"
        check("stdout.version", f"c2m-idle {VER}" in out, f"(got {out.strip()[:60]!r})")
        check("marker.bytes", mk.is_file() and mk.read_text() == f"c2m-idle {VER}\n")
        logs = sorted(diag.glob("boot-*.log")) if diag.is_dir() else []
        check("diag.one-log", len(logs) == 1, f"(logs={len(logs)})")
        body = logs[0].read_text() if logs else ""
        check("diag.start", body.startswith(f"START v={VER} pid=") and
              "boot=abcdef12" in body and "uptime=100" in body and
              "marker=ok" in body, f"(head={body[:110]!r})")
        check("diag.heartbeat", "\nHB uptime=100 n=" in body, "(BEAT_EVERY=2, ~6s run)")
        seqf = diag / "boot.seq"
        check("diag.seq1", seqf.is_file() and seqf.read_text().strip() == "1")
        out2 = run_brief(exe, 3.0)
        check("diag.seq2", seqf.read_text().strip() == "2")
        check("diag.two-logs", len(sorted(diag.glob("boot-*.log"))) == 2)
        check("diag.second-run-alive", f"c2m-idle {VER}" in out2)

        # 3. byte cap honored, daemon unaffected.
        exe_c = build(tmp, cc, "c", ["-DC2M_DIAG_CAP_BYTES=150"])
        run_brief(exe_c, 5.0)
        clog = next(iter((tmp / "diag_c").glob("boot-*.log")), None)
        check("cap.file-small", clog is not None and clog.stat().st_size < 600,
              f"(size={clog.stat().st_size if clog else 'MISSING'})")
        check("cap.marker-still-ok", (tmp / "marker_c").read_text() == f"c2m-idle {VER}\n")

        # 4. fail-safe: diag path blocked by a regular file.
        blocker = tmp / "blocked"
        blocker.write_text("x")
        exe_f = build(tmp, cc, "f", [f'-DC2M_DIAG_DIR="{blocker.as_posix()}"'])
        outf = run_brief(exe_f, 3.0)
        check("fail.version", f"c2m-idle {VER}" in outf)
        check("fail.marker", (tmp / "marker_f").is_file())

    if fails:
        print(f"SDLOG HOST FAILURES: {fails}")
        return 1
    print("sdlog host: OK (version/marker/START+heartbeat/seq/cap/fail-safe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
