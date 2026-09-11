# U-Boot ih_comp=9 Reverse Engineering V1

Verdicts (canonical):
- COMP=9 identity: CONFIRMED (vendor label `mz`; algorithm raw DEFLATE)
- Decompression: PASS (see KERNEL_DECOMPRESS_EN_VI_V1.md)
- Kernel diff: NEAR-IDENTICAL
- mmap_reserved: MECHANISM_SUPPORTED
- ADAS impact: NO_NEW_CAUSAL_EVIDENCE

Scope: ANALYSIS-ONLY. No firmware modified, no U-Boot patched, no flash,
no Candidate C built. Every claim below cites exact offsets/strings/tool
output. Unproven items are labeled UNKNOWN.

## 1. Inputs (re-verified)

| Artifact | Path | Size (B) | SHA-256 |
|---|---|---|---|
| EN firmware TAR | `firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar` | 58368000 | `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` |
| VI firmware TAR | `firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar` | 58122240 | `f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa` |
| EN U-Boot uImage | `build/carve_en/uboot.es.load0.off_00018000.size_48a44.bin` | 297540 | `7c64be8cb848af856a9f107139ee90765be4c3c3bdcd4eb49563839b57304490` |
| VI U-Boot uImage | `build/vi_carve/uboot.es.load0.off_00018000.size_48a44.bin` | 297540 | `0e1e13409beaf77e680f5c9c5221ab21d796164dc926715e649ac52457102fd9` |

U-Boot uImage headers (struct `>IIIIIIIBBBB32s`, verified with Python
`struct` + `binascii.crc32`; both header CRCs valid):

- Magic `0x27051956`, `ih_os=17`, `ih_arch=2` (ARM), `ih_type=2`,
  `ih_comp=3`, `load=0x23F00000`, `entry=0x23E00000`,
  name `MVX4##M6##ga6898f3CM_UBT1501#XVM` (identical both releases).
- Payload length 297476 (`0x48A04`), data CRCs valid
  (EN `0x6108048D`, VI `0xF97FC22E`).
- Payload magic `FD 37 7A 58 5A 00` = XZ (`fd377a585a00`).
  `lzma.decompress()` succeeds:
  - EN decompressed 882768 B, SHA `0149b185064261ecde5bf3a61528936a712bcca9b9c85c5e50059a1cf773aa2f`
  - VI decompressed 882768 B, SHA `db98e11801f73ecd11713af6da3b2c10b58f00d00ef6027115ff9ed4638a25c6`
  - First 64 B both: `b00000ea14f09fe5…efbeadde` (ARM vector table).

Tool: `python tools/fw/parse_uboot_image_dispatch.py <uimage>`
reproduces the above.

## 2. Architecture / endianness

- Decompressed image base `0x23E00000` (CONFIRMED by pointer scan).
  For every bootm string at file offset `S`, the little-endian word
  `0x23E00000+S` occurs exactly once in the binary (e.g. `Uncompressing`
  at `0xAC2F2` → `0x23EAC2F2` at file `0x23E0`; `GUNZIP` at `0xAC30C` →
  `0x23EAC30C` at `0x23E4`; `MZ fail` at `0xAC39D` → `0x23EAC39D` at
  `0x23F8`). No other base yields hits. Therefore ARM little-endian,
  linked at `0x23E00000` (= uImage entry).
- Version string at file `0xBBFD0-80`: `U-Boot 2015.01 (Jul 31 2023 -
  20:04:26)` (EN) vs `U-Boot 2015.01 (Aug 21 2023 - 11:08:52)` (VI).
  See §8 for full EN/VI U-Boot diff.
- Disassembly: ARM 32-bit (`capstone` `CS_ARCH_ARM`/`CS_MODE_ARM`).
  Example prologue at file `0x2220`/`VA 0x23E02220`:
  `E92D... push {r4-r8,sl,fp,lr}`, `E59F... ldr rX,[pc,#...]`,
  `EB... bl ...`. Thumb not used in U-Boot bootm path.

Tool limits (honest): no ARM `objdump`/`readelf` on Windows host;
all control-flow claims below are from Python `struct` word scans +
`capstone 5.0.7` (pip-installed for this task) + string-pointer xrefs.
No JTAG/trace; UNKNOWN items labeled as such.

## 3. String tables (exact offsets, decompressed image)

Bootm / image strings:

