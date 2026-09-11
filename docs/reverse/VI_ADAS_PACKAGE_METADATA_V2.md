# VI ADAS Package and Interstitial Metadata V2

## Verdict

The EN and VI `adas` executables have nearly identical executable-code structure and byte-identical embedded model blobs. The entire 17,862-byte VI size increase is accounted for by seven non-model interstitial regions. Their exact proprietary format, consumer, and causal relationship to the VI activation regression remain **UNKNOWN** because no direct reader or cross-reference has been proven.

## Binary identity

```text
EN size: 11,636,008 bytes
EN SHA-256: 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043

VI size: 11,653,870 bytes
VI SHA-256: 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1

VI minus EN: 17,862 bytes
```

## ELF and code surface

Both executables expose 3,875 named symbols, with no EN-only or VI-only symbol name. The only symbol-size change is:

```text
_Z10SystemInitj
EN address: 0x94499
EN size: 124 bytes
VI address: 0x94499
VI size: 100 bytes
```

Both versions retain calls to:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

The observed `SystemInit` difference primarily changes failure logging. It does not statically remove system, SCL, or IPU initialization.

A Thumb-2 call-sequence comparison reports:

```text
comparable functions: 2,734
same call sequence: 2,731
changed call sequence: 3
```

The changed functions are:

```text
SystemInit(unsigned int)
lane_calib::LaneCalib::get_extrinsic(double)
vehicle::VehicleAlgo::PedProcess()
```

The two same-sized algorithm functions retain identical resolved/direct call sequences and differ only in indirect-call register tokens. They remain compiler/register-allocation noise unless a decompiler proves a different target.

## Correct package boundary

The file-backed ELF boundary is:

```text
0x172B1C
```

This boundary excludes `.bss` and other `SHT_NOBITS` content that is not stored in the file.

Overlay identities:

```text
EN overlay size: 10,117,644 bytes
EN overlay SHA-256: c395db153a76cd15f6e50ef003ccfa4295ec87dc01e409b0721ae8d4d24c6084

VI overlay size: 10,135,506 bytes
VI overlay SHA-256: 6becae4d9eb413f36d0b8418a747de5fed24d8eec7d7f5f265a54b84201e04f7
```

## Embedded model directory

`FLAGS_m0` contains an AES-128-encrypted directory of six offset/size records. The recovered model identifiers are:

```text
d0
v_a
v_t
p_r
road
tl
```

Proven facts:

- All six model sizes are equal between EN and VI.
- All six model blobs are byte-identical between EN and VI.
- VI changes model offsets.
- The VI `m0` directory consistently tracks those changed offsets.

Therefore changed CNN weights or model payloads are **EXCLUDED AS THE PRIMARY CAUSE**.

Canonical evidence:

```text
docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json
```

## Seven interstitial regions

| Region | EN bytes | VI bytes | Delta |
|---|---:|---:|---:|
| ELF end to `d0` | 7,394 | 8,706 | +1,312 |
| `d0` to `v_a` | 16,790 | 21,304 | +4,514 |
| `v_a` to `v_t` | 7,624 | 16,974 | +9,350 |
| `v_t` to `p_r` | 17,384 | 15,410 | -1,974 |
| `p_r` to `road` | 14,532 | 15,616 | +1,084 |
| `road` to `tl` | 20,660 | 21,880 | +1,220 |
| `tl` to packaged flags | 6,746 | 9,102 | +2,356 |
| **Total** |  |  | **+17,862** |

The arithmetic is exact:

```text
VI executable size minus EN executable size = 17,862
sum of seven interstitial deltas          = 17,862
```

No part of the VI size increase is caused by larger model blobs.

Canonical geometry evidence:

```text
docs/reverse/EVIDENCE_ADAS_GAP_GEOMETRY.json
```

## Metadata interpretation

The interstitial regions are high-entropy non-model content positioned around protected model blobs. Their placement is consistent with package, protection, alignment, encryption, authentication, or loader metadata. This is a structural observation, not a proven semantic interpretation.

The following remain **UNKNOWN**:

