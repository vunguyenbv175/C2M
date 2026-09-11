# C2M AI ADAS Model Matrix V1

**Status:** research only. Accuracy metrics from different benchmarks are NOT comparable — see `BENCHMARK NOTE`. `UNKNOWN` = not verified in fetched source, not estimated.
**Device lens:** SSC8838G (LIKELY dual A53 1.2 GHz + 0.8 TOPS NPU); ARMv7-A VFPv3-D16 userspace; INT8 IPU assumed, op list UNKNOWN — risk scores assume vanilla Conv/BN/ReLU/Pool/Concat/ResizeNearest-only NPU.
**Date:** 2026-09-11. Columns per §50.

## BENCHMARK NOTE (read before comparing)

```text
COCO mAP      = COCO val2017 AP 50:95 single-scale unless noted; GPU latency NOT transferable to C2M
CULane F1     = F1@50 (IoU 0.5) official; mF1 = mean over thresholds (do not mix with F1@50)
TuSimple F1   = highway-only, easy; high 96–98 hides CULane gaps
Cityscapes    = mIoU 19-class test; GPU FPS NOT transferable
MOT17 MOTA/IDF1/HOTA = tracking test; detector-coupled
Edge benchmark column = fetched ARM/GPU numbers where available, else UNKNOWN — never infer C2M FPS from them
```

## MATRIX

