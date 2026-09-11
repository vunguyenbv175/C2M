# C2M SigmaStar IPU Stack V1 — Accelerator, Runtime, Memory, Coexistence

**Status:** RESEARCH ONLY. No firmware/Candidate change. No flash. No SDK archive committed.
**Date:** 2026-09-11. **SoC:** SSC8838G (upgrade image `SigmastarUpgradeSD_SSC8838G.bin`).
**Ground truth reused:** ARMv7-A hard-float VFPv3-D16 (`docs/firmware/TARGET_ABI.md`); `MI_SYS_Init→MI_SCL_CreateDevice→IPUCreateDevice`; `1920x1440@10Hz raw_adas/ringbuf_vehicle`; 6 blobs byte-identical EN/VI (`docs/reverse/ADAS_PACKAGE_LOADER_V1.md`).

## 0. Confidence taxonomy (binding)

```text
CONFIRMED — byte-measured local artifact or fetched official doc statement
HIGH — strong primary evidence, minor inference
MEDIUM — family-level or single-source official doc, needs chip-exact proof
LOW — weak/secondary only
UNKNOWN — not verified; do not design safety on it
```

## 1. Accelerator identity

| Claim | Evidence | Status | Confidence |
|---|---|---|---|
| AI block is SigmaStar **IPU** (Intelligence Processing Unit), also called **DLA** in SDK docs | `lib/libmi_ipu.so` + `bootconfig/modules/4.9.227/mi_ipu.ko` in rootfs; `mi_ipu.ko` strings `sstar,ipu` + `sstar,dla`, `DLA_PowerOn/Off`, `dla auto power`; DLA SDK tool doc states `DLA与IPU指代同一个部件` (DLA==IPU); IPU User Guide `IPU (Intelligence Processing Unit)` | CONFIRMED name | CONFIRMED |
| Family: Mercury6 / Tiramisu generation (SSC35X) | OpenIPC `ipctool#21`: `mercury6 (SSC35X) Tiramisu`, e.g. `SSC359G 2xA53 Extern BGA439`; C2M upgrade name `SSC8838G`; customer `BGA439`-class package reported in CN vendor-news cluster (secondary); lib version `project_commit.0940dba sdk 2022-06` matches Tiramisu-era Alkaid SDK | FAMILY-LEVEL | MEDIUM (chip-exact datasheet NDA-blocked) |
| CPU: ARMv7-A 32b LE, dual Cortex-A53 (LIKELY), VFPv3-D16, **no NEON evidence** | `TARGET_ABI.md`: `EM_ARM`, `e_flags 0x5000400`, `.ARM.attributes CPU_arch=10/Profile A/VFPv3-D16`, `Advanced_SIMD_arch` absent on `cardv`+`adas` | CONFIRMED userspace / LIKELY cores | HIGH (cores need datasheet) |
| TOPS / freq / RAM usable | No primary source. CN news `0.8 TOPS` is secondary, NOT design basis. `LX_MEM/mma_heap/cma` are bootargs only, not DRAM proof. **Do not invent.** | UNKNOWN | UNKNOWN |
| IPU is DLA + RISC-V control + single core (this generation) | `mi_ipu.ko` strings: `wait risc-v response timeout`, `shutdown IPU/RISCV`, `CCIF_RISC2CPU_IRQ`, `hal_ccif_*`, `MDRV_IPU_*`; IPU User Guide: `current chip has only one IPU core, only core0`; IPU API doc chip table: Tiramisu `Channel 48 / Core 1` (Pcupid doc, family row) | Core count HIGH, RISC-V CONFIRMED | HIGH |

Primary sources:

```text
SOURCE: C2M EN rootfs (build/rootfs_en_inner.bin, 17769984 B) + customer UBIFS (build/en_carve/customer...)
VERSION: mi_ipu lib/ko build_time.20220606101905/0908, sdk_commit.b03a7d4, project_commit.0940dba
FILE: lib/libmi_ipu.so (26168 B, sha256 8f95f28d...ac80d54), bootconfig/modules/4.9.227/mi_ipu.ko (32940 B, c84da5eb...5f4d94)
SYMBOL: sstar,ipu / sstar,dla / MI_IPU_IOCTL_* / risc-v strings
CONFIDENCE: CONFIRMED existence; MEDIUM exact SSC8838G stepping
```

