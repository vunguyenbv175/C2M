# C2M IPU SDK First-30-Minute Checklist V1

**Date:** 2026-09-11. **Starts at SDK receipt. Time-boxed triage, not a full bring-up.**
Assumes the disposable-host safety rule from the receipt-validation doc. Check boxes in order; STOP at the first failed gate.

## Minutes 0–5 — Intake and safety

- [ ] `sha256sum` recorded with filename / size / date / source (private note, never commit)
- [ ] Extracted under `external/sgs_ipu_sdk/` only
- [ ] `git status --short` shows NOTHING tracked (if SDK files appear: STOP, fix ignore first)
- [ ] Disposable VM/container confirmed (no creds, keys, or home secrets mounted)

## Minutes 5–15 — Identify the drop (no execution)

- [ ] Version files / release notes found → record branch, date, supported SoCs
- [ ] `fingerprint_sgs_sdk.py` metadata JSON emitted → tool hits (ConvertTool/Calibrator/Compiler/Simulator/headers/demos) listed
- [ ] Identifier search done → hits recorded for `b03a7d4 / 0940dba / T_0.0.1_210525 / SSC8838G / Tiramisu / Mercury6`
- [ ] License/access files read → NDA + license-server/dongle needs recorded

## Minutes 15–25 — Compatibility gates

- [ ] `cfg_env.sh` sourced (or drop equivalent); `show_sdk_info.py` chip list contains SSC8838G/Tiramisu (else STOP → FAMILY_ONLY/INCOMPATIBLE)
- [ ] `ConvertTool -h` (or `SGS_converter -h`) captured → `ONNX_SUPPORTED = YES / NO` recorded from output only
- [ ] Calibrator/Compiler/Simulator `-h` captured
- [ ] `compare_mi_ipu_api.py` run → all 11 local APIs present, newer-API absences noted (else STOP → INCOMPATIBLE)
- [ ] Classification written: EXACT / NEAR / FAMILY_ONLY / INCOMPATIBLE / UNKNOWN

## Minutes 25–30 — Decision

- [ ] If EXACT or vendor-confirmed NEAR → schedule the MobileNetV2-caffe-224 host proof (recipe doc; record tool versions, exact commands, input/output SHA256, sizes, logs, simulator result). No YOLO yet. No weights committed without license-safe approval.
- [ ] If anything else → STOP, keep `NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`, reply to FAE with fingerprint + chip list + missing API.

Expected artifacts of a PASS: fingerprint JSON, four `-h` outputs, `show_sdk_info` output, API diff output, classification + gate checklist, all stored privately (not in git).
