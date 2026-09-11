# C2M SGS_IPU_SDK Hunt V1 — Toolchain Recovery / Search

**Status:** RESEARCH ONLY. No firmware/Candidate change. No flash. No SDK archive downloaded or committed.
**Date:** 2026-09-11. **Target:** SSC8838G / Mercury6 / Tiramisu, `sdk_commit b03a7d4`, `project_commit 0940dba`, fw `T_0.0.1_210525`.
**Ground truth reused:** `docs/research/C2M_SIGMASTAR_IPU_STACK_V1.md`, `C2M_IPU_TOOLCHAIN_V1.md`, `C2M_IPU_MODEL_FORMAT_V1.md`, `docs/hardware/C2M_IPU_TOOLCHAIN_REQUEST_CARD.md`.

## 0. Objective and stop rule

Find the closest obtainable SGS_IPU_SDK / compiler package to the C2M runtime, prove provenance/version/SoC fit,
and decide whether a tiny custom model can be compiled into a C2M-loadable offline IPU model.
Stop at SUCCESS (P0/P1 SDK + host validation) or EXHAUSTED (no legal/public package, only NDA/FAE path).
**This hunt stopped at EXHAUSTED → `NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`. Verdict D.**

## 1. C2M target fingerprint (ground truth, not re-derived)

```text
SoC:            SigmaStar SSC8838G (SigmastarUpgradeSD_SSC8838G.bin)
Family:         Mercury6 / Tiramisu, SSC35X generation (family-level, MEDIUM)
Userspace:      ARMv7-A hard-float VFPv3-D16, no NEON evidence
Kernel:         4.9.227
libmi_ipu.so:   26168 B, sha256 8f95f28d…ac80d54
                project_commit.0940dba sdk_commit.b03a7d4 build_time.20220606101908
                runtime tag T_0.0.1_210525
libmi_scl.so:   sdk_commit.b03a7d4 (same drop lineage)
libmi_sys.so:   project_commit.0940dba / sdk_commit.c5dda48 (sibling drop)
ipu_firmware:   600208 B, sha256 61c4663d…0842d55
MI_IPU exports (11, CONFIRMED dynsym): CreateDevice/DestroyDevice/CreateCHN/DestroyCHN/
  GetInOutTensorDesc/GetInputTensors/PutInputTensors/GetOutputTensors/PutOutputTensors/
  Invoke/GetOfflineModeStaticInfo
Absent locally (present only in newer docs): Tensors2/Invoke2/Invoke2Custom/
  CreateCHNWithUserMem/DestroyDeviceExt/CancelInvoke
Reference flow: Caffe/TF-GraphDef/SavedModel/Keras/TFLite → ConvertTool.py → .sim →
  Calibrator.py → _fixed.sim → Compiler.py → _sgsimg.img → Simulator.py → board MI_IPU
2021 Pudding doc ConvertTool -h lists 5 frameworks, NO onnx subcommand (see §3 correction below).
```

## 2. Search strategy executed (2026-09-11)

Broad hunt with provenance logging, in priority order:

1. SigmaStar official/comake mirrors — HIT (docs only, §3).
2. Public GitHub/Gitee/GitLab code, forks, release artifacts — HIT on mirrors, MISS on SDK drop.
3. Vendor BSP mirrors (Buildroot_SigmastarOriginalSDK, DongshanPI, OpenIPC, waybeam, linux-chenxing).
4. OpenIPC/community SDK mirrors (johnchia sdk/headers/lib, divinus, waybeam_venc).
5. Board-support packages (Comake Pi D2/D3, SSD20X/SSD220/Pcupid sigdocs).
6. Chinese embedded forums (bbs.16rd, CSDN, Zhihu).
7. CSDN/16rd/EEWorld-style posts — HIT (manual text, no attachment recovered).
8. Baidu/OneDrive/Google Drive references — NO traceable SGS_IPU_SDK link found (dead end, recorded).
9. Archived release indexes (doc.comake.online versioned toolchain dirs) — HIT (S21 + vS03.0.8 + 26062914 LLM dirs).

Chinese queries used: 星宸 IPU SDK, 星宸 DLA SDK, 星宸 模型转换, SGS IPU 模型转换,
SSC8838G SDK/IPU/DLA, Mercury6 IPU, Tiramisu IPU, SGS_IPU_SDK 下载, SigmaStar 模型编译.
Adjacent SoCs swept: SSC9381G/SSC9383/SSC359G/SSC335/SSC333/SSD20X/Infinity6/6E/Pudding/Pcupid/Mercury6/Tiramisu.
No cross-chip compatibility assumed.

## 3. Findings

### 3.1 Official/comake documentation (PUBLIC docs, Confidential-A mirrors) — CONFIRMED

