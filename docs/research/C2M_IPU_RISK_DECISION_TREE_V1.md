# C2M IPU Risk / Decision Tree V1 — Verdict, Blockers, Fallbacks

**Status:** RESEARCH ONLY. **Date:** 2026-09-11. No fake precision. Probabilities are qualitative (HIGH/MED/LOW).

## 1. Architecture verdict (choose one)

```text
B. Native SigmaStar IPU likely but toolchain blocker remains
WHY: IPU + runtime + multi-channel + HW-resize + MMA path all PROVEN present; official DLA flow + demos + versioned libs all exist; stock already runs 6 models via same APIs custom would use; cardv uses no IPU (clean client slot). BUT: no public SDK drop (NDA), no ONNX in 2021 SDK, no chip-exact op/struct/quant proof, no coexistence scheduler proof, stock blobs encrypted (no shape leak). Native is PRIMARY path, but BLOCKED on toolchain access — not on silicon.
NOT A (primary upgrade proven) — needs smoke proof. NOT C/D (CPU/Android primary) — IPU evidence too strong to demote. NOT E (insufficient evidence) — we have material API/format/toolchain bounds.
CONFIDENCE: MEDIUM (verdict), HIGH (blocker identity)
```

## 2. Biggest blocker + top 3 risks + UNKNOWNs

```text
BIGGEST BLOCKER: R1 model compiler unavailable (NDA SDK drop matching sdk_commit.b03a7d4 / T_0.0.1_210525 + SSC8838G target). Without it no custom .sim→_sgsimg.img can be produced or proven to load. All IPU HIGH→UNKNOWN until closed.
TOP 3 RISKS: R1 (toolchain access) > R3 (IPU exclusive/scheduler contention) > R2 (unsupported ops — SiLU/DFL/NMS/attention).
REMAINING UNKNOWNS: chip-exact TOPS/RAM headroom; enum values/struct packing; per-model input/output shapes; quant granularity/QAT; SCL max ports/resolutions; stock invocation order/cadence; compiler host/license/docker; cross-SDK model portability (assume NO).
```

## 3. Risk analysis (R1–R8)

```text
R1 model compiler unavailable | Prob HIGH | Impact BLOCKING | Mitigation: FAE/comake NDA request citing b03a7d4+T_0.0.1_210525; parallel CPU/Android fallback prep; never commit SDK to git | Next: SDK drop + ConvertTool -h + conv-only .sim
R2 unsupported ops | Prob MED | Impact HIGH (model fails Convert/Compiler or falls to CPU) | Mitigation: BN+ReLU+static+nearest+raw-output design; onnx_operator_audit gate; substitution plan (SiLU→ReLU, DFL→plain, LN→BN, NMS→CPU) | Next: op audit + Compiler proof per family
R3 IPU exclusive ownership | Prob MED | Impact HIGH (jitter/timeout/hang, stock regress) | Mitigation: separate channel, depth 2, ≤40% duty, stock-first, watchdog kills custom only, SAFE→COEXIST ladder | Next: single Invoke beside stock + task_channel/ipu_log/dmesg
R4 accelerator memory insufficient | Prob MED | Impact HIGH (CreateCHN/Invoke OOM) | Mitigation: tiny-ROI first, time-slice, RSS/MMA caps, heap_stat/vb_pool_global monitor | Next: meminfo/buddyinfo + heap_stat + smoke alloc
R5 model ABI mismatch | Prob MED-HIGH | Impact HIGH (MISMATCH_MODEL/version fail) | Mitigation: exact SDK/fw match; never cross-SDK; version-string check first | Next: GetOfflineModeStaticInfo + CreateCHN version test
R6 preprocessing mismatch | Prob MED | Impact MED (accuracy collapse, not crash) | Mitigation: input_config BGR/YUV_NV12 + mean/std from training; SCL vs CPU A/B; Simulator vs board compare | Next: StretchBuf stride/format dump + single-image compare
R7 runtime memory fragmentation | Prob LOW-MED | Impact MED | Mitigation: separate proc, MMA caps, lazy-load, staggered start ≤5s after stock | Next: long-run RSS/buddyinfo soak
R8 performance insufficient | Prob MED | Impact MED (Hz miss, need tracker/propagate) | Mitigation: nano+ROI+tracker+vote+gate (Bundle A), benchmark p50/p95/FPS/IPU_ms | Next: video bench + ipu_utilization
```

## 4. Decision tree (concrete)

```text
Vendor compiler (matching b03a7d4) recovered?
  NO → NATIVE_IPU_TOOLCHAIN_BLOCKED → pursue A(CPU crops/classical) + B(Android advisory) in shadow; retry FAE quarterly; STOP on-device IPU work (do not fabricate).
  YES ↓
Tiny (MobileNetV2-caffe) compiles to _sgsimg.img?
  NO → operator/toolchain blocker → fix input_config/substitutions or request newer SDK; if still NO → fall back to A/B.
  YES ↓
Tiny loads on device (CreateCHN+Invoke 0, XOR≈Simulator)?
  NO → ABI/runtime blocker (MISMATCH/version/OOM) → check fw/lib versions, varSize, depths, MMA; if unfixable → A/B.
  YES ↓
Coexists with stock ADAS (stock FPS/latency delta <10%, no hang)?
  NO → scheduler/offload path → lower Hz/duty, serialize (custom only when stock idle), or B(Android) for quality models; keep tiny shadow if safe.
  YES ↓
Benchmark small ADAS family (YOLOX-Nano-ReLU + UFLDv2-R18 ROI + Lite0 crops, time-sliced) → promote Bundle A → B per gates.
```

