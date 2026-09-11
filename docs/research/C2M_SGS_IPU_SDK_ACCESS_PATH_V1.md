# C2M SGS_IPU_SDK Access Path V1 — Licensing, Request Card, Safe Handling

**Date:** 2026-09-11. **Research only. No bypass of any access control was attempted or is authorized.**

## 1. License/access verdicts per candidate

```text
K1 Pudding tool doc ............ public doc MIRROR (page carries Confidential-A marking; mirror ≠ redistribution grant for binaries)
K2 bbs.16rd post ................ public TEXT; attachment (if any) login/reply-gated — not recovered, not bypassed
K3/K4/K5 comake docs ............ public doc MIRRORS (Confidential-A marking); toolchain binaries + sgs_docker + Quick_Start_Demo NOT public
K6/K7/K8 public git mirrors ..... public code (own licences: johnchia PROPRIETARY-pinned / MIT reconstructions / GPL BSP) — contain NO IPU compiler
K9 forum/blog posts .............. public text, supporting only
K10 cloud drives ................. no traceable link — no verdict possible
Any SGS_IPU_SDK / SGS_IPU_Toolchain ARCHIVE matching b03a7d4:
  NDA/FAE/registration-gated (evidence: "FTP provided by SStar" in Alkaid env-setup docs;
  Comake "SDK Download Request Process / SDK Download Center"; Confidential-A on all toolchain docs).
  Redistribution rights: UNKNOWN → treat as NOT redistributable. Do NOT commit archives.
  License-server / dongle / activation: UNKNOWN (no doc evidence; assume possible — confirm with FAE).
```

## 2. Exact FAE/vendor request card (copy/paste)

```text
To: SigmaStar / Comake FAE (via dev.comake.online SDK Download Request Process / SDK Download Center)
Subject: SGS_IPU_SDK request — SSC8838G / Mercury6-Tiramisu matching C2M runtime b03a7d4

Target: SSC8838G / Mercury6 / Tiramisu (dashcam, ARMv7-A userspace, kernel 4.9.227)
Compat (from shipped lib, exact):
  libmi_ipu.so: project_commit.0940dba sdk_commit.b03a7d4 build_time.20220606101908
  libmi_scl.so: sdk_commit.b03a7d4
  IPU firmware tag: T_0.0.1_210525
  MI_IPU surface (11): CreateDevice/DestroyDevice/CreateCHN/DestroyCHN/
    GetInOutTensorDesc/GetInputTensors/PutInputTensors/GetOutputTensors/
    PutOutputTensors/Invoke/GetOfflineModeStaticInfo
  (NOT present locally: Tensors2/Invoke2/Invoke2Custom/CreateCHNWithUserMem/
    DestroyDeviceExt/CancelInvoke — please confirm branch predates these.)
Please provide the SGS_IPU_SDK (or SGS_IPU_Toolchain) drop for this branch containing:
  - ConvertTool / SGS_converter.py (caffe / tf-graphdef / savemodel / keras / tflite;
    confirm ONNX support Y/N + opset range for THIS branch)
  - Calibrator.py (+torch_calibrator if branch has it) / Compiler.py / Simulator.py / SGS Netron viewer
  - mi_ipu.h, mi_ipu_datatype.h (+ mi_sys.h / mi_scl.h of this generation)
  - compiler target config for SSC8838G (show_sdk_info.py output + CompilerConfig.txt equivalent +
    input_config.ini templates + concat_net/postprocess if applicable)
  - board examples: dla_classify / dla_detect / dla_simulator(+NBatch) / show_img_info /
    ipu_log / utilization / ipu_server (+sdk/verify paths for this SDK)
  - IPU Log analysis notes + supported-op list + model limits (dims/size/depth/align) for Tiramisu
  - sgs_docker reference if the branch uses it
Please confirm: NDA terms, redistribution limits, license-server/dongle/activation needs,
Linux host deps for THIS drop, and whether pcupid-target .img loads on Tiramisu (we assume NO).
We will NOT redistribute the drop. No unrelated project information is disclosed with this request.
```

## 3. Staging (already gitignored — do NOT commit)

```text
external/sgs_ipu_sdk/  — SDK drop (private; record filename + SHA256 + version strings privately)
external/models/       — prototxt/caffemodel/onnx + calibration images (private)
build/ipu/             — generated .sim / _fixed.sim / _sgsimg.img (private)
```

`.gitignore` covers `external/` and `build/ipu/`. Verify with `git status --short` before every commit.

## 4. On-receipt verification (READ-ONLY first pass, no execution)

```sh
sha256sum <sdk_archive> > sdk.sha256            # private record, never commit
# inspect tree only: README / release notes / version files / cfg_env.sh /
#   requirements / chip DB / target configs / license files / example models
python3 tools/research/ipu_sdk/fingerprint_sgs_sdk.py --sdk <dir> --out sdk_fingerprint.json
python3 tools/research/ipu_sdk/compare_mi_ipu_api.py --dynsym <local_dynsym.txt> --header <sdk_mi_ipu.h>
# gate: show_sdk_info.py chip list MUST contain Tiramisu/SSC8838G before any compile
# gate: ConvertTool/SGS_converter -h output decides the ONNX question for THIS branch
```

## 5. Safe execution policy (before any LEVEL 3 run)

```text
hash + tree inspect + strings + dependency scan + malware scan if available;
disposable VM/container (no creds/SSH keys/home secrets mounted);
no network unless required and understood; Intel AVX2 host (legacy: i7/8GB;
S21 docker: i7/32GB min); record every command + tool version + input/output hash.
Never run unknown compiler binaries on the production workstation.
First compile is MobileNetV2-caffe 224 ONLY (vendor-documented lineage). No YOLO yet.
```

## 6. Vendor contact path (ordered)

1. Comake forum SDK Download Request Process → SDK Download Center (`dev.comake.online`) with card §2.
2. Board/vendor FAE channel (cite lib version strings so FAE can identify the branch).
3. SigmaStar official site `sigmastar.com.cn` / `sigmastarsemi.com` support route (docs mirror `sigmastar.com.tw` was unreachable in prior study — retry, do not depend on it).