| # | Doc | Version/date | What it proves | C2M fit |
|---|---|---|---|---|
| D1 | Pudding DLA tool doc `wx.comake.online/.../SSC9381G_9351_Pudding-ULS00V040-20210913/customer/development/dla/tools.html` | 2021-09-13 | Full legacy flow: ConvertTool(5 fw)/Calibrator/Compiler/Simulator/SGS Netron 3.4.3, `cfg_env.sh`, `~/SGS_IPU_SDK+~/SGS_Models`, Py3.5/TF1.14/AVX2, mobilenet_v2 + ssd_mobilenet_v1 walkthroughs, `concat_net --transform CompilerConfig.txt`, dla_simulator cmd | OLD_ANALOG (Pudding/Infinity6e doc; flow HIGH, chip/ABI MEDIUM) |
| D2 | bbs.16rd `thread-570050-1-1` DLA SDK user manual repost | 2021-01-29 | Same flow but ConvertTool list **includes ONNX** + extra deps (`onnx==1.7.0 onnx-simplifier==0210 onnxruntime==1.3.0 sympy packaging joblib`); Netron 3.4.3; attachment gated behind forum reply/login (not recovered) | OLD_ANALOG with ONNX discrepancy (see §3.4) |
| D3 | Pcupid MI IPU API `doc.comake.online/Pcupid_DLC173V2.3.3_disp_sigdoc_en/platform/MI/ipu_en.html` | rev 3.0 2021-07-23 → updates to 2024-07-25, §1.5 extended 2025-04-16 | 21-API surface, chip table **Pudding/Tiramisu/Muffin/Mochi/Maruko/Opera/Souffle/Ifado/Iford/Pcupid/Ibopper/Ifackel/Jaguar1/Ifliegen** (Tiramisu: 48 ch / 1 core), full dla_classify/detect/NBatch/simulator/show_img_info/ipu_log/utilization/server examples, `E_IPU_ERR_MISMATCH_MODEL` (added 2022-06-01), struct reserve-field history | FAMILY_ONLY lineage anchor (names/arity match local 11; newer 10 absent locally) |
| D4 | Pcupid IPU User Guide `.../customer/Common/Development/ipu_userguid_en.html` | 2024 | `sdk/verify/release_feature/source/dla/` demo paths, `prog_dla_dla_simulator -i JPEG -m *.sim_sgsimg.img -c Unknown -f BGRA`, IPU Log + utilization flows, single-core statement, pointer to `IPU_Sigdoc_vS03.0.8` online docs | FAMILY_ONLY |
| D5 | SGS_IPU_Toolchain S21.0.5 `doc.comake.online/SGS_IPU_Toolchain_25111209-S21_en/` | **verified 25111209 (2025-11-12)** | ONNX-first flow: `SGS_converter.py onnx/caffe/tflite/tensorflow_graphdef`, `show_sdk_info.py` soc_version gating, `sgs_docker_v1.8.tar.xz` + `run_docker.sh`, `Quick_Start_Demo/onnx_yolov8s`, OpenDLA model zoo (YOLOv5/v8/seg/pose, LPR, PP-OCR, CLIP, MobileSAM, Conformer, WeSpeaker…), `Linux_SDK/sdk/verify/opendla` + `project/board/${chip}/dla_file/ipu_open_models/` | FAMILY_ONLY docs (all board examples show `CHIP_LIST=pcupid`; **no Tiramisu/SSC8838G row seen**; NO archive, toolchain binaries gated) |
| D6 | IPU_Sigdoc vS03.0.8 / SGS_IPU_Toolchain_26062914 LLM converter dirs | 2024–2026 refs | Referenced by User Guide §1.6; LLM `convert_hf_to_sim.py` path exists in 26062914 tree | UNKNOWN (index not fully enumerated; docs only) |
| D7 | Env setup docs (SSD20X/Alkaid) | 2021–2022 | SDK comes from **"FTP provided by SStar"**: `boot/kernel/project/SDK` tarballs; full-package build via deconfig | ACCESS evidence: registration/FTP-gated, not public |

### 3.2 GitHub/Gitee mirrors — inspected, NO compiler

