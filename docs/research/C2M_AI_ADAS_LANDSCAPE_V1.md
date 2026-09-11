# C2M AI ADAS Landscape V1 — Model Survey + Shortlist

**Status:** research / analysis only. No firmware modification, no Candidate A/B change, no Candidate C.
**Baseline:** MINIEYE/UTOUR C2M, SigmaStar SSC8838G, ARMv7-A userspace (VFPv3-D16, no NEON evidence), stock `raw_adas` 1920x1440 @ ~10 Hz (`vehicle_run_freq=10`), KEEP STOCK + ENHANCE, shadow-mode first.
**Method:** web survey (official repos/papers/vendor-derived news where datasheet NDA-blocked) + local static reverse (`docs/reverse/`, `docs/firmware_en_vi/`, `docs/master/`). Accuracy numbers from different papers are NOT directly comparable; see §35 normalization. `UNKNOWN` means not verified, not guessed.
**Date:** 2026-09-11. Versions pinned per-model below.

---

## 0. Terminology / evidence tags

```text
CONFIRMED — byte-measured local evidence or official repo/paper statement fetched
LIKELY    — strong secondary evidence (e.g. multiple CN vendor-news reports), needs datasheet/SDK proof
UNKNOWN   — not verified; do not design safety logic on it
HIGH / MEDIUM / LOW / NOT PRACTICAL — C2M feasibility (compute+memory+conversion, not accuracy alone)
LOW / MEDIUM / HIGH — operator/conversion risk for SigmaStar-class INT8 NPU
```

Stock facts reused (CONFIRMED): six embedded blobs `d0/v_a/v_t/p_r/road/tl` byte-identical EN vs VI; `m0` AES-128 directory valid; +17,862 B VI growth in 7 interstitial gaps; `raw_adas` writer (`CRingBuf("fortest","raw_adas",0x400,2,0,0)`, `RequestWriteFrame(...,0,0x48,1)`) instruction-identical EN vs VI; ADAS flags `--image_width=1920 --image_height=1440 --vehicle_run_freq=10 --npu_buffer_size=5620000 --enable_tsr=false --camera_input=ringbuf_vehicle --ringbuf_name=raw_adas`; CPU attrs `armv7-a / VFPv3-D16 / hard-float / no Advanced_SIMD`; kernel 4.9.227; glibc 2.30. See `docs/reverse/ADAS_PACKAGE_LOADER_V1.md`, `CARDV_RAW_ADAS_CONTRACT_V1.md`, `docs/firmware/TARGET_ABI.md`, `docs/firmware_en_vi/03_ADAS_ENGINE_TSR_AND_REGRESSION.md`, `05_CAMERA_MEDIA_IMU.md`.

Hardware summary (detail in `C2M_AI_HARDWARE_FEASIBILITY_V1.md`): SSC8838G LIKELY = dual Cortex-A53 1.2 GHz + 0.8 TOPS NPU + DDR3 up to 16 Gb + Caffe/ONNX/TF SDK (CN vendor-news, not official datasheet — treat TOPS/SDK as LIKELY until SDK in hand). No INT8/FP16/op-list/input-limit claim is CONFIRMED.

---

## 1. What open / obtainable ADAS models exist? (Q1)

By class (detail §§A–14, matrix in `C2M_AI_ADAS_MODEL_MATRIX_V1.md`):

```text
lane:        UFLDv2-R18/R34, LaneATT-R18/R34, CLRNet-R18/DLA34, CondLaneNet-S, YOLOP, YOLOPv2, HybridNets
detection:   YOLOv5n/s, YOLOv6-N/S, YOLOv7-tiny, YOLOv8n/s, YOLOv9t/s, YOLOv10-N/S, YOLO11-N/S,
             YOLOX-Nano/Tiny, NanoDet-Plus-m/m-1.5x, PP-PicoDet-XS/S/M/L, MobileNet-SSD, RT-DETR-R18/R34
tracking:    SORT, ByteTrack, OC-SORT, DeepSORT (+BoT-SORT/C-BIoU noted, not shortlisted)
sign:        single-stage YOLO-nano (TT100K/Mapillary-pretrained) vs two-stage (nano detector + EfficientNet-Lite0/GTSRB classifier)
light:       tiny 4-class detector (red/yellow/green/off) + ROI + temporal vote; classical blob rejected alone
seg:         Fast-SCNN, BiSeNetV1/V2, PIDNet-S/M/L, DDRNet-23-slim/23, YOLOP/HybridNets heads
depth:       FastDepth, MonoDepth2-R18, Lite-Mono-tiny, DepthAnythingV2-S, MiDaS-small
weather:     classical stats (brightness/histogram/edge-density/dark-channel) vs tiny CNN
scene:       heuristic (detector+lane+GPS/nav), no dedicated CNN recommended
hazard:      same detector + extra classes (cone/stopped/hazard) vs specialized head vs segmentation
DMS:         NOT APPLICABLE (forward-only, no inward camera)
```

