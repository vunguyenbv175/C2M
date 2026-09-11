# ADAS Package Loader / Encrypted Model Directory V1

**Target:** stock C2M `adas` executable, EN V23.07.29.1 vs VI V23.08.04.1  
**Status:** static evidence, reproducible with `tools/fw/adas_m0_directory.py`

## Executive result

The ~11.6 MB `adas` file contains:

```text
ELF executable
+ protected/interstitial package metadata
+ 6 embedded CNN/model blobs
+ more protected/interstitial metadata
+ final 3602-byte plaintext gflags package tail
```

The final `--m0=` value is an **AES-encrypted directory of six `(offset, size)` records** pointing to the six embedded model blobs.

Most importantly:

> **All six embedded model blobs are byte-for-byte identical between EN and VI.**

VI changes their absolute offsets because the high-entropy metadata/gaps between blobs changed size. `m0` was updated consistently to the new VI offsets.

This sharply reduces the probability that VI ADAS failed because it shipped different AI weights/models.

## 1. Correction: true ELF file-backed end

An earlier overlay tool counted `.bss` (`SHT_NOBITS`) as file-backed bytes and incorrectly reported `0x1755e4`. The tool is being corrected to exclude `SHT_NOBITS`.

The real end of normal ELF file structures is:

```text
0x172b1c
```

Correct appended-overlay metrics:

```text
EN overlay start 0x172b1c
EN overlay size  10,117,644
SHA256 c395db153a76cd15f6e50ef003ccfa4295ec87dc01e409b0721ae8d4d24c6084

VI overlay start 0x172b1c
VI overlay size  10,135,506
SHA256 6becae4d9eb413f36d0b8418a747de5fed24d8eec7d7f5f265a54b84201e04f7
```

## 2. The executable self-loads its final flag tail

`RunAlgorithm` calls `LoadPackageFlags(argv[0])` before loading external device-specific flag files.

`LoadPackageFlags(char*)` has the confirmed call path:

```text
fopen(argv[0])
fseek(..., SEEK_END)
ftell()
fseek(file_size - FLAGS_fs, SEEK_SET)
new[]
fread(..., FLAGS_fs)
fclose()
LoadFlagsText1(buffer)
```

`LoadFlagsText1()` then calls `myenv::put_flags_text(...)` and `google::ReadFlagsFromString(...)`.

On both EN and VI, the last plaintext region beginning at:

```text
--switch_file=/customer/minieye/config/adas_de.flag
```

is exactly **3602 bytes**.

The effective order is:

```text
packaged tail
-> FLAGS_flag_file
-> FLAGS_switch_file   (adas_de.flag)
-> FLAGS_calib_file    (calib_de.flag)
-> FLAGS_produce_file  (produce_de.flag)
```

## 3. `m0` is consumed by CNN configuration

`FLAGS_m0` is referenced in `cnn::CnnConfig::UpdateFromEnv()`.

The same function statically references:

```text
model_root_dir
params
/model.img
/model.txt
```

Stock `params/model.txt` contains exactly six IDs:

```text
d0        1.img
v_a       2.img
v_t       3.img
p_r       4.img
road      5.img
tl        6.img
```

`m0` is 384 hex characters = 192 bytes = twelve 16-byte encrypted blocks. `CnnConfig::UpdateFromEnv()` processes it in 64-character records and calls `DecryptNum()` twice per record, yielding six pairs.

## 4. `DecryptNum()` algorithm

Thumb-2 disassembly confirms:

```text
ParseString(hex32, ciphertext16)
AES::AES(AESKeyLength=0)
AES::DecryptECB(ciphertext16, 16, key16)
return numeric value derived from decrypted block
```

The return-building sequence shifts the 16 plaintext bytes through a 32-bit accumulator; the final value is the final four plaintext bytes interpreted big-endian. Observed plaintext is:

```text
000000000000000000000000XXXXXXXX
```

## 5. Recovering the CNN key

`vehicle::GetKey()` embeds four 16-character literals:

```text
A = de091ce6cb357335
B = 62a7676f542bd17b
C = 40c86656fa1692e8
D = 0db92ebec2685b78
```

Static disassembly shows the returned string is initialized from A and appends C. B and D are constructed but are not included in the returned key string.

AES-128 key:

```text
de091ce6cb35733540c86656fa1692e8
```

## 6. Decrypted six-record directory

