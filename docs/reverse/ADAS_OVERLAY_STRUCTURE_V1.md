# ADAS Appended Payload Structure V1

## Corrected boundary

The file-backed ELF ends at:

```text
0x172b1c
```

Payload sizes:

```text
EN 10,117,644 bytes
VI 10,135,506 bytes
VI - EN = +17,862 bytes = 0x45c6
```

The earlier `0x1755e4` boundary was wrong because `.bss` / `SHT_NOBITS` was counted as file-backed data. `tools/fw/elf_overlay_report.py` now excludes memory-only sections.

## Exact-anchor mapping

`tools/fw/overlay_anchor_map.py` samples exact 64-byte anchors from EN and searches for the same bytes in VI.

With a 32 KiB sampling stride:

```text
total EN anchors:   309
exactly matched:    306
```

Large regions are therefore byte-for-byte identical, separated by changed-size regions.

Dominant EN->VI offset plateaus:

```text
+0x0520   1,312 bytes
+0x16c2   5,826 bytes
+0x3b48  15,176 bytes
+0x3392  13,202 bytes
+0x37ce  14,286 bytes
+0x3c92  15,506 bytes
```

At the plaintext flag tail, VI is shifted by the full file-size delta:

```text
+0x45c6 = +17,862 bytes
```

## Plaintext tail

Both builds expose exactly 121 default `--key=value` flags with identical key sets.

Only one packaged default value differs:

```text
m0
```

Operational defaults remain identical, including:

```text
enable_vehicle=true
enable_ped=true
enable_lane=true
enable_fcw=true
enable_hmw=true
enable_ldw=true
enable_tsr=false
enable_screen_service=true
sdk_use_msgpack=true
camera_input=ringbuf_vehicle
ringbuf_name=raw_adas
protocol=1.4.0
```

## `m0` is now decoded

`m0` is no longer UNKNOWN.

Static reverse shows:

```text
vehicle::GetKey()
  -> AES-128 key

cnn::CnnConfig::UpdateFromEnv()
  -> split m0 into 12 encrypted 16-byte blocks
  -> DecryptNum()
  -> six (offset,size) records
```

The records map, in `model.txt` order, to:

```text
d0
v_a
v_t
p_r
road
tl
```

VI changes all six absolute offsets because the interstitial regions change size, but all six model sizes remain unchanged.

Most importantly, hashing each sliced model proves all six model blobs are **byte-identical EN vs VI**.

See `docs/reverse/ADAS_PACKAGE_LOADER_V1.md` and `docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json`.

## Seven interstitial regions

Once the six identical model blobs and the final 3602-byte flag tail are removed, seven non-model regions remain.

Their size deltas are:

```text
before d0       +1,312
before v_a      +4,514
before v_t      +9,350
before p_r      -1,974
before road     +1,084
before tl       +1,220
before flags    +2,356
----------------------
total          +17,862 bytes
```

Thus the seven regions account for the entire VI file-size increase.

`tools/fw/adas_gap_report.py` now analyzes these regions directly: SHA-256, entropy, ASCII/zero ratio, block repetition, aligned equal-byte ratio, common prefix/suffix and block-set similarity.

See `docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md`.

## Regression implication

Static evidence now argues against:

```text
different CNN weights
changed model sizes
stale m0 model offsets
broad ADAS rewrite
```

Highest-value remaining static questions:

1. What code reads or validates the seven interstitial regions?
2. Are they BitAnswer/protection/license package data or another proprietary container layer?
3. Does VI fail when its `adas` package is executed on the otherwise-working EN base?
4. If VI `adas` works on EN, does VI `cardv` stop or change the `raw_adas` producer contract?

## Confidence

- **CONFIRMED:** true file-backed ELF boundary is `0x172b1c`.
- **CONFIRMED:** `m0` is a six-record encrypted model directory.
- **CONFIRMED:** all six model blobs are identical EN vs VI.
- **CONFIRMED:** seven interstitial regions account for all +17,862 bytes.
- **UNKNOWN:** exact proprietary format and runtime significance of those interstitial regions.