| MODEL | TASK | SOURCE | LICENSE | PARAMETERS | MODEL SIZE | INPUT SIZE | FLOPs/MACs | METRIC | BACKBONE | EXPORT ONNX | INT8 | OPERATOR RISK | C2M IPU FEAS. | C2M CPU FEAS. | ANDROID OFFLOAD FEAS. | EXPECTED VALUE | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UFLDv2-R18 | lane | cfzd/Ultra-Fast-Lane-Detection-v2, 2206.07389, 2022 | MIT | UNKNOWN | UNKNOWN | 800x320 typical (UNKNOWN exact) | UNKNOWN | CULane F1 75.0, TuSimple 96.11 | ResNet18 | EASY (deploy/pt2onnx.py) | GOOD (PTQ ok) | LOW | HIGH | LOW (fallback only) | HIGH | HIGH — lane baseline | row/col classifier, 300+ FPS GPU claim; first lane spin |
| UFLDv2-R34 | lane | same | MIT | UNKNOWN | UNKNOWN | same | UNKNOWN | CULane 76.0, TuSimple 96.24 | ResNet34 | EASY | GOOD | LOW | HIGH | NOT PRACTICAL | HIGH | MEDIUM | ~1.8x R18; only if R18 misses |
| UFLDv2-MobileNetV3 | lane ultra-light | TSY845 fork, 2023 | MIT | UNKNOWN | UNKNOWN | same | UNKNOWN | TuSimple 96.48 | MobileNetV3-Large | EASY | GOOD | LOW | HIGH | MEDIUM | HIGH | MEDIUM | CULane training harder; eval as ultra-light |
| LaneATT-R18 | lane | lucastabelini/LaneATT, 2010.12035, 2021 | MIT | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | CULane 75.13, TuSimple 96.71, 250 FPS GPU | ResNet18 | MEDIUM (anchor gather + NMS port) | GOOD | MEDIUM | MEDIUM-HIGH | LOW | HIGH | HIGH | better occlusion; runner-up |
| LaneATT-R34 | lane | same | MIT | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | CULane 76.68, 171 FPS GPU | ResNet34 | MEDIUM | GOOD | MEDIUM | MEDIUM | NOT PRACTICAL | HIGH | MEDIUM | heavier alt |
| CLRNet-R18 | lane | Turoad/CLRNet, 2203.10350, 2022 | Apache-2.0 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | CULane F1@50 79.58 | ResNet18 | HARD | MEDIUM (QAT) | HIGH (ROIGather/bilinear, iterative) | LOW | NOT PRACTICAL | MEDIUM | LOW on-device | SOTA acc, NPU-hostile; reject first |
| CLRNet-DLA34 | lane | same | Apache-2.0 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | CULane F1@50 80.47 | DLA34 | HARD | MEDIUM | HIGH | LOW | NOT PRACTICAL | MEDIUM | LOW | reject |
| CondLaneNet-S | lane | aliyun/conditional-lane-detection, 2105.05003, 2021 | Apache-2.0 | UNKNOWN | UNKNOWN | UNKNOWN | 10.2G | CULane 78.14 | ResNet18 | HARD (conditional/dynamic kernels) | POOR | HIGH | LOW | NOT PRACTICAL | LOW | LOW | reject |
| YOLOP-full | lane+det+seg multi | hustvl/YOLOP, 2022 | MIT | 7.9M | UNKNOWN | 640x384 typical | UNKNOWN | BDD lane 70.5, da 91.5, det 76.5@50 | CSPDarknet | EASY (export_onnx.py) | MEDIUM | LOW-MED | MEDIUM | NOT PRACTICAL | MEDIUM | MEDIUM | only if multitask chosen |
| YOLOPv2 | multi | CAIC-AD/YOLOPv2, 2208.11434, 2022 | MIT | 38.9M @640 | UNKNOWN | 640 | UNKNOWN | BDD lane 87.3, da 93.2, det 83.4@50 | CSP+ELAN | EASY | MEDIUM | LOW (but too large) | LOW | NOT PRACTICAL | LOW | LOW | 5x YOLOP; reject weak NPU |
| HybridNets | multi | datvuthanh/HybridNets, 2203.09035, 2022 | MIT | 12.83M | UNKNOWN | 640x384 | 15.6G | BDD det 77.3, lane 85.4, da 90.5 | EfficientNet-B3+BiFPN | EASY (export.py) | MEDIUM (SiLU/BiFPN) | MEDIUM | MARGINAL | NOT PRACTICAL | MEDIUM | MEDIUM | better than YOLOP, NPU pain |
| YOLOv5n 640 | object | ultralytics/yolov5, 2021 | AGPL-3.0 (Enterprise for closed) | 1.9M | ~3.8 MB FP16 est (UNKNOWN exact) | 640 | 4.5G | COCO 28.0 (45.7@50) | CSP-Darknet-n | EASY | GOOD | MEDIUM (Focus+SiLU) | MEDIUM | LOW | HIGH | MEDIUM | mature; legal gate |
| YOLOv6-N 640 | object | meituan/YOLOv6, 2022 | GPL-3.0 | 4.7M | UNKNOWN | 640 | 11.4G | COCO 37.5 | RepVGG-Eff | EASY | EXCELLENT (RepOpt PTQ/QAT 34.8 vs 35.9) | LOW (ReLU) / MED (SiLU+DFL) | MEDIUM-HIGH (ReLU) | LOW | HIGH | HIGH | best quant story; runner-up |
| YOLOv7-tiny 416 | object | WongKinYiu/yolov7, 2022 | GPL-3.0 | 6.2M | UNKNOWN | 416 | 5.8G | COCO 35.2@416 | E-ELAN | EASY | MEDIUM (Leaky) | MEDIUM | MEDIUM | LOW | HIGH | MEDIUM | no advantage vs v6-N |
| YOLOv8n 640 | object | ultralytics/ultralytics, 2023 | AGPL-3.0 | 3.2M | UNKNOWN | 640 | 8.7G | COCO 37.3 | C2f+CSP | EASY (export) | MEDIUM (PTQ −1–2, DFL needs QAT) | MED-HIGH (SiLU+DFL) | MARGINAL | LOW | HIGH | HIGH if SiLU ok | quality candidate |
| YOLOv9t 640 | object | WongKinYiu/yolov9, 2024 | GPL-3.0 / MIT re-impl | 2.0M | UNKNOWN | 640 | 7.7G | COCO 38.3 | GELAN+PGI | EASY | UNKNOWN (no recipe) | HIGH | LOW | NOT PRACTICAL | MEDIUM | LOW | reject first |
| YOLOv10-N 640 | object | THU-MIG/yolov10, 2024 | AGPL-3.0 | 2.3M | UNKNOWN | 640 | 6.7G | COCO 38.5–39.5 | C2fCIB+SCDown | EASY | GOOD FP16, INT8 UNKNOWN | MEDIUM (SiLU, NMS-free helps) | MARGINAL-HIGH | LOW | HIGH | HIGH | NMS-free saves ARM; quality winner |
| YOLO11-N 640 | object | ultralytics, 2024 | AGPL-3.0 | 2.6M | UNKNOWN | 640 | 6.5G | COCO 39.5 | C3k2+C2PSA | EASY | MEDIUM (C2PSA sensitive) | MED-HIGH | MARGINAL | LOW | HIGH | HIGH | best acc, worst NPU fit |
| YOLOX-Nano 416 | object baseline | Megvii/YOLOX, 2021 | Apache-2.0 | 0.91M | 1.8 MB FP16 | 416 | 1.08G | COCO 25.8 | CSP-depthwise | EASY | GOOD (ReLU swap) | LOW | HIGH | MEDIUM (23 ms A76; ARMv7 slower) | HIGH | HIGH | **det baseline**; commercial-friendly |
| YOLOX-Tiny 416 | object | same | Apache-2.0 | 5.06M | UNKNOWN | 416 | 6.45G | COCO 32.8 | CSP | EASY | GOOD | LOW-MED | MEDIUM | LOW | HIGH | MEDIUM | step-up |
| NanoDet-Plus-m 320 | object ultra-light | RangiLyu/nanodet, 2021+ | Apache-2.0 | 1.17M | 2.3 MB FP16 / 1.2 MB INT8 | 320 | 0.9G | COCO 27.0 | ShuffleNetV2+GhostPAN | EASY | EXCELLENT | LOW | HIGH | MEDIUM | HIGH | HIGH | **ultra-light co-winner** |
| NanoDet-Plus-m 416 | object ultra-light | same | Apache-2.0 | 1.17M | 2.3 MB FP16 / 1.2 MB INT8 | 416 | 1.52G | COCO 30.4 | same | EASY | EXCELLENT | LOW | HIGH | MEDIUM | HIGH | HIGH | same @416 |
| NanoDet-Plus-m-1.5x 416 | object | same | Apache-2.0 | 2.44M | 4.7 MB FP16 | 416 | 2.97G | COCO 34.1 | ShuffleNetV2-1.5x | EASY | GOOD | LOW | HIGH | LOW | HIGH | MEDIUM | quality ultra-light |
| PP-PicoDet-S 320/416 | object ultra-light | PaddleDetection, 2111.00902, 2021 | Apache-2.0 | 0.99M | UNKNOWN | 320/416 | 0.73G@320 / 1.24G@416 | COCO 27.1@320 / 30.6@416 | ESNet+CSP-PAN | MEDIUM (Paddle→ONNX friction) | EXCELLENT (+NPU variant, PaddleLite 150 FPS) | LOW | HIGH | MEDIUM | HIGH | HIGH | **ultra-light co-winner** |
| PP-PicoDet-M 416 | object | same | Apache-2.0 | 2.15M | UNKNOWN | 416 | 2.5G | COCO 34.3 | same | MEDIUM | EXCELLENT | LOW | HIGH | LOW | HIGH | MEDIUM | balanced alt |
| MobileNetV2-SSDLite 320 | object | TF/Caffe/torchvision, 2018–19 | Apache-2.0/MIT/BSD | ~3–5M | UNKNOWN | 300–320 | ~1–2G | COCO ~22 | MobileNet+SSD | EASY | EXCELLENT | LOW | MEDIUM (convert) / LOW (value) | MEDIUM | HIGH | LOW | reject as base (accuracy) |
| RT-DETR-R18 640 | object | lyuwenyu/RT-DETR, 2023 | Apache-2.0 | 20M | UNKNOWN | 640 | 60G | COCO 46.5 | ResNet+HybridEncoder+DeformDETR | HARD | POOR | HIGH | NOT PRACTICAL | NOT PRACTICAL | LOW | LOW | 10x FLOPs; reject |
| SORT | tracking | abewley/sort, 2016 | MIT | 0 (KF) | N/A | N/A | negligible | MOT17 MOTA 74.6 / IDF1 76.9 | N/A (IoU+KF) | N/A (code) | N/A | LOW | N/A (CPU HIGH) | HIGH | HIGH | MEDIUM | baseline tracker |
| ByteTrack | tracking | FoundationVision/ByteTrack, 2110.06864, 2022 | MIT | 0 | N/A | N/A | negligible | MOT17 80.3 / 77.3 / HOTA 63.1 | N/A (BYTE 2-stage) | N/A | N/A | LOW | N/A (CPU HIGH) | HIGH | HIGH | HIGH | **tracker winner (tie)** |
| OC-SORT | tracking | noahcao/OC_SORT, 2022–23 | MIT | 0 | N/A | N/A | negligible | MOT17 78.0 / 77.5 / HOTA 63.2 | N/A (O-C RU) | N/A | N/A | LOW | N/A (CPU HIGH) | HIGH | HIGH | HIGH | **tracker winner (tie)** |
| DeepSORT | tracking | nwojke, 2017 | GPL-2/3 (fork variance) | 0.5–2M ReID | UNKNOWN | crop-dep | HIGH (per-crop CNN) | MOT17 75.4 / 77.2 | CNN ReID | MEDIUM | MEDIUM | MEDIUM | LOW (CPU-heavy) | MEDIUM | MEDIUM | LOW | only if long re-ID needed |
| YOLO11n-sign 640 | traffic sign single-stage | ultralytics, 2024 (fine-tuned QCVN 10–20 cls) | AGPL-3.0 (base; fine-tune legal gate) | 2.6M | UNKNOWN | 640 (or ROI) | 6.5G | TT100K-class ~39% mAP50 baseline (community) | C3k2 | EASY | MEDIUM (PTQ −3–7% nano) | MEDIUM | MARGINAL-HIGH @2Hz gated | LOW | HIGH | HIGH | **sign winner** |
| Nano-detector + EfficientNet-Lite0-cls | sign two-stage | detector above + TF-Lite0, 2020 | Apache-2.0 (Lite0) | det 1–3M + 4.7M cls | UNKNOWN | det 416–640 + cls 48–64 | det 1–3G + cls 0.4G | GTSRB 95–99% cls; e2e 83–96% papers | ESNet/Shuffle + Lite0 | EASY | GOOD (Lite0 ReLU6 −0.7%) | LOW-MED | HIGH (gated K≤3) | LOW | HIGH | MEDIUM | runner-up if digit confusion |
| YOLO-nano-TL 4cls | traffic light | ultralytics/Paddle nano + LISA/Bosch/DriveU pre-train | AGPL/Apache (base-dep) | 1–3M | UNKNOWN | 320–416 ROI (upper-center) | 0.5–1.5G ROI | Bosch-YOLO mAP50 0.665 (ref) | nano | EASY | MEDIUM (tiny-object sensitive) | MEDIUM | MARGINAL @5Hz gated | LOW | MEDIUM | MEDIUM | optional; drop first |
| Fast-SCNN | drivable/road seg | 1902.04502, 2019 (Tramac impl Apache-2.0) | Apache-2.0 (impl) | 1.11M | ~4.4 MB FP32 est | 1024x2048 (train); infer 320x192–512x288 ROI | UNKNOWN (low) | Cityscapes 68.0 mIoU @123 FPS TitanXp | LtD+bottleneck | EASY | GOOD | LOW | MARGINAL-HIGH (ROI 2–5Hz) | LOW | MEDIUM | MEDIUM | **seg winner (fallback)** |
| BiSeNetV2 | seg | 2004.02147, 2020 | UNKNOWN (MIT impls vary) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | ~75–78 mIoU | Detail+Semantic | EASY | GOOD | LOW | MARGINAL | LOW | MEDIUM | LOW | superseded; SDK-sample only |
| PIDNet-S | seg quality | XuJiacong/PIDNet, 2206.02066, 2022 | MIT | 7.6M | UNKNOWN | 1024x2048 (speed script) | 47.6G@2048x1024 | Cityscapes test 78.6 @93 FPS 3090 | P-I-D 3-branch | EASY-MED (drop boundary head) | MEDIUM | LOW-MED | LOW-MARGINAL | NOT PRACTICAL | MEDIUM | MEDIUM | quality pick if fits |
| DDRNet-23-slim | seg | ydhongHIT/DDRNet, 2101.06085, 2021 | MIT | 5.7M | UNKNOWN | 1024x1024 crop (train) | 36.3G@2048x1024 | Cityscapes val 77.8 / test 77.4 | Dual-res+DAPPM | EASY | GOOD | LOW-MED | MARGINAL | NOT PRACTICAL | MEDIUM | MEDIUM | road prior; runner-up |
| FastDepth | depth (optional) | dwotk/fast-depth, ICRA19 | MIT | UNKNOWN | UNKNOWN | 224x224 | 0.37G MACs | NYU RMSE 0.604; TX2 CPU 37 ms | MobileNet+NNConv5 | EASY | GOOD | LOW | MEDIUM (feas) / LOW (TTC value) | LOW | MEDIUM | LOW | edge-feasible, TTC-marginal |
| MonoDepth2-R18 | depth (optional) | nianticlabs/monodepth2, 1806.01260, 2019 | NON-COMMERCIAL (research) | UNKNOWN | UNKNOWN | 640x192 | UNKNOWN | KITTI AbsRel 0.115 mono | ResNet18 UNet | EASY | MEDIUM | LOW | MEDIUM / MEDIUM TTC | LOW | MEDIUM | LOW | best TTC potential; license gate |
| Lite-Mono-tiny | depth | 2023 (repos 404 at study) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | CNN+LGFI attention | MED-HARD | MEDIUM | MED-HIGH | LOW | NOT PRACTICAL | LOW | LOW | unverified; prefer FastDepth |
| DepthAnythingV2-S | depth teacher | DepthAnything/V2, 2406.09414, 2024 | Small Apache-2.0; B/L CC-BY-NC | 24.8M (S) | UNKNOWN | 518 | UNKNOWN | relative only | DINOv2-ViT-S+DPT | HARD | POOR | HIGH | NOT PRACTICAL | NOT PRACTICAL | LOW (teacher) | LOW on-device | offline labeler only |
| MiDaS-small v2.1 | depth viz | isl-org/MiDaS, 2019–23 | MIT | 21M (small) | UNKNOWN | 256 | UNKNOWN | zero-shot relative | lite-CNN | MEDIUM | MEDIUM | LOW-MED | LOW | LOW | MEDIUM | LOW | visualisation only, not TTC |
| Classical weather stats | weather adapt | FADE/dark-channel/Canny lit. | papers open (re-impl safe) | 0 | N/A | 160–320 ROI | negligible CPU | day/night 97.8% (RF demo) | N/A | N/A | N/A | LOW | N/A (CPU HIGH) | HIGH | HIGH | MEDIUM | **weather winner (no CNN)** |
| Heuristic scene tags | scene context | BDD tags ontology + own rules | N/A | 0 | N/A | N/A | negligible CPU | tagger 50–60% (DLA-34 ref) | N/A | N/A | N/A | LOW | N/A (CPU HIGH) | HIGH | HIGH | MEDIUM | **scene winner (no CNN)** |

