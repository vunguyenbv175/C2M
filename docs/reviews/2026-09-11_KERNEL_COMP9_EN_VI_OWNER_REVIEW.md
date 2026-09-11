# Owner Review — EN/VI U-Boot comp=9 + Kernel Semantic Diff

## Reviewed commit

`4747b420848111c1cf99859f1b226e3bdbcfd594`

## Decision

**PASS — ROOT CAUSE NARROWED, NOT CONFIRMED**

The analysis is accepted as the canonical static evidence for the EN/VI kernel/U-Boot comparison.

## Accepted findings

1. `ih_comp=9` is **CONFIRMED** as vendor label `mz`, implemented as raw DEFLATE compatible with zlib `wbits=-15`.
2. Offline decompression of both kernels is **PASS**, with fail-closed validation of uImage magic, header CRC, data CRC and `comp==9`.
3. Decompressed kernels are the same size (3,870,720 B) and are **NEAR-IDENTICAL** rather than materially different.
4. The appended DTB is byte-identical EN vs VI (`dcf1714b55eb1330c5e7a88aaea6b9d6eb9e82f8f4d80436c40e60d23a39b6c1`).
5. U-Boot decompressed code is effectively the same; the observed EN/VI delta is limited to build/version timestamp bytes, with the comp=9 dispatch table unchanged.
6. No material VIF/ISP/SCL/IPU/NPU/sensor/DMA kernel-code delta was demonstrated.
7. VI uniquely adds `mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000` in the runtime bootargs environment.
8. The `mmap_reserved` mechanism is **SUPPORTED**: the VI-only argument is parsed by U-Boot and consumed by the kernel generic reserved-memory parser that reaches `memblock_reserve`.
9. This does **NOT** establish causality. Runtime reservation success, allocator layout, fragmentation, raw_adas availability and IPU allocation remain unproven.

## Owner interpretation

This pass strongly downgrades a materially different kernel implementation or U-Boot decompression/boot implementation as the EN→VI ADAS regression carrier.

The current regression boundary is now narrower:

`VI-only runtime bootargs / memory layout` + `cardv/customer/runtime state` + `persistent config/license/input conditions`.

The highest-value concrete delta is the VI-only 8 MiB framebuffer reservation, but it must remain a **hypothesis under test**, not a root-cause claim.

## Updated root-cause ranking

1. **VI-only `mmap_reserved=fb` changes runtime contiguous-memory layout / allocation order** — mechanism supported, causality UNKNOWN.
2. **Runtime raw_adas starvation / malformed cadence through unchanged writer contract** — UNKNOWN.
3. **Persistent calibration/config compatibility** — UNKNOWN.
4. **ADAS package interstitial metadata / runtime feature state** — UNKNOWN/LOW.
5. **Material kernel/U-Boot code rewrite** — strongly downgraded by this pass.

## Next discriminating experiment

On the same physical unit, collect a read-only paired EN vs VI runtime capture before any new feature work:

- `/proc/cmdline`
- `/proc/meminfo`
- `/proc/iomem`
- `/proc/buddyinfo`
- `/proc/pagetypeinfo`
- `dmesg` filtered for `mmap|reserved|cma|mma|ipu|alloc|fail|vif|isp|scl`
- process/thread state for `cardv` and `adas`
- `raw_adas` existence/frame counters/geometry/cadence if observable
- return codes/logs around `MI_SYS_Init`, `MI_SCL_CreateDevice`, `IPUCreateDevice`

Do not create a VI-minus-fb experimental firmware yet. Candidate A/B remain frozen until physical A/B validation is complete. If A/B pass and EN-vs-VI runtime evidence implicates the reservation, a later one-delta VI experiment may remove only `mmap_reserved=fb` to test causality.

## Release state

- Candidate A: unchanged / frozen
- Candidate B: unchanged / frozen
- C2M status: **FLASH-READY / NOT FLASH-PROVEN**
- VI regression root cause: **NARROWED / NOT CONFIRMED**