Total evaluated in this study: **38 model/config entries** (see evidence JSON). No weights downloaded into repo.

## 2. Which functions can be added beyond stock C2M? (Q2)

Stock CONFIRMED/HIGH-CONFIDENCE capability: vehicles + TTC/headway + FCW/HMW/VB/SAG warning classes, pedestrians (`is_danger`→PCW, `have_bike` attr), lanes (`deviate_state`→LDW, `lanelines`, `turn_radius`), TSR code present but `--enable_tsr=false` default (runtime state UNKNOWN), TLR code (`TlrDetect/TlrCnnCls/GreenWarning`) present but WAV missing → capability, not proven feature. See `docs/firmware_en_vi/03_ADAS_ENGINE_TSR_AND_REGRESSION.md`.

Addable value (ranked, §38–39 detail):

```text
1. speed-limit recognition (stock disabled/UNKNOWN → greenfield, HUD-ready) — HIGHEST VALUE / LOWEST RISK
2. navigation/ADAS fusion (RoadIntelligence + VietMap + OsmRoadProvider, no NN) — HIGH VALUE / NO NPU
3. motorcycle/pedestrian small-object + night/rain robustness via fine-tuned nano detector — MEDIUM-HIGH
4. road-hazard classes (cone/stopped-vehicle/pothole-debris) inside same detector — MEDIUM
5. traffic-light advisory (ROI + vote, optional) — MARGINAL, gate behind 1–4
6. drivable-area fallback + weather-adaptive thresholds + scene tags — LOW-COST AUX, not standalone
7. monocular depth — NOT RECOMMENDED on-device (geometry/TTC instead)
8. DMS — NOT APPLICABLE
```

## 3–6. Size / on-device / conversion / external-compute summary (Q3–Q6)

| Class | Fully on-device plausible (0.8 TOPS INT8, time-sliced)? | Needs conversion/quant? | Needs external compute? |
|---|---|---|---|
| lane (UFLDv2-R18 800x320-class ROI, LaneATT-R18) | YES (5–10 Hz ROI) | YES: ONNX static + simplify + INT8 PTQ, NMS/anchor on CPU | NO |
| detection nano (YOLOX-Nano 416, NanoDet-Plus-m 320/416, PicoDet-S 320/416, YOLOv6-N-ReLU 416/512) | YES (3–5 Hz) + tracker 10 Hz | YES: ReLU swap, Focus/DFL strip, raw-boxes + CPU NMS | NO |
| detection quality (YOLOv10-N 512/640 NMS-free, YOLOv8n/11-N 512) | MARGINAL (needs SiLU/DFL LUT proof) | YES + QAT likely | fallback Android if fails |
| tracker (ByteTrack/OC-SORT/SORT motion-only) | YES (CPU, 10 Hz, <2 ms) | NO (C++/Python, no NN) | NO |
| TTC geometry (pinhole + height/ground-plane + KF + bbox-expansion check) | YES (CPU) | NO | NO |
| sign single-stage nano (10–20 QCVN classes, 640 or ROI-crop) | YES @ 2 Hz gated | YES + VN fine-tune | NO |
| sign two-stage (+EfficientNet-Lite0 48–64px crop classifier) | YES (only on trigger, K≤3 crops) | YES | NO |
| traffic light (4-class nano + upper-center ROI + 5-frame vote) | MARGINAL/OPTIONAL @ 5 Hz gated | YES | drop first if budget tight |
| seg fallback (Fast-SCNN / DDRNet-23-slim / PIDNet-S, 320x192–512x288 ROI, 2–5 Hz) | MARGINAL (one only, lowest-Hz) | YES | NO (or Android visualisation) |
| depth (FastDepth/MonoDepth2) | NOT RECOMMENDED on-device | YES + scale/temporal fix | offline teacher only |
| weather/scene | YES (classical stats + heuristics, CPU) — no CNN needed | NO | NO |
| hazard extra classes | YES (same detector, +1–3 cls channels) | YES (fine-tune) | NO |
| mid/large transformers (CLRNet-iterative, CondLane, RT-DETR, YOLO-World, DepthAnything, MiDaS-trans) | NOT PRACTICAL | HIGH risk | NO — reject |

