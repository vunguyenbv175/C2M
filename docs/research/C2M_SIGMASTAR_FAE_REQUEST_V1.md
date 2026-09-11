# C2M SigmaStar FAE Request V1 — SGS_IPU_SDK for SSC8838G

**Date:** 2026-09-11. **Purpose:** owner-ready request package for SigmaStar / Comake / SDK Download Center / board-vendor FAE.
**Policy:** include only information FAE needs to identify the SDK branch. No reverse-engineering details.
Do NOT commit any SDK files received in response (stage under `external/`, gitignored).

## 1. Where to send (ordered)

1. Comake SDK Download Center / SDK Download Request Process (`dev.comake.online`).
2. Board/module vendor FAE channel.
3. SigmaStar support route (`sigmastar.com.cn` / `sigmastarsemi.com`).

## 2. Subject line (copy/paste)

```text
SGS_IPU_SDK request — SSC8838G (Mercury6/Tiramisu) matching device runtime sdk_commit b03a7d4
```

## 3. Request body (copy/paste, concise professional English)

```text
Dear SigmaStar/Comake support team,

We are developing a custom AI model for a device based on the SSC8838G
(Mercury6/Tiramisu family). The device firmware already ships the IPU
runtime (libmi_ipu.so + mi_ipu.ko + ipu_firmware.bin), and our requirement
is to compile and validate custom offline IPU models against this existing
runtime — no firmware changes are involved.

Device runtime identifiers (from the shipped libraries):
  SoC: SSC8838G (Mercury6/Tiramisu family)
  libmi_ipu.so: project_commit.0940dba, sdk_commit.b03a7d4,
    build_time.20220606101908
  IPU firmware/model tag: T_0.0.1_210525
  Kernel: 4.9.227 (ARM 32-bit userspace, hard-float)

Request: SGS_IPU_SDK (or SGS_IPU_Toolchain) compatible with SSC8838G,
preferably from the branch matching sdk_commit b03a7d4 /
project_commit 0940dba / T_0.0.1_210525, containing:
  - ConvertTool (Caffe / TF GraphDef / SavedModel / Keras / TFLite;
    please confirm whether this branch supports ONNX input)
  - Calibrator + Compiler + Simulator + model viewer
  - mi_ipu.h, mi_ipu_datatype.h, mi_sys.h, mi_scl.h for this SDK generation
  - SSC8838G/Tiramisu compiler target configuration
    (target name + CompilerConfig equivalent + input_config templates)
  - IPU firmware compatibility documentation and
    model/compiler/runtime compatibility rules
  - Board examples: dla_classify, dla_simulator,
    ipu_log / utilization tools, and a MobileNetV2 example

Questions:
  1. If the exact b03a7d4 branch is unavailable, is a newer SDK
     backward-compatible with the T_0.0.1_210525 runtime and firmware?
     Which SDK version do you recommend for this device?
  2. What is the compiler target name for SSC8838G, and what are the
     model ABI compatibility rules (chip / compiler / firmware matching)?
  3. What is the supported host environment (OS, CPU, Python, Docker image)?
  4. What are the license requirements (NDA, license server, dongle,
     activation) and the download/access procedure?

We will not redistribute the SDK. Thank you for your support.
```

## 4. What the owner attaches / tells FAE if asked

- The four runtime identifiers in §3 (SoC + lib commits + firmware tag + kernel). Nothing else is needed.
- Do NOT disclose: model contents, keys, disassembly, internal schedules, or unrelated project information.

## 5. What to record when FAE replies (private, never commit)

```text
responder / date / ticket or thread URL
SDK filename + size + SHA256 + stated version/branch
download source (FTP / Download Center / direct link)
NDA or license terms accepted (file the paperwork, note expiry)
```

Next step on receipt: `docs/research/C2M_IPU_SDK_RECEIPT_VALIDATION_V1.md`.
Status until a compatible drop is in hand: `NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`.
