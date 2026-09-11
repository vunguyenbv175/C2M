# C2M IPU Zero-Copy Pipeline V1 — SCL, Buffers, Preprocessing

**Status:** RESEARCH ONLY. **Date:** 2026-09-11.

## 1. Preprocessing path (traced)

```text
SOURCE: build/fw_bin_en/adas strings+dynsym; libmi_* dynsym; customer lane libs
VERSION: EN V23.07.29.1
PATH (PROVEN symbols, order HIGH):
  IMX415 MIPI front (chmap=1) + TP9950 rear (chmap=2) [05_CAMERA_MEDIA_IMU.md]
  → VIF → ISP → SCL [cardv 12×SCL / 12×VIF / 86×ISP imports; adas 3×SCL]
  → cardv CRingBuf("fortest","raw_adas",0x400,2,0,0) RequestWriteFrame(...,0,0x48,1)/CommitWrite [CARDV_RAW_ADAS_CONTRACT_V1.md, instruction-identical EN/VI]
  → adas RingbufReader::GetFrame / RingbufImageConsumer::Consume(ImageYuvAddress*) / NonblockImageBufferedConsumer::Consume+GenerateGrayMat
  → vehicle::ImageResizer::Resize (SCL StretchBuf default) vs CpuResize (cv::resize fallback)
  → vehicle::Cnn::InputYuv(u64,u64,int) / CnnDetect::SetInput(FrameMsg, ROI) → IPU Invoke → CPU decode/NMS/polyfit/TTC
FLAGS: --image_width=1920 --image_height=1440 --vehicle_run_freq=10 --camera_input=ringbuf_vehicle --ringbuf_name=raw_adas --cpu_resize=false --npu_buffer_size=5620000 --model_root_dir=params
CONFIDENCE: path CONFIRMED; pixel exact format UNKNOWN (YUV family CONFIRMED, NV12 vs NV21 UNKNOWN); mean/scale/stride UNKNOWN
```

Key symbols:

```text
Sigmastar::MMAMemory::Create/Flush/Release/FromFile/DumpYuv2jpg
Sigmastar::GetPixelFormat(MI_IPU_ELEMENT_FORMAT) / GetImageSize(MI_IPU_ELEMENT_FORMAT|MI_SYS_PixelFormat_e)
vehicle::ImageResizer::{Resize,CpuResize,GetOutput(Vir/UV/),DebugDumpImage} + mul_resize.cpp leak (/media/zac/S/code/adas/rk3566/adas/src/platform/sigmastar/mul_resize.cpp)
Bgr2YuvNv12 / cv::resize / COLOR_BGR2RGB/BGRA2BGR/GRAY conversions
input tensor[...] / eElmFormat: / output tensor[...] / tensor%d_%s.bin/.txt / create ipu channel failed! / MI_SCL_StretchBuf failed: / Set if use cpu_resize
```

## 2. SCL-assisted preprocessing (can it fan out?)

Local SCL surface:

```text
libmi_scl.so (9680 B): CreateDevice/DestroyDevice/CreateChannel/DestroyChannel/SetChnParam/GetChnParam/SetInputPortCrop/GetInputPortCrop/StartChannel/StopChannel/SetOutputPortParam/GetOutputPortParam/EnableOutputPort/DisableOutputPort/StretchBuf (15 exports, CONFIRMED)
cardv imports 12 SCL APIs (full channel lifecycle + crop + output-port param + enable) — PROVEN multi-channel capable caller
adas imports only CreateDevice/DestroyDevice/StretchBuf — uses SCL as one-shot resizer, NOT as bound channel (CONFIRMED)
mi_scl.ko 122576 B + mhal.ko present
```

Official SCL API (Pcupid `platform/MI/scl_en.html`, family-level): channel + multiple output ports + crop + `StretchBuf` (sync one-shot). Exact max ports/resolutions/ROI/fps for SSC8838G: UNKNOWN (needs `mi_scl.h` drop + `MI_SCL_GetOutputPortParam` dump on HW).

Ideal architecture assessment:

```text
camera → ISP → SCL ├─ preview / recorder / stock raw_adas / custom_ai 640x384/ROI
STATUS: TECHNICALLY PLAUSIBLE (SCL is designed for multi-output fan-out; cardv already drives 12 SCL calls suggesting multi-pipe) but UNPROVEN for C2M params.
PROOF on HW: dump immediates around MI_SCL_CreateDevice/CreateChannel/SetOutputPortParam in cardv + live frame metadata (collect_baseline.sh) + try EnableOutputPort for 4th port at 640x360 YUV420 @5Hz while stock runs.
RISK: adding a port changes ISP/SCL load + MMA; must be shadow-gated + kill-switch (see deployment doc).
CONFIDENCE: MEDIUM (plausible, not proven)
```