- `johnchia/sigmastar-sdk` (PROVENANCE: modules harvested from shipped camera fw via OpenIPC `sigmastar-osdrv-infinity6e`, Alkaid release_0607 built 2022-06-07; explicitly NOT a vendor tarball): Infinity6e kmods + sensor/ISP blobs. **No IPU toolchain, no ConvertTool/Compiler, no Tiramisu.** Rank: UNRELATED (wrong family) for C2M compile.
- `johnchia/sigmastar-headers` (reconstructed ABI headers, NOT vendor drops; validated against Alkaid `mi_*_datatype.h`): `infinity6e` (SSC30KQ/336Q/338Q/339G, MI 0xF1) + `infinity6c` (MI 3.0). **No `mi_ipu.h`, no Tiramisu/Mercury6 dir.** Rank: UNRELATED for C2M compile; useful only as header-reconstruction method reference.
- `johnchia/sigmastar-lib` (companion userspace MI libs): same Infinity6e scope. No IPU compiler.
- OpenIPC (`firmware`, `u-boot-sigmastar`, `linux`, `sensors`, `divinus`, `waybeam`, `ipctool#21`): VIF/ISP/VENC scope; `ipctool#21` gives the **mercury6 (SSC35X) Tiramisu** label incl. `SSC359G 2xA53 BGA439`. No IPU SDK.
- `DongshanPI/Buildroot_SigmastarOriginalSDK`, `fifteenhex/buildroot_mercury5` (70mai dashcam), `linux-chenxing/linux-chenxing.org` (`mercury6/` = stub `index.md` + SSD268 demo-board PDF only): BSP/kernel scope, no DLA/IPU toolchain.
- `Sigmastar-Opensource` org (tagline "Makes AI product development easier Based On SGS IPU SOC"): only `Comake_Pi_D3` intro + `PhyAgentOS-core` pinned. No SDK drop.
- `HuaqiuOpenHardware/Comake-Pi-D2` (SSC309QL, not Tiramisu): board files only.
- Code search for `"ConvertTool.py" SigmaStar`, `"SGS_IPU_SDK"`, `"sim_sgsimg.img"`, `"prog_dla_dla_simulator"`, `"MI_IPU_GetOfflineModeStaticInfo"`: only doc mirrors + prior C2M research hit. **Zero public repo hosts the scripts or binaries.**
- Gitee-scoped query: no SGS_IPU_SDK repo found (only unrelated `sgs-*` bioinformatics/firmware-service noise).

### 3.3 Forums / vendor news

- CSDN `magic_ll` 2023-06-26 (YOLOv5s → 9383): states `DLA==IPU`, SGS `.sim` + Netron 5.3.5; assumes SDK in hand, no drop link, page not fetchable (521) — supporting-only.
- Zhihu/vendor-news cluster: SSC8838G ≈ dual-A53 + IPU (0.8 TOPS figure is secondary, NOT design basis); SSD268G Tiramisu display-series note.
- Comake forum article 790: **Tiramisu ISP-tuning series applies to SSD268G, SSC359G, SSC8838G** — best public evidence SSC8838G ∈ Tiramisu (MEDIUM, secondary).
- 16rd SigmaStar/Mstar board: manual-text posts only; SDK attachments (if any) behind login/reply gate, not recovered.

### 3.4 ONNX verdict (corrects prior "2021 doc has no ONNX")

```text
Pudding ULS00V040 2021-09-13 ConvertTool -h : 5 subcommands, NO onnx  → ONNX ABSENT in that drop.
bbs.16rd 2021-01-29 variant            : lists TF/Keras/Caffe AND ONNX (+onnx* pip deps) → ONNX PRESENT in that variant.
S21.0.5 2025-11-12 (SGS_converter.py)  : ONNX is the PRIMARY supported framework → ONNX PRESENT (newer).
C2M-era (sdk b03a7d4, 2022-06)         : UNKNOWN — no matching drop inspected; do NOT claim either way.
Stock blobs give no ONNX evidence (encrypted, no magic) — format verdict unchanged.
```

### 3.5 Exact version matching (all negative)

Searched package contents/indexes for `b03a7d4`, `0940dba`, `T_0.0.1_210525`, `210525`, `20220606`,
`Tiramisu`, `Mercury6`, `SSC8838G`, `SSC35`: **zero public SDK hits**.
`b03a7d4`/`0940dba` appear only in C2M-local strings and prior C2M research.
`SSC8838G` appears only in C2M firmware name + comake forum article-790 title context + CN news.
No `sdk_commit`/`project_commit`/build-date/chip-table match exists in any public candidate.
Compatibility ranks assigned: best docs = FAMILY_ONLY; mirrors = UNRELATED/OLD_ANALOG; nothing EXACT or NEAR.

### 3.6 Host / license / docker facts (docs only)

- Legacy (2021): Linux x86-64 AVX2 Intel, i5/6GB min, i7/8GB rec; Python 3.5, TF 1.14, numpy 1.16.4/1.16.6, protobuf≥3.8, six, opencv≥3.4.0.14, cython, pycocotools, matplotlib, scipy, pillow 6.1, python3-tk, libc6-dev-i386, libstdc++6, python-qt4; `source cfg_env.sh`; Netron `.exe` on Windows.
- New (S21): Docker `sgs_docker_v1.8.tar.xz` + `run_docker.sh` (`--privileged --net=host -v /:/work`); container does NOT include toolchain (copy in via mount/`docker cp`); rec Xeon Gold 6242+/256GB, min i7/32GB; `source cfg_env.sh`; `show_sdk_info.py` for chip list.
- License: every toolchain doc carries `Confidential A`; SDK distribution is via SStar FTP / Comake SDK Download Center / FAE request (registration-gated, NDA expected). **No license-server/dongle evidence in docs** (recorded UNKNOWN, assume possible). No public redistribution grant found → archives must NOT be committed even if obtained.

