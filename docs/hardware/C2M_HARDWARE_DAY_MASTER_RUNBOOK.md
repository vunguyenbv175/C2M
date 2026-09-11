# C2M Hardware-Day Master Runbook — One controlled sequence

**Safety labels:** `READ_ONLY` observe · `SAFE_WRITE_OUTPUT_ONLY` workstation/notes · `BENCH_ONLY` bench-only device op · `DANGEROUS` never improvise · `FLASH` manual flash · `BLOCKED` forbidden.
**Freeze:** A/B byte-frozen (A `3a703522...`, B `247e9a82...`). This pack never rebuilds them.

## One-screen checklist

```text
[ ] 0. Recovery ready ............ 01_recovery/ ............ RECOVERY_READY=YES else STOP
[ ] 1. Candidate A flash ......... 02_candidate_A/ ......... FLASH (manual SD contents, NOT outer TAR)
[ ] 2. Candidate A validation .... 02_candidate_A/ ......... CANDIDATE_A=PASS else B BLOCKED
[ ] 3. Candidate B flash ......... 03_candidate_B/ ......... FLASH (manual)
[ ] 4. Candidate B validation .... 03_candidate_B/ ......... CANDIDATE_B=PASS (x5+soak; one boot insufficient)
[ ] 5. EN runtime baseline ....... 04_en_runtime/ .......... READ_ONLY capture
[ ] 6. VI runtime capture ........ 05_vi_runtime/ .......... FLASH+READ_ONLY (recovery path only)
[ ] 7. EN-vs-VI class A–H ....... 06_adas_compare/ ........ classifier card (no generic "broken")
[ ] 8. M4 passive L0/L1 ......... 07_m4/ .................. READ_ONLY; L2 gated; L3/L4 BLOCKED
[ ] 9. M4 L2 (conditional) ....... 07_m4/ .................. ONLY DispBrightSet/StorageStatus/ScreenModeSet/ClientConn after proof
[ ] 10. IPU baseline ............ 08_ipu_baseline/ ........ READ_ONLY (missing=UNKNOWN)
[ ] 11. SCL/media topology ...... 09_media_topology/ ...... READ_ONLY capture only
[ ] 12. IPU SAFE smoke .......... 10_ipu_safe/ ............ BENCH_ONLY single Invoke, stock untouched
[ ] 13. IPU coexist single-shot . 11_ipu_coexist/ ......... BENCH_ONLY beside live stock, <10% delta
[ ] 14. Shadow prep (optional) .. 12_summary/ ............. plan only, no integration
```

## Step table (command → expected → failure meaning → rollback → next)

| # | Command | Expected | If fail | Rollback | Next |
|---|---|---|---|---|---|
| 0 | `sh tools/device/init_hardware_day_dir.sh [YYYYMMDD]` `SAFE_WRITE_OUTPUT_ONLY` + §3 recovery checklist `READ_ONLY` | `C2M_HW_<date>/` tree + `RECOVERY_READY=YES` | NO → STOP | n/a | 1 |
| 1 | Copy `C2M_FLASH_A/*` contents to FAT32 SD root; flash per `C2M_FLASH_A_RUNBOOK.md` `FLASH` | live view in budget, no loop | boot loop/no view/stall → STOP | re-flash verified A once, then STOP | 2 |
| 2 | A acceptance §2 `READ_ONLY` | system+ADAS nominal x3 reboots | any FAIL → STOP | stay on A, preserve evidence | 3 (only if PASS) |
| 3 | Copy `C2M_FLASH_B/*`, flash per `C2M_FLASH_B_RUNBOOK.md` `FLASH` | boots | loop → STOP | re-flash A | 4 |
| 4 | B acceptance + `ps \| grep c2m-idle` + `cat /tmp/c2m_idle.marker` (`c2m-idle 0.1.0-sprint1`) `READ_ONLY` (+ kill test `BENCH_ONLY`) | A-green + B3–B7 green x5+soak | regress → STOP | re-flash A | 5 |
| 5 | `sh tools/device/run_c2m_runtime_capture.sh en` `READ_ONLY` | timestamped dir + MANIFEST + hashes | missing files → UNKNOWN (continue) | n/a (read-only) | 6 |
| 6 | Recovery-path VI flash `FLASH`, same readiness wait, `... vi` `READ_ONLY`, restore EN `FLASH` | EN+VI captures | no recovery → SKIP VI (record BLOCKED) | restore EN | 7 |
| 7 | `python3 tools/fw/compare_c2m_runtime_capture.py <en> <vi> -o ... --markdown ...` + classifier card `SAFE_WRITE_OUTPUT_ONLY` | `ADAS_FAILURE_CLASS=A–H` | UNKNOWN → STOP swap experiment | n/a | 8 |
| 8 | `sh tools/device/capture_c2m_m4_runtime.sh [label]` `READ_ONLY` (+ pcap only on verified iface) | L0/L1 evidence, no transmits | iface unproven → stay L0 | n/a | 10 |
| 9 | L2 `BENCH_ONLY` conditional | only 4 allowlisted messages | no proof → SKIP (BLOCKED) | n/a | 10 |
| 10 | `sh tools/device/capture_c2m_ipu_baseline.sh [label]` `READ_ONLY` | baseline dir; absent=UNKNOWN | hang/panic → STOP | n/a | 11 |
| 11 | `sh tools/device/capture_c2m_media_topology.sh [label]` `READ_ONLY` | topology dir; no channel change | instability → STOP | n/a | 12 |
| 12 | `tools/device/c2m-ipu-smoke/` probe-only default `READ_ONLY`; single Invoke `BENCH_ONLY` per `RUNBOOK.md` | Create/CHN/Invoke/Destroy 0 + XOR + latency | non-zero/hang → STOP | reboot, confirm stock | 13 (only if SAFE PASS) |
| 13 | Coexist single-shot `BENCH_ONLY` beside live stock | custom 0 + stock alive/health + <10% delta | timeout/degrade → STOP | kill custom only, reboot if needed | 14 |
| 14 | Shadow prep plan only | notes in `12_summary/` | n/a | n/a | done |

EN-base+VI-adas swap stays BLOCKED until class A–H assigned. `tools/device/c2m_hw_day.sh` orchestrates (shows next step, verifies files, runs read-only captures, hashes, records manual PASS/FAIL) but never flashes/kills/infers/injects automatically.

## Stop conditions (STOP day on any)

```text
Candidate A FAIL / B destabilizes stock / boot loop / recording FAIL / ADAS FAIL on A /
read-only FS unexpectedly / kernel panic / IPU hang / thermal issue / SCL/media instability
```

Never keep testing after a major safety/recovery failure. Preserve evidence first.

## Evidence root

```text
C2M_HW_<YYYYMMDD>/00_manifest/01_recovery/02_candidate_A/03_candidate_B/04_en_runtime/
05_vi_runtime/06_adas_compare/07_m4/08_ipu_baseline/09_media_topology/10_ipu_safe/11_ipu_coexist/12_summary/
```

Gates file: `docs/hardware/C2M_HARDWARE_DAY_GATES.json` (PASS/FAIL/PARTIAL/UNKNOWN/BLOCKED/NOT_RUN + evidence_path + timestamp + notes).