| File off | String |
|---|---|
| `0xAC2BB` | `   XIP %s ... ` |
| `0xAC2CA` | `   Force XIP %s ... ` |
| `0xAC2DF` | `   Loading %s ... ` |
| `0xAC2F2` | `   Uncompressing %s ... \n` |
| `0xAC30C` | `   GUNZIP: uncompress, out-of-mem or overwrite error - must RESET board to recover\n` |
| `0xAC360` | `  xz_dec_init ERROR!!` |
| `0xAC376` | `   XZ: uncompressed size=0x%x, ret=%d\n` |
| `0xAC39D` | `   MZ: uncompress failed - must RESET board to recover\n` |
| `0xAC3D5` | `   MZ: uncompressed size=0x%x\n` |
| `0xAC3F4` | `   Unimplemented compression type %d\n` |
| `0xAC41A` | `OK\n` |
| `0xB5B0E` | `uncompressed` |
| `0xB5B1B` | `bzip2` |
| `0xB5B21` | `bzip2 compressed` |
| `0xB5B32` | `gzip` |
| `0xB5B37` | `gzip compressed` |
| `0xB5B47` | `lzma` |
| `0xB5B4C` | `lzma compressed` |
| `0xB5B5C` | `lzo` |
| `0xB5B60` | `lzo compressed` |
| `0xB5B6F` | `mz` |
| `0xB5B72` | `mz compressed` |
| `0xB5B80` | `XIP` |
| `0xB194E` | `Error: Bad gzipped data` |
| `0xBC410` | `Error: inflateInit2() returned %d` |
| `0xBC433` | `Error: inflate() returned %d` |
| `0xB15E9` | `Unknown Compression` |
| `0xB1C1C` | `Bad Magic Number` |
| `0xB1C5E` | `Bad Data CRC` |
| `0xACF2F` | `Wrong Image Type for %s command` |
| `0xACF50` | `Wrong Image Format for %s command` |

SigmaStar/MStar terms (proves vendor tree, not codec):
`0xAC584 SigmaStar # `, `0xAE9A0 SigmastarUpgradeSD_SSC8838G.bin`,
`0xAEB36 [U-Boot] SIGMASTAR Key`, `0xB60FE Control Mstar AES engine`,
`0xA82F4 SSTAR`, `0xA8337 mmap_reserved=fb,miu=%d,sz=%[^,],...` (see §7).

`lz4`/`zstd`/`decompress` strings: zero hits (case-insensitive scan of
4615 printable strings ≥4). `lzo` appears only in the table above;
no live `lzo` decoder strings.

## 4. Command tables

`bootm` at `0xB40D0` (`boot application image from memory`), sub-commands
`loados/ramdisk/cmdline/prep/fake` at `0xB40F9-0xB4119`. `crc32` at
`0xB402D`, ` Flat Device Tree` at `0xB5BCA`. No `uImage` literal (zero
hits) — image-type names come from the tables in §5.

## 5. image_comp table (enum mapping, file offsets)

`image_comp[]` entries are `{id:u32, sname:ptr, lname:ptr}` (12 B).
Scan for `id≤12` with both pointers in the comp-string set yields
(aligned at `0xA15A0`):

| File off | id | sname | lname |
|---|---|---|---|
| `0xA15A0` | 0 | `none` | `uncompressed` |
| `0xA15AC` | 2 | `bzip2` | `bzip2 compressed` |
| `0xA15B8` | 1 | `gzip` | `gzip compressed` |
| `0xA15C4` | 3 | `lzma` | `lzma compressed` |
| `0xA15D0` | 4 | `lzo` | `lzo compressed` |
| `0xA15DC` | 9 | `mz` | `mz compressed` |
| `0xA15E8` | 10 | `XIP` | `XIP` |

No entries for 5/6/7/8. Order in file is 0,2,1,3,4,9,10 (bzip2 before
gzip); IDs are authoritative, not file order.

## 6. comp dispatch (bootm_load_os equivalent, VA 0x23E02220)

Function at file `0x2220` (`VA 0x23E02220`):

```arm
0x23E02254: cmp  r5, #0xA
0x23E02258: ldrls pc, [pc, r5, lsl #2]   ; table base PC+8 = 0x23E02260
0x23E0225C: b    0x23E023C0              ; Unimplemented compression type %d
```

Jump table at file `0x2260` (11 LE words, each an absolute VA):