| Model ID | EN offset | VI offset | VI-EN delta | Size |
|---|---:|---:|---:|---:|
| `d0` | `0x1747fe` | `0x174d1e` | `+0x520` | `0x2b9000` |
| `v_a` | `0x431994` | `0x433056` | `+0x16c2` | `0x1ea000` |
| `v_t` | `0x61d75c` | `0x6212a4` | `+0x3b48` | `0x40000` |
| `p_r` | `0x661b44` | `0x664ed6` | `+0x3392` | `0x189000` |
| `road` | `0x7ee408` | `0x7f1bd6` | `+0x37ce` | `0x2fe000` |
| `tl` | `0xaf14bc` | `0xaf514e` | `+0x3c92` | `0x25000` |

These offset deltas exactly match the dominant alignment plateaus independently found by exact-anchor mapping.

## 7. Six model blobs are identical EN vs VI

| Model | SHA-256 | EN vs VI |
|---|---|---|
| `d0` | `0b5533eea7af01c3075b517a36a9238c7d91c82dec5fc7c34c87307da725d4f9` | identical |
| `v_a` | `342db12adb9bbeaf83595fbb7178bd2ba6b5de06f14c8fb476c4d52cad23142a` | identical |
| `v_t` | `f63b18df7b5d0c6e22241fc743e51ef8a5e27750503e481fabc509143108d0cf` | identical |
| `p_r` | `fb5795ec70b7d2cfdf06ce61a1fb627e18b4008d811ca1c73ddf7b9ca47239a9` | identical |
| `road` | `4bc0e6f262e919beeba7f384da4a8347b39943066a05963355b46e404f704914` | identical |
| `tl` | `ce2da36309acab718205d63b566c45489a3683adfa412e815670abf00d424753` | identical |

**CONFIRMED:** model contents and sizes did not change.  
**CONFIRMED:** absolute offsets changed.  
**CONFIRMED:** VI `m0` correctly tracks those new offsets.

Therefore a simple stale-offset/directory bug is not supported by static evidence.

## 8. Where VI's +17,862 bytes came from

Because model sizes are unchanged, the delta lies entirely in high-entropy interstitial regions around the models and the final package/tail transition.

| Gap | EN bytes | VI bytes | Delta |
|---|---:|---:|---:|
| ELF end -> `d0` | 7,394 | 8,706 | +1,312 |
| `d0` -> `v_a` | 16,790 | 21,304 | +4,514 |
| `v_a` -> `v_t` | 7,624 | 16,974 | +9,350 |
| `v_t` -> `p_r` | 17,384 | 15,410 | -1,974 |
| `p_r` -> `road` | 14,532 | 15,616 | +1,084 |
| `road` -> `tl` | 20,660 | 21,880 | +1,220 |
| `tl` -> plaintext flags | 6,746 | 9,102 | +2,356 |

Sum: `+17,862` bytes.

The exact metadata/protection format remains UNKNOWN. BitAnswer code and `/proc/self/exe` references make a protection/package layer plausible, but do not yet prove these gaps are BitAnswer framing.

## 9. Regression ranking after this result

Lower probability now:

```text
Different CNN weights/models
Stale m0 offsets
Broad ADAS algorithm rewrite
SystemInit/IPU creation removal
```

Highest-value remaining suspects:

1. changed protected/interstitial metadata inside the self-contained ADAS package;
2. subtle same-size code/data changes inside VI `adas` not visible at call-graph level;
3. VI `cardv` / `raw_adas` integration;
4. VI kernel/memory/driver interaction;
5. changed validation/license behavior using package metadata.

The safest discriminating runtime experiment remains:

```text
working EN userspace/kernel/config
+
VI adas executable only (temporary/reversible launch)
```

## 10. Reproduction

```sh
python3 tools/fw/adas_m0_directory.py <EN-adas> --model-txt <EN>/params/model.txt
python3 tools/fw/adas_m0_directory.py <VI-adas> --model-txt <VI>/params/model.txt
```

Dependency: `cryptography`.

Machine-readable comparison: `docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json`.

## Confidence

- **CONFIRMED:** executable self-loads its package flag tail.
- **CONFIRMED:** stock tail is exactly 3602 bytes in both builds.
- **CONFIRMED:** `FLAGS_m0` is consumed by `cnn::CnnConfig::UpdateFromEnv()`.
- **CONFIRMED:** `DecryptNum()` uses AES ECB over one 16-byte block.
- **CONFIRMED:** recovered AES key path A+C.
- **CONFIRMED:** `m0` decrypts to six offset/size pairs.
- **CONFIRMED:** all six referenced blobs are byte-identical EN vs VI.
- **HIGH-CONFIDENCE:** the six records correspond in `model.txt` order to `d0/v_a/v_t/p_r/road/tl`.
- **UNKNOWN:** exact proprietary semantics of the interstitial high-entropy metadata.