Rule: no model runs on full 1920x1440; always via SCL downscale (640x360-class) + task ROIs + crops. Full-frame 640x640 only if NPU proves headroom.

## A. Lane detection

| Model | Source / ver | License | Input (reported) | Metric (reported, not comparable) | Params / FLOPs | Verdict |
|---|---|---|---|---|---|---|
| UFLDv2-R18 | cfzd/UFLDv2, TPAMI22 (2022), MIT | MIT | 800x320 typical (UNKNOWN exact) | CULane F1 75.0, TuSimple 96.11 | UNKNOWN (must measure) | **BEST BASELINE + WINNER** — row/col classifier, no deform/grid_sample, `deploy/pt2onnx.py` easy, INT8 LOW risk |
| UFLDv2-R34 | same | MIT | same | CULane 76.0 | UNKNOWN | runner-up if R18 misses; ~1.8x cost |
| UFLDv2-MobileNetV3 | TSY845 fork (2023), MIT | MIT | same | TuSimple 96.48 | UNKNOWN | ULTRA-LIGHT candidate, CULane training harder — eval |
| LaneATT-R18 | lucastabelini/LaneATT, CVPR21, MIT | MIT | UNKNOWN | CULane 75.13, 250 FPS GPU | UNKNOWN | **runner-up** — better occlusion, needs anchor-gather+NMS port (MED risk) |
| LaneATT-R34 | same | MIT | UNKNOWN | CULane 76.68 | UNKNOWN | quality alt, MED risk |
| CLRNet-R18/DLA34 | Turoad/CLRNet, CVPR22, Apache-2.0 | Apache-2.0 | UNKNOWN | CULane F1@50 79.58/80.47 | UNKNOWN | most accurate, **reject on-device** (ROIGather/bilinear + iterative refine = HIGH risk) |
| CondLaneNet-S/M/L | aliyun, ICCV21, Apache-2.0 | Apache-2.0 | UNKNOWN | CULane 78.14–79.48; S 10.2G/M 19.6G/L 44.8G | S 10.2G known | **reject** (conditional conv, dynamic kernels, HIGH) |
| YOLOP (lane head) | hustvl/YOLOP (2022), MIT | MIT | 640x384 typical | BDD lane acc 70.5 | 7.9M | MED — only if multitask already chosen |
| YOLOPv2 | CAIC-AD/YOLOPv2 (2022), MIT | MIT | 640 | BDD lane acc 87.3 | 38.9M | **reject** (5x size) |
| HybridNets | datvuthanh/HybridNets (2022), MIT | MIT | 640x384 | BDD lane acc 85.4, 15.6G, 12.83M | 12.83M/15.6G | MARGINAL (EfficientNet+BiFPN SiLU pain) |

**Lane winner: UFLDv2-R18; runner-up LaneATT-R18; ultra-light: UFLDv2-MobileNetV3.** Reason: only row/col-classification family fits INT8 NPU + ROI + CPU-simple postprocess; CLRNet/CondLane accuracy does not compensate for deform/sampling ops on 0.8 TOPS. VN note: CULane/TuSimple lack VN chaotic markings/rain-night — fine-tune on shadow-logged VN clips; prefer segmentation fallback (§9) over bigger lane net.

## 4. Object detection (detail)

Core table (COCO val2017 mAP 50:95 unless noted; GPU numbers NOT transferable to C2M — for relative ordering only):

