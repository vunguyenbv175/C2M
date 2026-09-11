# ADAS Static Diff V1 — EN V23.07.29.1 vs VI V23.08.04.1

## Scope

This report records reproducible static facts from the two stock `adas` executables. It intentionally separates raw binary differences from semantic conclusions.

## Stable ABI / symbol surface

`readelf -Ws` comparison:

```text
3875 symbols on EN
3875 symbols on VI
3875 common names
0 EN-only
0 VI-only
```

This strongly favors same-name function matching rather than whole-program blind diffing.

## Section layout

Both files have 30 ELF sections and identical section-header-table placement.

Relevant code/data sizes:

```text
                 EN          VI
.text          0x109de4    0x109dcc
.rodata        0x00eea0    0x00ee50
.ARM.extab     0x007540    0x007528
.ARM.exidx     0x001f70    0x001f70
.data          0x001474    0x001474
.bss           0x0030f0    0x0030f0
```

`.text` shrinks by exactly `0x18` (24) bytes.

## Only symbol-size change found

```text
_Z10SystemInitj
EN value 0x94499, size 124
VI value 0x94499, size 100
```

All same-name symbols remain present.

## SystemInit call path

Static Thumb-2 disassembly and PLT relocation mapping identify the common early calls:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

EN failure path uses:

```text
google::LogMessage::LogMessage
google::LogMessage::stream
std::__ostream_insert
google::LogMessage::~LogMessage
```

VI failure path uses a direct:

```text
fwrite
```

Thus the size change currently looks like error-reporting simplification, not removal of the IPU creation call.

## Why raw function hashes over-report changes

A first byte-hash pass reports many changed functions because a 24-byte shrink shifts later code and changes:

- internal branch immediates,
- PC-relative literal references,
- references to shifted functions/data.

Therefore `raw SHA-256 per function` is useful evidence but **not** a semantic diff.

## Appended package

Correct ELF file-backed boundary:

```text
0x172b1c
```

Overlay:

```text
EN 10,117,644 bytes, SHA-256 c395db153a76cd15f6e50ef003ccfa4295ec87dc01e409b0721ae8d4d24c6084
VI 10,135,506 bytes, SHA-256 6becae4d9eb413f36d0b8418a747de5fed24d8eec7d7f5f265a54b84201e04f7
```

The earlier `0x1755e4` value was incorrect because `.bss`/`SHT_NOBITS` was treated as file-backed data.

## Decrypted model directory

`FLAGS_m0` is now confirmed to contain six AES-128-encrypted `(offset,size)` records. They correspond to the six stock model IDs:

```text
d0
v_a
v_t
p_r
road
tl
```

All six model blobs are byte-identical between EN and VI. VI changes their offsets but updates `m0` consistently.

Therefore the remaining static package delta is concentrated in the seven interstitial regions around those models, not in CNN weights.

See:

```text
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md
docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json
docs/reverse/EVIDENCE_ADAS_GAP_GEOMETRY.json
```

## Priority reverse targets

```text
/proc/self/exe readers
BitAnswer / license / check-SN paths
package metadata validators
main / startup
CameraReader / RingbufReader
VehicleAlgo::Init
VehicleRun::CameraLoop
ScreenService / SendScreenMsg
VehicleAlgo::TsrProcess
VehicleRun::ReadTsr
SpeedLimitReporter
```

## Current confidence

- **CONFIRMED:** same public/internal symbol-name surface.
- **CONFIRMED:** `.text` shrinks 24 bytes and `SystemInit` is the only symbol with changed size.
- **CONFIRMED:** `SystemInit` still calls core system/SCL/IPU creation routines.
- **CONFIRMED:** all six embedded model blobs are identical EN vs VI.
- **HIGH-CONFIDENCE:** the `SystemInit` delta is mainly a logging-path change.
- **UNKNOWN:** exact format/meaning of the seven interstitial package regions and whether they are causal for the VI runtime failure.