```text
SOURCE: SigmaStar official docs via comake.online mirror (wx/doc.comake.online)
VERSION: IPU API rev 3.0 (2021-07-23) + updates to 2024-07-25; IPU User Guide 2024; DLA tool doc SSC9381G Pudding ULS00V040 2021-09-13
FILE: platform/MI/ipu_en.html, customer/Common/Development/ipu_userguid_en.html, customer/development/dla/tools.html
CONFIDENCE: DIRECT API evidence (names/signatures match local libs); FAMILY-LEVEL for chip limits (Pcupid/Pudding doc, Tiramisu row)
```

## 2. Runtime libraries and versions

| File | Size | SHA256 | ELF | SONAME/NEEDED | Role | Confidence |
|---|---|---|---|---|---|---|
| `lib/libmi_ipu.so` | 26168 | `8f95f28daa83f8d132073a1eddd9afbfa536be8ce56f81a56ccba6e16ac80d54` | ARM32 LE EXEC? ET_DYN, EM_ARM, `e_flags 0x5000400` | NEEDED `libc.so.6`; `sstar_mi_so_version_string`: `Sigmastar Module mi_ipu version: project_commit.0940dba sdk_commit.b03a7d4 build_time.20220606101908`; `T_0.0.1_210525` | IPU userspace shim (ioctl marshal) | CONFIRMED |
| `lib/libmi_sys.so` | 13808 | `87f511957577a7fc001f0bfd0c08d3a69bf3c5d75c8394cef6f5b280bbbd5265` | ET_DYN ARMv7 hard-float | `...mi_sys version: project_commit.0940dba sdk_commit.c5dda48 build_time.20220815100459` | Sys/MMA/map/bind | CONFIRMED |
| `lib/libmi_scl.so` | 9680 | `ebfb0503e85f3591d35b6b643381de21ba9bcf5a9866d02175d84d135608311f` | ET_DYN ARMv7 | `...mi_scl version: project_commit.0940dba sdk_commit.b03a7d4 build_time.20220606102207` | Scaler shim | CONFIRMED |
| `bootconfig/modules/4.9.227/mi_ipu.ko` | 32940 | `c84da5eb0921c9dde3f4576b8eb69c146b454ba7121ce92ec17cdbe94d5f4d94` | ET_REL ARM, `vermagic 4.9.227 SMP preempt mod_unload ARMv7 thumb2` | `depends=mi_common`, `author=Sigmastar license=GPL` | IPU kernel driver | CONFIRMED |
| `lib/libmi_isp.so` | 77792 | `c24ef540...` | ET_DYN | IQ/3A stack | ISP (not AI) | CONFIRMED |
| `lib/libmi_vif.so` | 9680 | `0221daa2...` | ET_DYN | VIF shim | sensor input | CONFIRMED |
| `mi_sys.ko` 547264, `mi_scl.ko` 122576, `mi_isp.ko` 119768, `mi_vif.ko` 89872 | — | — | — | — | media drivers | CONFIRMED (rootfs list) |
| `/minieye/adas/ipu_firmware.bin` | 600208 | `61c4663ddef26bdfef16b1789f90d90bb6f2e9a36c10de7f6c365a9600842d55` | firmware blob, entropy 7.04, header `73700430...` | loaded by `MI_IPU_CreateDevice(pFirmwarePath...)` | IPU firmware image | CONFIRMED |
| `/minieye/adas/third_lib/libmi_ive.so` | 754524 | (inventory; hash in `en_customer_inventory.json`) | ET_DYN | IVE (video engine) | CV pre/post, NOT the NN core | HIGH |

All `libmi_*` are thin shims (`9680–26168 B` except isp): they marshal ioctl blocks (`_MI_WRAPPER_DEVICE_Open`, `/dev/mi/*`, `failed to ioctl 0x%08lx`) to `/dev/mi_ipu`, `/dev/mi_sys`, `/dev/mi_scl`. Real work is in `mi_ipu.ko` + `mhal.ko` (2572184 B) + firmware.

