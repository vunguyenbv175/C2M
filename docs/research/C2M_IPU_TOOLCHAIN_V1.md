# C2M IPU Toolchain V1 — Converter, Compiler, Host Setup, Pipeline

**Status:** RESEARCH ONLY. No SDK archive downloaded/committed. **Date:** 2026-09-11.

## 1. Toolchain identity (primary evidence)

Official DLA/IPU SDK docs (comake.online mirror of SigmaStarDocs):

```text
SOURCE: customer/development/dla/tools.html (SSC9381G Pudding ULS00V040 2021-09-13) + bbs.16rd DLA manual 2021-01-29 + CSDN yolov5→9383 2023-06-26
VERSION: SGS_IPU_SDK with Netron Setup 3.4.3.exe / 5.3.5.exe; Python 3.5, TF 1.14, AVX2 host
TOOLS:
  ConvertTool.py (Scripts/ConvertTool) — TF_graphdef/savemodel, Keras, TFLite, Caffe → SGS Float .sim (flatbuffer)
  Calibrator.py (Scripts/calibrator/calibrator.py) — .sim → _fixed.sim (8/16bit quant, needs calibration images)
  Compiler.py (Scripts/calibrator/compiler.py) — _fixed.sim → _fixed.sim_sgsimg.img (SGS Offline cmd file, deployable)
  Simulator.py (Scripts/calibrator/simulator.py) — sim/fixed/offline PC sim + accuracy eval
  SGS Netron — view .sim/_fixed.sim/_sgsimg.img (+ native frameworks)
  postprocess.py + concat_net — SSD-style backbone + custom NMS/box-decode append
  DumpDebug/auto_dump_debug.sh/histogram.py — per-layer dump
  Board demos: dla_classify/detect/classifyNBatch/simulator(NBatch)/show_img_info/ipu_log/utilization/server (sdk/.../source/dla/)
  dla_simulator board cmd: ./prog_dla_dla_simulator -i JPEG -m *.sim_sgsimg.img -c Unknown -f BGRA
CONFIDENCE: HIGH for flow/names (official doc); MEDIUM for C2M applicability (Pudding doc, C2M is Mercury6/Tiramisu — flow likely same, versions differ)
```

Key quotes (translated, original Chinese in source):

```text
ConvertTool: convert TF/Keras/Caffe-trained nets to SigmaStar float net (SGS Float file)
Calibrator: statistics on FeatureMap → quantize SGS Float to 8bit/16bit fixed
Compiler: fixed net → offline instruction file deployable on SigmaStar HW
Simulator: PC simulator for all three stages
DLA与IPU指代同一个部件 (DLA == IPU)
SigmaStar模型为sim，全称Sigmastar IPU Model (model is .sim, Sigmastar IPU Model)
```

## 2. Compatibility matrix (required)

```text
INPUT FRAMEWORK | CONVERTER | OUTPUT FORMAT | HOST OS | LICENSE/ACCESS | STATUS
Caffe (.prototxt+.caffemodel) | ConvertTool.py caffe | .sim (SGS Float flatbuffer) | Linux (AVX2 Intel, 6–8GB, Python3.5/TF1.14 stack) | NDA SDK drop (not public) | PROVEN in doc, C2M-applicability MEDIUM
TF frozen GraphDef (.pb) | ConvertTool.py tensorflow_graphdef | .sim | same | same | PROVEN in doc / MEDIUM for C2M
TF SavedModel | ConvertTool.py tensorflow_savemodel | .sim | same | same | PROVEN / MEDIUM
Keras (.h5) | ConvertTool.py keras | .sim | same | same | PROVEN / MEDIUM
TFLite (non-quant) | ConvertTool.py tflite | .sim | same | same | PROVEN / MEDIUM
ONNX | NONE in 2021 doc (no onnx subcommand; `ConvertTool -h` lists only 5 above) | — | — | — | ABSENT in this SDK version (do NOT assume ONNX accepted; newer Toolchain 2024+ may add — UNKNOWN, needs drop)
PyTorch | INDIRECT only (export → ONNX → ? → TF/Caffe/TFLite → ConvertTool, or via Toolchain 2024+ if ONNX added) | .sim | same + export env | same | EXPECTED path, UNPROVEN on SigmaStar
SGS Float .sim | Calibrator.py | _fixed.sim (INT8/16) | same | same + calibration set | PROVEN / MEDIUM
SGS Fixed | Compiler.py | _sgsimg.img (offline cmd) | same | same | PROVEN / MEDIUM
SGS any | Simulator.py / dla_simulator | accuracy + board verify | PC + board | same | PROVEN / MEDIUM
```