## SHORTLIST (≤3 per major task)

```text
lane:        UFLDv2-R18 (baseline+winner) / LaneATT-R18 (runner-up) / UFLDv2-MobileNetV3 (ultra-light)
detection:   YOLOX-Nano-416-ReLU (baseline+winner) / YOLOv6-N-ReLU-RepOpt (runner-up, quant) /
             NanoDet-Plus-m-320 + PP-PicoDet-S-320 (ultra-light tie — toolchain decides)
tracking:    ByteTrack (winner tie) / OC-SORT (winner tie) / SORT (fallback baseline)
sign:        YOLO11n-single-stage-QCVN (winner) / nano-detector+EfficientNet-Lite0 (runner-up) / — (no third; avoid V3-Small INT8)
light:       YOLO-nano-4cls-ROI+vote (winner) / classical-blob (NOT recommended alone) / — (deprioritize)
seg:         Fast-SCNN (winner/fallback) / DDRNet-23-slim (runner-up) / PIDNet-S (quality)
depth:       FastDepth (ultra-light) / MonoDepth2-R18-mono+stereo (quality, license-gated) / — (reject transformers)
weather:     classical stats (winner) / — (no CNN)
scene:       heuristic (winner) / — (no CNN)
hazard:      same-detector-extra-classes (winner) / specialized head (runner-up if gap) / seg-extent (quality, deferred)
```

## FINAL RANKING (summary; reasons in LANDSCAPE)

```text
lane:         winner UFLDv2-R18 / runner-up LaneATT-R18 — row/col classification fits INT8 NPU + simple CPU post
detector:     winner YOLOX-Nano-416-ReLU (tie PicoDet-S / NanoDet-Plus-m by toolchain) / runner-up YOLOv6-N-ReLU / quality YOLOv10-N NMS-free
sign:         winner single-stage YOLO11n-QCVN-10–20cls / runner-up +Lite0 crop classifier if digit confusion
light:        winner nano-4cls ROI + 5-frame vote (optional, droppable)
seg:          winner Fast-SCNN ROI fallback / runner-up DDRNet-23-slim / quality PIDNet-S
depth:        winner NONE on-device (optional FastDepth; teacher DepthAnythingV2-S offline) — geometry instead
overall stack: det-nano-5Hz + Byte/OC-tracker-10Hz + UFLDv2-R18-7–10Hz + sign-2Hz-gated (+TL-5Hz-gated + seg-2–5Hz optional)
```
