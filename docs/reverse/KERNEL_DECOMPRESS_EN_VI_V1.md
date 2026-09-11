# Kernel Decompression EN/VI V1

Verdicts (canonical):
- COMP=9 identity: CONFIRMED (mz = raw DEFLATE)
- Decompression: PASS
- Kernel diff: NEAR-IDENTICAL
- mmap_reserved: MECHANISM_SUPPORTED
- ADAS impact: NO_NEW_CAUSAL_EVIDENCE

Scope: ANALYSIS-ONLY. No firmware modified. Fail-closed tool:
`tools/fw/decompress_c2m_kernel.py` (verifies magic/header-CRC/data-CRC/
`comp==9`, then raw-inflate only; any other codec fails closed).

## 1. uImage headers (re-verified with struct)

Both files parsed as `>IIIIIIIBBBB32s` (64 B); `binascii.crc32` recomputed.

EN `build/carve_en/kernel.es.load0.off_00061000.size_22691f.bin`
(2255135 B, SHA `c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030`):

- `magic=0x27051956`, `hcrc=0x39BB95CA` valid, `size=0x2268DF` (2255071),
  `load=0x20008000`, `entry=0x20008000`, `dcrc=0xCEDBB786` valid,
  `os=5`, `arch=2`, `type=2`, `comp=9`,
  name `MVX4##M6##ge46e0aa7KL_LX409##[BR`.
- `payload_len=2255071 == size`; `first32=ecfd777c5347d6308ecf2deab22537900bb68a0d2e14d998604a822cc9d7b265`;
  `last32=0e623f24f526e77edd8103070e1c3870e0c08103070e1c3870e0c041f5f1ff00`.

VI `build/vi_carve/kernel.es.load0.off_00061000.size_226921.bin`
(2255137 B, SHA `8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314`):

- `magic=0x27051956`, `hcrc=0x4B55F442` valid, `size=0x2268E1` (2255073),
  `load/entry=0x20008000`, `dcrc=0x0984D022` valid,
  `os/arch/type/comp` identical except payload, `comp=9`,
  name `MVX4##M6##g7fcd0350KL_LX409##[BR`.
- `payload_len=2255073 == size`; `first32` identical to EN;
  `last32=7710fb21a93739f7eb0e1c3870e0c08103070e1c3870e0c08103070eaa8fff07`.

Load/entry equality excludes relocation as a variable.

## 2. Payload profile

| Metric | EN payload (2255071 B) | VI payload (2255073 B) |
|---|---|---|
| SHA-256 | `4c9b8b1ad13cbe8520c7cb18819c1249d22e7733e967f2427e7a7ea87041b665` | `cf9f928dc53bd43dc9253634f86c0a159988907cdb7b537b4cfe16e12810b983` |
| First 256 hex | `ecfd777c5347d630…189dc08` (see §1) | identical first 5979 B, then diverges |
| Last 256 hex | `15df7d45…1f5f1ff00` | `abf8ee2b…eaa8fff07` |
| Overall entropy | 7.9959 | 7.9959 |
| First 4K entropy | 7.9545 | 7.9545 |
| Last 4K entropy | 7.8773 | 7.8806 |
| `0e1c3870` count | 40 | 37 |
| `1F8B` (gzip) count | 28/35 (coincidental, not at offset 0) | same (not a header) |
| `FD377A585A` (xz) | 0 | 0 |
| `04224D18` (lz4) | 0 | 0 |
| `28B52FFD` (zstd) | 0 | 0 |
| First diff EN vs VI | offset `0x175B` (5979); overlap diff 2227354/2255071 = 98.771%; length delta 2 B | — |

First `0x175B` bytes identical (common header/initial deflate block);
remainder diverges as expected for two compressed builds of slightly
different trees. High entropy (7.996) is consistent with compressed,
not encrypted (successful inflate proves it).

Block boundaries/trailer: raw DEFLATE has no container magic; the
repeated tail pattern `0e1c3870e0c08…` is deflate bit-padding at
end-of-stream, not a separate trailer. No appended CRC/footer beyond
the uImage `dcrc` (already verified).

## 3. Decoder trials (payload bytes 64..end, no silent fallback)