| Model | License | Params / FLOPs @size | COCO mAP | NPU risk | Note |
|---|---|---|---|---|---|
| YOLOv5n 640 | AGPL-3.0 (Enterprise needed for closed product) | 1.9M / 4.5G | 28.0 | MED (Focus+SiLU+anchors) | mature INT8/TFLite/NCNN, fixable |
| YOLOv6-N 640 | GPL-3.0 | 4.7M / 11.4G (v3) | 37.5 | LOW (ReLU+RepOpt) / MED (SiLU+DFL) | **best YOLO INT8 story (RepOpt PTQ/QAT: N 34.8 vs 35.9)** |
| YOLOv7-tiny 416/640 | GPL-3.0 | 6.2M / 5.8G@416 | 35.2@416 | MED (Leaky/E-ELAN) | no advantage vs v6-N/v8n |
| YOLOv8n 640 | AGPL-3.0 | 3.2M / 8.7G | 37.3 | MED-HIGH (SiLU+DFL softmax) | PTQ −1–2 mAP, QAT for DFL |
| YOLOv9t 640 | GPL-3.0 (orig) / MIT (re-impl) | 2.0M / 7.7G | 38.3 | HIGH (GELAN, no quant recipe) | reject first |
| YOLOv10-N 640 | AGPL-3.0 | 2.3M / 6.7G | 38.5–39.5 | MED (SiLU but **NMS-free**) | **best modern if SiLU LUT ok** — saves ARM NMS jitter |
| YOLO11-N 640 | AGPL-3.0 | 2.6M / 6.5G | 39.5 | MED-HIGH (C2PSA attention) | best acc, worst NPU fit in class |
| YOLOX-Nano 416 | Apache-2.0 | 0.91M / 1.08G | 25.8 | **LOW** (ReLU-swappable, no DFL/Focus) | **BEST BASELINE** commercial-friendly |
| YOLOX-Tiny 416 | Apache-2.0 | 5.06M / 6.45G | 32.8 | LOW-MED | quality step |
| NanoDet-Plus-m 320/416 | Apache-2.0 | 1.17M / 0.9G@320, 1.52G@416 | 27.0@320, 30.4@416 | **LOW** (ShuffleNetV2+GhostPAN, 1.2 MB INT8) | **BEST ULTRA-LIGHT** |
| NanoDet-Plus-m-1.5x 416 | Apache-2.0 | 2.44M / 2.97G | 34.1 | LOW | quality ultra-light |
| PP-PicoDet-S 320/416 | Apache-2.0 | 0.99M / 0.73G@320, 1.24G@416 | 27.1@320, 30.6@416 | **LOW** (+NPU variant, PaddleLite 150 FPS ARM) | **co-winner ultra-light**; Paddle→ONNX friction only downside |
| PP-PicoDet-M 416 | Apache-2.0 | 2.15M / 2.5G | 34.3 | LOW | balanced alt |
| PP-PicoDet-L 640 | Apache-2.0 | 3.3M / 8.91G | 40.9 | LOW-MED | too big for first spin |
| MobileNet-SSD/V3-SSDLite 320 | Apache-2.0/MIT/BSD | ~3–5M / ~1–2G | ~21–22 COCO | LOW convert, HIGH accuracy risk | **reject as base** (10–15 mAP behind, weak small/night) |
| RT-DETR-R18/R34 640 | Apache-2.0 | 20M/60G, 31M/92G | 46.5/48.9 | **HIGH** (deformable attn, LayerNorm, queries) | **reject** (10x FLOPs, unsupported) |
| YOLO-World-tiny | GPL-3.0 | ~8–13M | zero-shot only | HIGH (CLIP+dynamic vocab) | reject unless open-vocab needed |

**Detector winner: YOLOX-Nano 416 ReLU (baseline) — tie with PP-PicoDet-S / NanoDet-Plus-m for ultra-light depending on toolchain (Paddle vs PyTorch/ONNX). Runner-up: YOLOv6-N-ReLU-RepOpt (best quant story) ; quality: YOLOv10-N (NMS-free).** Reason: usefulness/compute — 0.9–1.5G vs 6–9G for +7–10 mAP that vanishes under INT8 + VN domain gap; Apache-2.0 avoids AGPL/GPL closed-product trigger (legal review still required). VN: COCO under-represents dense motorbike occlusion + rear dashcam view + cone (no COCO cone) → fine-tune 8–10 classes on BDD100K + 2–5k VN boxes; keep P3/8 head; 416 loses distant bikes → prefer 512 + ROI crops over 640 full-frame.

## 5. Forward collision / tracking (detector+tracker+TTC, not monolith)

**Do monolithic FCW nets? No.** Implement `detector → tracker → monocular distance/TTC (geometry)` with deterministic warning logic (§45). Reasons: failure isolation, tunable NHTSA-style thresholds, no extra NN cost, works in shadow mode.