## 3. MI_IPU API surface (recovered from ELF dynsym + official API doc)

### 3.1 Local exports (`libmi_ipu.so` dynsym, 59 entries)

```text
SOURCE: build/rootfs_en_inner.bin:lib/libmi_ipu.so
VERSION: sdk_commit.b03a7d4 20220606
FUNCTIONS (all GLOBAL FUNC in .text):
  MI_IPU_CreateDevice      @0x21f1 sz544
  MI_IPU_DestroyDevice     @0x2411 sz628
  MI_IPU_CreateCHN         @0x2685 sz3280
  MI_IPU_DestroyCHN        @0x3355 sz832
  MI_IPU_GetInOutTensorDesc@0x3695 sz616
  MI_IPU_GetInputTensors   @0x38fd sz292
  MI_IPU_PutInputTensors   @0x3a21 sz208
  MI_IPU_GetOutputTensors  @0x3af1 sz300
  MI_IPU_PutOutputTensors  @0x3c1d sz208
  MI_IPU_Invoke            @0x3ced sz2108
  MI_IPU_GetOfflineModeStaticInfo @0x4529 sz232
  + sstar_mi_so_version_string
IMPORTS: MI_SYS_Mmap/Munmap/FlushInvCache/ConfigPrivateMMAPool/PrivateDevChnHeapAlloc/Free, CamOs*/CamFs* wrappers, libc
CONFIDENCE: CONFIRMED (byte-measured dynsym)
```

No `MI_IPU_Init/DeInit/LoadModel/CreateModel/Run/Forward` in this lib. Model load is via `CreateCHN` with offline-model path or serialized-read callback (see §3.3 and dla_classify example).

Newer API doc lists additionally `..._Tensors2/Invoke2/Invoke2Custom/CreateCHNWithUserMem/DestroyDeviceExt/CancelInvoke` — **ABSENT from C2M lib** (2022-06). Do not call them on C2M.

### 3.2 Stock callers

| Function | Library | Caller | Args (from example + disasm) | Return | Confidence |
|---|---|---|---|---|---|
| `MI_IPU_CreateDevice` | libmi_ipu.so | `adas:_Z15IPUCreateDevicePcj` (VA 0x94475, sz34) → PLT `MI_IPU_CreateDevice` | `(DevAttr*, NULL, fwPath, 0)`; local wrapper `(char *fwPath, u32 varBufSize)` builds DevAttr on stack: `[0]=varSize, [4]=0x10, [8]=2, [12]=0x10` (Thumb-2 disasm §5) | 0 on success; logs `client [%d] Create IPU device` | HIGH |
| `MI_IPU_DestroyDevice` | libmi_ipu.so | adas | `()` | — | CONFIRMED import |
| `MI_IPU_CreateCHN` | libmi_ipu.so | adas `vehicle::Cnn::InitIpu` → `cnn::CreateCnn` | `(u32 *chn, ChnAttr{inDepth,outDepth}, SerializedReadFunc|NULL, modelPath|mem)`; stock depths `2,2` in demo; adas logs `create ipu channel failed!`, `client [%d] Create IPU channel %u` | 0 / `no available IPU channel` | HIGH |
| `MI_IPU_DestroyCHN` | libmi_ipu.so | adas | `(chn)` | — | CONFIRMED |
| `MI_IPU_GetInOutTensorDesc` | libmi_ipu.so | adas | `(chn, SubNet_InputOutputDesc*)`; adas logs `MI_IPU_GetInOutTensorDesc failed.` + `input tensor[%d] / eElmFormat: / output tensor[%d]` | 0 | CONFIRMED |
| `MI_IPU_GetOutputTensors` / `PutOutputTensors` | libmi_ipu.so | adas | `(chn, TensorVector*)` | 0 | CONFIRMED |
| `MI_IPU_Invoke` | libmi_ipu.so | adas `vehicle::Cnn::Forward / cnn::CnnDetect::Forward` | `(chn, inVec, outVec)` blocking; kernel may `IPU invoke timeout, try again` | 0 | CONFIRMED |
| `MI_IPU_GetInputTensors` / `PutInputTensors` | libmi_ipu.so | **NOT imported by adas** (present in lib, unused) | — | — | CONFIRMED absence (19 MI imports listed §3.3) |
| `MI_IPU_GetOfflineModeStaticInfo` | libmi_ipu.so | **NOT imported by adas**; used by demo `dla_classify` to size `u32VariableBufferSize` from model file | `(readFunc, mem/path, OfflineModelStaticInfo*)` | 0 | CONFIRMED absence in adas; HIGH role from official example |
| `MI_SYS_*` in adas | libmi_sys.so | adas | `Init/Exit/MMA_Alloc/MMA_Free/Mmap/Munmap/FlushInvCache/ReadUuid` (8 only) | — | CONFIRMED |
| `MI_SCL_*` in adas | libmi_scl.so | adas | `CreateDevice/DestroyDevice/StretchBuf` (3 only) | `MI_SCL_StretchBuf failed:` log | CONFIRMED |
| `MI_IPU_*` in cardv | — | **NONE** (701 UND, 238 MI_*, zero IPU) | — | — | CONFIRMED (cardv is not an IPU client) |

