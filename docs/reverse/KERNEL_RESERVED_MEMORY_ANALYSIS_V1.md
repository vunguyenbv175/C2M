# Kernel Reserved-Memory Analysis V1 (mmap_reserved=fb)

Verdicts (canonical):
- COMP=9 identity: CONFIRMED
- Decompression: PASS
- Kernel diff: NEAR-IDENTICAL
- mmap_reserved: MECHANISM_SUPPORTED
- ADAS impact: NO_NEW_CAUSAL_EVIDENCE

Scope: ANALYSIS-ONLY. Traces the exact queried reservation
`mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000`
from U-Boot env through U-Boot parser to kernel consumer. No runtime
proof of starvation is claimed.

## 1. The delta (env-level, VI-only)

`build/carve_en/upgrade_script.txt` vs `build/vi_carve/upgrade_script.txt`
`# set_config` (byte-exact, `Get-Content` verified):

- EN: `setenv bootargs ubi.mtd=ubi0,2048 rootfstype=ramfs initrd=0x21000000,0xc00000 LX_MEM=0x3ffe0000 mma_heap=mma_heap_name0,miu=0,sz=0x1f000000 mma_memblock_remove=1 cma=2M@0x23800000 loglevel=3 $(mtdparts)`
- VI: inserts before `loglevel`: `mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000`

Parsed: label `fb`, `miu=0`, `sz=0x800000` (8 MiB), window
`0x3F000000–0x3F800000` (8 MiB window, exactly `sz`; i.e. pinned, not
floating). No such string in either decompressed kernel
(`mmap_reserved=fb` count 0/0) or either static DTB (`chosen/bootargs`
identical, no `mmap_reserved`; DTB SHA `dcf1714b…` both). Therefore the
reservation is U-Boot-env-only in static artifacts; runtime kernel
receives it via `bootargs` register passing (standard `bootm` path;
`bootargs` getenv at U-Boot `VA 0x23E0F85C`, `Starting kernel ...`
at `0xAC23E`).

## 2. U-Boot synthesizer/parser (decompressed U-Boot, base 0x23E00000)

Display-init function around file `0xF800-0xFB00`
(`capstone ARM`, string-pointer xrefs CONFIRMED):

- `0x23E0F85C: ldr r0,[pc,#0x384]` → `0x23EAC23E (bootargs)`;
  `bl 0x23E16E34` (getenv). `cmp r0,#0; bne 0x23E0FA10` — null bootargs
  skips fb logic (`#### get bootargs null` at `0xAC4DB`).
- `0x23E0FA10: ldr r1,[pc,#0x1E4]` → `[0x23E0FBFC]=0x23EA8326
  (mmap_reserved=fb)`; `bl 0x23E8AF80` (strstr). `cmp r0,#0;
  beq 0x23E0F878` — absent substring skips parsing (EN path).
- `0x23E0FA20: ldr r1,[pc,#0x1D8]` → `[0x23E0FC00]=0x23EA8337
  (mmap_reserved=fb,miu=%d,sz=%[^,],max_start_off=%[^,],max_end_off=%[^ ])`
  ; `bl 0x23E8C250` (sscanf). Buffers at `sp+0x18/0x50/0xD0`.
- Hex conversion via `bl 0x23E8B9DC` (`simple_strtoul`, `r2=#0x10`)
  at `0x23E0FA48/0x23E0FA5C` (`r1=r8` base pointer, `r0=sp+0x50/0xD0`).
- `0x23E0FA78: ldr r0,[pc,#0x184]` → `0x23EA837E
  (Parsing bootargs size 0x%x addr 0x%x)`; printed only when debug flag
  `tst r3,#2` passes.

Format specifiers prove the parser expects exactly
`miu=%d` (decimal), `sz=%[^,]` (hex string), `max_start_off=%[^,]`,
`max_end_off=%[^ ]`, matching the VI env string byte-for-byte.
U-Boot EN/VI binaries are identical here (only timestamp differs),
so the mechanism is present in both; only the env input differs.

UNKNOWN: which INI/panel branch sets `m_eDeviceType`/`m_wDispWidth`
upstream of this parser (many `INI_GET_*` strings surround it);
whether U-Boot also patches DTB `reserved-memory` (no `fdt` xrefs found).

