# C2M Pre-Hardware Pack Dry-Run V1 — offline self-test report

**Date:** 2026-09-11. **No hardware used. No firmware modified. No Candidate A/B/C touched.**
**Scope:** bug-find-and-fix in scripts/runbooks/gates only. No features, no new reverse-engineering, no SDK hunting.
**Runner:** `sh tools/device/selftest_pre_hardware_pack.sh` → `RESULT pass=31 fail=0 skip=0` (exit 0).

## 1. Tests executed (PASS/FAIL table)

| # | Area | Test | Result |
|---|---|---|---|
| 1 | Gates | template parses, schema + pristine NOT_RUN | PASS |
| 2 | Shell | `sh -n` clean on all pack scripts | PASS |
| 3 | Python | `py_compile` clean on all pack tools | PASS |
| 4 | Gates | fresh → `recovery_ready` next | PASS |
| 5 | Gates | `recovery_ready=FAIL` → STOP, A never suggested | PASS |
| 6 | Gates | `recovery_ready=PASS` → A allowed | PASS |
| 7 | Gates | `candidate_a_pass=FAIL` → STOP, B blocked | PASS |
| 8 | Gates | pre-coexist → `ipu_safe_pass` next; BLOCKED safe → coexist STOP | PASS |
| 9 | Gates | STOP_DAY sentinel halts all progression | PASS |
| 10 | Gates | template-path record refused; start.json record refused | PASS |
| 11 | Gates | template JSON byte-identical before/after | PASS |
| 12 | Hash | 4/4 nested files hashed incl. space-path | PASS |
| 13 | Hash | SHA256SUMS self-excluded; `sha256sum -c` 4/4 | PASS |
| 14 | Hash | deterministic rerun; valid tar; sources unmodified | PASS |
| 15 | Docs | 18 script refs in hardware docs, 0 dangling | PASS |
| 16 | IPU | probe-only rc=0; single-invoke rc=4; usage rc=2 (`-Wall -Werror` clean) | PASS |
| 17 | Python | test_candidate_b / test_firmware_pipeline / test_classify_adas_state OK | PASS |
| 18 | Python | onnx audit fail-closed rc=3 (no onnx lib, no crash) | PASS |
| 19 | Python | compare_c2m_runtime_capture synthetic + empty-dir tolerance | PASS |
| 20 | Python | compare_mi_ipu_api 11/0/0; fingerprint metadata-only JSON | PASS |
| 21 | Python | promax parser (WRITE_REQ/NOTIFY/interval) + correlator never-PROVEN | PASS |
| 22 | Repo | `git diff --check` clean | PASS |

`simplify: 31 sub-checks total (gate block counts individually), 0 fail, 0 skip.`

## 2. Bugs found → fixes made (5 files, all in pack scripts)

1. **SHA256SUMS hashed itself** (`capture_c2m_m4_runtime.sh`, `capture_c2m_ipu_baseline.sh`,
   `capture_c2m_media_topology.sh`): `find` lacked the `! -name 'SHA256SUMS.txt'` exclusion the
   wrapper already had → checksum file contained its own hash-of-empty line, breaking verification.
   Fixed with the wrapper-identical exclusion + `LC_ALL=C sort` (determinism).
2. **Space-containing paths silently skipped**: `find … | xargs sha256sum` splits on whitespace
   (proven: `dir with space/f.txt` missed with stderr suppressed). `proc_<pid>_<comm>` dirs can
   contain spaces. All 5 hashing sites (above + `run_c2m_runtime_capture.sh` + `collect_baseline.sh`)
   now use a POSIX `while IFS= read -r` loop (space-safe, empty-safe, busybox-ash compatible).
3. **Missing hash manifest**: `collect_baseline.sh` (widely referenced by runbooks) wrote no
   SHA256SUMS/FILELIST although the EN gate requires "capture + MANIFEST + hashes". Added the same
   guarded block (additive only; `compare_baselines.py` unaffected).
4. **Unguarded `netstat`** (`capture_interface_pcap.sh`): before/after snapshots now record
   `UNKNOWN (netstat absent)` when the binary is missing instead of a bare shell error.
