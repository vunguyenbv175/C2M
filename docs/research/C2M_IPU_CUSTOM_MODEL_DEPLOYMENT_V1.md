# C2M IPU Custom Model Deployment V1 — Smoke Test, Harness, Fallbacks

**Status:** RESEARCH ONLY. No implementation. **Date:** 2026-09-11.
**Principle:** KEEP STOCK + ENHANCE. Stock ADAS is safety baseline. Custom AI starts in SHADOW MODE, separate process, kill-switch, no stock writes.

## 1. Accelerator coexistence verdict (critical)

```text
COEXISTENCE: LIKELY (not PROVEN)
EVIDENCE:
  + IPU API supports 48 channels, 1 core, multi-thread/process, multi-model by channels (Pcupid doc §1.2–1.5, family row Tiramisu 48/1) — MEDIUM (doc newer than C2M lib but channel concept matches lib "no available IPU channel", "client [%d] Create IPU channel %u")
  + cardv uses ZERO IPU APIs (CONFIRMED) — only adas owns IPU; custom would be 2nd client, not 3rd
  + adas uses 6 models via Cnn channels (CnnDetect/VehicleCnn/PedCnn/TlrCnn/LaneCnnSeg) + lane_accelerator links mi_ipu (NEEDED, no UND — DDS path?) — multi-channel already exercised by stock
  − IPU has NO HW time-slice ("maximized when operates", utilization = core busy %; gap is SW overhead; 100% impossible) — User Guide §1.4 — so concurrent Invokes SERIALIZE; scheduler/mutex/global-lock UNKNOWN statically
  − Stock invocation order/cadence/serialization UNKNOWN (needs IPU_Statistic + ipu_log + thread trace)
  − MI_IPU_DeviceLock/Unlock, SetIpuParameter, SetMallocRegion exist in kernel IOCTLs but NOT in C2M userspace lib — locking semantics UNKNOWN
RISK: custom Invoke while stock Invokes → queueing/jitter or `IPU invoke timeout` / `IPU hang` (kernel strings). Mitigation: time-slice (custom ≤40% duty, stock first), separate channel, low depth (2), low Hz, watchdog that kills custom only.
PROOF on HW: create custom channel while stock alive → GetDesc → single Invoke → measure stock FPS/latency delta + `task_channel`/`ipu_log`/`dmesg`. If fail → SAFE MODE (bench without stock) vs scheduler/offload fallback.
```

## 2. Prototype (smoke) model choice — ONE tiny model

**Choice: MobileNetV2 classifier (Caffe prototxt+caffemodel, 224×224, ReLU, GAP+FC, ~3.5M FP32 / ~1.3MB INT8) — SMOKE ONLY, not ADAS.**

```text
WHY (grounded in toolchain evidence):
  + Official DLA walkthrough converts EXACTLY caffe_mobilenet_v2 → .sim → _fixed.sim → _sgsimg.img (PROVEN flow in tool doc §2.2.1)
  + Tiny, Conv/BN/ReLU/Pool/FC only — LOWEST operator risk for 2022 IPU (see operator doc)
  + Static 1x3x224x224, easy INT8 (ilsvrc2012 calib), known output (1000 cls, top5), easy verify (XOR + top5 vs Simulator)
  + Caffe input matches adas CaffeModelConfig lineage (HIGH toolchain fit); avoids ONNX-absent problem in 2021 SDK
ALTS if Caffe SDK unavailable: SSD-MobileNetV1-concat (TF) or TFLite non-quant MobileNetV2 → same flow.
NOT YOLO/NanoDet/UFLD for smoke (larger, NMS/anchor risk — save for step 2).
CONFIDENCE: HIGH as smoke (flow-proven); UNKNOWN until C2M-matching SDK drop + board Invoke
```

## 3. First deployment experiment (smallest, two modes)

Do NOT kill stock ADAS in normal driving. Bench only, recovery proven, serial console + `collect_baseline.sh` ready.

```text
SAFE MODE (if coexistence UNKNOWN or first bring-up):
  1. Host: ConvertTool caffe mobilenet_v2 (prototxt+caffemodel+input_config.ini BGR, mean 0 std 1) → _float.sim → Calibrator (32 ILSVRC cal) → _fixed.sim → Compiler → _fixed.sim_sgsimg.img → Simulator single-image (expect top5) + SGS Netron view
  2. Bench: boot C2M WITHOUT stock adas autostart ONLY in controlled bench (prevent via run.sh guard, reversible; never on road) OR run custom harness BEFORE stock starts (measure first, then let stock start)
  3. Device harness `c2m-ipu-smoke` (host skeleton now, device build later): MI_SYS_Init(0) → GetOfflineModeStaticInfo (or fixed 5620000 fallback) → IPUCreateDevice(fw=/config/dla/ipu_firmware.bin, varSize) → CreateCHN(depths 2,2, model=/tmp/smoke.sgsimg.img) → GetInOutTensorDesc (print names/shapes/eElmFormat/alignedSize) → mmap test image (BGR 224) → memcpy+FlushInvCache → GetOutputTensors → Invoke once → print XOR + top5 + clock_gettime latency → Put → DestroyCHN/Device → MI_SYS_Exit
  4. PASS = Create+Invoke return 0, output XOR matches Simulator within fixed-vs-float tolerance, latency logged. FAIL = MISMATCH_MODEL/version → ABI blocker; channel fail → resource blocker.
COEXISTENCE MODE (after SAFE passes, stock alive):
  Same harness but stock adas left running; custom channel id != stock; custom Hz=single-shot then 1Hz; monitor stock ScreenService :26012 + raw_adas + `ipu_log`/`task_channel`/`dmesg` + stock FPS. PASS = custom Invoke 0 + stock unaffected (FPS/latency delta <10%). FAIL → scheduler/offload path (see risk doc).
ARTIFACTS: model in /tmp (never /customer/c2m/models until proven); logs to /tmp + workstation; no M4/stock-config writes.
```

