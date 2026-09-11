# C2M SGS_IPU_SDK Compatibility V1 — API / Chip / Model-Format

**Date:** 2026-09-11. **Research only.** Local baseline: `sdk_commit b03a7d4`, 11 MI_IPU exports, fw `T_0.0.1_210525`.
Doc baseline: Pcupid MI IPU API rev 3.0 (2021-07-23 → 2024-07-25) + §1.5 chip table (2025-04-16).

## 1. MI_IPU API diff: local lib vs doc surface

Local (CONFIRMED `libmi_ipu.so` dynsym, 2022-06-06): 11 functions.

```text
MI_IPU_CreateDevice, MI_IPU_DestroyDevice, MI_IPU_CreateCHN, MI_IPU_DestroyCHN,
MI_IPU_GetInOutTensorDesc, MI_IPU_GetInputTensors, MI_IPU_PutInputTensors,
MI_IPU_GetOutputTensors, MI_IPU_PutOutputTensors, MI_IPU_Invoke,
MI_IPU_GetOfflineModeStaticInfo
```

Doc (Pcupid API §§2.2–2.21): 21 functions = local 11 + 10 newer.

```text
MATCH (11):  all local exports exist in doc with same names/arity (HIGH).
ADDED in doc, ABSENT locally (10 — must NOT be called on C2M):
  MI_IPU_GetInputTensors2, MI_IPU_PutInputTensors2,
  MI_IPU_GetOutputTensors2, MI_IPU_PutOutputTensors2,
  MI_IPU_Invoke2, MI_IPU_Invoke2Custom,
  MI_IPU_CreateCHNWithUserMem, MI_IPU_DestroyDeviceExt,
  MI_IPU_CancelInvoke, (DestroyDeviceExt counted; CreateDevice/Device pair otherwise same)
MISSING (doc lacks something local has): NONE.
SIGNATURE_RISK (same name, wider struct in doc — MEDIUM, do NOT copy):
  MI_IPU_DevAttr_t: doc adds au32Reserve[8] (2022-06-13) + u32VariableGroup/u32CoreMask (2023-09-26).
    Local disasm proves only [0]=varSize, [4]=0x10, [8]=2, [12]=0x10. Extra fields POSTDATE the lib.
  MI_IPUChnAttr_t: doc adds au32Reserve[8]. Demo sets depths 2,2 (matches stock).
  MI_IPU_TensorDesc_t: doc adds u32BufSize/u32InputWidthAlignment/u32InputHeightAlignment/
    eLayoutType (ex-bOutputNCHW) + au32Reserve[4] across 2022-02-25→2022-06-13→2022-08-15.
  MI_IPU_OfflineModelStaticInfo_t: doc adds eBatchMode/u32TotalBatchNumTypes/
    au32BatchNumTypes[]/eIpuWorkMode (2022-06-13). Local demo path uses u32VariableBufferSize only.
  MI_IPU_ELEMENT_FORMAT: doc adds GRAY (2022-02-25), COMPLEX64 (2022-08-15). Local lib handles INT16→float log.
```

Machine-checkable version of this table: `tools/research/ipu_sdk/compare_mi_ipu_api.py`
(local dynsym list vs candidate `mi_ipu.h` / `libmi_ipu.so`).

## 2. Revision timeline (doc rev history + local pin)

| Date | Event | C2M relevance |
|---|---|---|
| 2021-01-29 | bbs DLA manual (ONNX-listed variant) | OLD_ANALOG; ONNX discrepancy anchor |
| 2021-07-23 | MI IPU API rev 3.0 initial | lineage start |
| 2021-09-13 | Pudding tool doc ULS00V040 (5-fw ConvertTool) | OLD_ANALOG flow anchor |
| 2021-11-30 → 2022-01-20 | procfs, fw-path, chn limits, align numbers | family runtime behavior |
| 2022-02-25 | Invoke2Custom, GRAY, TensorDesc buf/align/NCHW fields | POSTDATES local lib — risk flag |
| **2022-06-01** | **`E_IPU_ERR_MISMATCH_MODEL`** | **proves compiler↔runtime version gate** |
| **2022-06-06** | **C2M `libmi_ipu.so` build (`b03a7d4`)** | **local pin** |
| 2022-06-13 | reserve fields + batch/work-mode enums | POSTDATES local lib — risk flag |
| 2022-08-15 | COMPLEX64, RuntimeInfo us unit | POSTDATES local lib |
| 2023-05-25 → 2023-09-26 | CancelInvoke, CreateCHNWithUserMem, DestroyDeviceExt, DevAttr group/mask | newer-only APIs |
| 2024-07-25 | permission/interrupt err codes | newer-only |
| 2025-04-16 | §1.5 chip table incl. Tiramisu | family anchor |
| 2025-11-12 | SGS_IPU_Toolchain S21.0.5 verified | modern ONNX flow (pcupid examples) |