- Record framing or header format.
- Whether regions contain IVs, tags, signatures, hashes, padding, encrypted configuration, or license material.
- Whether each model has independent metadata.
- Whether the regions are read directly by the executable.
- Whether an opaque indirect dispatcher consumes them.
- Whether EN and VI use different metadata-generation tooling.
- Whether any region is malformed in VI.
- Whether metadata causes the observed runtime activation failure.

## Loader and xref status

Static analysis has not established a direct code reference from a known loader, BitAnswer function, license function, or `/proc/self/exe` helper to the seven interstitial regions.

The `/proc/self/exe` helper identified in the BitAnswer code only resolves the current executable path. It is byte-identical between EN and VI and does not itself prove executable-integrity validation.

Compared functions including these paths are byte-identical:

```text
Bit_SetRootPath
Bit_Login
Bit_ReadFeature
Bit_CheckOutSn
Bit_CheckOutFeatures
selected internal dispatcher
```

Consequently:

```text
changed BitAnswer implementation: DOWNGRADED
same implementation acting on different runtime state: UNKNOWN
interstitial metadata causing failure: UNKNOWN
```

## Packaged flags and tail

The package tail differs in `m0`, whose offset/size-directory role is understood. The model offsets encoded by VI are self-consistent. No proven tail field currently identifies a corrupt model size or out-of-range model extent.

This excludes a simple stale-offset explanation for the six recovered model blobs. It does not validate every opaque interstitial byte or every runtime protection check.

## Regression ranking impact

1. **UNKNOWN, higher priority:** kernel/media/memory integration and live frame/IPU behavior.
2. **UNKNOWN, higher priority:** persistent calibration/config compatibility.
3. **UNKNOWN:** upstream `raw_adas` frame availability despite unchanged writer helpers.
4. **UNKNOWN:** package interstitial metadata or an unidentified reader.
5. **UNKNOWN but lower:** identical license code receiving incompatible runtime state.
6. **DOWNGRADED:** broad ADAS algorithm rewrite.
7. **DOWNGRADED:** changed BitAnswer implementation.
8. **EXCLUDED AS PRIMARY:** changed CNN/model weights.

## Required proof before assigning causality

A package-metadata root cause requires at least one of:

- A direct xref from executable code to an interstitial offset.
- A recovered parser that validates one of the regions.
- A runtime log identifying package or integrity rejection.
- A read trace showing access to the relevant executable offsets.
- A controlled, reversible launch proving VI fails on the EN kernel, `cardv`, and persistent-state baseline specifically because of package validation.

Absent such evidence, the package hypothesis must remain **UNKNOWN**.

## Reproduction

From repository root, using the existing extracted binaries and model directory evidence:

```powershell
python tools\fw\adas_gap_report.py build\fw_bin_en\adas build\fw_bin_vi\adas --left-directory-json docs\reverse\EVIDENCE_ADAS_MODEL_DIRECTORY.json --right-directory-json docs\reverse\EVIDENCE_ADAS_MODEL_DIRECTORY.json -o build\adas_gap_geometry.json --markdown build\adas_gap_geometry.md
Get-FileHash -Algorithm SHA256 build\fw_bin_en\adas,build\fw_bin_vi\adas
```

For code-level comparison, with the documented ELF/disassembly dependencies installed:

```powershell
python tools\fw\thumb_callgraph_diff.py build\fw_bin_en\adas build\fw_bin_vi\adas
python tools\fw\elf_function_diff.py build\fw_bin_en\adas build\fw_bin_vi\adas
```

Canonical supporting reports and evidence:

```text
docs/reverse/ADAS_STATIC_DIFF_V1.md
docs/reverse/ADAS_SEMANTIC_DIFF_V2.md
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md
docs/reverse/BITANSWER_LICENSE_PATH_V1.md
docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json
docs/reverse/EVIDENCE_ADAS_GAP_GEOMETRY.json
docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json
```

## Conclusion

The package delta is real, precisely bounded, and completely outside the six model blobs. The VI executable is larger solely because the seven interstitial regions changed size. No direct reader, validator, or failure log currently proves that these regions caused the VI activation regression. Package-metadata causality therefore remains **UNKNOWN**, while changed CNN weights are excluded as a primary explanation.