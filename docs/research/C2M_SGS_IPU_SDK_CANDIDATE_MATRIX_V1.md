# C2M SGS_IPU_SDK Candidate Matrix V1

**Date:** 2026-09-11. **Research only; no archives downloaded, no binaries committed.**
Confidence: CONFIRMED / HIGH / MEDIUM / LOW / UNKNOWN (binding taxonomy from IPU stack doc).
Compatibility: EXACT / NEAR / FAMILY_ONLY / OLD_ANALOG / UNRELATED / UNKNOWN.

Ground truth (not a candidate): C2M runtime `sdk_commit b03a7d4 / project 0940dba / T_0.0.1_210525 / SSC8838G / 4.9.227 / 11 MI_IPU APIs`.

## Ranked matrix (required columns)

```text
SDK | DATE | SOURCE | SOC | API MATCH | MODEL FORMAT | COMPILER | CALIBRATOR | SIMULATOR |
HEADERS | ACCESS | COMPATIBILITY | RISK
```

| SDK | DATE | SOURCE | SOC | API MATCH | MODEL FORMAT | COMPILER | CALIBRATOR | SIMULATOR | HEADERS | ACCESS | COMPAT | RISK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K1 Pudding DLA tool doc ULS00V040 | 2021-09-13 | `wx.comake.online/.../SSC9381G_9351_Pudding-ULS00V040-20210913/.../dla/tools.html` (CONFIRMED fetched) | SSC9381G/Pudding Infinity6e | n/a (tool doc; flow names match) | `.sim→_fixed.sim→_sgsimg.img` documented | doc YES / binary NO | doc YES / binary NO | doc YES + `dla_simulator` cmd / binary NO | doc code excerpts only | public doc mirror (Confidential-A marking); **archive NDA-gated** | OLD_ANALOG | MEDIUM: flow proven, chip/ABI transfer unproven |
| K2 bbs.16rd DLA manual repost | 2021-01-29 | `bbs.16rd.com/thread-570050-1-1` (CONFIRMED fetched; attachment gated) | generic DLA/IPU | n/a | same + **ONNX listed** in ConvertTool (differs from K1) | doc YES / binary NO | doc YES / binary NO | doc YES / binary NO | none | public post; full text/attach behind reply+login (not recovered) | OLD_ANALOG | MEDIUM + ONNX-discrepancy flag (do not pick a winner without drop) |
| K3 Pcupid MI IPU API + IPU User Guide | rev3.0 2021-07-23 → 2024-07-25, §1.5 to 2025-04-16 | `doc.comake.online/Pcupid_DLC173V2.3.3_disp_sigdoc_en/{platform/MI/ipu_en.html, customer/Common/Development/ipu_userguid_en.html}` (CONFIRMED fetched) | Pcupid doc; chip table incl. **Tiramisu 48ch/1core** | **11/11 local names ⊆ 21 doc APIs**; 10 newer absent locally (HIGH, see compat doc) | SGS offline `.sim_sgsimg.img` + `MISMATCH_MODEL` (2022-06-01) | n/a (API doc) | n/a | board `dla_simulator(NBatch)/show_img_info/ipu_log/utilization/server` sources referenced | signature-level excerpts (`mi_ipu.h` snippets in examples) | public doc mirror; headers/libs gated | FAMILY_ONLY | LOW as lineage anchor; MEDIUM if used for struct values |
| K4 SGS_IPU_Toolchain S21.0.5 | **verified 25111209 (2025-11-12)** | `doc.comake.online/SGS_IPU_Toolchain_25111209-S21_en/` (CONFIRMED: index/Env/QuickStart/Convert/Simulate/OpSupport/OCR demo fetched) | examples all `CHIP_LIST=pcupid`; **no Tiramisu/SSC8838G row observed** | n/a (toolchain doc; `--soc_version CHIP` + `show_sdk_info.py` gating) | one-click `SGS_converter.py → .img (+--export_models .sim)`; float/fixed/offline sim; RPC `ipu_server` sim | doc YES / binary NO | doc YES (`calibrator`, `torch_calibrator`, `calibrator_custom`) / binary NO | doc YES (`simulator.py`, custom + RPC) / binary NO | `input_config.ini`/preprocess-spec level | public doc mirror; **toolchain + `sgs_docker_v1.8.tar.xz` + `Quick_Start_Demo` gated (mount/docker-cp path)** | FAMILY_ONLY (docs; wrong-chip examples) | MEDIUM: best modern flow reference; cross-chip load assume NO |
| K5 IPU_Sigdoc vS03.0.8 + 26062914 LLM tree | 2024–2026 refs | Referenced from K3 §1.6; `doc.comake.online/.../IPU_Sigdoc_vS03.0.8...`, `SGS_IPU_Toolchain_26062914_en/.../LLMConverter` (partially fetched) | UNKNOWN (not enumerated) | UNKNOWN | ONNX + HF `convert_hf_to_sim.py` (LLM branch) | doc-partial / binary NO | UNKNOWN | UNKNOWN | none recovered | public doc refs; drops gated | UNKNOWN | HIGH uncertainty — do not cite as C2M path |
| K6 johnchia sigmastar-sdk + sigmastar-lib | Alkaid release_0607 built 2022-06-07 (per PROVENANCE) | `github.com/johnchia/sigmastar-sdk`, `sigmastar-lib` (CONFIRMED fetched; harvest-from-shipped-fw, NOT vendor tarball) | Infinity6e (6b0/6c/6e kmods) — **not Tiramisu** | none (kmods/sensors/ISP; no IPU API) | none | NO | NO | NO | NO (see K7) | public git (proprietary payload, pinned-hash fetch) | UNRELATED (compile) | LOW risk if untouched; HIGH if mistaken for C2M SDK |
| K7 johnchia sigmastar-headers (+divinus/waybeam lineage) | validated vs 2021-09-02 & 2022-06-01 Alkaid drops (per README) | `github.com/johnchia/sigmastar-headers` (CONFIRMED fetched) | infinity6e MI0xF1 + infinity6c MI3.0; **no Mercury6/Tiramisu, no mi_ipu.h** | n/a (SYS/VIF/VENC/SCL scope) | n/a | NO | NO | NO | reconstructions, NOT vendor drops (explicit) | public MIT-scope reconstructions | UNRELATED (compile) | method reference only; struct reuse on C2M = memory-corruption risk |
| K8 BSP/board mirrors (OpenIPC, Buildroot_SigmastarOriginalSDK, linux-chenxing mercury6, Comake Pi D2/D3) | 2019–2026 | OpenIPC org, `DongshanPI/Buildroot_SigmastarOriginalSDK`, `linux-chenxing.org/mercury6/` (stub), `HuaqiuOpenHardware/Comake-Pi-D2` (SSC309QL), `Sigmastar-Opensource/Comake_Pi_D3` (CONFIRMED listings) | SSC309QL / Infinity6x / SSD20X / stub Mercury6 | none IPU | none | NO | NO | NO | BSP-level only | public | UNRELATED | LOW (out of scope for compile) |
| K9 CSDN YOLOv5s→9383 + Zhihu/vendor-news cluster | 2023-06-26; 2021–2024 | `blog.csdn.net/magic_ll/article/details/131320806` (index CONFIRMED; page 521 on fetch), Zhihu selection guides | SSC9383 / SSC359G / SSC8838G mentions | n/a | `.sim` + Netron 5.3.5 mention | assumed, not shown | assumed | assumed | none | public posts; no links | OLD_ANALOG (supporting only) | MEDIUM-LOW: proves community flow exists, proves no drop |
| K10 Cloud-drive / re-upload mirrors | — | Baidu/OneDrive/Drive queries in CN+EN | — | — | — | NO | NO | NO | NO | **no traceable link found** | UNKNOWN | dead end recorded 2026-09-11; do NOT invent links |