Full adas MI import list (19, dynsym UND):

```text
MI_IPU_CreateCHN/CreateDevice/DestroyCHN/DestroyDevice/GetInOutTensorDesc/GetOutputTensors/Invoke/PutOutputTensors
MI_SCL_CreateDevice/DestroyDevice/StretchBuf
MI_SYS_Exit/FlushInvCache/Init/MMA_Alloc/MMA_Free/Mmap/Munmap/ReadUuid
```

Notable absences in adas: `MI_SYS_MemcpyPa/ChnOutputPortGetBuf`, `MI_IPU_Get/PutInputTensors`, `GetOfflineModeStaticInfo`. Input path uses `vehicle::Cnn::InputYuv(u64,u64,int)` + `ImageResizer` + `SCL StretchBuf`, not the generic input-tensor queue. See zero-copy doc.

### 3.3 Official signature reference (corroboration, not replacement)

```text
SOURCE: MI IPU API (Pcupid doc, platform/MI/ipu_en.html), rev 3.0 + §1.8 dla_classify.cpp
MI_S32 MI_IPU_CreateDevice(MI_IPU_DevAttr_t*, void*, char *fwPath, MI_U32);
MI_S32 MI_IPU_CreateCHN(MI_U32 *chn, MI_IPUChnAttr_t *attr, SerializedReadFunc, char *model);
MI_S32 MI_IPU_GetInOutTensorDesc(chn, MI_IPU_SubNet_InputOutputDesc_t*);
MI_S32 MI_IPU_GetInput/OutputTensors(chn, MI_IPU_TensorVector_t*);
MI_S32 MI_IPU_PutInput/OutputTensors(chn, MI_IPU_TensorVector_t*);
MI_S32 MI_IPU_Invoke(chn, inVec, outVec);
MI_S32 MI_IPU_GetOfflineModeStaticInfo(readFunc, mem, OfflineModelStaticInfo*);
CALL ORDER (§1.7): StaticInfo → CreateDevice → CreateCHN → GetDesc → GetInput(addr+memcpy+Flush) → GetOutput → Invoke → Put → Destroy
CONFIDENCE: HIGH (names/arity match local lib; struct layouts need chip-exact proof — see §4)
```

## 4. Structs (reconstruction status — do NOT copy as proven headers)

All layouts below are **MEDIUM or lower** unless noted. They combine: (a) Thumb-2 immediates in `IPUCreateDevice/SystemInit`, (b) `dla_classify.cpp` field names, (c) IPU API rev-history field names, (d) `sigmastar-headers` warning that MI 2.x vs 3.0 layouts differ and SDK skew exists. Validate `sizeof`/offsets against the shipped `libmi_ipu.so` ioctl size slot before use.