ONNX verdict: **do NOT claim ONNX input unless tool evidence confirms it.** 2021 SDK has no ONNX converter. Modern candidate path `PyTorch→ONNX(static, opset 11–13)→simplify→?→vendor` has a `?` that is currently UNKNOWN (either via TFLite/TF/Caffe export or a newer SDK with ONNX import — needs drop). Fail-fast gate: `onnx_operator_audit.py` BEFORE any export work.

## 3. Compiler availability (required verdict)

```text
Publicly downloadable? NO evidence. No public SGS_IPU_SDK download found (GitHub MI_IPU/SSC8838G 0 hits; OpenIPC covers VIF/ISP only; sigmastar.com.tw unreachable in prior study).
Inside SDK? YES (Scripts/... per doc).
Requires NDA? HIGH likelihood (all SDK docs are Confidential, SDK drops via FAE/comake registration; CSDN/bbs posts assume SDK in hand).
Windows-only/Linux-only/Docker/license-server? Host is Linux AVX2 (PROVEN); Netron viewer is Windows .exe (PROVEN); Docker/license-server UNKNOWN (not stated; assume possible, verify on request).
SDK version compatibility? STRICT (fw/lib version checks + MISMATCH_MODEL error; need drop matching sdk_commit.b03a7d4 / T_0.0.1_210525).
CONFIDENCE: HIGH that toolchain is NDA-blocked; MEDIUM on exact request channel (FAE/comake/NDA).
This is the likely LARGEST BLOCKER (see risk doc).
```

## 4. Input config / calibration / quantization (from tool doc §3.2 + §4)

`--input_config input_config.ini` (required for ConvertTool):

```text
[INPUT_CONFIG] inputs='data' (image first); training_input_formats / input_formats ∈ {RGB,BGR,RGBA,BGRA,YUV_NV12,RAWDATA_S16_NHWC/NHWX,RAWDATA_U8_NHWC/NHWX}; quantizations=TRUE/FALSE per input; mean_red/green/blue + std_value (normalization fused into model — board only resizes); [OUTPUT_CONFIG] outputs='prob'; dequantizations=TRUE/FALSE; [CONV_CONFIG] tensor_arrays='conv1-1,...'
Calibrator: -i <calib_images> -m <float.sim> -c {Classification|Detection} --input_config ... -n <name> (default 10 procs); prompts Start to analysis images... → Run convert model OK.
Quant: 8bit/16bit fixed (per-tensor/per-channel/symmetric details UNKNOWN in excerpt; conv-quant options §4.3 not fetched — mark UNKNOWN).
CONFIDENCE: HIGH for formats/flags (doc template); UNKNOWN for quant granularity/QAT/PTQ/mixed (needs drop)
```

## 5. Host-side setup plan (future, gated on SDK drop)