| COMP | File | Target VA / foff | Handler role (string evidence) |
|---|---|---|---|
| 0 | `0x2260` | `0x23E0228C`/`0x228C` | none/memcpy (`Loading %s ...` at `0xAC2DF`) |
| 1 | `0x2264` | `0x23E022D0`/`0x22D0` | gzip (`Uncompressing` + `GUNZIP` error) |
| 2 | `0x2268` | `0x23E023C0`/`0x23C0` | UNIMPLEMENTED (`Unimplemented ... %d`) |
| 3 | `0x226C` | `0x23E02308`/`0x2308` | lzma/xz (`xz_dec_init ERROR`, `XZ: uncompressed size`) |
| 4 | `0x2270` | `0x23E023C0` | UNIMPLEMENTED (table says `lzo` but no code) |
| 5 | `0x2274` | `0x23E023C0` | UNIMPLEMENTED |
| 6 | `0x2278` | `0x23E023C0` | UNIMPLEMENTED |
| 7 | `0x227C` | `0x23E023C0` | UNIMPLEMENTED |
| 8 | `0x2280` | `0x23E023C0` | UNIMPLEMENTED |
| 9 | `0x2284` | `0x23E02384`/`0x2384` | **mz** (`Uncompressing` + `MZ: ...` pair) |
| 10 | `0x2288` | `0x23E0228C` | XIP (same target as 0) |

Literal pool `0x23D4-0x23FC` holds exactly the 8 bootm string pointers
in handler order (`0xAC2BB…0xAC3F4`), e.g. `0x23E4: 0x23EAC30C (GUNZIP)`,
`0x23EC: 0x23EAC376 (XZ)`, `0x23F4: 0x23EAC3D5 (MZ size)`,
`0x23F8: 0x23EAC39D (MZ fail)`, `0x23FC: 0x23EAC3F4 (Unimplemented)`.
LDR resolutions confirm: `0x23E022D0: ldr r0,[pc,#0x108]` →
`[0x23E023E0]=0x23EAC2F2`; `0x23E02364: ldr r0,[pc,#0x80]` →
`0x23EAC376`; `0x23E023AC (ldrge): →0x23EAC3D5`;
`0x23E023B0 (ldrlt): →0x23EAC39D`; `0x23E023C0: ldr r0,[pc,#0x34]` →
`0x23EAC3F4`.

COMP VALUE | DECODER TARGET | ALGORITHM | EVIDENCE | CONFIDENCE:

- `0 | 0x23E0228C | none/memcpy | jump-table + Loading + image_comp id 0 | CONFIRMED`
- `1 | 0x23E022D0 | gzip/deflate (gzip header + inflate) | jump-table + GUNZIP/Uncompressing + id 1 | CONFIRMED`
- `2 | 0x23E023C0 | bzip2/UNIMPLEMENTED | jump-table + id 2 but target=Unimplemented | CONFIRMED`
- `3 | 0x23E02308 | lzma/xz | jump-table + xz_dec_init/XZ strings + id 3 | CONFIRMED`
- `4 | 0x23E023C0 | lzo/UNIMPLEMENTED | jump-table + id 4 but target=Unimplemented | CONFIRMED`
- `5,6,7,8 | 0x23E023C0 | UNIMPLEMENTED | jump-table (no table entry) | CONFIRMED`
- `9 | 0x23E02384 | mz/raw-deflate | jump-table + MZ pair + id 9 + §7 inflate proof + empirical raw-deflate PASS | CONFIRMED`
- `10 | 0x23E0228C | XIP | jump-table + id 10, shared handler with 0 | CONFIRMED`

Upstream constants were NOT relied upon; the table above is from
control-flow (jump-table words) + string-table IDs.

## 7. comp=9 (mz) decoder trace

Handler at `0x2384` (VA `0x23E02384`):

```arm
0x23E02384: ldr r0,[pc,#0x54]   ; Uncompressing
0x23E02388: bl  0x23E17460      ; printf
0x23E0238C: mov r3,#0
0x23E02390: mov r1,sl
0x23E02398: mov r2,r8
0x23E0239C: ldr r3,[sp,#0x48]
0x23E023A0: mov r0,r7
0x23E023A4: bl  0x23E8D738      ; mz wrapper
0x23E023A8: subs r1,r0,#0
0x23E023AC: ldrge r0,[pc,#0x40] ; MZ size (0xAC3D5) on r0>=0
0x23E023B0: ldrlt r0,[pc,#0x40] ; MZ fail (0xAC39D) on r0<0
0x23E023B4: blt 0x23E022F8      ; error path (mvn r0,#0)
0x23E023B8: bl  0x23E17460      ; print size
0x23E023BC: b   0x23E022C0      ; memcpy-finish path
```

Prototype matches gzip handler at `0x22D0`
(`r0=r7 src, r1=sl, r2=r8, r3=[sp+0x48] out-len-ptr, [sp]=0`);
only the callee differs (`0x88B40` gzip vs `0x8D738` mz).
Return convention: `0` = success (size printed), `<0` = fail.

