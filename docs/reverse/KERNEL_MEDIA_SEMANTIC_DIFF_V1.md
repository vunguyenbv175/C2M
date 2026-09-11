# Kernel Media Semantic Diff V1 (decompressed EN vs VI)

Verdicts (canonical):
- COMP=9 identity: CONFIRMED
- Decompression: PASS
- Kernel diff: NEAR-IDENTICAL
- mmap_reserved: MECHANISM_SUPPORTED
- ADAS impact: NO_NEW_CAUSAL_EVIDENCE

Scope: ANALYSIS-ONLY on decompressed raws:
EN `188677bf…` / VI `13b25c76…` (3870720 B each, see
KERNEL_DECOMPRESS_EN_VI_V1.md). No firmware modified.

## 1. Byte diff summary

- Same length 3870720; differing bytes 6392 (0.1651%).
- Run histogram (1948 runs): `1:1010, 2:514, 4:113, 3:104, 8:32, …,
  151:1, 109:1, 85:1, 80:1`. Dominantly 1–4 B isolated runs =
  pointer/immediate adjustments, not logic rewrites.
- Per-256 KiB: `0x000000:158, 0x040000:44, 0x080000:1, 0x0C0000:2,
  0x100000:3, 0x140000:0, 0x180000:4, 0x1C0000:0, 0x200000:5598,
  0x240000:221, 0x280000:0, 0x2C0000:7, 0x300000:141, 0x340000:157,
  0x380000:56`. Code region `<0x200000` contributes only ~202 B;
  `0x200000` chunk (rodata + version + literals) holds 5598/6392.
- Largest runs are rodata shifts from the 3-byte version-length delta
  (`Linux version … #5 …Jul 31` len 107 vs `#27 …Sep 20` len 104):
  e.g. file `0x21C022` len 80 (version strings), `0x21C0C8` len 53,
  `0x21E110` len 109, `0x21E2CC` len 151 (shifted literal tables +
  `printk` strings). No run shows a new function body.

Low-address examples (all literal-pool pointer bumps, Thumb alignment
verified with `capstone THUMB`; ARM decode at these offsets is
nonsense `svc/strhtgt`, proving they are data not code):

- `0x2C18`: `B64022C0 (0xC02240B6)` vs `B04022C0 (0xC02240B0)` (Δ6)
- `0x3450`: same pattern (Δ6)
- `0x67AC-0x67B5`: `844222C0/7C4222C0` (Δ8) — cumulative shift, not new logic.

## 2. Strings diff (52036 EN vs 52038 VI, ≥4 chars)

EN-only (5): `HpGpB"`, `%s version %s (zac@minieye)…`,
`Linux version 4.9.227 (zac@minieye)…#5…Jul 31…`,
`MVX4##M6##ge46e0aa7KL_LX409##[BR…`, `#5 SMP PREEMPT…Jul 31…`.

VI-only (7): `HpGhB"`, `%s version %s (zac@Zoe)…`,
`Linux version 4.9.227 (zac@Zoe)…#27…Sep 20…`,
`MVX4##M6##g7fcd0350KL_LX409##[BR…`, `;KZ9`, `G]mW`,
`#27 SMP PREEMPT…Sep 20…`.

All non-version-only strings (`HpGpB"/HpGhB"`, `;KZ9`, `G]mW`) are
4–5 char fragments from shifted rodata alignment, not driver names
(confirmed by context: they sit inside the shifted `0x200000` runs).

## 3. Focused media/driver constants (MMA/MIU/CMA/mmap/fb/SCL/VIF/ISP/IPU/NPU/sensor/DMA)

Counts (case-insensitive, full-image):

| Keyword | EN | VI | Verdict |
|---|---|---|---|
| MMA | 68 | 68 | IDENTICAL |
| MIU | 179 | 179 | IDENTICAL |
| CMA | 44 | 44 | IDENTICAL |
| mmap | 33 | 33 | IDENTICAL |
| reserved | 63 | 63 | IDENTICAL |
| fb | 342 | 342 | IDENTICAL |
| SCL/scl | 26 | 26 | IDENTICAL |
| VIF/vif | 39 | 39 | IDENTICAL |
| ISP/isp | 57 | 57 | IDENTICAL |
| IPU | 7 | 7 | IDENTICAL |
| NPU | 83 | 83 | IDENTICAL |
| sensor | 8 | 8 | IDENTICAL |
| DMA | 222 | 222 | IDENTICAL |
| mma_heap | 4 | 4 | IDENTICAL |
| cma | 44 | 44 | IDENTICAL |
| gop/disp/mipi/csi/venc | 27/29/37/205/6 | same | IDENTICAL |
| ion/ge | 659/1568 vs 659/1567 | apparent diff is version-string substrings (`version` contains `ion`, `ge46e…` contains `ge`) | IDENTICAL after exclusion |

