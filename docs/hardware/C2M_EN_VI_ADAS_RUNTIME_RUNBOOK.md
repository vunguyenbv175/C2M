# C2M EN/VI ADAS Runtime Runbook — Capture + Compare (no swap yet)

**Safety:** all capture `READ_ONLY` on device; workstation compare `SAFE_WRITE_OUTPUT_ONLY`. EN-base+VI-adas swap is BLOCKED until A–H class assigned.

## 0. Gates

```text
[ ] CANDIDATE_B = PASS ............ (or explicit A-only path recorded)
[ ] RECOVERY_READY = YES ...........
[ ] VI flash performed ONLY under documented recovery process, EN restore ready
```

## 1. Sequence

```text
1. EN boot, allow normal ADAS activation (same drive/readiness interval each time). READ_ONLY
2. Capture EN:  sh tools/device/run_c2m_runtime_capture.sh en    READ_ONLY (writes only to $C2M_CAPTURE_BASE, default /mnt/mmc)
3. Record visible behavior (lane/FCW/PCW/display/audio) in 04_en_runtime/notes.md. SAFE_WRITE_OUTPUT_ONLY
4. Power off. READ_ONLY
5. Flash/boot VI ONLY if recovery proven. Allow EQUIVALENT readiness interval. FLASH (flash) + READ_ONLY (observe)
6. Capture VI:  sh tools/device/run_c2m_runtime_capture.sh vi    READ_ONLY
7. Restore EN if unit must return to known-good. FLASH
8. Offline compare on workstation (SAFE_WRITE_OUTPUT_ONLY):
   python3 tools/fw/compare_c2m_runtime_capture.py <capture_en> <capture_vi> -o 06_adas_compare/compare.json --markdown 06_adas_compare/compare.md
9. Classify with C2M_ADAS_FAILURE_CLASSIFIER_CARD.md → ADAS_FAILURE_CLASS (single letter). SAFE_WRITE_OUTPUT_ONLY
```

Wrapper usage:

```sh
sh tools/device/run_c2m_runtime_capture.sh en
sh tools/device/run_c2m_runtime_capture.sh vi
```

Wrapper guarantees: label check, timestamped dir, calls existing collector, writes MANIFEST + hashes, tars if `tar` exists; never modifies config, never restarts/kills services, never remounts, never decodes secrets.

## 2. Do NOT do yet

```text
EN-base + VI-adas executable swap — BLOCKED until ADAS_FAILURE_CLASS = A–H (not UNKNOWN).
Any kill/restart/remount/edit on device — DANGEROUS/BLOCKED in this phase.
```

## 3. Evidence

`04_en_runtime/`, `05_vi_runtime/`, `06_adas_compare/compare.json|.md`, classifier card result. Missing files stay UNKNOWN, never SAME.