```text
PROVEN (from doc):
  OS: Linux x86-64 with AVX2 Intel CPU (i5 min 6GB / i7 rec 8GB); docker needs ≥6GB
  Deps: Python 3.5, enum34==1.1.6, numpy==1.16.4, protobuf>=3.8, six>=1.12, opencv-python>=3.4.0.14, TF==1.14, cython>=0.29.13, pycocotools>=2.0, matplotlib>=3.0.3, scipy>=1.3.1, pillow==6.1, python3-tk, libc6-dev-i386, libstdc++6, python-qt4
  Layout: ~/SGS_IPU_SDK + ~/SGS_Models; source cfg_env.sh for lib path
  Viewer: SGS_IPU_SDK/Netron/Netron Setup *.exe on Windows
EXPECTED (needs drop to confirm):
  Newer SDK may support Python 3.8+/TF2/ONNX (check SGS_IPU_Toolchain_2024+ / IPU_Sigdoc_vS03.0.8 Quick_Start); keep 2021 env as fallback in container
UNKNOWN:
  Exact C2M-matching SDK version URL, license server, docker image, calibration-set license, compiler flags for SSC8838G/Tiramisu target (`--transform CompilerConfig.txt`? concat_net?)
STEPS (do not run until SDK in hand):
  1. Request SGS_IPU_SDK matching sdk_commit.b03a7d4 + SSC8838G target from vendor/FAE (cite lib version + T_0.0.1_210525).
  2. Provision AVX2 Linux host (or container) with pinned deps above; record `pip freeze` + `lscpu`.
  3. Unpack SDK to ~/SGS_IPU_SDK (do NOT commit to git; add to .gitignore; keep drop hash private).
  4. Run ConvertTool `-h` to confirm supported frameworks (ONNX present?).
  5. Follow §6 pipeline on conv-only smoke first.
```

## 6. Reproducible conversion pipeline (fail-fast checklist)

```text
source model (PyTorch/TF/Caffe, train with BN-only, ReLU, static shapes)
→ export (ONNX opset 11–13 static 1x3xHxW OR TF frozen .pb OR Caffe prototxt+caffemodel OR TFLite non-quant)
→ simplify (onnx-simplifier / flatbuffer check; strip unused outputs; freeze H/W/C)
→ operator audit (tools/research/ai_adas/onnx_operator_audit.py — FAIL here if SiLU/DFL/NMS/Loop/Attention/GridSample present; see operator doc)
→ input_config.ini (set input_formats=BGR (or YUV_NV12 if zero-copy path proven), mean/std from training, quantizations=TRUE, outputs dequant TRUE for heads)
→ vendor ConvertTool → .sim (check Debug_.sim vs .sim note: Debug_ is unoptimized, NOT runnable)
→ INT8 calibrate (500–2k rep images night/rain/VN; Classification vs Detection mode; verify top1/mAP drop vs float via Simulator.py)
→ vendor Compiler.py → _sgsimg.img (expect Run Offline OK + Run Pack Tool OK)
→ model inspection (SGS Netron + Simulator single-image + board dla_simulator -c Unknown -f BGRA)
→ deploy (copy to bench dir, NOT /customer yet; standalone harness; see deployment doc)
→ shadow bench (video clips, FPS/p50/p95/RSS/IPU_ms, agreement vs stock)
GATES: any step FAIL → stop, log SDK version + input_config + op list; do not hand-edit .sim/_sgsimg.img.
```

## 7. GitHub converted-model search (public examples)

| Model | SoC | SDK | Runtime | Format | License | Note |
|---|---|---|---|---|---|---|
| MobileNetV2 (caffe) | Pudding-class (doc example) | SGS 2021 | Simulator + board | `.sim→_fixed.sim→_sgsimg.img` | example only | doc walkthrough, PROVEN flow |
| SSD-MobileNetV1 (TF) | same | same | same + concat_net postprocess | same + `concat_net --mode append` | example | proves detection + custom NMS append pattern |
| YOLOv5s | SSC9383 (CSDN 2023-06-26) | SGS (assumed) | board | `.sim` (Sigmastar IPU Model) + Netron 5.3.5 | blog (supporting only) | DLA==IPU statement; conversion details not verified |
| Face/human/det/attr/LPR/pose/seg (algo libs `libsgsalgo_*`) | Pcupid + family | Alkaid SDK + IPU SDK | MI_IPU demos | `_sgsimg.img` (assumed) | vendor proprietary | proves vendor ships prebuilt models, NOT custom path |

No public SSC8838G-converted YOLO/MobileNet weight found. No public SGS_IPU_SDK drop found. Record as UNKNOWN, not as proof of impossibility.

## 8. Decision input

```text
Vendor compiler recovered? NO (docs only, no drop) → NATIVE_IPU_TOOLCHAIN_BLOCKED until FAE/NDA succeeds.
Tiny model compiles? UNKNOWN (needs drop).
Next evidence: SDK drop matching b03a7d4 + `ConvertTool -h` output + conv-only .sim header vs stock be2d6fe9... prefix comparison.
```