Rule: any struct/API dated after 2022-06-06 is guilty-until-proven-innocent on C2M.

## 3. Compiler target discovery (required output)

```text
TARGET NAME | TARGET ID | SOURCE FILE | CONFIDENCE
Tiramisu    | numeric ID UNKNOWN | Pcupid ipu_en.html §1.5 chip table (48ch/1core row) | MEDIUM (family row, no per-chip ID published)
Pudding     | UNKNOWN | same table + Pudding tool doc filename | MEDIUM
Pcupid      | UNKNOWN | same table + S21 CHIP_LIST=pcupid examples | MEDIUM (wrong chip for C2M)
SSC8838G    | UNKNOWN | comake forum art.790 snippet (Tiramisu series SSD268G/SSC359G/SSC8838G) + fw filename | MEDIUM (series membership, not compiler ID)
Mercury6/SSC35X | UNKNOWN | OpenIPC ipctool#21 (mercury6 SSC35X Tiramisu; SSC359G 2xA53 BGA439) | MEDIUM
show_sdk_info.py chip list (any drop) | UNKNOWN | NOT recovered — first check on SDK receipt | UNKNOWN
```

No `strings`-level target database exists locally (no archive). Do NOT invent numeric arch IDs.

## 4. Model-format versioning

Legacy (K1/K2 docs): `.sim` (SGS Float flatbuffer) → `_fixed.sim` (INT8/16) → `_fixed.sim_sgsimg.img`
(SGS Offline cmd file, `Run Offline OK + Run Pack Tool OK`) → `Simulator.py`/`dla_simulator -m *.sim_sgsimg.img`.
Modern (K4): `SGS_converter.py --soc_version CHIP [--export_models]` → `.img` (+ optional float/fixed `.sim`).
C2M stock: six `adas`-embedded blobs (common 16B prefix `be2d6fe9…`, 7.8–8.0 entropy, page-aligned, no cleartext
magic/names) + `model.img` (507040 B, distinct header) — HIGH encrypted/compressed proprietary; detailed in
`C2M_IPU_MODEL_FORMAT_V1.md`. Firmware `ipu_firmware.bin` (600208 B, `73700430…`) is NOT a model.
No magic/version/chip-ID/compiler-stamp recovered from stock (encrypted). **Byte compatibility with any
candidate output is UNPROVEN and must NOT be claimed.** First discriminating test post-SDK:
compile conv-only model on matching drop and compare header prefix vs stock `be2d6fe9…`.

## 5. Cross-SDK compatibility verdict: UNKNOWN / unsafe (assume NO)

Evidence: `E_IPU_ERR_MISMATCH_MODEL` + `fw major/minor not matching` + `T_0.0.1_210525` checks tie a compiled
model to IPU generation + compiler version + firmware ABI. No compiler↔runtime compatibility table recovered.
S21 `pcupid`-target `.img` on Tiramisu C2M: assume NO until a `CreateCHN` mismatch test says otherwise.
Newer-compiler → older-runtime and older-compiler → newer-runtime are both UNKNOWN.

## 6. INT8 / framework verdicts (this hunt)

- INT8 path: doc-PROVEN flow (Calibrator 8/16-bit + `eElmFormat` INT8/INT16/INT32/FP32 + Simulator fixed/offline
  + `dequantizations` TRUE→FP32 / FALSE→int16). C2M proof: BLOCKED (needs compiler + `GetInOutTensorDesc` dump).
- ONNX: corrected §HUNT-3.4 — Pudding-2021 NO, bbs-2021-variant YES, S21 YES-primary, C2M-branch UNKNOWN.
- Legacy Caffe/TF-GraphDef/SavedModel/Keras/TFLite inputs: doc-PROVEN (K1 walkthroughs), C2M-branch applicability MEDIUM.
