# C2M AI ADAS Roadmap V1 — Bundles, Phases, Verdict

**Status:** research only. STOP after research: no AI implemented, no weights downloaded, no firmware/Candidate change.
**Date:** 2026-09-11.

## 1. Candidate bundles (Q37)

All bundles: stock recorder/camera/ISP/ADAS/M4/calib preserved; custom = separate shadow process; full-res never to NN; SCL one-downscale + ROIs; CPU geometry.

### Bundle A — Ultra-light (highest fully-on-device chance)

```text
det:   NanoDet-Plus-m-320 or PP-PicoDet-S-320 (Apache-2.0, ~1M, ~0.7–0.9G, INT8 ~1.2 MB) @5 Hz full-central
track: ByteTrack or OC-SORT motion-only (CPU) @10 Hz
lane:  UFLDv2-R18 (MIT) lower-half ROI 512x288-ish @7–10 Hz
sign:  same-detector QCVN-limits subset OR 2 Hz upper-ROI scan + Lite0-48px classifier on trigger (K≤3)
ttc:   geometry (pinhole+height/ground-plane+KF) + bbox-expansion check (CPU)
ctx:   classical day/night/fog/glare + heuristic scene tags (CPU)
cost:  ~2–4 MB INT8, ~1–2G avg (time-sliced), RSS ≤80 MB target
```

### Bundle B — Balanced (A + advisories)

```text
A + det→YOLOX-Nano-416-ReLU or YOLOv6-N-ReLU-RepOpt-416/512 (better bike/small recall) +
TL nano-4cls upper-center ROI @5 Hz gated + 5-frame vote +
drivable fallback Fast-SCNN (or DDRNet-23-slim) 320x192–512x288 @2–5 Hz +
sign full QCVN-10–20cls single-stage (YOLO11n-640-class @2 Hz gated; +Lite0 if digit confusion)
cost:  ~4–7 MB INT8, time-sliced; drop TL/seg first under pressure
```

### Bundle C — Advanced optional (B + offboard/teacher, non-safety)

```text
B + Android offload (crops→phone NNAPI/GPU/NPU, advisory only) +
offline teachers (DepthAnythingV2-S/MonoDepth2 labelling, distill→student) +
hazard split (pothole vs debris vs flood after >2k labels each) +
PIDNet-S / YOLOv10-N-NMS-free if IPU proves SiLU/DFL headroom
cost:  on-device same as B; phone/cloud experimental, never safety
```

## 2. Minimum useful upgrade (Q38)

**Speed-limit HUD + navigation/ADAS fusion — without touching stock warnings.** Stock TSR `enable_tsr=false` default (greenfield) + RoadIntelligence (`FuseSpeedLimit camera>viemap>osm`) + VietMap LIVE nav already designed (`ROAD_INTELLIGENCE_DESIGN.md`) = visible product value (limit icon, overspeed memo, nav arrows on M4/Web) at ~2 Hz sign cost + zero NPU for fusion. Do not replace lane/objects first — stock already does them adequately; augment the gap.

## 3. Highest-value low-risk first AI feature (Q39)

**ONE: speed-limit recognition at 2 Hz gated (single-stage YOLO11n-QCVN or nano-subset + optional Lite0 crop check), shadow → AUGMENT HUD memo.**

```text
why: greenfield (no stock conflict), easy eval (photo-able limits, GPS/map cross-check),
     clear HUD value, ~1 NPU slice @2 Hz, fully reversible (feature-flag + kill-switch),
     proves whole pipeline (SCL-crop → INT8 → CPU-fuse → DisplayState/M4Adapter/Voice) before FCW-grade work
```

## 4. Deployment phases (Q53)

| Phase | Scope | Entry gate | Success | Rollback |
|---|---|---|---|---|
| 0 — Candidate A/B proof | no custom AI; EN-base + VI-adas temp test; M4 transport prove | recovery proven; baselines captured | failure class A–F assigned; M4 L0–L2 proven | reboot to EN golden |
| 1 — offline bench only | same `raw_adas` clips; stock vs candidates on workstation/GPU; conversion dry-run (ONNX→simplify→op-inventory) | clips + calib + GPS logged | matrix filled; SHORTLIST locked; no UNSUPPORTED-op surprise | n/a (no device change) |
| 2 — on-device shadow | custom proc passive; det-5Hz+track-10Hz+lane-7–10Hz+sign-2Hz; JSONL + ±5 s clips; no display/audio | vendor compiler smoke + SCL map + RSS/IPU caps | agreement/FP/miss/stability measured; stock unaffected (pull-custom test) | kill-switch + uninstall custom |
| 3 — non-safety augment | speed-limit/hazard-memo/nav on M4/Web; stock warnings unchanged | Phase-2 recall/stability gates + VN-miniset no-regress | limit-HUD precision/recall + user-accept; zero stock-warning delta | feature-flag off → stock-only display |
| 4 — fusion | advisory confidence fusion (both-agree↑; disagree→log); warnings still stock-driven | Phase-3 field weeks + threshold review | advisory precision + disagreement-review SLA | fuse-weight 0 (stock-only) |
| 5 — selective replace (OPTIONAL) | per-function override, flagged, default-off | per-function evidence + safety review + rollback pinned | function-level A/B wins + rollback drill pass | per-function flag off; pinned prior `.ipumodel` restore |

