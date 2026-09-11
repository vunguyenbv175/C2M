# Owner Review — C2M SigmaStar IPU Stack V1

Reviewed commit: `13e276295e1ce77ee5d730d88c8219bd3b9168f1`

## Verdict

**PASS WITH GUARDRAILS — native IPU deployment path is technically credible, but currently TOOLCHAIN-BLOCKED and hardware-unproven.**

This research materially advances the C2M AI plan. It recovers the local MI_IPU runtime/API from the actual EN firmware, identifies the stock accelerator stack and firmware, bounds the proprietary offline model path, finds a documented SigmaStar conversion chain, and defines a safe first hardware smoke test. It does not modify Candidate A/B or claim real-time custom AI performance.

## Accepted findings

1. **Accelerator/runtime identity — ACCEPT.** C2M exposes SigmaStar IPU/DLA through `libmi_ipu.so`, `mi_ipu.ko`, MHAL and `ipu_firmware.bin`. The local `libmi_ipu.so` API surface is materially mapped: Create/DestroyDevice, Create/DestroyCHN, tensor descriptors, Get/Put input/output, Invoke and offline static-info. Actual stock `adas` imports eight IPU calls while `cardv` imports none.

2. **Toolchain flow — ACCEPT, chip-exact applicability remains MEDIUM.** The documented SGS flow `framework -> ConvertTool -> .sim -> Calibrator -> _fixed.sim -> Compiler -> _sgsimg.img -> Simulator/board` is credible primary/family evidence. The 2021 SDK does not prove ONNX input support, so PyTorch/ONNX remains gated on the exact SDK drop.

3. **Compiler availability — ACCEPT as the primary blocker.** No matching public SDK/compiler drop is established. The practical next dependency is an SGS_IPU_SDK/toolchain compatible with local `sdk_commit.b03a7d4` / runtime ABI and SSC8838G/Tiramisu target. Do not assume cross-SDK model portability.

4. **Stock model format — ACCEPT with wording guardrail.** The six stock blobs are high-entropy proprietary wrapped/compiled content and are not raw ONNX/TFLite/Caffe. Their exact equality to ordinary `_sgsimg.img` is NOT proven. Custom smoke testing should use the generic MI_IPU documented offline-model path rather than attempting to clone or rewrite the stock encrypted wrapper.

5. **Quantization/operator support — ACCEPT as bounded, not chip-exact.** 8/16-bit calibration is supported by the documented SigmaStar toolchain. INT8 on this exact C2M remains hardware/toolchain proof pending. Conv/BN/ReLU/Pool/Concat/Add/FC are reasonable low-risk candidates; SiLU/DFL/LayerNorm/attention/GridSample/deform/dynamic/NMS-in-graph remain high-risk until Compiler acceptance is measured.

6. **SCL preprocessing / copy strategy — ACCEPT.** Stock evidence supports SCL `StretchBuf` preprocessing and strongly argues against full-frame CPU resize/copy on ARMv7. Preferred ladder is: hardware SCL into IPU tensor buffer if legal -> hardware one-copy -> bounded fallback. Exact zero-copy aliasing/lifetime/coherency remains unproven.

7. **Coexistence — ACCEPT only as LIKELY/RISKY.** Family documentation describes one IPU core and up to 48 channels, and stock already uses multiple CNN channels while `cardv` is not an IPU client. This supports multi-channel capability, not scheduler fairness or safe concurrent multi-process Invoke. Do not state that 48 channels are chip-exact C2M capacity until board/API evidence confirms it. Assume serialized accelerator execution and possible stock jitter until measured.

8. **Smoke model — ACCEPT.** MobileNetV2 Caffe 224 is the correct first proof because the documented SigmaStar walkthrough already exercises that family and its graph is intentionally simple. It is a toolchain/ABI proof, not an ADAS product model.

## Guardrails

- Do not use `0.8 TOPS`, 48 channels, INT8 throughput, available RAM, or stock/custom scheduler behavior as proven C2M specifications.
- Do not overwrite or repack the six stock ADAS model blobs for the first custom-AI experiment.
- Do not attempt YOLO/UFLD conversion before a trivial MobileNet/conv-only model compiles, simulates and invokes successfully.
- SAFE bring-up must be bench-only. Normal driving must never require stopping stock ADAS.
- In coexistence testing, start with a single custom Invoke, then 1 Hz; observe stock ADAS latency/FPS/logs before increasing duty. Any timeout/jitter means stop and return to stock-only.
- `stock delta <10%` is an engineering target, not an established safe threshold. Record the actual baseline distribution first and define the acceptance gate from measured variability.
- Zero-copy remains a hypothesis until buffer ownership, aligned sizes, cache coherency, and Get/Invoke/Put lifetime are proven on hardware.

## Owner decision

Current architecture verdict: **B — Native SigmaStar IPU is likely viable, but the matching vendor toolchain is the blocking dependency.**

The next high-value work is NOT another broad model survey and NOT firmware integration. It is to obtain/identify the matching SigmaStar IPU SDK/compiler, then run the minimal conversion + simulator proof. If the toolchain cannot be obtained, native custom-IPU development is blocked and the project should fall back in order to CPU-only tiny functions and Android companion offload while keeping stock ADAS as the safety baseline.

## First hardware gate

After Candidate A/B physical proof and runtime baseline capture:

1. Establish matching compiler/toolchain and compile documented MobileNetV2/conv-only smoke model.
2. Verify PC Simulator output.
3. Bench-only single Invoke with stock ADAS not competing.
4. If successful, repeat one Invoke with stock ADAS alive on a separate channel while collecting IPU/stock runtime evidence.
5. Only after this gate passes should a real ADAS candidate be converted.

Recommended first real model family after smoke: `YOLOX-Nano-416-ReLU` / `NanoDet-Plus-m` / `PicoDet-S`, selected by actual Compiler operator acceptance, followed separately by UFLDv2-R18 ROI and gated sign classifiers.

## Final status

`IPU_RUNTIME_API: PASS`
`MODEL_FORMAT: PARTIAL / SUFFICIENT FOR CUSTOM-PATH PLANNING`
`TOOLCHAIN_FLOW: PASS FAMILY-LEVEL / MATCHING DROP BLOCKED`
`INT8: LIKELY, BOARD-PROOF REQUIRED`
`ZERO_COPY: PLAUSIBLE, UNPROVEN`
`STOCK_CUSTOM_COEXISTENCE: LIKELY / RISKY / BOARD-PROOF REQUIRED`
`NATIVE_CUSTOM_AI: PLAUSIBLE`
`PRODUCT_REALTIME_AI: NOT YET PROVEN`