| Struct | Likely fields | Evidence | Confidence |
|---|---|---|---|
| `MI_IPU_DevAttr_t` | `u32MaxVariableBufSize @0` (PROVEN by disasm `str r4,[sp]` where r4=2nd arg); `+4: 0x10`, `+8: 2`, `+12: 0x10` (observed immediates); newer doc adds `u32VariableGroup/u32CoreMask/au32Reserve[8]` (absent in 2022 lib) | disasm `IPUCreateDevice` 0x94474 (`mov r4,r1; str r4,[sp]; movs r4,0x10; str r4,[sp,4]; movs r5,2; strd r5,r4,[sp,8]`); demo `memset+u32MaxVariableBufSize=`; API rev 09-2023 | OFFSET0 PROVEN; rest MEDIUM |
| `MI_IPUChnAttr_t` | `u32InputBufDepth, u32OutputBufDepth` (demo sets `2,2`); doc adds `au32Reserve[8]` | demo `IPUCreateChannel`; lib strings `input or output buffer depth is big than max depth(%d)`, `ipu_chn%d_%s_port%d_depth%d` | HIGH (names), MEDIUM (offsets) |
| `MI_IPU_TensorDesc_t` | `name[]`, `eElmFormat`, `u32TensorDim`, `u32TensorShape[]`, `s32AlignedBufSize`, `u32BufSize`, `u32InputWidth/HeightAlignment`, `eLayoutType (ex-bOutputNCHW)`, `au32Reserve[4]` | adas logs `input tensor[%d] / eElmFormat:`; demo `shape[1]=H,[2]=W,[3]=C`, `s32AlignedBufSize` length check; API rev 02-2022/06-2022 renames | MEDIUM |
| `MI_IPU_SubNet_InputOutputDesc_t` | `u32InputTensorCount, u32OutputTensorCount, astMI_Input/OutputTensorDescs[]` | adas `tensor description is ERROR!!!InputCount:%d, OutputCount:%d` (lib); demo loops both counts | MEDIUM-HIGH |
| `MI_IPU_Tensor_t/_Vector_t` | `ptTensorData[]`, `astArrayTensors[]` | demo `InputTensorVector.astArrayTensors[0].ptTensorData[0]`, `memcpy+FlushInvCache`, `MI_IPU_GetOutputTensors` | MEDIUM |
| `MI_IPU_OfflineModelStaticInfo_t` | `u32VariableBufferSize` (+ `eBatchMode/u32TotalBatchNumTypes/au32BatchNumTypes/eIpuWorkMode` in newer doc) | demo `GetOfflineModeStaticInfo→u32VariableBufferSize→IPUCreateDevice`; adas does NOT import it (uses fixed `npu_buffer_size=5620000`? see §6) | FIELD HIGH, FULL STRUCT MEDIUM |
| `MI_IPU_ELEMENT_FORMAT` | `INT8/INT16/INT32/FP32/UNKNOWN + GRAY/COMPLEX64` (doc); lib handles `INT16→float` (`The output data isn't int16 type... eElmFormat=%d, bFP32Out=%d`) | lib rodata; API §3.3 | MEDIUM (enum values UNKNOWN) |
| `MI_SYS/MI_SCL` structs | NOT recovered here; use `sigmastar-headers` ONLY as hypothesis + ioctl-size-slot check | `johnchia/sigmastar-headers` README (reconstruction warning) | UNKNOWN |

Mark every C header derived from the above `MEDIUM` until `sizeof`/ioctl-size-slot + on-device `Invoke` proof.

## 5. IPUCreateDevice / SystemInit reverse (Thumb-2, EN adas)

```text
SOURCE: build/fw_bin_en/adas (sha 0dcc6982..., 11636008 B)
VERSION: EN V23.07.29.1 (VI identical symbol set; SystemInit 124→100 B delta per SUMMARY.json)
SYMBOLS: _Z15IPUCreateDevicePcj @0x94475 sz34; _Z10SystemInitj @0x94499 sz124 (dynsym GLOBAL FUNC, .text)
TOOL: capstone Thumb-2 (local disasm scripts)
```

`IPUCreateDevice(char *fwPath, u32 varSize)` (0x94474):

```text
push {r4,r5,lr}; sub sp,0x14
r2=r0(fw); r4=r1(varSize); r0=sp(DevAttr); r1=0
[sp+0]=r4; [sp+4]=0x10; [sp+8]=2; [sp+12]=0x10
blx MI_IPU_CreateDevice (PLT 0x5ae98 → rel MI_IPU_CreateDevice)
add sp,0x14; pop {r4,r5,pc}
CONFIDENCE: HIGH (call target proven via .rel.plt; DevAttr immediates PROVEN bytes)
```

