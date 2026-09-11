# C2M PRE-HARDWARE OWNER CHECKPOINT — DONE / BLOCKED / FROZEN

**Date:** 2026-09-11. **Authoritative status. No new work authorized beyond §7.**
**Basis:** pre-hardware self-test `c945321` (31 PASS / 0 FAIL / 0 SKIP),
`C2M_PRE_HARDWARE_PACK = HARDWARE_DAY_READY` (offline scope only).

## 1. DONE (completed, frozen)

```text
firmware extraction/repack/validation ........... DONE
Candidate A (3a703522…c465f8c) ................... DONE / FROZEN / RELEASE READY (NOT FLASH-PROVEN)
Candidate B (247e9a82…0756a) ..................... DONE / FROZEN / RELEASE READY (NOT FLASH-PROVEN)
QEMU stock runtime .............................. DONE
EN/VI static reverse ............................ DONE (broad pass closed)
VI runtime capture kit .......................... DONE
M4 static research .............................. DONE (broad pass closed)
ProMax static analysis .......................... EXHAUSTED (V6 final, level unchanged)
ProMax BLE capture kit .......................... DONE (awaiting hardware session)
AI ADAS feasibility V1 .......................... DONE
SigmaStar IPU stack V1 .......................... DONE
SGS_IPU_SDK hunt ................................ DONE (verdict D: docs only, NDA-gated)
FAE request package ............................. DONE (ready to send)
hardware-day pack (gates/runbooks/captures) ..... DONE
offline self-tests 31/31 ........................ DONE (c945321)
```

## 2. FROZEN (explicit prohibitions until an unlock event)

```text
NO rebuild Candidate A/B
NO Candidate C
NO broad VI static reverse
NO broad ProMax static reverse (V7 forbidden)
NO generic AI-model survey
NO generic SGS_IPU_SDK web hunt
NO feature implementation before Candidate B physical proof
NO Android/VietMap/custom-AI implementation
NO BLE replay/emulation/injection
NO flash action without the §4 sequence
```

## 3. BLOCKER → UNLOCK EVENT

```text
WORK ITEM                  | CURRENT STATE | UNLOCK EVENT
A flash validation         | blocked       | physical C2M
B flash validation         | blocked       | A PASS (x3 reboots)
VI ADAS diagnosis          | blocked       | EN+VI runtime captures
M4 protocol advancement    | blocked       | passive runtime capture (L0/L1)
ProMax protocol advancement| blocked       | BLE HCI session (T0–T10)
Native IPU custom model    | blocked       | compatible SGS_IPU_SDK received (b03a7d4/Tiramisu)
IPU board smoke            | blocked       | host compile + Simulator PASS + physical C2M
Android/VietMap/custom AI  | blocked       | Candidate B physical PASS
```

Current blockers: `PHYSICAL_C2M_ACCESS`, `NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`,
`PROMAX_RUNTIME_CAPTURE_REQUIRED`.

## 4. FIRST ACTION WHEN C2M IS AVAILABLE (exact sequence)

```text
1  recovery gate (RECOVERY_READY=YES or STOP)
2  Candidate A flash (manual SD contents, never outer TAR)
3  A acceptance + x3 reboot
4  Candidate B flash
5  B acceptance + x5 reboot + soak
6  EN capture (read-only)
7  VI capture (recovery path only)
8  classify A–H (UNKNOWN blocks swap experiment)
9  M4 passive capture (L0/L1; L2 gated; L3/L4 BLOCKED)
10 IPU baseline (read-only, missing=UNKNOWN)
11 SCL topology (capture only, no channel changes)
```

IPU custom Invoke is NOT scheduled before the toolchain gate (host PASS first).
Runbook: `docs/hardware/C2M_HARDWARE_DAY_MASTER_RUNBOOK.md`,
orchestrator: `tools/device/c2m_hw_day.sh`.

## 5. FIRST ACTION WHEN SGS SDK ARRIVES (exact sequence)

```text
1 hash archive (private record, external/ only, never commit)
2 fingerprint SDK (tools/research/ipu_sdk/fingerprint_sgs_sdk.py)
3 verify SSC8838G/Tiramisu in chip/target list (absent → STOP)
4 compare MI_IPU API (compare_mi_ipu_api.py; all 11 local APIs required)
5 check compiler target for SSC8838G
6 check ONNX support via ConvertTool -h (record YES/NO, no inference)
7 MobileNetV2 Caffe 224 conversion (.sim → _fixed.sim → _sgsimg.img)
8 Simulator PASS
9 STOP before board until host PASS
```

Full workflow: `docs/research/C2M_IPU_SDK_RECEIPT_VALIDATION_V1.md`.
FAE package: `docs/research/C2M_SIGMASTAR_FAE_REQUEST_V1.md`.

## 6. FIRST ACTION WHEN ProMax IS AVAILABLE (exact sequence)

```text
1 enable Android HCI snoop (Developer Options)
2 verify log grows (30-s test toggle)
3 nRF read-only GATT discovery (no manual writes; build handles.csv)
4 run T0–T10 navigation session with wall-clock event log
5 export btsnoop_hci.log
6 parse + correlate (tools/reverse/promax/)
7 NO replay
```

Runbook: `docs/research/PROMAX_BLE_CAPTURE_RUNBOOK_V1.md`.

## 7. STOP-WORK POLICY

If no hardware and no SDK is available:

```text
DO NOT INVENT NEW TASKS JUST TO KEEP AGENTS BUSY.
```

Allowed before an unlock event:

```text
bug fix / security or safety fix / documentation correction / owner-requested targeted task
```

Everything else: `WAIT_FOR_EVIDENCE`.

## 8. Machine-readable status

`docs/reports/C2M_PRE_HW_STATE.json` (beside this file).
