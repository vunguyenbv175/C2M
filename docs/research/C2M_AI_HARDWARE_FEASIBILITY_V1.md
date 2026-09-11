# C2M AI Hardware Feasibility V1

**Status:** research only. No TOPS invented. Tags: CONFIRMED / LIKELY / UNKNOWN.
**Date:** 2026-09-11.

## 1. SoC / CPU (Q16)

| Item | Verdict | Evidence |
|---|---|---|
| ISA userspace | CONFIRMED ARMv7-A 32-bit LE, EABIv5, hard-float | `cardv`+`adas` ELF `EM_ARM=0x28`, `e_flags=0x5000400`, interp `/lib/ld-linux-armhf.so.3`; `.ARM.attributes` `CPU_arch=10/Profile A/Thumb-2/VFPv3-D16/VFP-args` (`docs/firmware/TARGET_ABI.md`, `tools/fw/arm_attributes.py`) |
| FPU / SIMD | CONFIRMED VFPv3-D16; **no NEON evidence** (`Advanced_SIMD_arch` absent both binaries) — build `-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16`, no NEON intrinsics | same |
| Core / freq | LIKELY dual Cortex-A53 @ 1.2 GHz | CN vendor-news cluster (sekorm/comake/wliuyuan/CSDN, Dec 2021): `SSC8838G/SAC8542: dual A53 1.2 GHz` — secondary, needs datasheet; consistent with A53-in-AArch32 + community `linux-chenxing` (SSC8838G=Cortex-A53 BGA, Mercury6 SDK TIRAMISU) |
| libc/kernel | CONFIRMED glibc 2.30 (stock max need 2.29), kernel modules 4.9.227, GCC 9.1.0 (+Linaro 4.9.4 libs) | rootfs cpio + `.comment` |
| RAM total | UNKNOWN (need `cat /proc/meminfo`, `iomem`, `buddyinfo`) | `LX_MEM=0x3ffe0000 (~1024M−128K)`, `mma_heap 0x1f000000 (496 MB)`, `cma=2M`, VI `fb 8 MB @0x3F000000`, DTB `LX_MEM=0xfee0000/mma 0x5000000` — bootargs only, not DRAM proof |
| NPU | LIKELY 0.8 TOPS + Caffe/ONNX/TF SDK | same CN news (`NPU:0.8Tops`, `兼容Caffe/ONNX/TensorFlow, 完整SDK`); package `15x15 BGA439`, DDR3 ≤16 Gb @2133, ISP ≤8 MP, H264/265 4K@45, MIPI/DSI — all LIKELY until datasheet/SDK |
| INT8/FP16, ops, limits, TOPS usable | UNKNOWN — do not design on assumed numbers | no `MI_IPU.h`/SCL headers in repo; `sigmastar.com.tw` unreachable; GitHub `MI_IPU/IPUCreateDevice/SSC8838G` 0 hits; OpenIPC covers VIF/ISP/MFE/JPE/display, not IPU; community `CEVA-XM6/Cambricon` note is family-generic, NOT SSC8838G fact |

Implication: locally prove everything. Assume ~0.8 TOPS INT8 ceiling for budgeting, but gate every claim on measured `ipu_ms/RSS/FPS` after SDK in hand.

## 2. Media / SCL / memory path (Q43–44, HIGH PRIORITY)

CONFIRMED: pipeline `IMX415 MIPI front (chmap=1) + TP9950 MIPI rear (chmap=2) → VIF → ISP → SCL → preview/recording + raw_adas`; `MI_SYS_Init → MI_SCL_CreateDevice → IPUCreateDevice` both builds; `MI_SCL_* x12 cardv / x4 adas`, `MI_VIF x12`, `MI_ISP x86`, `MI_SYS x31` counts EN==VI; `MI_SYS_ChnOutputPortGetBuf + MI_SYS_MemcpyPa + MI_SYS_MMA_Alloc/Mmap` present; ringbuf `RequestWriteFrame/CommitWrite` stable; ADAS flags `1920x1440@10Hz`, `npu_buffer 5,620,000 (~5.36 MB)`; frame math YUV420 ~4.15 MB/frame → 2–4-frame ring ~8–16 MB fits 496 MB MMA (format ESTIMATED, geometry CONFIRMED).

LIKELY: SCL can fan out multiple scaled pipes (rec + preview + ADAS) in HW with zero ARM cost (typical SigmaStar ISP/SCL, 12 SCL calls suggest multi-channel) — UNPROVEN params.
Current stock is COPY (`GetBuf → MemcpyPa → CRingBuf write → Commit`), not zero-copy (HIGH-CONFIDENCE). Zero-copy (pass handle/fd, single Mmap, refcount + cache flush, no MemcpyPa) needs code change + MIU-coherence proof — propose `zero-copy / one-copy / fallback-copy` ladder, prove via `maps/buddyinfo/dmesg` + lifetime tests. Never `cv::resize` full 2.7 MP on ARMv7 per frame; one HW downscale to 640x360 YUV420 + pointer+stride crops is the goal. Exact SCL channel/port/stride/fps = UNKNOWN until immediates around `MI_SCL_CreateDevice/VIF/ISP/ChnOutputPortGetBuf` + live frame metadata captured (`tools/device/collect_baseline.sh`).

