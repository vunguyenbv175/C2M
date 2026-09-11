# C2M IPU Toolchain Request Card — What to ask vendor/FAE (no SDK in repo)

**Blocker:** no public `SGS_IPU_SDK` drop matches C2M (`sdk_commit b03a7d4`, `T_0.0.1_210525`). Do NOT commit SDK contents if received (see staging below).

## Exact request (copy/paste)

```text
Target: SSC8838G / Mercury6 / Tiramisu (C2M dashcam, ARMv7-A userspace, kernel 4.9.227)
Compat: sdk_commit b03a7d4 (libmi_ipu 20220606101908) + IPU firmware T_0.0.1_210525
Please provide SGS_IPU_SDK drop containing:
  - ConvertTool.py (caffe / tf-graphdef / savemodel / keras / tflite; confirm ONNX support Y/N + version)
  - Calibrator.py + Compiler.py + Simulator.py + SGS Netron viewer
  - MI_IPU headers (mi_ipu.h, mi_ipu_datatype.h) + MI_SCL headers for this SDK generation
  - model compiler target config for SSC8838G (CompilerConfig.txt / concat_net / input_config templates)
  - board examples: dla_classify / dla_detect / dla_simulator(NBatch) / show_img_info / ipu_log / utilization + ipu_server
  - IPU Log performance analysis tool notes (User Manual §7.11 equivalent) + supported-op list (§11 Caffe/TF) + model limits (dims, size, depth)
License/host needed: confirm NDA terms, Linux AVX2 host deps, Docker image if any, license-server if any.
```

## Staging (already gitignored; do NOT commit)

```text
external/sgs_ipu_sdk/  — SDK drop (private)
external/models/       — prototxt/caffemodel + calibration images (private)
build/ipu/             — generated .sim / _fixed.sim / _sgsimg.img (private)
```

## On receipt (READ_ONLY verify, private notes only)

```sh
sha256sum <sdk_archive> > sdk.sha256            # private record
python3 $SGS_IPU_SDK/Scripts/ConvertTool/ConvertTool.py -h   # confirm frameworks (ONNX?)
```

Then follow `C2M_IPU_SMOKE_MODEL_RECIPE.md` (conv-only first). Evidence: `ConvertTool -h` output + drop version strings.