## 5. Model conversion experiment plan (Q42, ordered)

```text
1. conv-only 10-line ONNX → vendor compiler → load → single-image (TOOLCHAIN PROOF; fail-fast here)
2. YOLOX-Nano-416-ReLU (or PicoDet-S/NanoDet-Plus-m by toolchain): Pt→ONNX static→simplify→runtime-check→
   op-inventory→INT8-calib (night/rain/VN 500+)→vendor-compile→single-image→video-bench (5 Hz + ByteTrack-10 Hz)
3. UFLDv2-R18 ROI: same; keep head-FP if jitter; compare vs LaneATT-R18 only if gap
4. sign-QCVN single-stage @2 Hz gated; add Lite0-crop classifier only on digit-confusion evidence
5. TL-4cls ROI @5 Hz gated + vote (droppable); seg Fast-SCNN ROI @2–5 Hz (droppable)
6. promote bundle A → B → C-optional per gates; every step: p50/p95, RSS, IPU_ms, FP/miss/stability, VN-miniset
```

## 6. Do-not-do (Q54)

```text
full firmware rewrite; stock ADAS removal; cloud-only real-time ADAS; giant transformer w/o edge proof;
redundant models same task; NN for trivial geometry/thresholds; new hardware unless on-device fails gates
```

## 7. Final ranking (Q51) — repeated for completeness

```text
lane:         UFLDv2-R18 / runner LaneATT-R18 (ultra UFLDv2-MobileNetV3)
detector:     YOLOX-Nano-416-ReLU (tie PicoDet-S/NanoDet-Plus-m) / runner YOLOv6-N-ReLU / quality YOLOv10-N-NMS-free
sign:         single-stage YOLO11n-QCVN / runner +Lite0-crop
light:        nano-4cls-ROI+vote (optional)
seg:          Fast-SCNN / runner DDRNet-23-slim / quality PIDNet-S
depth:        NONE on-device (optional FastDepth; teacher DepthAnythingV2-S offline)
overall:      det-5Hz + track-10Hz + lane-7–10Hz + sign-2Hz (+TL-5Hz + seg-2–5Hz optional)
```

## 8. Required conclusion (Q55)

1. Can C2M run additional modern AI? **YES — small INT8 specialists time-sliced alongside stock (Bundle A) within LIKELY 0.8 TOPS, PROVEN only after §5 smoke + bench.**
2. Likely fully on-device? **det-nano + motion tracker + lane-tiny + gated sign-crops + geometry/TTC + classical ctx/heuristics.**
3. Marginal? **quality detectors (SiLU/DFL), TL-ROI, seg-fallback (one, low-Hz).**
4. Require Android/offboard? **nothing safety-critical; advanced visualisation/teachers/optional quality-headroom → phone advisory / RK3588 bench / cloud-overnight (non-safety only).**
5. Best first AI upgrade? **speed-limit recognition (2 Hz gated) + RoadIntelligence fusion → HUD.**
6. Best long-term stack? **Bundle B on-device + C-advisory offboard (E-HYBRID).**
7. Should stock remain safety baseline? **YES — all phases; stock warnings never suppressed until per-function evidence.**
8. Is replacing stock justified now? **NO — stock six-models + TTC/LDW/PCW proven; custom unvalidated; violates KEEP STOCK.**
9. Top optimization? **SCL-one-downscale+ROI → temporal+tracker → cascade-gating → INT8-backbone/FP-heads+op-cleanup → separate-proc/CPU-IPU-budget.**
10. Single first experiment after hardware? **conv-only ONNX → vendor-compiler → single-image on device (+ SCL/stride map + meminfo/dmesg/MI-codes); in parallel log `raw_adas` clips for offline bench.**

## 9. Remaining blockers

```text
vendor SDK/IPU toolchain + op/coverage + format + limits (else IPU stays UNKNOWN)
SCL multi-output/stride/format map + zero-copy lifetime proof
/proc/meminfo-iomem-buddyinfo + dmesg + MI_* codes (also closes VI-regression triage)
own VN collection (2–5k frames) + frozen holdout + legal review (NC-data, AGPL/GPL)
M4 L0–L2 + StockADASProvider observability (Phases 0–1) before any AUGMENT
```