## Ranking

```text
P0 exact (b03a7d4+Tiramisu archive, inspected) .... NONE
P1 near-C2M (same-branch archive) ................ NONE
P2 same IPU generation (docs, Tiramisu row) ...... K3, K4 (docs only; K4 examples pcupid-gated)
P3 older reference only .......................... K1, K2, K9
Out of scope (no compiler) ....................... K6, K7, K8
Not found ........................................ K10, any archive of K1–K5
```

## Per-candidate file inventory (what was actually seen)

- K1: HTML tool doc (12 sections: Convert/Calibrator/Compiler/Simulator/DumpDebug/postprocess/new-Layer/gray/op-lists/limits); `cfg_env.sh`, `requirements.txt` (tuna mirror), `CompilerConfig.txt`, `concat_net`, Netron 3.4.3 refs. No archive.
- K2: HTML post text (tool list + env table incl. onnx* deps); framework diagram image alt-text; attachment denied without login. No archive.
- K3: API HTML (rev table, §1.5 chip table, §1.7 call order, §1.8 nine demos incl. full `dla_classify.cpp`, §2 21 APIs, §3 types, §4 `E_IPU_ERR_*`, §5 procfs). No archive.
- K4: toolchain HTML (Env: `sgs_docker_v1.8`, QuickStart onnx_yolov8s one-click, Convert: input_config/preprocess/SGS_converter per-fw, Simulate: `simulator.py`+RPC, OpSupport: Caffe/TF/ONNX tables + SGS_CHALK + constraints). No archive.
- K6/K7/K8: public git trees (kmods, headers, BSP). Cloned listings only; nothing executed.
- Dead links recorded: CSDN article body (HTTP 521 on 2026-09-11); `dev.comake.online/home/article/790` body (empty fetch; title snippet confirms SSD268G/SSC359G/SSC8838G Tiramisu series — MEDIUM).