`SystemInit(u32)` (0x94498):

```text
push {r4-r6,lr}; sub sp,0x20
r6=r0(arg); r0=0; r4=sp+0x0c; r5=PC+... (config blob)
blx 0x5b7dc  (= MI_SYS_Init per rel; r0=0)
r0=3; r1=sp; [sp]=0x20; blx 0x5c028 (= MI_SCL_CreateDevice path, MEDIUM — PLT resolve pending)
ldm r5!,{r0-r3}; ldr r5,[r5]; stm r4!,{r0-r3}; strb r5,[r4]  (struct copy)
r0=sp+0x0c; r1=r6; bl IPUCreateDevice
r4=r0; cbnz r0→error path (logs + cleanup via 0x5b83c/0x5b800/0x5b97c/0x5bf98)
return r4
VI delta: 124→100 B (24 B smaller). Static-only; runtime impact UNKNOWN. Do not claim VI IPU regression from this alone.
CONFIDENCE: HIGH for MI_SYS_Init + IPUCreateDevice order; MEDIUM for SCL device id 3 / config copy semantics
```

Init order (PROVEN): `MI_SYS_Init → MI_SCL_CreateDevice → IPUCreateDevice`. Global resources: `/dev/mi_sys`, `/dev/mi_scl`, `/dev/mi_ipu` + `ipu_firmware.bin` + MMA heaps (`ipu_firmware/heap/variable/version` strings). Error paths log via `CamOsPrintf`.

## 6. Memory budget (static only)

| Item | Value | Source | Class |
|---|---|---|---|
| `npu_buffer_size` default | `5620000` (~5.36 MB) | adas tail `--npu_buffer_size=5620000` @0xb188c7 | STATICALLY KNOWN (default; runtime override via `adas_de.flag` possible) |
| 6 embedded blobs total | ~10.1 MB overlay (`d0 2.8 + v_a 1.9 + v_t 0.25 + p_r 1.6 + road 3.1 + tl 0.15 MB`) | `ADAS_PACKAGE_LOADER_V1.md` + §7 hashes | STATICALLY KNOWN |
| `model.img` | 507040 B, entropy 8.0, high-entropy (encrypted/compressed) | customer `/minieye/adas/params/model.img` sha `07ba919b...` | STATICALLY KNOWN |
| `ipu_firmware.bin` | 600208 B, entropy 7.04 | sha `61c4663d...` | STATICALLY KNOWN |
| `mma_heap sz=0x1f000000` (496 MB), `LX_MEM=0x3ffe0000`, `cma=2M` | bootargs only | `upgrade_script.txt` EN | STATICALLY KNOWN as request, RUNTIME REQUIRED for actual free |
| IPU heap stat / MMA global pools | `cat /proc/mi_modules/mi_ipu/heap_stat`, `.../mi_sys_mma/vb_pool_global` | IPU API §5 + SigmaStarDocs debug page | RUNTIME REQUIRED |
| Free RAM / headroom for custom | UNKNOWN until `meminfo/iomem/buddyinfo/dmesg` + `RSS` capture | — | RUNTIME REQUIRED (do not invent) |

## 7. Runtime timing hooks (stock)

No `latency/fps/time cost/inference time` strings around IPU in adas. Present: `Stopwatch::ElapsedMilliSeconds`, `clock_gettime` (1 import), `MI_IPU_RuntimeInfo_t {u64IpuTime us, u64BandWidthRead/Write}` (API doc), kernel `IPU_Statistic / IPU_execute_time / CPU_execute_time / DMA Statistic / Decoder Offline mode start-end duration / opName` (mi_ipu.ko), `/proc/mi_modules/mi_ipu/*`, `dla_show_img_info` + `ipu_utilization.c` demos. Stock per-model latency: UNKNOWN (no log format recovered). Future harness must use `clock_gettime(CLOCK_MONOTONIC)` around `Invoke` + `RuntimeInfo` + `ipu_log` (see deployment doc).

## 8. SDK compatibility matrix

