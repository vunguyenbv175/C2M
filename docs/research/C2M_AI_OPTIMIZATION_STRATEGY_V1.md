# C2M AI Optimization Strategy V1

**Status:** research only. Assumes separate shadow-mode process; stock pipeline untouched; full 1920x1440 never to NN.
**Date:** 2026-09-11.

## 1. Guiding principle

```text
ONE HW DOWNSCALE → MANY CHEAP ROIs → FEW GATED NNS → CPU GEOMETRY/LOGIC
```

Every technique below is ranked by expected saving on SSC8838G-class (LIKELY 0.8 TOPS). Measure, don't assume.

## 2. Input / SCL / zero-copy (HIGH PRIORITY, Q43–44)

- One HW downscale (goal): SCL `1920x1440 → 640x360 YUV420` + per-task pointer+stride crops (no copy). Never `cv::resize` 2.7 MP on ARMv7 (10–20 ms kill).
- Static ROI fractions (tune per mount; fractions of 1920x1440):
```text
lane lower-middle:   x 0.05–0.95, y 0.45–1.00 → 512x160-ish or 512x288 padded (~50% pixels saved)
vehicles central:    x 0.05–0.95, y 0.30–0.95 → 640x360
signs upper/right:   x 0.35–1.00, y 0.00–0.50 → crops on trigger only (VN right-shoulder bias)
lights upper-middle: x 0.25–0.75, y 0.00–0.45 → crops on trigger only
```
- Ladder: `zero-copy (handle/fd, single Mmap, refcount+flush)` → `one-copy` → `fallback-copy (stock GetBuf+MemcpyPa+CRingBuf)`. Stock is fallback-copy (HIGH-CONFIDENCE); prototype zero-copy only with lifetime + `buddyinfo/maps/dmesg` validation. SCL channel/port/format = UNKNOWN until SDK + live metadata.

## 3. Resolution per task (Q21)

| Task | Min | Sweet spot | Rule |
|---|---|---|---|
| cars/ped/bike near <40 m | 416x256 | 512x288–640x360 | 320x192 loses distant bikes/signs; keep aspect, no stretch |
| lane | 512x288 | 512x288–640x360 | width>512 for thin lines; height can halve (lower ROI) |
| seg | 416x256 | 512x288 | coarse mask ok |
| signs full-frame | 640x360 min | ROI/cascade, not 640x640 full | <32 px signs vanish <640w |
| TL full-frame | 640x360 min | ROI/cascade | same |
| depth | 416x256 | defer | geometry instead |

Cropped-ROI value HIGH: detector 512x288 full + native-res 64x64 upper-band crops = 2x effective resolution free.

## 4. Temporal (Q23) — run less, track more

ADAS video is sequential; no model needs 10 FPS.

```text
detector (veh/ped/bike)  5 Hz (every 2nd frame) — 200 ms = 3.3 m @60 km/h; tracker bridges; IPU 80–200 ms/nano realistic
tracker (IoU/SORT-lite) 10 Hz every frame, <2 ms CPU — predict+associate, no NN
lane seg                 7–10 Hz (every frame or 2nd) + EMA + ego-straight propagate if 5 Hz
TL classifier (crops)    5 Hz gated (intersection/urban/slow + crop present)
sign classifier          2 Hz gated (static signs; proposal or 500 ms upper-ROI scan)
fusion/TTC/warnings/JSON 10 Hz CPU geometry
fallback if saturated:   detector 3 Hz + tracker 10 Hz acceptable for logging (not actuation)
```

Smoothing: `EMA α 0.4–0.6`, KF/α-β 4-state bbox, hysteresis `enter conf>0.6×3f / exit <0.4×5f`, `TTC=median(dZ)/−vrel` 5–10f + warn 2.0 s / urgent 1.2 s + lane/brake gating. No optical/feature flow on ARMv7.

## 5. Cascaded / event-triggered (Q24, HIGH PRIORITY)