5. **`-Wall` warning** (`c2m-ipu-smoke/main.cpp`): unused `single_invoke` variable removed
   (behavior identical: `--single-invoke` still forces the refuse branch, rc=4). Builds `-Werror` clean.

A dry-run harness artifact (not a pack bug): the first gate-test expectation wrongly assumed bare
`record` is refused while an active copy exists — auto-detect of exactly one copy is intended
behavior; the test was corrected, the script unchanged.

## 3. BusyBox/ash compatibility audit

`tools/device/*.sh` + `tools/fw/capture_c2m_adas_runtime.sh`: no `[[ ]]`, `(())`, arrays,
`readarray`/`mapfile`, process substitution, `local`, `function`, `source`, `==`, `pushd/shopt`,
`grep -P`, `xargs -r`, `stat -c`, `date -d`, `find -printf`, `sort -V`. Only POSIX constructs
plus `command -v`, `local`-free functions, `awk '{print $1}'`, `cut -c`, `tr`, `ls -dt|head -n 1`
(all BusyBox-safe). Python heredocs in `c2m_hw_day.sh` require python3/python (exit 3 otherwise).
Workstation behavior unchanged (all fixes also valid under Git-Bash `sh`).

## 4. Missing-command behavior

Every optional binary (`sha256sum`, `tar`, `ss`, `netstat`, `tcpdump`, `readlink`, `ip`,
`ifconfig`, `dmesg`, `lsmod`, `ps`) is guarded by `has()`/`command -v` or `|| true`, except
`tcpdump`/`netstat` in `capture_interface_pcap.sh` which are preconditions with explicit
exit codes (4 = no tcpdump; netstat now degrades to UNKNOWN). Nothing fabricates success;
absent data stays UNKNOWN.

## 5. Gate-engine proof

14 scenario checks (§1 of task order, all covered): next-gate chain, FAIL→STOP both levels,
B blocked without A, coexist blocked without safe PASS, STOP_DAY sentinel, template/start.json
refusal, template byte-immutability. Runtime state only ever in `C2M_HW_<date>/00_manifest/
GATES.current.json` (temp copies in self-test; zero repo pollution verified).

## 6. Capture safety proof

Per-command audit of the 4 capture scripts + wrapper + fw collector + pcap:
every redirect targets `$OUT*`/`$OUTDIR*`; all device reads are `cat` of `/proc|/sys|/dev`
listings (read-only); the sole `kill` is `kill -INT` of the script's own tcpdump child.
Verdicts: `capture_c2m_m4_runtime.sh` READ_ONLY, `capture_c2m_ipu_baseline.sh` READ_ONLY,
`capture_c2m_media_topology.sh` READ_ONLY, `run_c2m_runtime_capture.sh` READ_ONLY,
`capture_c2m_adas_runtime.sh` READ_ONLY, `collect_baseline.sh` READ_ONLY,
`capture_interface_pcap.sh` BENCH_ONLY (bounded passive tcpdump, verified iface only).
Zero BLOCKED commands present.

## 7. A/B freeze verification

`git status` shows no change to frozen paths. `build/EN_REPACK_GOLDEN.tar` re-hashed:
`3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` (matches A).
`EN_ENHANCE_IDLE.tar` (B, `247e9a82…`) is not present in this checkout (build artifact);
nothing in this task creates/modifies flash inputs, `firmware/original/`, manifests, or
`C2M_FLASH_*` (absent = build outputs, untouched).

## 8. Remaining hardware-only tests (NOT proven here)

Recovery YES, A x3-reboot acceptance, B x5+soak, EN/VI captures, A–H classification,
M4 L0/L1, IPU baseline/SCL topology contents, SAFE Invoke, coexist delta. IPU stays
`BLOCKED_TOOLCHAIN` (skeleton rc=4 by construction).

## 9. Remaining toolchain blocker

`NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY` (SGS_IPU_SDK matching `b03a7d4` still gated).

## 10. Status

`C2M_PRE_HARDWARE_PACK = HARDWARE_DAY_READY` (offline scope only).
`HARDWARE_DAY_READY != FLASH_PROVEN`, `!= IPU_PROVEN` — both need physical hardware.