Wrapper at `0x8D738` (`VA 0x23E8D738`): `sub sp,#0x2B0C`, massages
`bic r3,#6 / orr r3,#4`, builds `stm sp,{r0,r3}`, `bl 0x23E8C340`,
`cmp r0,#0; ldreq r0,[sp,#0x14]; mvnne r0,#0`. Inner at `0x8C340`
is a self-contained DEFLATE decoder (not a call to the gzip
`inflateInit2` wrapper at `0x88A1C`):

- Code constants: `mov r3,#0x120` (=288, DEFLATE lit/len count) at
  `VA 0x23E8C92C` and `0x23E8CA94`; `mov r2,#0x800`, `#0x480`,
  `cmp #0x10` (16), `cmp #0xF` (15), `tst #0x100` (256) throughout
  `0x8C340-0x8D740`. These are DEFLATE Huffman parameters
  (288 lit/len, 32 dist, 19 precode, max bits 15, alphabet 256),
  not generic immediates.
- Inflate tables embedded in the image and referenced by the shared
  inflate core: order array
  `10 11 12 00 08 07 09 06 0A 05 0B 04 0C 03 0D 02 0E 01 0F`
  at file `0xB37C9`; length-base table (29 halfwords
  `03 04 05…E3 01 02`) at `0xA198E`; distance-base table (30 halfwords)
  at `0xA188E`. `Error: inflateInit2/inflate` strings at
  `0xBC410/0xBC433` xref to `0x88B38/0x88B3C` (gzip path); the mz path
  uses the same tables via its embedded decoder.
- Gzip wrapper at `0x88A1C` sets `mvn r1,#0xE` (= −15, raw windowBits)
  before `bl 0x23E870A0` (`inflateInit2`); mz skips the gzip header
  parser at `0x88B40` (`cmp ip,#8` for `CM=8`, `tst lr,#0xE0` for
  `FLG`, `Bad gzipped data` at `0xB194E`) and inflates the payload
  directly as raw DEFLATE — consistent with the empirical result that
  `zlib.decompress(payload,-15)` consumes 100% of input with `eof=True`
  (see KERNEL_DECOMPRESS_EN_VI_V1.md) while `wbits=31/15` fail.

Algorithm identification is from code constants + tables + successful
raw-inflate of both kernel payloads to valid ARM Linux images, not from
the name `mz` alone.

UNKNOWN: exact stack-layout meaning of `sl/r8/sp+0x48` (inferred as
dst/src/len triple from gzip-parallelism, not proven by symbol names);
whether the mz wrapper enforces an output-size cap beyond the
`memblock` checks in the inner prologue (`0x8C340-0x8C3D8`).

## 8. EN vs VI U-Boot diff (decompression path, bootargs, fb/MIU, DTB)

Decompressed SHAs differ (`0149b…` vs `db98e…`) but byte diff is
8 bytes in 882768 (0.0009%), 6 regions, all in the version-timestamp
ASCII at file `0xBBFD0`:

- EN: `U-Boot 2015.01 (Jul 31 2023 - 20:04:26)`
- VI: `U-Boot 2015.01 (Aug 21 2023 - 11:08:52)`

No code-byte differences. Therefore decompression path, bootargs
assembly (`bootargs` getenv at `VA 0x23E0F85C`, `mmap_reserved=fb`
`strstr` at `0x23E0FA10`, `sscanf` format at `0x23E0FA20`, hex parse
via `0x8B9DC`, `Parsing bootargs size` at `0x23E0FA78`), fb/MIU setup,
and DTB handling are byte-identical. No `lz4`/`zstd` code present in
either.

## 9. Reproduction

```powershell
python tools/fw/parse_uboot_image_dispatch.py build/carve_en/uboot.es.load0.off_00018000.size_48a44.bin
python -c "import lzma,hashlib; d=open('build/carve_en/uboot.es.load0.off_00018000.size_48a44.bin','rb').read(); print(hashlib.sha256(lzma.decompress(d[64:])).hexdigest())"
# expect 0149b185064261ecde5bf3a61528936a712bcca9b9c85c5e50059a1cf773aa2f
```

## 10. UNKNOWNs

- Symbol names for `0x8C340/0x8D738/0x870A0` (stripped; addresses used).
- Whether `lzo` (id 4) ever had a decoder in another U-Boot revision
  (here it is UNIMPLEMENTED).
- Runtime output address / overwrite checks for mz (static only).