## 4. Host toolchain setup + conversion pipeline

See `C2M_IPU_TOOLCHAIN_V1.md` §§5–6 for exact steps + fail-fast checklist. Summary: AVX2 Linux + pinned 2021 deps + SDK drop matching `b03a7d4` → conv-only → INT8 → offline → Simulator → board `dla_simulator -c Unknown -f BGRA` cross-check.

## 5. Runtime harness design (`c2m-ipu-smoke`, future)

```text
init (MI_SYS_Init, parse fw/model/image/labels args) → load model (mmap + GetOfflineModeStaticInfo or path) → alloc input (GetInputTensors or MMA_Alloc+Mmap) → invoke once (Flush + GetOutput + Invoke + clock_gettime) → read output (XOR + top5/decode) → print latency (us) + tensor descs → cleanup (Put+Destructor+Exit)
HOST-ONLY now: API plan + arg parsing + file checks (no MI link). DEVICE later: cross `-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -Os`, NEEDED {libc,libmi_sys,libmi_ipu,libmi_scl}, glibc≤2.30 (per TARGET_ABI.md).
Ref: dla_classify.cpp (official example, full code in IPU API doc §1.8.1) — reuse its GetImage/Flush/Invoke/XOR/TopN pattern, replace OpenCV imread with static YUV/BGR buffer for C2M.
```

## 6. Failure isolation (future implementation requirements)

```text
separate process (never thread in adas/cardv) + cgroups/cpuset+nice + VSZ/RSS caps (≤80MB des, ≤120 max) + IPU-hang watchdog (kills custom only, leaves stock) + no stock config writes (no adas_de.flag/calib/produce edits) + no stock model overwrite (no /minieye/adas/* write) + no M4 write + no stock ADAS injection (no ScreenService spoof) + JSONL shadow logs to separate partition + event clips FIFO ≤1GB + kill-switch + uninstall reversibility
```

## 7. Fallbacks (ordered, do NOT jump to new HW)

**A. ARM CPU tiny model (if IPU blocked):** TFLite / NCNN / MNN with ARMv7-A + VFPv3-D16, NO NEON assumption, `-Os`. Candidates: 64×64 crop classifier (EfficientNet-Lite0) @2Hz gated, classical day/night/fog stats, geometry TTC — all CPU-proven pattern. Need: cross-build + `RSS/CPU%` bench. ONNX Runtime: NOT recommended (heavy, NEON expectation). **B. Android companion offload (best fallback if on-device recall fails):** `SCL crop → JPEG q60 96–128px (6–12KB) + meta @5Hz (~0.4–1.2Mbps burst) or 640×360 q50–60 @2Hz (~0.4–0.7Mbps)` → Wi-Fi Direct/AP TCP/WS/MQTT → phone NNAPI/GPU/NPU (Snap 7/8, 5–20× IPU) → CBOR/JSON `<2KB {seq,ts,boxes,ver,infer_ms}>` → C2M shadow-match by `ts_ms`, drop >500ms, local nano fallback. Safety stays on dashcam; phone = non-safety advisory. Costs: Wi-Fi load, phone heat, 300–800mA. **C. External accelerator (USB NPU Coral/NCS2):** driver UNKNOWN on 4.9.227 — NOT recommended. **D. Remote/cloud (non-safety only):** overnight active-learning upload only (0.5–3s LTE, cost/privacy/offline gaps); never real-time warnings.

CPU feasibility note: VFPv3-D16 without NEON is weak for conv; keep CPU to decode/NMS/track/TTC/fusion/stats, NOT backbones, unless INT8 IPU fully blocked (then only crop classifiers + classical).

## 8. Best first REAL ADAS family (after smoke)

**YOLOX-Nano-416-ReLU (or NanoDet-Plus-m / PicoDet-S by toolchain) for detection + UFLDv2-R18 ROI for lane + EfficientNet-Lite0 crops for sign/TL — separate specialists, time-sliced (Bundle A).** Reason: LOWEST IPU risk + Apache/MIT + ROI/cascade fit + prior benchmark ordering. See operator doc §4 + roadmap Bundle A. Gate each behind smoke + `dla_simulator` + shadow bench.