`StretchBuf` vs bound-channel: stock ADAS `Resize` uses `StretchBuf` (one-shot, needs `FlushInvCache`), NOT a bound `SYS_BindChnPort` pipe. Custom can reuse same pattern without rebinding stock pipe — lower coexistence risk.

## 3. Zero-copy feasibility (HIGH PRIORITY)

Candidate buffer APIs (all CONFIRMED in libmi_sys.so dynsym):

```text
MI_SYS_ChnOutputPortGetBuf/PutBuf (+Pa variants) | MI_SYS_ChnInputPortGetBuf/PutBuf (+Pa) | MI_SYS_MMA_Alloc/Free | MI_SYS_Mmap/Munmap/Va2Pa | MI_SYS_MemcpyPa/MemsetPa/BufBlitPa/BufFillPa | MI_SYS_FlushInvCache | MI_SYS_ConfigPrivateMMAPool/PrivateDevChnHeapAlloc/Free | MI_SYS_BindChnPort(2)/UnBind | MI_SYS_DupBuf/ChnPortInjectBuf
MI_IPU_GetInputTensors (returns ptTensorData pointers into private pool) + FlushInvCache (demo pattern: memcpy→Flush; zero-copy = skip memcpy, pass handle/fd)
```

Stock behavior:

```text
cardv: GetBuf → MemcpyPa → CRingBuf write → Commit (COPY, HIGH-CONFIDENCE from import set + prior study)
adas: MMA_Alloc + Mmap + InputYuv(phys?) + StretchBuf + FlushInvCache (no MemcpyPa import — suggests NO extra CPU copy in adas hot path beyond resizer)
Current stock: COPY at cardv→ringbuf boundary; adas internal: ONE-COPY or ZERO-COPY via SCL (MEDIUM)
```

Classification for custom architectures:

```text
ZERO_COPY: custom channel GetInputTensors → use MI_SYS/MMA phys handle directly as tensor addr (or SCL StretchBuf dst = tensor addr) + FlushInvCache only, no MemcpyPa. Needs: tensor s32AlignedBufSize == SCL output stride; cache coherence via FlushInvCache; lifetime (Get→Invoke→Put) held; private-pool config allows alias. PLAUSIBLE (demo supports external buffer; API supports manual alloc + CreateCHNWithUserMem in newer doc) — PROOF NEEDS HW (maps/buddyinfo/dmesg + lifetime test).
ONE_COPY: SCL StretchBuf (HW, no ARM) into tensor buffer + Flush. This is stock pattern. EXPECTED default.
CPU_COPY: cv::resize / Bgr2YuvNv12 / memcpy on ARMv7 (no NEON) full 2.7MP per frame — FORBIDDEN (perf + CPU starvation). Only for 64×64 crops (K≤3) if SCL unavailable.
VERDICT: ZERO_COPY PLAUSIBLE, ONE_COPY (HW StretchBuf) EXPECTED, CPU_COPY for full frames NOT VIABLE. All need HW proof (UNKNOWN until then).
```

Coherence/lifetime rules (from demo + lib strings):

```text
After CPU write to input: MI_SYS_FlushInvCache(ptr, size) before Invoke (PROVEN demo).
After Invoke: read output via GetOutputTensors pointers (may need Invalidate — FlushInvCache covers both per name).
Buffers: Get→use→Put strictly; depth 2 in demo; `input or output buffer depth > max` + `no available buffers` + `the address is illegal` guard.
Alignment: `pitch alignment error`, `c_align<4 neon`, `variable buffer size invalid`, `MMA buffer too small, enlarge it` — respect s32AlignedBufSize/u32BufSize/alignments from GetInOutTensorDesc.
```

## 4. Memory budget (static + runtime-required)

See stack doc §6. For pipeline: YUV420 1920×1440 ≈4.15MB/frame (ESTIMATED format); 2–4-frame ring ≈8–16MB fits 496MB MMA request (geometry CONFIRMED, format ESTIMATED). Custom 640×360 YUV420 ≈0.34MB/frame; tensor 1×3×416×256 INT8 ≈0.27MB + workspace — fits IF headroom exists. Headroom: RUNTIME REQUIRED (`meminfo/buddyinfo/dmesg`, `vb_pool_global`, `heap_stat`, RSS caps). Do not invent free RAM.

## 5. Proof checklist (HW)

```text
[ ] Dump MI_SCL channel/port/crop/stride/fps immediates + live metadata (collect_baseline.sh)
[ ] Try 4th SCL port 640x360 while stock runs (shadow, kill-switch)
[ ] Implement Get→StretchBuf(dst=tensor)→Flush→Invoke→Put ladder: zero-copy → one-copy → fallback-copy; measure maps/buddyinfo/dmesg + MI_* codes
[ ] Never cv::resize full frames on ARMv7; pointer+stride crops only
```
