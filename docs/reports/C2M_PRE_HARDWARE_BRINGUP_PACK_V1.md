# C2M Pre-Hardware Bring-up Pack V1 — Ready / Blocked / First Action

**Date:** hardware-day pack, preparation only. No flash, no Candidate change, no hardware proof claimed.

## 1. What is ready

```text
Master order enforced (0 recovery → A → B → EN → VI → A–H → M4 L0/L1 → IPU → SCL → SAFE → COEXIST → shadow-prep).
Flash runbooks A/B with hash gates (A 3a703522..., B 247e9a82...), SD-contents rule (4 files, never outer TAR), x3/x5 + soak gates.
Read-only capture wrappers reusing proven collectors (capture_c2m_adas_runtime.sh + compare script), M4/IPU/media topology captures with discovery + UNKNOWN-on-absent.
A–H classifier operator card (single-letter verdict, no generic "broken").
M4 L0-L4 gate table (L0/L1 allowed, L2 4 allowlisted messages gated, L3/L4 BLOCKED).
IPU baseline + SCL topology runbooks (capture-only) + smoke skeleton (probe-only default, BENCH_ONLY single Invoke, compat header UNVERIFIED).
Toolchain request card + smoke recipe placeholders (no invented CLI) + ONNX audit reuse note + Tier1-3 SCL plan.
Evidence root C2M_HW_<date>/ (13 dirs) + init script + orchestrator (c2m_hw_day.sh never flashes/kills/infers/injects) + machine gates JSON.
```

## 2. What is hardware-blocked (needs device)

```text
All PASS/FAIL verdicts (A/B acceptance, EN/VI captures, A–H class, M4 L0/L1 proof, IPU/SCL captures, SAFE/COEXIST Invoke + latency/XOR + stock-delta).
Boot/reboot/soak behavior, calibration times, serial/panic/thermal observations.
```

## 3. What is toolchain-blocked (needs vendor/FAE)

```text
SGS_IPU_SDK drop matching sdk_commit b03a7d4 + fw T_0.0.1_210525 + SSC8838G target (Convert/Calibrator/Compiler/Simulator + mi_ipu/mi_scl headers + target config + board examples).
Until then: NATIVE_IPU_TOOLCHAIN_BLOCKED — smoke model cannot be compiled; c2m-ipu-smoke stays probe-only; no custom weights committed.
```

## 4. What is intentionally not automated

```text
Flashing (manual SD steps only), stock config edits/kills/remounts, IPU inference auto-run, M4 transmit/injection, EN+VI-adas swap (BLOCKED until A–H), continuous shadow inference.
```

## 5. Frozen release verification (this pack)

```text
A EN_REPACK_GOLDEN.tar 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c (RELEASE READY, NOT FLASH-PROVEN)
B EN_ENHANCE_IDLE.tar 247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a (RELEASE READY, NOT FLASH-PROVEN)
Check: git status shows ONLY new bring-up files; no tracked release/contract/toolchain file modified; build/ + release/ + firmware/original + external/ stay ignored.
C2M_FLASH_A/B contents rule re-asserted (4 files each); no Candidate C created.
```

## 6. Script safety audit

| Script | Class | Verdict |
|---|---|---|
| init_hardware_day_dir.sh | SAFE_WRITE_OUTPUT_ONLY (workstation mkdir) | PASS (host test) |
| run_c2m_runtime_capture.sh | READ_ONLY wrapper (label gate, delegates to proven collector) | PASS |
| capture_c2m_m4_runtime.sh | READ_ONLY passive (no transmit) | PASS |
| capture_c2m_ipu_baseline.sh | READ_ONLY (no sysfs writes; absent=UNKNOWN) | PASS |
| capture_c2m_media_topology.sh | READ_ONLY capture-only (no channel change) | PASS |
| c2m_hw_day.sh | orchestrator (status/next/record only) | PASS |
| c2m-ipu-smoke (probe default) | READ_ONLY default; BENCH_ONLY inference refused without vendor headers | skeleton builds only with private SDK (expected) |
| compare/capture reuse | unchanged proven scripts (no redesign) | PASS |

Host checks run: `python -m py_compile`, `sh -n` where available, `json.tool`, `--help`/usage, missing-file handling, `git diff --check`. No CI workflow added (cheap local only).

## 7. Remaining risks

```text
A FAIL (packaging bug) blocks entire day; B regression reverts to A; boot loop/panic/thermal/read-only-FS stops day.
VI flash only with recovery; EN+VI swap blocked until A–H.
M4 interface mistaken (usb0 assumption) — guarded by on/off delta requirement + verified-iface pcap gate.
IPU hang/timeout or stock degradation on SAFE/COEXIST — guarded by single-shot + <10% + kill-custom-only + reboot-confirm.
SCL instability from extra port — capture-only phase makes no changes; Tier plan needs SAFE PASS first.
```

## 8. Exact first action when C2M is physically available

```text
1. sh tools/device/init_hardware_day_dir.sh $(date +%Y%m%d)   [SAFE_WRITE_OUTPUT_ONLY]
2. Complete 01_recovery/ checklist + hash verify (A 3a703522... + B 247e9a82... + 4-file SD roots) → RECOVERY_READY=YES or STOP. [READ_ONLY]
3. sh tools/device/c2m_hw_day.sh status   (then follow master runbook step 1; flash A manually). [READ_ONLY]
```