```text
cheap nano-det 5 Hz → expensive crop-classifiers (sign 64px / TL 48px MobileNet/Lite0, <5 ms IPU each, K≤3/frame)
TL branch only if speed<50 AND (urban OR stopped OR map-intersection) [default-open in eval so recall unbiased]
sign branch only if upper-ROI proposal energy OR 500 ms scan
depth/TTC-NN only if lead bbox exists (else geometry) — in practice never (no depth net)
motion gate: frame-diff<thr AND speed~0 → skip NN, reuse last (heat/batt save)
```

Measure skip-rate offline; gates default-open during eval.

## 6. Quantization (Q19)

| Task | FP16 | INT8-PTQ tensor | INT8-PTQ channel+calib | QAT? |
|---|---|---|---|---|
| large boxes | ~free | ok (−1–2 mAP) | ok | no (500–2k rep imgs) |
| small/distant/night bikes | small | sensitive (−3–8, recall↓) | recovers most | QAT or keep head FP if strict |
| signs (small, color) | ~free | MEDIUM | ok (det) / robust (crop-cls) | two-stage avoids QAT; single-stage-tiny may need it |
| TL (tiny bright, color-state) | ~free | HIGH (R/Y/G confusion) | MEDIUM | QAT or keep last-FC FP |
| lane regression | small | HIGH (jitter x2–3) | MEDIUM | YES (or seg-formulation) |
| binary lane/seg | ~free | MEDIUM (−1–3 mIoU) | ok | PTQ usually suffices |
| depth | MEDIUM | HIGH (scale drift) | HIGH | QAT+scale-inv; defer depth |

Strategy: backbone INT8, dequant heads to CPU-FP (decode/NMS/argmax/polyfit on ARM); rep-set must include night/rain/VN (not BDD-day); use quant-debugger.

## 7. Pruning / distillation / scaling (Q20, good tooling only)

Order: `low-res + nano-backbone + ReLU/nearest cleanup → PTQ → distill (large teacher→student, +2–5 mAP; mmdet/mmrazor or Ultralytics-loss) → structured channel-prune 20–40% (torch-pruning / model.prune + finetune) → QAT last`. Backbone-swap (CSP-tiny→MobileNetV2/ShuffleNetV2/GhostNet/EffLite0 via timm+ultralytics yaml), head-simplify (drop P5 if near-field only, keep P3/P4; single 1/4-res lane head, no aux), op-sub (SiLU→ReLU, Focus→stride-conv, DFL→plain, Bilinear→Nearest). Avoid NAS/mixed-precision-search/sparse/dynamic (no toolchain).

## 8. Conversion experiment order (Q42 summary; full plan in ROADMAP)

```text
PyTorch ckpt → ONNX opset11/12 fixed 1x3xHxW → onnx-simplifier → onnxruntime check →
op inventory (tools/research/ai_adas/onnx_op_inventory.py) → INT8 calibrate (night/rain/VN) →
vendor compiler → load → single-image → video bench
fail-fast: any UNSUPPORTED op / dynamic shape / NMS-in-graph / grid_sample/deform/transformer → strip or reject model
```

Prove with 10-line conv-only ONNX first (toolchain proof before accuracy work).

## 9. CPU vs IPU split (Q25)

See HARDWARE doc §6. Restate as rule: IPU = conv-only INT8; everything else (decode/NMS/argmax/fit/tracker/KF/TTC/hysteresis/JSON/GPS/ring/watchdog/IO/encode/IPC/upload) = CPU/HW-blocks. Cap custom IPU ≤60% duty, RSS ≤120 MB, kill-switch on hang/OOM.

## 10. Top 5 techniques (for final report)

```text
1. HW SCL one-downscale + task ROIs/crops (kills 2.7 MP CPU resize; ~2x effective res free)
2. Temporal sub-sampling + CPU tracker/EMA/KF/hysteresis (5 Hz det + 10 Hz track ≈ 10 Hz UX)
3. Cascaded/event-gated classifiers (2 Hz sign / 5 Hz TL on K≤3 crops; context+motion gates)
4. INT8-backbone + FP-heads + ReLU/nearest/Focus-strip + per-task PTQ/QAT choice
5. Separate-process isolation + CPU/IPU budgeting + raw-boxes/CPU-NMS (protects stock, bounds tail)
```
