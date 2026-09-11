# C2M IPU Smoke Model Recipe — MobileNetV2 Caffe 224 (metadata + recipe, no weights)

**Safety:** host work only. Do NOT download large models. Do NOT commit SDK archives or weights.
**Blocker:** `SGS_IPU_SDK` matching C2M (`sdk_commit b03a7d4`, firmware `T_0.0.1_210525`, `SSC8838G/Mercury6/Tiramisu` target) is UNAVAILABLE — recipe stays placeholder until drop arrives.

## 1. Expected chain (from `docs/research/C2M_IPU_TOOLCHAIN_V1.md` + DLA tool doc)

```text
prototxt + caffemodel (MobileNetV2, 224x224, ReLU, GAP+FC)
→ ConvertTool.py caffe → .sim (SGS Float)
→ Calibrator.py (32+ ILSVRC cal images, Classification) → _fixed.sim (INT8)
→ Compiler.py → _fixed.sim_sgsimg.img (SGS Offline cmd, deployable via MI_IPU_CreateCHN)
→ Simulator.py (single-image + val-set) → board dla_simulator -c Unknown -f BGRA cross-check
→ c2m-ipu-smoke single Invoke (SAFE then COEXIST)
```

Placeholders (UNKNOWN CLI flags stay placeholders — do NOT invent beyond evidence):

```sh
# AFTER SDK drop arrives; verify ConvertTool -h first (2021 SDK has NO onnx subcommand)
# python3 $SGS_IPU_SDK/Scripts/ConvertTool/ConvertTool.py caffe \
#   --model_file <mobilenet_v2.prototxt> --weight_file <mobilenet_v2.caffemodel> \
#   --input_arrays <FROM_PROTOTXT> --output_arrays <FROM_PROTOTXT> \
#   --input_config <input_config.ini> --output_file <mobilenet_v2_float.sim>
# python3 $SGS_IPU_SDK/Scripts/calibrator/calibrator.py \
#   -i <ilsvrc_cal_dir> -m <mobilenet_v2_float.sim> -c Classification \
#   --input_config <input_config.ini> -n mobilenet_v2
# python3 $SGS_IPU_SDK/Scripts/calibrator/compiler.py -m <mobilenet_v2_fixed.sim>
# python3 $SGS_IPU_SDK/Scripts/calibrator/simulator.py \
#   -i <single.bmp> -m <mobilenet_v2_fixed.sim_sgsimg.img> -c Classification -t Offline -n mobilenet_v2
```

`input_config.ini` skeleton (fill tensor names from prototxt; BGR + mean/std from training):

```ini
[INPUT_CONFIG]
inputs='data'
training_input_formats=BGR
input_formats=BGR
quantizations=TRUE
mean_red=0.0
mean_green=0.0
mean_blue=0.0
std_value=1.0
[OUTPUT_CONFIG]
outputs='prob'
dequantizations=TRUE
[CONV_CONFIG]
tensor_arrays=''
```

## 2. Why this model (from operator doc)

Conv/BN/ReLU/Pool/FC only, static 1x3x224x224, trivial PTQ, known top5 — LOWEST 2022-IPU risk. Official DLA walkthrough converts EXACTLY this net. SMOKE ONLY, not ADAS.

## 3. Staging (no SDK bytes in git)

```text
external/sgs_ipu_sdk/  (drop lives here, gitignored)
external/models/       (prototxt/caffemodel + cal images, gitignored)
build/ipu/             (generated .sim/_fixed.sim/_sgsimg.img, gitignored)
```

Record SDK drop hash + `ConvertTool -h` output + header prefix compare vs stock `be2d6fe9...` in build notes (private, never commit weights).