| Tracker | License | MOT17 (ref) | CPU | Verdict |
|---|---|---|---|---|
| SORT | MIT | MOTA 74.6 / IDF1 76.9 | negligible (KF+Hungarian IoU) | OK baseline, fragile occlusion |
| ByteTrack | MIT | MOTA 80.3 / IDF1 77.3 / HOTA 63.1 (V100 30 FPS) | negligible + NMS only | **RANK 1 (tie)** — 2-stage BYTE recovers low-conf night/rain, threshold-robust |
| OC-SORT | MIT | MOTA 78.0 / IDF1 77.5 / HOTA 63.2; DanceTrack 55.1 vs 47.3 | negligible | **RANK 1 (tie)** — better non-linear/motorbike-weave, drop-in |
| DeepSORT | GPL-2/3 (fork variance) | MOTA 75.4 / IDF1 77.2, 13.5 FPS vs 29.6 | HIGH (ReID CNN per crop) | only if long re-ID proven needed |
| BoT-SORT-lite / C-BIoU | GPL-3.0 / mixed | +CMC gains | small (ECC) | add ECC CMC for bumps if Byte/OC flickers |

Appearance embeddings? **Unnecessary for dashcam FCW.** Radial motion + 0.5–2 s horizon needs stable d/dt per lead, not minutes-long re-ID. BYTE-without-ReID beats DeepSORT-with-ReID on MOT17 val; ReID only wins on BDD-driving with large ego-motion + low fps (reserve 64-d OSNet-tiny on 1/4 crops only if ID-switch causes TTC flicker in motorbike swarms).

TTC rank (reliability/compute): **(1) calibration+geometry `Z=f·H/h`, `TTC=Z/−dZ/dt` + KF (tiny CPU, anchored, tunable) + (2) bbox-expansion looming `h/dh/dt` as fallback/check → production hybrid; (3) optical flow (heavy, night/rain-fragile, needs engine); (4) depth-DNN (extra net, scale-ambiguous — not justified).** Use median dZ over 5–10 frames + hysteresis (warn 2.0 s, urgent 1.2 s) + lane/brake gating; never single-frame threshold.

## 6. Pedestrian / cyclist collision warning

Standard detector **sufficient as base**; dedicated ped model **not justified first**. Instead: (a) keep `person` + `motorcycle/bicycle` heads with P3 retained, (b) fine-tune on BDD100K-night/rain + VN motorbike data (small-object mosaic + photometric + rain aug), (c) add crossing-pedestrian logic (lateral velocity + road mask) on CPU, (d) `have_bike`-style attribute via class co-occurrence (person+motorcycle IoU), not a new net. Dedicated small-object ped nets (e.g. drained from CrowdHuman) only if PCW miss-rate on shadow logs proves gap. Night/occlusion handled by ByteTrack low-conf recovery + EMA + hysteresis, not by bigger net.

## 7. Traffic sign recognition

**Winner: single-stage YOLO-nano (YOLO11n or YOLOv8n, 640 or ROI) with merged 10–20 QCVN classes — runner-up: two-stage (nano detector 1–4 superclasses + EfficientNet-Lite0 48–64px crop classifier) only if digit confusion persists.**

- Two-stage pros: higher recall on tiny signs + 95–99% GTSRB classifier in papers; cons: 2 NPU passes + crop/resize/sync + pipeline complexity.
- Single-stage pros: 1 pass, simpler shadow eval, QCVN-direct; cons: speed-limit digit confusion (50/60/80) at distance.
- Ship single-stage first (COCO → Mapillary/TT100K research-weights pre-train → VN fine-tune); add Lite0 classifier on K≤3 crops at 2 Hz only if field confusion proven. Avoid MobileNetV3-Small INT8 (hard-swish/SE collapse; use EfficientNet-Lite0 ReLU6, −0.7% PTQ). Never ship 43/221-class heads.
- Datasets: GTSRB (51k crops/43 cls, research-only), GTSDB (900 imgs, research-only), TT100K (100k pano/30k instances/221 cls, CC-BY-NC — commercial contact required), Mapillary MTSD (100k imgs/320k signs/313–400 cls, CC BY-NC-SA — commercial agreement required), LISA-US (MUTCD, low VN relevance), DFG-Slovenia (6957 imgs/200 cls, CC BY-NC-SA), VN sets (1–4k imgs/29–100 cls, mixed/UNKNOWN — must re-license/collect own). VN follows Vienna/QCVN 41:2019 (like DE/CN/SI), not US MUTCD — prioritize EU/CN pre-train + own VN collection. All SOTA sign datasets are NON-COMMERCIAL → production needs own VN collection + legal review (weights lower risk than data redistribution, still review).