## 3. Kernel consumer (decompressed raws, identical offsets)

Strings (identical EN/VI, file offsets EN=VI):

- `0x30E0E6 sz=`, `0x30E0EB miu=`, `0x30E0F9/0x30E107 max_start_off`,
  `0x30E119/0x30E125 max_end_off`, format `miu=%d,sz=%lx` etc.
- `0x30E15E`: `error: mma_heap args invalid`,
  `error: mmap_reserved args invalid`, `no any mmap reserved`,
  `mmap reserved size is 0, skip`,
  `mmap reserved[%d] overbound, skip`,
  `error!!! %s:%d not support miu %d in this chip!!!!`,
  `%s memblock_reserve fail/success mmap_reserved_config[%d].reserved_start=`.
- Symbols (kallsyms/rodata): `mstar_driver_boot_mmap_reserved_buffer_num`,
  `mmap_reserved_config`, `mstar_driver_boot_mma_buffer_num`,
  `mma_config` at `0x3354B5/0x3354CE`.

Mechanism (from strings + identical code; function names stripped so
addresses not symbolized, but logic order is fixed by string adjacency):
parse `mmap_reserved` → validate `miu/sz/start/end` → `size==0: skip` →
`overbound: skip` → `memblock_reserve(start,size)` →
record `mmap_reserved_config[i].reserved_start`. `mma_heap` parsing is
adjacent and shares `sz=/miu=/max_start_off` vocabulary but is a
separate heap (`LX_MEM=0xfee0000` in DTB vs `0x3ffe0000` in U-Boot env;
`mma_heap … sz=0x5000000` in DTB vs `sz=0x1f000000` in env — env
overrides DTB at boot; DTB values are defaults, not runtime).

The queried `fb` reservation (8 MiB, MIU0, pinned window) passes the
`size==0` and `overbound` checks by construction (window == size).
`memblock_reserve` success/failure printks would appear in `dmesg`
(`mmap_reserved_config[%d].reserved_start=`), but no runtime logs were
collected in this static pass — consumption UNKNOWN.

## 4. Overlap / starvation assessment (static only)

- Static DTB has no `mmap_reserved` and no `reserved-memory` node
  delta; kernel code has no fb-specific carve-out beyond the generic
  parser. Therefore no static overlap with CMA (`cma=2M@0x23800000`
  in env; `cma=2M` in DTB), `mma_heap`, or IPU buffers can be proven.
- 8 MiB is small vs `mma_heap 0x1F000000` (496 MiB) / `LX_MEM`, but
  physical-contiguity / ordering effects (whether `fb` at
  `0x3F000000` fragments the `raw_adas` 1920×1440 ring or IPU CMA
  window) cannot be determined without `/proc/iomem`, `/proc/meminfo`,
  `dmesg|grep -Ei 'mmap|reserved|cma|mma|ipu|alloc|fail'`.
- Hence MECHANISM_SUPPORTED (parser + consumer + VI-only input all
  traced), not CAUSALITY_CONFIRMED, not DIFFERENCE_ONLY (difference +
  mechanism both shown), not UNKNOWN (mechanism is known).

## 5. ADAS linkage

Kernel media code is NEAR-IDENTICAL (§SEMANTIC_DIFF) and DTB IDENTICAL,
so the kernel does not contribute a new ADAS causal delta beyond
receiving the VI-only `fb` bootarg. Whether that 8 MiB pin causes VI
ADAS/CameraReader starvation is unproven statically. See
KERNEL_MEDIA_SEMANTIC_DIFF_V1.md for the narrowed hypothesis list
(runtime `cat /proc/cmdline/meminfo/iomem`, `dmesg`, `MI_SYS_Init` /
`IPUCreateDevice` return codes required).

## 6. Reproduction

```powershell
Get-Content build/carve_en/upgrade_script.txt | Select-String bootargs
Get-Content build/vi_carve/upgrade_script.txt | Select-String bootargs
python tools/fw/parse_uboot_image_dispatch.py build/carve_en/uboot.es.load0.off_00018000.size_48a44.bin
# strings: mmap_reserved=fb at 0xA8326/0xA8337, Parsing bootargs at 0xA837E
```
