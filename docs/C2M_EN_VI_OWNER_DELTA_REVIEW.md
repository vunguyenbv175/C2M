# C2M EN vs VI Owner Delta Review

**Status:** static-review checkpoint 2026-09-11  
**Repository:** `vunguyenbv175/C2M`  
**Ground truth:** EN 2023-08-03 runs ADAS on the user's physical unit; VI 2023-09-20 did not.

## Executive conclusion

Treat the two vendor images as a good/bad differential pair:

```text
EN 2023-08-03 = GOLDEN WORKING BASELINE
VI 2023-09-20 = VENDOR VIETNAM / DONOR / REGRESSION BUILD
```

Do not replace stock ADAS yet. The static delta is narrow enough that a reversible userspace bisect is more valuable than a rewrite.

## Reproducible findings

### Rootfs

`tools/fw/tree_hash_diff.py` reproduces:

```text
same:       526
different:    2
EN only:      0
VI only:      0
```

Only:

```text
bootconfig/bin/cardv
bootconfig/modules/4.9.227/sc7a20.ko
```

differ.

### ADAS subtree

Most ADAS dependencies are byte-identical, including the main model image, IPU firmware, lane binaries, pedestrian library, startup scripts and most shared libraries. The main `adas` executable is different and remains the highest-priority userspace suspect.

### ELF ABI/symbol surface

The EN and VI `adas` binaries expose the same symbol-name set. A `readelf -Ws` based comparison finds:

```text
left symbols:   3875
right symbols:  3875
common symbols: 3875
left only:         0
right only:        0
```

Among common symbols, only one function changes reported size:

```text
SystemInit(unsigned int)
EN: 124 bytes
VI: 100 bytes
```

Most later symbol addresses move by `-0x18`, explained by that 24-byte shrink.

### `SystemInit` semantic delta

Thumb-2 disassembly shows that both builds still perform the same essential platform/IPU initialization sequence:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice(...)
```

The observed difference is primarily the **failure logging path**:

- EN constructs a `google::LogMessage`, writes an error string through the C++ stream, and destroys the log object.
- VI emits a shorter direct `fwrite`-style failure message.

Current assessment:

```text
CONFIRMED: SystemInit implementation changed.
HIGH-CONFIDENCE: the size reduction is mostly logging-path simplification.
LOW likelihood: this specific delta alone explains total ADAS failure.
```

Therefore the regression search must continue beyond a naïve “only one function changed size” interpretation: same-sized functions can still contain code/data-reference changes.

### Corrected appended-payload boundary

A stricter ELF parser uses the maximum end of file-backed sections/segments plus header tables. It finds:

```text
overlay start: 0x172b1c

EN file size:     11,636,008
overlay size:     10,117,644
overlay entropy:  ~7.9767 bits/byte

VI file size:     11,653,870
overlay size:     10,135,506
overlay entropy:  ~7.9767 bits/byte
```

This supersedes the temporary incorrect `0x1755e4` boundary, which counted `.bss`/`SHT_NOBITS` as file-backed data.

### Embedded-model directory and interstitial gaps

Static reverse of `FLAGS_m0` now proves it is an AES-128-encrypted directory of six `(offset,size)` records corresponding to the six stock model IDs:

```text
d0
v_a
v_t
p_r
road
tl
```

All six model blobs are **byte-identical EN vs VI**, including size and SHA-256. VI only moves their absolute offsets and updates `m0` consistently.

The complete VI file-size increase is instead located in the seven interstitial regions around those models:

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

Therefore different CNN weights, changed model sizes and stale model offsets are now low-probability regression explanations. The protected/interstitial package metadata and its validation/decryption path move up in priority.

## Highest-priority suspects

### R1 — VI `adas` protected/interstitial package metadata or validation path

Priority: **highest**.

Why:
- known-good vs known-bad aligns with this version change;
- all six embedded CNN/model blobs are identical;
- `m0` correctly tracks the moved blobs;
- the complete file-size increase is in non-model interstitial regions;
- static code/call-graph differences are narrow.

### R2 — `cardv` / `raw_adas` producer integration

Priority: **high**.

Why:
- one of only two rootfs changes;
- media/ringbuffer producer candidate;
- participates in screen/GPS/device state;
- VI adds `SendGPSSpeedToScreen(int)`.

### R3 — kernel / memory / driver integration

Priority: **medium-high**.

Why:
- kernel changed;
- VI adds an 8 MiB `fb` reserved-memory bootarg;
- SC7A20 module changed;
- multiple customer kernel modules were rebuilt.

### R4 — changed interpretation of persistent config/license/calibration

Priority: **medium**.

The scripts are mostly identical, but the new executable may validate the same persistent data differently.

## Reuse targets already worth preserving

Static evidence supports reuse-first work on:

```text
vehicle detection/tracking
pedestrian detection
lane/LDW
FCW/headway
distance/TTC
TSR/speed-limit path
ScreenService
M4/status integration
```

## M4 static anchors

Confirmed static anchors include:

```text
screen_export_port default string: 26012
sdk_use_msgpack=true
ScreenService::Send<C1VehicleWarning>
ScreenService::Send<vector<C1VehicleMeasureRes>>
ScreenService::Send<vector<C1PedRes>>
libflow WebSocket support
```

These facts justify a dedicated passive M4 capture/decoder workstream. They do **not** yet prove the physical M4 transport.

## Next coding-agent actions

1. Trace readers/validators of the seven interstitial package regions and `/proc/self/exe`.
2. Continue normalized ARM/Thumb semantic diff for same-sized ADAS functions.
3. Function-diff `cardv` around `raw_adas`, screen, GPS and G-sensor changes.
4. Prepare a one-command read-only device baseline collector.
5. Prepare, but do not execute destructively, the reversible test:

```text
EN working userspace/base + VI adas executable only
```

## Safety rule

No full NAND reflash for bisecting userspace behavior. Preserve EN recovery and persistent config before any physical-device experiment.