## 8. Traffic light detection

4-class tiny detector (red/yellow/green/off; arrows collapsed initially) on **upper-center ROI** + confidence + N-frame majority + map/GPS gating, 5 Hz gated. Worth on C2M? **MARGINAL — deprioritize behind signs/lane/FCW.** Reasons: <10 px beyond 80 m, night glare, LED flicker, VN occluded/horizontal/countdown variance; INT8 tiny-object drop worst here (−3–7% mAP nano, worse under noise). Classical blob alone rejected (tail-light confusion). No separate paper model — reuse YOLO-nano head (shared backbone with signs or separate 320–416 head). Do not promise violation/countdown. Drop first under NPU pressure.

## 9. Drivable area / road segmentation

Value vs cost: **useful as lane fallback + free-space context + hazard extent, but second-order behind lane+objects.** Run ONE tiny binary model at LOW Hz on ROI (320x192–512x288, 2–5 Hz), not full-res Cityscapes.

| Model | License | Params | Cityscapes (reported) | Risk | Verdict |
|---|---|---|---|---|---|
| Fast-SCNN | Apache-2.0 (impl) | 1.11M | 68.0 mIoU @123.5 FPS TitanXp 1024x2048 | LOW (pure CNN, depthwise+nearest) | **WINNER fallback** — cheapest, sufficient for edge/lane-fallback |
| DDRNet-23-slim | MIT | 5.7M / 36.3G@2048x1024 | val 77.8 / test 77.4 | LOW-MED (DAPPM pooling ok) | runner-up — Comma10K road prior |
| PIDNet-S | MIT | 7.6M / 47.6G | test 78.6 @93 FPS 3090 | LOW-MED (drop boundary head at infer) | quality pick if NPU fits |
| BiSeNetV1/V2 | mixed/UNKNOWN | 5.8M (V1) | 71.4/75–78 | LOW | superseded, ok if SDK sample exists |
| YOLOP/HybridNets seg heads | MIT | 7.9M/12.83M | BDD da 91.5/90.5 | LOW-MED but large | only if multitask already running |

## 10. Monocular depth

**Be conservative: no depth net recommended for on-device TTC.** All are relative/disparity unless stereo-scaled; flicker + scale drift break TTC; visually good ≠ geometrically stable.

| Model | License | Edge evidence | TTC use |
|---|---|---|---|
| FastDepth (MobileNet+NNConv5, 224x224, 0.37G MACs, NYU RMSE 0.604, TX2 CPU 37 ms / GPU 5.6 ms) | MIT | HIGH feasibility | MED — only if fine-tuned NYU→driving + ground-plane scale + EMA |
| MonoDepth2-R18 (640x192, KITTI AbsRel 0.115 mono / 0.106 mono+stereo) | **non-commercial** | HIGH feasibility | BEST potential if mono+stereo + mask + smoothing — check product license |
| Lite-Mono tiny | UNKNOWN (repo 404s, attention LGFI) | MARGINAL | prefer FastDepth/MonoDepth2 (attention NPU pain) |
| DepthAnythingV2-S (24.8M, ViT-S+DPT, 518px) | Small Apache-2.0; B/L CC-BY-NC | reject on-device | offline teacher/auto-labeler only |
| MiDaS-small (21M lite-CNN; Swin2/LeViT 42–51M trans) | MIT | borderline (small-256 visualisation only) | not for TTC (relative, flickery) |

If TTC needed: geometry (§5) first; depth only as offline labeler.

## 11. Road hazard detection

**Same generic detector + extra classes first** (`car/truck/bus/motorbike/bicycle/person/cone/stopped-vehicle/road-hazard(pothole/debris)` = 8–10 cls; split pothole/debris/flood only after >2k labels each). Minimal NPU delta (cls channels). Specialized head only if hazard AP proves gap; segmentation only if boundary needed for path planning (2–4x FLOPs, decoder-hostile). Datasets: RDD2020 (26k/31k boxes D00/D10/D20/D40), RDD2022 (47k/55k, 6 countries), Pothole-600 (+EdmCrack/CPRID; SHREC Mix 4340 pairs), Kaggle/Roboflow pothole-665 (VOC); flood box set: no standard — custom collect (UNKNOWN standard).