## 3. Stock AI stack roles (Q17)

Blobs (sizes/offsets CONFIRMED §loader; semantics below are inference, NOT proof):

```text
d0   0x2b9000 (~2.8 MB) — LIKELY vehicle/detection main (largest; vehicleWarning/Measure + TTC/FCW logic present)
v_a  0x1ea000 (~1.9 MB) — UNKNOWN (vehicle-attribute? appearance? — do not guess from name)
v_t  0x40000  (256 KB)  — UNKNOWN (tiny; tracker/temporal/trigger? — UNKNOWN)
p_r  0x189000 (~1.6 MB) — LIKELY pedestrian (libPedDetect.so + C1PedRes/PedWarningExport present; have_bike/is_danger)
road 0x2fe000 (~3.1 MB) — LIKELY road/lane (lane_accelerator/postprocess/calib_service + LaneWarning/LDW present; largest)
tl   0x25000  (148 KB)  — LIKELY traffic-light (TlrDetect/TlrCnnCls/GreenWarning present; tiny classifier-sized)
model.img 507 KB + ipu_firmware.bin 600 KB + libmi_ive.so 754 KB + OpenCV 4.1 (incl. dnn) — identical EN/VI
```

Do the six cover vehicle/ped/road/TL separately? LIKELY yes by size + library/symbol correlation, but filenames alone prove nothing — mark per-model role UNKNOWN until `MI_IPU` call-graph + input-dims + runtime dump prove it. What matters for this study: stock already spends ~10 MB overlay + 5.36 MB NPU buffer on six small models — custom additions must fit in the REMAINDER (see budgets §40), not replace them.

## 4. Conversion feasibility (Q18)

Assumed path `PyTorch → ONNX(opset 11–13, static 1x3xHxW) → simplify → INT8 calibrate → vendor compiler → .ipumodel → single-image → video bench` (vendor names UNKNOWN; TFLite intermediate/test only). Fail-fast gates per step in ROADMAP §42.

| Op / pattern | TFLite risk | Small-IPU risk (est.) | Mitigation |
|---|---|---|---|
| Conv/BN/ReLU/ReLU6/H-Swish, Pool, Concat, Add, FC, 3x3/1x1 s2, ResizeNearest | LOW | LOW | keep to these |
| ResizeBilinear/upsample (seg) | LOW-MED | MEDIUM | force nearest, fixed 2x |
| LeakyReLU/SiLU/Mish/HardSwish | LOW | MEDIUM-HIGH (many old IPUs lack SiLU LUT) | SiLU→ReLU retrain |
| BN-fold/Clip/Pad/Slice/Split/Transpose/Reshape | LOW | LOW-MED | fold BN, fix layout |
| Anchor-decode, DFL (reshape+softmax+matmul) | MEDIUM | MEDIUM-HIGH (CPU fallback) | plain regression or NMS-free w/o DFL; decode on CPU |
| NMS/TopK/Gather | MED-HIGH | HIGH (almost never on IPU) | export raw boxes+scores, CPU NMS (≤500 boxes, ≤8 cls) |
| Focus (slice+concat), SPPF, ELAN/CSP | LOW-MED | MEDIUM (Focus slice unsupported) | stride-conv backbones (v6/v8/nano, no Focus) |
| LayerNorm/GroupNorm/InstanceNorm | MEDIUM | HIGH | BN-only backbones |
| grid_sample / DeformConv / attention / transformer / dynamic shapes / control-flow | HIGH | HIGH | never use on this SoC |

Per-family score: LOW = YOLOX-Nano/Tiny-ReLU, NanoDet-Plus, PicoDet(+NPU), YOLOv6-N-ReLU-RepOpt, Fast-SCNN, UFLDv2, MonoDepth2-UNet, EfficientNet-Lite0; MEDIUM = YOLOv5n/s, YOLOv6-SiLU+DFL, YOLOv10-N, YOLOv7-tiny, YOLOv8n/11n, PIDNet-S/DDRNet-slim, MiDaS-small; HIGH = YOLOv9t/s, RT-DETR, YOLO-World, CLRNet, CondLane, DepthAnything, Lite-Mono-attention.

## 5. Quantization / pruning / resolution (Q19–21, detail in OPTIMIZATION doc)

- FP16 ~free; INT8-PTQ ok for large boxes/binary-seg/detector-backbone (500–2k night/rain/VN rep images); sensitive: small/distant bikes, sign color, TL state, lane-regression jitter (x2–3 lateral), depth scale-drift → keep heads dequantised on CPU-FP, QAT or two-stage (INT8 detector + crop classifier) where needed; lane-regression likely needs QAT or seg-formulation.
- Practical shrinking order: low-res + nano-backbone + ReLU/nearest cleanup → PTQ → distill (teacher→student +2–5 mAP) → structured channel-prune 20–40% (`torch-pruning`, Ultralytics prune) → QAT last resort. No NAS/sparse/dynamic (no toolchain).
- Min practical (16:9, never full 1920x1440 to NN): cars/ped/bike near-field 416x256, sweet 512x288–640x360; lane 512x288–640x360 (width>512, lower-half ROI); seg 416x256–512x288; signs/TL full-frame ≥640x360 — instead ROI/cascade (det 512x288 full + 64x64 native crops); depth 416x256 or defer. 320x192 loses distant bikes/signs; 640x640 wasteful letterbox.