## 4. Candidate ranking (summary; full matrix in companion doc)

```text
P0 exact (C2M-matching archive) ............ NONE FOUND
P1 near-C2M (b03a7d4/Tiramisu archive) ..... NONE FOUND
P2 same-IPU-generation docs ................ D3+D4 (Pcupid API+UserGuide, Tiramisu row) + D5 (S21 toolchain, pcupid-gated)
P3 older reference only .................... D1+D2 (Pudding 2021 flow + bbs ONNX variant), K9 (CSDN 9383 note)
Mirrors (no compiler) ...................... johnchia sdk/headers/lib, OpenIPC, Buildroot, linux-chenxing, Comake Pi boards
```

## 5. Success level reached: LEVEL 0 (docs only)

- LEVEL 1 (archive located): NO. LEVEL 2 (inspected plausible): NO (nothing to inspect).
- LEVEL 3 (`-h` runs): NO. LEVEL 4 (MobileNetV2 → sim → fixed → img → Simulator PASS): NO.
- LEVEL 5 (board Invoke): explicitly NOT claimed (no hardware action in this task).
- MobileNetV2 conversion status: NOT STARTED (no compiler; doc walkthroughs exist for caffe_mobilenet_v2 in D1 and onnx_yolov8s in D5, both unexecuted).

## 6. Largest blocker

`NATIVE_IPU_TOOLCHAIN_EXTERNAL_DEPENDENCY`: no public SGS_IPU_SDK/SGS_IPU_Toolchain drop matches
`sdk_commit b03a7d4 + T_0.0.1_210525 + SSC8838G/Tiramisu target`. All download paths are FAE/FTP/registration-gated.

## 7. Best vendor/FAE request path

Comake/SigmaStar FAE via Comake forum SDK Download Request Process / SDK Download Center
(`dev.comake.online`), citing exact C2M version strings (see ACCESS_PATH doc for copy/paste card).
Request must ask for: ConvertTool (+ONNX Y/N for the b03a7d4 branch), Calibrator, Compiler,
Simulator, SGS Netron, `mi_ipu.h`/`mi_ipu_datatype.h`/`mi_sys.h`/`mi_scl.h` of that generation,
SSC8838G compiler target config (`show_sdk_info.py` output + `CompilerConfig.txt` equivalent),
board demos (dla_classify/detect/simulator(NBatch)/show_img_info/ipu_log/utilization/server),
op list + model limits, `sgs_docker` image reference, and NDA/redistribution terms.

## 8. Top 3 next actions

1. Send FAE request card (ACCESS_PATH doc §2) and record drop filename/SHA256/version privately in `external/`.
2. On receipt (no commit): hash → tree inspect → `show_sdk_info.py` (chip list must contain Tiramisu/SSC8838G) → `ConvertTool/SGS_converter -h` (record ONNX) → `compare_mi_ipu_api.py` vs local 11-API list.
3. If chip list fits: MobileNetV2-caffe 224 walkthrough only (`.sim → _fixed.sim → _sgsimg.img → Simulator`), then structural (NOT byte) comparison vs stock blobs.

## 9. Remaining UNKNOWNs

Chip-exact TOPS/RAM/opaque struct packing/enum values; C2M-branch ONNX support; `sgs_docker` image digest;
license-server/dongle requirement of the b03a7d4 drop; `show_sdk_info.py` chip list of any C2M-era toolchain;
model-header version/magic (stock encrypted); compiler↔runtime/fw compatibility table; whether S21-compiled
`pcupid`-target `.img` loads on Tiramisu (assume NO).

## 10. Evidence pointers

- Matrix: `docs/research/C2M_SGS_IPU_SDK_CANDIDATE_MATRIX_V1.md`
- Compatibility: `docs/research/C2M_SGS_IPU_SDK_COMPATIBILITY_V1.md`
- Access path: `docs/research/C2M_SGS_IPU_SDK_ACCESS_PATH_V1.md`
- JSON: `docs/research/EVIDENCE_C2M_SGS_IPU_SDK_HUNT_V1.json`
- Tools: `tools/research/ipu_sdk/fingerprint_sgs_sdk.py`, `tools/research/ipu_sdk/compare_mi_ipu_api.py`
- Prior baseline: `docs/research/C2M_SIGMASTAR_IPU_STACK_V1.md`, `C2M_IPU_TOOLCHAIN_V1.md`, `C2M_IPU_MODEL_FORMAT_V1.md`
