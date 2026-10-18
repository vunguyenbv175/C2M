# ADAS Semantic Diff V3 — EN vs VI (instruction-level sweep)

**Date:** 2026-10-18. **Mode:** static, read-only, host-side only. No device interaction.
**Inputs (canonical):**
- EN `adas` — `0dcc6982…`, 11,636,008 B (`build/c_verify/adas`)
- VI `adas` — `997b71c2…`, 11,653,870 B (`consumer_trace/adas`)

Companion docs: `ADAS_STATIC_DIFF_V1.md`, `ADAS_SEMANTIC_DIFF_V2.md` (call-sequence level),
`ADAS_INTERSTITIAL_GAPS_V1.md`, `EN_VI_ADAS_REGRESSION_CONCLUSION_V1.md`.

## 1. Why V3 exists

V2 proved the *call sequences* match (2731/2734). It explicitly left open:
constants, literal data, branch conditions — "same callgraph" ≠ "same code".

V3 closes that gap with a canonical instruction-level sweep of **all same-name
functions**, plus a sweep of **all literal-pool constants** (and movw/movt pairs).

## 2. Method (read-only, reproducible offline)

For every common function with equal symbol size:

1. Recursive-descent walk of the *reachable* instruction stream (both builds).
2. Branch operands canonicalized to their resolved target:
   - `.text` target → `TXT:<addr>` with piecewise −24 map (EN addr ≥ SystemInit end ⇔ VI = EN−24)
   - other section → `SEC:<name>:<addr>` with ≤0x100 tolerance
   - else `ABS:<addr>` (PLT stubs resolve identically in both builds).
3. PC-relative literal-pool loads normalized to `POOL` + pool value collected (sorted by load site).
4. `adr` / `add pc` immediates normalized and compared by **content CRC** at the materialized target.
5. `movw`/`movt` pairs reconstructed to full 32-bit values and compared with the same rules.
6. Pool values: equal ⇒ same; address-like pairs in the same section ⇒ layout shift;
   small non-address values must match exactly (candidate constants).

Byte-level artifacts excluded per prior reports: `.text` shifts −24 after `SystemInit`;
function call encodings (`bl`/`blx`) change only in their displacement fields.

## 3. Headline results

```text
common same-name functions (st_size>0)     2734
only size-changed function                 SystemInit (124 → 100)
same-size pairs compared                   2733
token-identical after canonicalization     2728
residual token diffs                         5
literal-pool values compared               ~7400 (3758 identical, 3246 shifted-address)
residual pool clusters                       7 words in 6 functions
adr content differences                      0
.text size                                 −24 B ; .rodata −80 B ; .ARM.extab −24 B ;
                                           .data/.bss unchanged
```

## 4. The 5 residual functions

1. **`SystemInit(unsigned)`** — known: size 124→100, Google-logging failure path replaced by
   short `fwrite` path; still calls `MI_SYS_Init`, `MI_SCL_CreateDevice`, `IPUCreateDevice`.
2. **`cnn::PedCnnClsReg::Forward`** — 1 of 127 tokens differs: two adjacent words in the
   function's trailing literal area (`0x000B0F8E` → `0x000B0F42`, both `.text` pointers;
   neighboring word preserves 10-byte spacing). Window search: the EN bytes at the target
   exist byte-identical in VI at delta −24 (same code, moved); the stored value additionally
   differs by 0x34 within the target region — flagged, unresolved, **not in the warning path**.
3. **`cnn::VehicleCnnRecognition::Forward`** — same pattern (1 of 134 tokens).
4. **`rapidjson …ParseArray…`** — 4 decoded words are a pointer table: all deltas exactly
   −0x18 (= `.text` shift); target windows found in the other build at −24. Layout artifact.
5. **`rapidjson …ParseNumber…`** — same pattern; all deltas exactly −0x18. Layout artifact.

## 5. Residual pool/constant clusters (7 words / 6 functions)

| Function(s) | Value EN → VI | Assessment |
|---|---|---|
| `bit_answer7b85…`, `bit_answer7bb1…` (×2), `bit_answer7bb8…` | several offsets, uniform delta 0x50 | equals the `.rodata` size delta → file-offset bookkeeping, layout |
| `vehicle::AlgoLimit::CheckConfigStr`, `vehicle::AlgoLimit::Update` | word `0x4ECF36FF` → `0x4ECDA39A` (+ neighboring offsets +0x18) | UNRESOLVED micro; value magnitude ~1.7e9 (float-timestamp-like sentinel). AlgoLimit is not part of the traced FCW/HMW/LDW/speed gates |
| `std::deque<cv::Point<int>>::_M_push_back_aux` | `0xE968F798` → `0xE974F798` | UNRESOLVED micro; neighboring pool words equal; not in warning path |

No residual cluster touches: `FcwState`, `HeadwayWarning`, `VehicleInfoRecv`, `Warner`,
`Warning::Process`, suppression, `product::Distribution`, `ScreenService`, `SdkOutputService`,
`AdasAudio`, speed-gate helpers, TSR paths, or the libflow vehicle feed.

## 6. Conclusion

At executable level the two `adas` binaries are **the same program**: every function in the
warning/speed/vehicle/display chain is instruction-identical modulo layout relocation; the
only code delta is `SystemInit`'s logging path (plus file packaging: models identical, gflags
tail identical except `m0` offsets, `+17,862 B` interstitial regions).

Therefore the EN-works / VI-broken FCW/HMW symptom **cannot be explained by different adas
warning logic**. The remaining failure surface is the same one ranked elsewhere: runtime
inputs and integration — VI `cardv` producer (GPS/speed/G-sensor deltas), `sc7a20.ko` +
kernel/fb reservation, persistent config/license state and overlay metadata.

## 7. Limits

- Thumb decode is heuristic around literal pools; pool-skip markers resolve ordering.
- Indirect calls (`blx reg`) compared structurally only (same opcode position).
- Dynamic relocations / runtime-mapped constants (e.g. the AlgoLimit word) cannot be ruled
  out as benign runtime values.
- This is a static statement; it does not replace driving-time event evidence.