## 12. Driver monitoring — NOT APPLICABLE TO CURRENT HARDWARE

Forward-only dashcam cannot see eyes/face; DMS needs inward RGB/IR + 940 nm LEDs + landmarks/gaze (EU 2024/Euro NCAP pattern; dual-channel JC261-style hardware). Do not claim fatigue/distraction/phone from road view; weave/proxy unreliable in VN mixed traffic. Needs hardware variant with cabin IR cam.

## 13. Weather / visibility classification

**No CNN — classical stats win cost/value.** Day/night RF on mean RGB/HSV 97.8% (µs CPU); fog via FADE/dark-channel/saturation/edge-density (Canny/extinction) 3–4 levels; rain via wiper-flag (if CAN) + specularity + contrast; glare via saturated blob + sun/GPS time. Purpose: adapt thresholds (`night/rain/fog → −0.1 lane/sign conf, +smoothing, glare mask, exposure note`), tag clips for retraining. Tiny CNNs plateau ~78% (A-BDD) + overfit + poor cross-domain (Mapillary 73% → Woodscape 40%). Add MobileNetV3-Small only if customer demands explicit label — low ROI. Commercial-safe if re-implemented (papers open).

## 14. Scene intelligence

**No separate model — infer from detector/lane/GPS/nav:** highway vs urban (speed+map+lane-count+density), tunnel (luminance+headlight+GPS-loss+walls), intersection (stop-line/crosswalk+TL+crossing+nav-maneuver), parking (ego~0+parked+lot-marks), roadworks (orange cones/barriers + TTC signs via sign-detector +2–3 classes). Saves ~1–5M params + DDR. BDD taggers only 50–60% (DLA-34); intersection CNN+LSTM fragile night/rural + video memory; ROADWork needs VLM (Detic 2.9–3.7 AP). Log heuristic label.

## 15. Multi-task vs separate models — VERDICT: SEPARATE SMALL SPECIALISTS (time-sliced)

| Dim | 1x multi-task (YOLOP/YOLOPv2/HybridNets) | N x tiny specialists |
|---|---|---|
| runtime | 1 backbone+3 heads; YOLOP 41 FPS desktop / 23 TX2 (far stronger than 0.8 TOPS) — will not transfer | each 0.1–0.8 GMAC; different Hz; skip idle; lower avg load |
| memory | 1 blob (5–15 MB INT8) + 1 arena — better peak | N blobs — worse concurrent, better time-sliced |
| conversion | HIGH — one exotic op blocks whole system | LOW-MED each — failure isolates, rest ships |
| isolation | one crash/OOM kills all | one fallback/disabled, others live |
| maintainability | coupled loss, joint panoptic labels (BDD all-3), sign update regresses lane | independent versioning/datasets/thresholds |
| fine-tune (VN bike/night-rain) | needs panoptic labels (scarce) | detector on BDD+VN alone; lane on CULane alone |
| shadow-mode | all-or-nothing Hz | per-task on/off + Hz throttle to protect stock |

**Do not default to multi-task elegance.** Only revisit if vendor demo proves YOLOP-tiny INT8 on this exact IPU. Starting set: `det-nano (primary) + lane-tiny (secondary) + sign/TL crop-classifiers (cascaded)` — skip drivable seg initially (lane+objects cover 80% LDW/FCW).

---

## 16–35. Pointers (detail in sibling docs)

Hardware/conversion/quant/pruning/resolution/ROI/temporal/cascade/CPU-IPU/offboard/fusion/arbitration/logging/active-learning/datasets/VN/benchmark-matrix/bundles → `C2M_AI_HARDWARE_FEASIBILITY_V1.md`, `C2M_AI_OPTIMIZATION_STRATEGY_V1.md`, `C2M_AI_ADAS_ARCHITECTURE_V1.md`, `C2M_AI_DATA_FINETUNE_PLAN_V1.md`, `C2M_AI_ADAS_MODEL_MATRIX_V1.md`, `C2M_AI_ADAS_ROADMAP_V1.md`. Final ranking §51 + verdict §52 + conclusion §55 in ROADMAP.