| Candidate | Call | Outcome |
|---|---|---|
| gzip (`wbits=31`) | `zlib.decompress(p,31)` | FAIL `incorrect header check` |
| zlib (`wbits=15`) | `zlib.decompress(p,15)` | FAIL `incorrect header check` |
| raw deflate (`wbits=-15`) | `zlib.decompress(p,-15)` / `decompressobj(-15)` | **SUCCESS**: 3870720 B each, `eof=True`, `unused=0`, `unconsumed=0` |
| LZMA-alone | `lzma.decompress(p,FORMAT_ALONE)` | FAIL `Input format not supported` |
| XZ | `lzma.decompress(p,FORMAT_XZ)` | FAIL `Input format not supported` |
| LZMA-alone off+4 | `lzma.decompress(p[4:],ALONE)` | FAIL same |
| bzip2 | `bz2.decompress(p)` | FAIL `Invalid data stream` |
| zstd | `zstandard.ZstdDecompressor().stream_reader(p).read()` | FAIL `Unknown frame descriptor` |
| LZO1X (helper `build/lzo_blockdec.exe`) | `batch_decompress([(p,3870720)])` | FAIL `rc=1 decompress failed r=-6` |
| lz4-frame | `lz4.frame.decompress` | UNKNOWN (module `lz4` not installed; honest tool limit, not codec evidence) |

Only raw DEFLATE succeeds and consumes 100% of input. No fallback was
used: the tool raises on any non-`-15` path.

## 4. Decompressed outputs (PASS)

| Build | Output size | SHA-256 |
|---|---|---|
| EN raw | 3870720 | `188677bf94d8ac9a0aefaa58db96687574a1c2ee1cbb69b973ffacd64e0c2b7a` |
| VI raw | 3870720 | `13b25c76ba095ff60ae33560541de9999d58aceaa04314a77102cf9066d8849e` |

Reproduction (fail-closed):

```powershell
python tools/fw/decompress_c2m_kernel.py build/carve_en/kernel.es.load0.off_00061000.size_22691f.bin -o out/kernel_en.raw
python tools/fw/decompress_c2m_kernel.py build/vi_carve/kernel.es.load0.off_00061000.size_226921.bin -o out/kernel_vi.raw
```

Both print `input/payload/output SHAs+sizes` and header fields.
Corrupt-header / `comp!=9` / truncated-stream inputs exit non-zero
with no output file (verified by code inspection; no silent write).

## 5. Output validation

- `Linux version 4.9.227` count 1 each; `4.9.227` count 5 each;
  `Kernel command line` count 1 each; `CPU:` 12 each;
  `mmap_reserved` 5 each; `console=` 3 each.
- Version contexts:
  - EN: `Linux version 4.9.227 (zac@minieye) (gcc 9.1.0) #5 SMP PREEMPT Mon Jul 31 20:08:11 CST 2023`
  - VI: `Linux version 4.9.227 (zac@Zoe) (gcc 9.1.0) #27 SMP PREEMPT Wed Sep 20 16:38:08 CST 2023`
  - Vermagic `4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8` at file `0x21EC7E`.
- `Uncompressing Linux` 0 (expected: this is a raw kernel, not a self-extracting zImage).
- `IKCFG_ST` / `config.gz` 0 → IKCONFIG not compiled in; config extraction UNKNOWN (honest: no config present, not a tool failure).
- FDT magic `D00DFEED` count 4 per image, but only one validates:
  file `0x389D20`, `totalsize=0xC5E4` (50660), `version=17`,
  SHA `dcf1714b55eb1330c5e7a88aaea6b9d6eb9e82f8f4d80436c40e60d23a39b6c1`
  (identical EN/VI; see DTB report). Other three hits fail header
  validation (garbage totalsize/version) and are coincidental byte
  sequences in compressed-then-decompressed code.
- First 16 output bytes `01908fe219ff2fe10bf04affeff30089`, last 16 all
  zero (BSS/page alignment tail). Output entropy ~7.09 (code+rodata,
  not random).
- DTB/config extraction: `tools/fw/extract_appended_dtb.py` writes the
  single valid DTB; no config found (see above).

## 6. Supersedes prior UNKNOWN

`VI_KERNEL_MEDIA_DIFF_V1.md` §"Kernel config and DTB status" stated
direct zlib failed because comp 9 is not zlib and left DTB/config
UNKNOWN. This pass resolves it: comp 9 is raw DEFLATE (`-15`), DTB is
recovered and byte-identical, config is confirmed absent (not merely
unrecovered).

## 7. UNKNOWNs

- `lz4` trial incomplete (no `lz4` package on host); irrelevant given
  raw-deflate PASS with full-input consumption, but recorded honestly.
- Whether vendor `mz` adds a pre-header in other images (here payload
  byte 0 is already deflate; no skip needed).
