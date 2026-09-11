# ADAS Static Diff V1 — EN V23.07.29.1 vs VI V23.08.04.1

## Stable ABI / symbol surface

`readelf -Ws` comparison:

```text
3875 symbols on EN
3875 symbols on VI
3875 common names
0 EN-only
0 VI-only
```

This favors same-name function matching rather than whole-program blind diffing.

## Section layout

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

## SystemInit call path

Thumb-2 disassembly and PLT relocation mapping identify the common early calls:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

EN failure path uses `google::LogMessage`, stream insertion, and its destructor. VI failure path uses direct `fwrite`. The size reduction therefore currently looks like error-reporting simplification, not removal of IPU creation.

## Why raw function hashes over-report changes

A first byte-hash pass reports many changed functions because a 24-byte shrink shifts later code and changes internal branch immediates, PC-relative literal references and references to shifted code/data. Raw SHA-256 per function is therefore a candidate generator, not a semantic diff.

The next tool should canonicalize ARM/Thumb branch and PC-relative targets before ranking true instruction changes.

## Appended payload

Strict ELF boundary: `0x1755e4`.

```text
EN 10,106,692 bytes
SHA-256 7c14be61f3f1618602dd020db4e5bf9960d7e34ffcb35547a2ac60c13ee62f2d

VI 10,124,554 bytes
SHA-256 8f0841496c7d5f42ca5fd8e67dd3aeea985ebe0af031c1dcd1e3d15e5825a423
```

Entropy is ~7.9767 bits/byte in both builds. Do not infer the overlay format yet.

## Priority reverse targets

```text
main / startup
LoadFlagsFile / FlagBlobFromFile
LicenseService
CameraReader / RingbufReader
VehicleAlgo::Init
VehicleRun::CameraLoop
Sigmastar / IPU initialization
ScreenService / SendScreenMsg
VehicleAlgo::TsrProcess
VehicleRun::ReadTsr
SpeedLimitReporter
```

## Confidence

- **CONFIRMED:** same symbol-name surface.
- **CONFIRMED:** `.text` shrinks 24 bytes and `SystemInit` is the only symbol with changed size.
- **CONFIRMED:** `SystemInit` still calls core system/SCL/IPU creation routines.
- **HIGH-CONFIDENCE:** the `SystemInit` delta is mainly logging-path simplification.
- **UNKNOWN:** which same-sized function(s) or appended data cause the VI runtime failure.