No new/removed driver string, no table-size change, no `SSTAR` media
ABI drift. Xrefs: `mstar_driver_boot_mmap_reserved_buffer_num`,
`mmap_reserved_config`, `mstar_driver_boot_mma_buffer_num`,
`mma_config` at file `0x3354B5/0x3354CE` (identical offsets both
builds); `sz=/miu=/max_start_off/max_end_off` format quartet at
`0x30E0E6-0x30E125` (identical). Therefore KERNEL_CODE =
NEAR-IDENTICAL (rebuild shift only; no MATERIAL_DELTA).

## 4. BOOTARGS delta (upgrade_script vs in-kernel/DTB)

- In-kernel DTB `chosen/bootargs` (file `0x389E63` in raw, DTB off
  `0x389D20`): identical both builds:
  `console=ttyS0,115200n8r androidboot.console=ttyS0 user_debug=31 root=/dev/mtdblock0 init=/linuxrc LX_MEM=0xfee0000 mma_heap=mma_heap_name0,miu=0,sz=0x5000000,max_start_off=0x28000000 mma_memblock_remove=1 cma=2M`.
  No `mmap_reserved=fb` in DTB or kernel rodata (`mmap_reserved=fb`
  count 0 in both raws).
- U-Boot env (`upgrade_script.txt # set_config`) differs (VI-only
  insertion):
  - EN: `… cma=2M@0x23800000 loglevel=3 $(mtdparts)`
  - VI: `… cma=2M@0x23800000 mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000 loglevel=3 $(mtdparts)`
- BOOTARGS verdict: DIFFERENCE_ONLY at env level; in-kernel/DTB
  bootargs IDENTICAL. The kernel consumer parses whatever U-Boot
  passes (see RESERVED_MEMORY report); the code path is identical.

## 5. DTB verdict: IDENTICAL

Single valid FDT at raw file `0x389D20`, `totalsize=0xC5E4`,
`version=17`, SHA `dcf1714b55eb1330c5e7a88aaea6b9d6eb9e82f8f4d80436c40e60d23a39b6c1`
both builds (`tools/fw/extract_appended_dtb.py` reproduces).
`model=MERCURY6 SZDEMO BGA2`, `compatible=sstar,mercury6`.
No node/property delta; no `reserved-memory` duplication/conflict in
static DTB. Runtime U-Boot DTB patching (if any) is UNKNOWN (no trace;
U-Boot `Flat Device Tree` string at `0xB5BCA` has zero `fdt` command
xrefs in the boot path examined).

## 6. Config verdict: UNKNOWN (absent, not unrecovered)

`IKCFG_ST`/`config.gz`/`CONFIG_*` (4 hits are coincidental `CONFIG_`
substrings in generic strings, identical). No IKCONFIG present in
either raw, so no config diff can exist. Labeled UNKNOWN (absent)
rather than IDENTICAL to avoid overclaiming.

## 7. Classification rationale

NEAR-IDENTICAL (not IDENTICAL) because 6392 bytes differ; not
MATERIAL_DELTA because differences are (a) version/build-id strings,
(b) rodata shifts thereof, (c) literal-pool pointer bumps of 6–8 B
consistent with (a), with zero media-string/table deltas and identical
DTB/bootargs-in-kernel. No evidence of changed VIF/ISP/SCL/IPU/NPU/
sensor/DMA logic.

## 8. Reproduction

```powershell
python tools/fw/decompress_c2m_kernel.py build/carve_en/kernel.es.load0.off_00061000.size_22691f.bin -o out/en.raw
python tools/fw/decompress_c2m_kernel.py build/vi_carve/kernel.es.load0.off_00061000.size_226921.bin -o out/vi.raw
python tools/fw/extract_appended_dtb.py out/en.raw -o out/dtb_en
python tools/fw/extract_appended_dtb.py out/vi.raw -o out/dtb_vi
# compare: fc /b, sha256, strings
```