## 5. Fallbacks (summary)

See deployment doc §7. Order: A CPU crops/classical → B Android advisory → C external (not recommended) → D cloud overnight (non-safety). Never replace stock warnings until per-function evidence + safety review + rollback pinned.

## 6. Required final answers (17)

```text
1. Accelerator? SigmaStar IPU == DLA, 1 core (fam), DLA+RISC-V, Mercury6/Tiramisu family. CONFIRMED name, MEDIUM stepping.
2. Runtime/API? libmi_ipu.so (11 APIs) + mi_ipu.ko (IOCTLs) + mhal.ko + ipu_firmware.bin; adas uses 8 (Create/DestroyDevice/CHN, GetDesc, Get/PutOutput, Invoke). CONFIRMED.
3. Model format? Encrypted proprietary offline (common 16B prefix, 7.8–8.0 entropy, no ONNX/TFLite); SGS _sgsimg.img family. HIGH.
4. Generatable outside vendor? ONLY via SGS Convert→Calibrator→Compiler SDK drop. No public drop → currently NO. HIGH.
5. Compiler required? SGS_IPU_SDK ConvertTool.py + calibrator.py + compiler.py (+Simulator/Netron). HIGH.
6. Obtainable? NO public; NDA/FAE channel likely; need b03a7d4 match. HIGH (blocked).
7. Frameworks? 2021 SDK: Caffe/TF-graphdef/savemodel/Keras/TFLite(non-quant). ONNX ABSENT in that version. HIGH for list, UNKNOWN for newer ONNX.
8. INT8? LIKELY (8/16bit Calibrator + eElmFormat path) — MEDIUM, needs board proof. FP32 I/O yes; FP16 UNKNOWN.
9. Layouts? RGB/BGR/RGBA/BGRA/YUV_NV12/RAWDATA (+GRAY newer); NCHW+NHWC appear; stock YUV family. MEDIUM-HIGH.
10. Known-supported ops? Conv/BN/ReLU/Pool/Concat/Add/FC + CPU NMS/box-decode (SSD pattern). Rest PARTIAL/UNKNOWN — needs Compiler proof. MEDIUM bound.
11. Custom consume MI_SCL/SYS buffers? PLAUSIBLE via GetInputTensors/MMA + StretchBuf(dst=tensor) + Flush. MEDIUM (needs HW).
12. Zero-copy? PLAUSIBLE, ONE_COPY(HW StretchBuf) EXPECTED, full-frame CPU_COPY NOT VIABLE. MEDIUM, needs HW proof.
13. Coexist? LIKELY via 48 channels (cardv uses none) but SERIALIZED (no HW time-slice) — RISKY without scheduler proof. MEDIUM.
14. Smallest smoke? MobileNetV2-caffe classifier 224 (official walkthrough, LOW risk). HIGH as choice.
15. Best first real family? YOLOX-Nano-ReLU / NanoDet-Plus-m / PicoDet-S + UFLDv2-R18 + Lite0 crops (Bundle A specialists). MEDIUM (prior bench + op fit).
16. Biggest blocker? R1 NDA compiler drop (matching b03a7d4). HIGH.
17. First HW experiment? Conv-only/MobileNetV2 → _sgsimg.img → c2m-ipu-smoke single Invoke (SAFE then COEXIST), see deployment §3. HIGH.
```

## 7. Tables

### Candidates (condensed; full in operator doc)

```text
MODEL | TASK | OPERATOR RISK | QUANT | CONVERSION RISK | C2M FEASIBILITY
YOLOX-Nano-ReLU-416 | det | LOW | PTQ | LOW | HIGH
NanoDet-Plus-m / PicoDet-S | det | LOW | PTQ | LOW(-MED) | HIGH
YOLOv6-N-ReLU | det | LOW | RepOpt best | LOW | HIGH
UFLDv2-R18-ROI | lane | LOW | PTQ | LOW | HIGH
Fast-SCNN-ROI | seg | LOW | PTQ | LOW | MARGINAL
MobileNetV2-224 | smoke | LOW | trivial | LOW | SMOKE
Lite0-crops | sign/TL | LOW | PTQ | LOW | HIGH (cascade)
v8n/v10n/11n | det quality | MED-HIGH | QAT | MED-HIGH | MARGINAL
CLRNet/RT-DETR/etc | — | HIGH | — | HIGH | REJECT
```

## 8. Stop condition

```text
MI_IPU mapped ✓ | format characterized ✓ | toolchain exhausted (public) ✓ | ops bounded ✓ | zero-copy assessed ✓ | coexistence assessed ✓ | smoke defined ✓ | tree written ✓
If compiler/format unavailable → NATIVE_IPU_TOOLCHAIN_BLOCKED (declared, not worked around).
```
