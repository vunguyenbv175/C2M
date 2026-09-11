# Owner Review — VI Static Last-Mile Root-Cause Narrowing

Reviewed commit: `1b7d018ea15da643d8d09896f20dec65d02297f3`

## Verdict

**PASS / STATIC_ANALYSIS_EXHAUSTED / RUNTIME_CAPTURE_READY**

This pass is accepted as the end of the useful static EN-vs-VI ADAS regression investigation before physical-device evidence.

No positive root cause is statically proven. The investigation has instead narrowed the remaining failure surface to runtime-dependent behavior and prepared a read-only paired EN/VI capture procedure capable of classifying the failure into A–H.

## Accepted findings

1. **Persistent config: SAME_SEMANTICS at the recoverable static surface.**
   - Key names, order, defaults, paths, and observed parser-facing strings are equivalent.
   - Apparent `fx/fy/cx/cy` differences are confined to high-entropy overlay bytes and are not parser-key deltas.
   - Internal branch/immediate thresholds remain UNKNOWN where the host lacked ARM disassembly tooling; therefore this verdict is not a claim of byte-identical every-branch semantics.

2. **raw_adas upstream: RUNTIME_DEPENDENT.**
   - The visible writer/consumer contract remains statically equivalent.
   - Thread-start guards, live SCL/VIF/ISP geometry, allocation success, startup order, cadence, timestamps, and frame availability cannot be decided from the firmware alone.

3. **Overlay metadata: PARTIAL / downgraded.**
   - Known model-directory and tail readers are accounted for.
   - No reader was found for the seven changed interstitial gaps; those gaps remain UNKNOWN but are downgraded as primary causal candidates.

4. **License state: INPUT_DEPENDENT.**
   - Compared BitAnswer implementation paths are statically the same.
   - A runtime difference remains possible only through device-specific UUID/license/feature/custom-info inputs or return codes.

5. **Static analysis is exhausted.**
   - No additional broad static round is approved unless new runtime evidence points to a specific function/range.

## Root-cause ranking after this review

1. **VI-only `mmap_reserved=fb` reservation causing a runtime allocator / contiguous-memory / IPU interaction** — UNKNOWN causality, highest-value runtime test.
2. **raw_adas upstream starvation or producer/startup-order/allocation failure despite unchanged visible writer contract** — UNKNOWN, runtime-dependent.
3. **Runtime calibration / feature / warning / license input gate suppression** — UNKNOWN, runtime-dependent.
4. Interstitial package metadata — downgraded; no reader found for changed gaps.
5. Display/M4-only masking — LOW until internal inference/warning liveness is demonstrated.

Kernel code rewrite, DTB delta, U-Boot decoder delta, model-weight changes, stale `m0`, script deltas, broad lane-algorithm rewrite, raw_adas endpoint rename, and BitAnswer implementation change remain excluded/downgraded per prior accepted evidence.

## Capture-kit review

`tools/fw/capture_c2m_adas_runtime.sh` is accepted as **read-only with respect to firmware, services, persistent configuration, and device state**. It creates output files only under the selected capture directory and does not restart/kill/remount/edit/decode persistent files. Persistent config is represented by metadata/hashes only.

`tools/fw/compare_c2m_runtime_capture.py` is accepted as a comparison helper; missing files remain UNKNOWN rather than being interpreted as equality.

## Required next experiment

Run the paired capture on the same physical C2M unit:

1. Boot known-good EN and allow the device to reach normal operating state / ADAS activation window.
2. Run `sh tools/fw/capture_c2m_adas_runtime.sh en`.
3. Preserve the capture off-device.
4. Flash/recover to VI using the known procedure, reproduce the non-activating state, then run `sh tools/fw/capture_c2m_adas_runtime.sh vi`.
5. Compare offline with `tools/fw/compare_c2m_runtime_capture.py` and classify the VI failure as A–H.

Do **not** build or flash an EN-base+VI-ADAS hybrid or a VI-minus-fb experimental image before A–H classification. If runtime evidence isolates allocator/reservation behavior, then a single one-delta `mmap_reserved=fb` experiment may be justified.

## Final decision

**PASS. Freeze static EN-vs-VI root-cause analysis. Next useful evidence must come from the physical device.**
