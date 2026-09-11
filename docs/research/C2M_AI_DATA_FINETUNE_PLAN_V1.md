# C2M AI Data + Fine-Tune Plan V1 (incl. Benchmark Methodology)

**Status:** research only. No scraping of proprietary DBs; respect dataset licenses; no huge weights in repo.
**Date:** 2026-09-11.

## 1. Shadow-mode data collection (Q30)

Log always-tiny, clip on event, respect storage + SD wear + privacy.

```text
per-frame 10 Hz in-RAM ring 60 s: {ts_ms, frame_id, gps{lat,lon,speed,heading}, calib,
  stock{fcw,pcw,ldw,lead_d,ttc}, custom{objects[],lanes[],signs[],tls[],ttc,confs,model_ver,ipu_ms}}
  → JSONL ~0.5–1 KB/frame (~0.5 MB/min), rotate hourly, fsync 1 Hz batched, sequential append (no SQLite/frame)
event trigger (stock≠custom OR custom>thr OR TTC<3 s OR lane-xing OR button):
  → persist ±5 s video (reuse stock MP4 segments if possible else 640x360 sub-stream) + JSONL slice + 2–3 JPEG keyframes
quotas: logs ≤200 MB + clips ≤1 GB FIFO auto-evict; never touch stock rec partition
privacy: blur faces/plates on export; raw stays on-device unless consented
```

Compare stock vs custom offline → agreement/FP/FN without affecting driver.

## 2. Active-learning loop (Q31)

```text
dashcam event clips → phone/PC review (CVAT/Label-Studio: accept/correct boxes/lanes/signs) →
versioned dataset (pins + model_ver traceability) → Colab/GPU finetune nano →
holdout + regression (BDD-val + frozen VN-miniset, ΔmAP≥0, Δrecall_small≥0, IPU_ms≤budget, no new UNSUPPORTED op) →
INT8 PTQ → canary 1-device shadow → promote (versioned .ipumodel + rollback)
```

Easiest→hardest: vehicles/bikes boxes (plentiful, BDD transfers; 2–5k VN boxes move needle) → lane masks (noisy polygons, distill helps) → signs (taxonomy gap, few-shot per limit-digit) → TL-state/depth (temporal, rare-yellow, bloom — defer). Tooling: Ultralytics train+export, onnx-simplifier, onnx2tf, vendor compiler, TrackEval; every log carries `model_ver`.

## 3. Dataset strategy (Q32) + licensing (Q47)

Pretrain (research-weights ok, redistribution not) → VN fine-tune (own collection, commercial-safe) → frozen VN-miniset holdout (never train).

| Dataset | Use | Scale | License / commercial | VN value |
|---|---|---|---|---|
| BDD100K | det/lane/seg/weather starter | 100k, night/rain tags, bike/rider | research/non-commercial | best starter; US-centric |
| Mapillary Vistas v2 | seg pretrain | 25k global | research-only | Asia variance |
| Cityscapes | seg/det sanity | 5k fine + 20k coarse, DE | research-only | clean, no bike chaos |
| CULane / TuSimple / LLAMAS | lane | 133k / 6k / 100k auto | research | dense/CN-highway; TuSimple too easy |
| TT100K | sign pre-train | 100k pano, 30k instances, 221 cls | CC-BY-NC (contact for commercial) | CN Vienna-style closer than US |
| GTSRB/GTSDB | sign classifier pre-train | 51k crops/43 + 900 scenes | research-only/UNKNOWN | Vienna shapes match QCVN; text differs |
| Mapillary MTSD | sign pre-train | 100k imgs, 320k signs, 313–400 cls | CC BY-NC-SA (agreement for commercial) | most diverse; +6% AP pre-train cited |
| LISA signs/TL | sign/TL aux | 6.6k frames signs; 43k frames TL | academic / CC BY-NC-SA | US MUTCD — low VN relevance (TL day/night useful) |
| Bosch BSTLD / DriveU DTLD | TL small-object/arrow | 13k 720p (median 8.5 px) / 230k 2 MP | non-commercial / gated research | defines tiny-TL problem; taxonomy overkill (collapse 4cls) |
| DFG Slovenia | sign method ref | 6957 1080p, 200 fine-grained | CC BY-NC-SA (contact) | Vienna fine-grained lesson |
| nuScenes / KITTI / AI City | det/track eval only | 1k 3D / 7k / challenge | research/challenge | night/rain splits; heavy (eval) |
| RDD2020/2022, Pothole-600/EdmCrack/CPRID, Kaggle-665 | hazard | 26k/47k boxes; 600+ pairs; 665 VOC | mixed research (check each) | road-damage starter; flood = custom |
| VN sets (DatasetNinja 1170/29cls, VTSDB46/VTS100, Roboflow-VN 4200/58cls DaNang, HF-YOLO11s-82cls) | VN fine-tune seed | 1–4k each | mixed/UNKNOWN community | only QCVN-correct; tiny/imbalanced → collect own |
| Own VN collection (target) | product fine-tune + holdout | 2–5k frames bikes/night/rain/signs/lights first | own consent, commercial-safe | highest; QCVN 41:2019 (Vienna 2014) |

Legal: all SOTA sign/TL/detection datasets above are NON-COMMERCIAL or gated — production needs own VN collection + counsel review; AGPL/GPL detector bases (v5/v8/v10/v11, v6/v7/v9) trigger source/weight duties for closed dashcam unless Enterprise/commercial license — prefer Apache-2.0/MIT (YOLOX/NanoDet/PicoDet/RT-DETR-license-only) if closed-source required. Weights-pretrained-on-NC-data < redistributing-data risk, still review.

## 4. Vietnam / SEA needs (Q33–34)

Challenges: dense motorcycles (occlusion/weave), inconsistent markings + informal lanes, mixed users, QCVN signs, night scooters (low-conf), congestion, rain. Generic COCO/Cityscapes/TuSimple models fail on: bike recall, lane continuity, sign taxonomy, TL occlusion. Priorities: (1) bike/person fine-tune + Byte/OC low-conf recovery, (2) lane+seg-fallback + classical rain/night adaptation, (3) QCVN sign set (P.127 limits, P.101 stop, P.209 yield, P.102 no-entry, W-triangles), (4) cone/barrier + stopped-vehicle, (5) own night/rain VN-miniset. SEA sets (TH/ID/MY/SG bike-heavy) help domain-adapt if VN-scarce — verify license each; goal motorbike-heavy adaptation, not generic mAP.

## 5. Benchmark methodology (Q35, Q41 harness)

Never compare cross-paper accuracy directly. Normalize per (model, task, data-split, input, INT8-state, NPU/CPU, Hz).

Harness (future `tools/research/ai_adas/bench.py` + recorded `raw_adas` clips, same frames for all):

```text
inputs:  same clips (day/night/rain/urban/highway/VN-bike) + calibration + GPS speed
runs:    stock (baseline) vs each candidate (same pre/post, same NMS/thr sweep)
outputs: fps, p50/p95 latency, RSS peak, IPU_ms, mAP/F1/mIoU (per-split), FP-rate, miss-rate,
         warning-stability (flicker/s), TTC-error vs geometry, agreement (stock∩custom), temp/power if measurable
gates:   Δrecall_small≥0, flicker↓, IPU≤budget, no UNSUPPORTED op, VN-miniset no-regress
```

Columns: model/task/year/license/params/FLOPs/input/metric/edge-bench/INT8/risk/C2M-feas (HIGH/MED/LOW/NOT PRACTICAL) — see MATRIX doc.