| SDK / BSP | SoC family | Kernel | MI_IPU ver | Compiler | Relevance | Confidence |
|---|---|---|---|---|---|---|
| C2M stock (2022-06-06/08-15) | SSC8838G / Mercury6-Tiramisu (FAMILY) | 4.9.227 | `b03a7d4`, `T_0.0.1_210525`, 11 APIs (no V2/UserMem) | UNKNOWN (need SGS_IPU_SDK drop matching `b03a7d4`) | DIRECT baseline | CONFIRMED version strings |
| Pcupid IPU API doc (2021-2025) | Pcupid (+Tiramisu row) | — | 21 APIs (adds V2/Invoke2Custom/UserMem/Ext) | SGS offline `.sim_sgsimg.img` | FAMILY-LEVEL API lineage | MEDIUM (newer than C2M lib) |
| Pudding DLA tool doc (2021-09-13) | SSC9381G/Pudding (Infinity6e) | — | Convert/Calibrator/Compiler/Simulator | `.sim→_fixed.sim→_sgsimg.img` | OLDER-SDK ANALOGY (flow, not ABI) | MEDIUM |
| Infinity6e headers (`johnchia/sigmastar-headers`) | SSC33X Pudding | — | MI 0xF1 / MI 2.x | — | ANALOGY ONLY (warns struct skew) | LOW for C2M |
| OpenIPC | SSC33X/37X IPC | — | VIF/ISP/MFE, no IPU | — | NOT relevant for IPU | CONFIRMED absence |

Rule: do NOT transfer Pudding/Pcupid limits/structs to SSC8838G without `sizeof`/ioctl + on-device proof. Compiled models are tied to IPU generation + SDK/compiler + firmware ABI (API doc `E_IPU_ERR_MISMATCH_MODEL`, `fw major/minor not matching` strings). Cross-SDK model reuse: UNKNOWN, assume NO.

## 9. Required tables

### Hardware/API

```text
CAPABILITY | EVIDENCE | STATUS | CONFIDENCE
IPU present (DLA==IPU, 1 core fam) | mi_ipu.ko+lib + User Guide single-core | CONFIRMED | HIGH
MI_IPU 11-API shim | dynsym addrs/sizes | CONFIRMED | CONFIRMED
adas IPU client (8 APIs) | dynsym UND + logs | CONFIRMED | CONFIRMED
cardv IPU client | 0 IPU UND | ABSENT | CONFIRMED
48 channels / multi-model | API doc Tiramisu row + lib "no available channel" | LIKELY | MEDIUM
INT8/FP16/FP32 | lib INT16→float + DLA quant 8/16bit (tool doc) | PARTIAL | MEDIUM (chip-exact UNKNOWN)
Tensor layouts | input_config RGB/BGR/.../YUV_NV12 (tool doc) + GetPixelFormat | PARTIAL | MEDIUM
Zero-copy MMA/SCL | MI_SYS Mmap/Flush + SCL StretchBuf + demo memcpy+Flush | PLAUSIBLE | MEDIUM (proof needs HW)
Free RAM/TOPS | none primary | UNKNOWN | UNKNOWN
```

### Stock models

See `C2M_IPU_MODEL_FORMAT_V1.md` for full table. Roles: all `UNKNOWN` (size/library correlation only, filenames prove nothing).

## 10. Stop-condition status

```text
MI_IPU surface: MATERIALLY MAPPED (11 exports, 8 adas imports, cardv absence, IOCTLs, versions)
Model format: MATERIALLY CHARACTERIZED (encrypted proprietary, not ONNX/TFLite — see format doc)
Toolchain search: EXHAUSTED at public level (official docs found, SDK drop NDA-blocked)
Operator support: BOUNDED (family-level, chip-exact UNKNOWN)
Zero-copy: ASSESSED (plausible, proof needs HW)
Coexistence: ASSESSED (LIKELY via channels, RISKY without scheduler proof)
Smoke test: DEFINED (see deployment doc)
```

Remaining UNKNOWNs: chip-exact TOPS/RAM, enum values/struct packing, per-model shapes, compiler drop, coexistence scheduler proof. Next evidence: `SGS_IPU_SDK` version matching `b03a7d4` + on-device `meminfo/dmesg/proc` + single-image smoke.