## 6. CPU vs IPU allocation (Q25)

```text
IPU (INT8, time-sliced ≤60% duty): all CNN backbones/necks + crop classifiers
CPU (A53-32bit/VFPv3-D16, -Os, no NEON): box-decode/sigmoid/softmax, NMS, seg-argmax, polyfit/warp,
  IoU/SORT-KF/EMA/TTC/lane-offset/hysteresis/state-machine, JPEG-crop (if not SCL), YUV→RGB/letterbox (minimal),
  JSONL/GPS/ring/event-clip (low-prio nice+ionice), IPC/watchdog/TLS, stock pipeline untouched
NEVER on accelerator: file IO, video encode (use HW venc), stock ADAS/M4 IPC, watchdog, upload
```

Isolation: separate process, cgroups/cpuset+nice, VSZ/RSS caps, IPU-hang watchdog that kills custom proc only.

## 7. Performance budget (Q40)

No hardware perf invented — budgets are targets to PROVE, with UNKNOWN-until-bench marked *.

| Item | Desired | Max acceptable | Notes |
|---|---|---|---|
| extra RAM (custom proc RSS) | ≤80 MB | ≤120 MB | stock MMA 496 MB + NPU 5.36 MB are taken; measure `RSS/VSZ/buddyinfo` * |
| extra model storage (INT8 blobs) | ≤6 MB | ≤12 MB | e.g. det 1–2 + lane 1–3 + sign 1–3 MB |
| detector latency (IPU) | ≤120 ms (5 Hz+) | ≤200 ms (3 Hz min + tracker) | 416–512 ROI * |
| lane latency | ≤100 ms (10 Hz) | ≤200 ms (5 Hz + propagate) | ROI * |
| sign/TL crop classifier each | ≤15 ms | ≤30 ms | K≤3/frame gated * |
| tracker+TTC+fusion (CPU) | ≤10 ms/frame | ≤20 ms | ARMv7, no NEON * |
| CPU util (custom) | ≤40% of one core avg | ≤70% burst | must not starve cardv/adas * |
| IPU duty (custom) | ≤40% | ≤60% | stock first * |
| thermal | no new throttle vs stock | ≤5 °C rise sustained | measure SoC-temp if driver exposes * |
| startup | ≤5 s after stock ADAS up | ≤15 s | lazy-load models, staggered * |
| shadow-log rate | ~0.5 MB/min JSONL + event clips ≤1 GB FIFO | ≤200 MB logs + ≤1 GB clips | never touch stock rec partition |

## 8. External compute (Q26–27)

Order: NO EXTRA HARDWARE first. Lab/vehicle-test: RK3588-class bench (6 TOPS) for offline eval/labeling (not shippable). USB NPU (Coral/NCS2): driver UNKNOWN — not recommended. Cloud GPU: **non-safety/experimental only** (0.5–3 s LTE, cost/privacy/offline gaps) — overnight active-learning upload only, never real-time warnings.
Android companion (NNAPI/GPU/NPU, Snapdragon 7/8, 5–20x SSC IPU): best fallback if on-device recall fails — safety logic stays on dashcam, phone = non-safety advisory. Protocol: dashcam AP/Direct, TCP/WS/MQTT, NTP-sync; uplink K≤3 JPEG q60 96–128px crops (~6–12 KB each) + meta @5 Hz (~0.4–1.2 Mbps burst) or 640x360 q50–60 @2 Hz fallback (~0.4–0.7 Mbps); never 1920x1440 raw (~40 MB/s @10 Hz); downlink CBOR/JSON <2 KB `{seq,ts,boxes,ver,infer_ms}`; budget ~100–250 ms RTT (shadow-match by `ts_ms`, drop >500 ms, local nano fallback). Costs: Wi-Fi load, phone heat, ~300–800 mA drain — measure, label `experimental, not for driving decisions`.

## 9. What to prove first (gates)

```text
1. SDK/IPU toolchain in hand (op list + converter version + .ipumodel format + limits) — else all IPU HIGH→UNKNOWN
2. conv-only ONNX smoke through vendor compiler + single-image on device (see ROADMAP §42)
3. SCL multi-output + stride/format map (immediates + live metadata)
4. /proc/meminfo/iomem/buddyinfo + dmesg(ipu/npu/mma/cma) + MI_* return codes EN vs VI (also serves regression triage)
5. same-clip offline bench (stock vs candidate: fps/p50/p95/RSS/FP/miss/stability)
```

Largest hardware UNKNOWN: IPU op/coverage + toolchain/format + input limits + usable TOPS/RAM headroom. Largest conversion UNKNOWN: vendor acceptance of SiLU/DFL/NMS/resize + exact гражданами .ipumodel without SDK.
