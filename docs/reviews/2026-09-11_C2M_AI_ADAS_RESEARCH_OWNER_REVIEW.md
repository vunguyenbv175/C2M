# C2M AI ADAS Research V1 — Owner Review

Reviewed commit: `00fbd4499dd65a30c74c19c2e5c6376074245424`

## Verdict

**PASS WITH GUARDRAILS**

The research is directionally strong and useful for planning. It correctly keeps stock ADAS as the safety baseline, uses shadow-first deployment, prefers small specialized models over a monolithic replacement, and selects speed-limit recognition as the first user-visible AI augmentation. The model survey is broad enough to stop further generic model hunting for now.

However, hardware feasibility remains conditional on the SigmaStar IPU toolchain and live hardware benchmarking. No real-time or capacity claim may be promoted to product fact until those gates are passed.

## Accepted decisions

1. Architecture **E — HYBRID**, with on-device small specialists as the product core and phone/offboard compute advisory-only.
2. Stock ADAS remains the safety baseline; custom AI starts in **SHADOW** and cannot suppress stock FCW/PCW/LDW.
3. First AI feature: **speed-limit recognition + RoadIntelligence fusion → HUD**, because it is low-rate, reversible, measurable, and does not require replacing existing stock warning functions.
4. Prefer accelerator-friendly CNN families and deterministic CPU logic for tracking, TTC, hysteresis, warning thresholds, fusion, and scheduling.
5. Prioritize SCL hardware resize/ROI, temporal subsampling, cascaded inference, INT8/operator cleanup, and process isolation.
6. On-device monocular depth is not a first-line feature; geometry/tracking is preferred.
7. Generic AI-model landscape research is sufficient for V1; next work must target the actual SSC8838G/SigmaStar IPU deployment path.

## Guardrails / corrections

### G1 — `0.8 TOPS` is not a proven C2M runtime budget

The report correctly labels SSC8838G `0.8 TOPS` as **LIKELY** from secondary vendor-news sources, while INT8/FP16 support, usable throughput, operator coverage, memory limits, and stock-ADAS accelerator occupancy remain UNKNOWN.

Therefore statements such as `Bundle A fits 0.8 TOPS` must be interpreted only as **architecture plausibility**, not measured feasibility.

Canonical wording:

> Bundle A architecture is PLAUSIBLE. Real-time execution alongside stock ADAS is UNPROVEN until vendor-compiler smoke test + on-device p50/p95 latency + RSS/MMA/IPU-duty measurements pass.

### G2 — YOLO11n-QCVN is a research candidate, not the default product sign model

YOLO11n has an AGPL/commercial-license gate and a more difficult operator surface. It may remain a quality/reference candidate, but the first deployable speed-limit model should prefer a commercially permissive, converter-friendly architecture if performance is adequate (for example an Apache/MIT nano detector or a small custom Conv/BN/ReLU head), followed by an optional crop classifier if digit confusion is observed.

Model selection is subordinate to the real SigmaStar operator/compiler matrix.

### G3 — Model winners remain benchmark shortlists

`UFLDv2-R18`, `YOLOX-Nano`, `NanoDet-Plus`, `PicoDet-S`, `Fast-SCNN`, etc. are accepted as **benchmark candidates**, not final production winners. The final winner must be selected on the same C2M clips after conversion, quantization and device benchmarking.

### G4 — Do not add lane/object replacement merely because modern models score higher

Stock C2M already implements lane/vehicle/pedestrian safety functions. Custom lane/object models should initially serve observability, robustness testing, disagreement capture, and future augmentation. Replacement requires per-function evidence and rollback proof.

## Owner-level priority after this review

### P0 — SigmaStar IPU/NPU deployment research

Recover/verify:

- actual `MI_IPU` API surface,
- stock model format,
- vendor compiler/converter,
- framework input path,
- supported operators,
- quantization types,
- tensor/layout constraints,
- stock/custom accelerator coexistence,
- SCL→IPU zero/one-copy feasibility.

This is now more valuable than surveying additional ADAS models.

### P1 — Hardware proof when device is available

1. Candidate A physical proof.
2. Candidate B physical proof.
3. EN/VI runtime capture for ADAS regression.
4. SCL/media geometry capture.
5. Vendor-compiler tiny Conv-model smoke test.
6. Measure latency/RSS/MMA/IPU-duty while stock ADAS remains alive.

Only after those gates should a real speed-limit model be deployed in shadow mode.

## Recommended first AI deployment experiment

Do **not** start with YOLO/UFLD.

First prove the toolchain with a tiny static-shape Conv/BN/ReLU classifier:

`source model → ONNX static → operator audit → vendor compiler → C2M model → standalone load/invoke → known-output comparison → cleanup`

Success criteria:

- model compiles,
- model loads,
- deterministic output matches host reference within quantization tolerance,
- stock recorder/ADAS remains alive,
- memory and latency are captured,
- custom process can be killed without affecting stock.

Then proceed to the first real feature: speed-limit recognition.

## Final owner verdicts

- AI landscape research: **PASS**
- Model shortlist quality: **PASS**
- Architecture E: **ACCEPT**
- Shadow-first policy: **ACCEPT / REQUIRED**
- Speed-limit-first feature: **ACCEPT**
- Real-time Bundle A on C2M: **UNPROVEN**
- `0.8 TOPS` as hard budget: **REJECT — LIKELY only**
- Native custom-IPU deployment: **BLOCKED pending toolchain/API proof**
- Replace stock ADAS now: **NO**
- More broad model survey now: **NO**

Next research task: **SigmaStar SSC8838G / MI_IPU custom-model deployment feasibility**.
