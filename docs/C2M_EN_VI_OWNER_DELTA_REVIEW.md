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

Only `bootconfig/bin/cardv` and `bootconfig/modules/4.9.227/sc7a20.ko` differ.

### ADAS ABI/symbol surface

A `readelf -Ws` based comparison finds:

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

Thumb-2 disassembly plus PLT relocation mapping shows that both builds retain the essential platform/IPU sequence:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice(...)
```

The visible change is mainly the failure logging path: EN uses `google::LogMessage`/C++ stream insertion; VI uses a shorter direct `fwrite` path. This makes `SystemInit` itself a lower-probability explanation for complete ADAS failure, despite being the only size-changing function.

### Corrected appended-payload boundary

Strict ELF file-backed boundary analysis gives:

```text
overlay start: 0x1755e4
EN overlay: 10,106,692 bytes
VI overlay: 10,124,554 bytes
```

This supersedes the earlier approximate `0x172b1c` boundary derived only from the section-header table.

## Highest-priority suspects

1. **VI `adas` executable / appended payload** — highest.
2. **VI `cardv` interaction / raw_adas producer** — high.
3. **Kernel/memory/driver integration** — medium-high.
4. **Changed interpretation of persistent config/license/calibration** — medium.

## Reuse targets worth preserving

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

```text
screen_export_port default string: 26012
sdk_use_msgpack=true
ScreenService::Send<C1VehicleWarning>
ScreenService::Send<vector<C1VehicleMeasureRes>>
ScreenService::Send<vector<C1PedRes>>
libflow WebSocket support
```

These justify passive M4 capture/decoder work, but do not yet prove the physical transport.

## Next actions

1. Land reproducible firmware-diff tools in `tools/fw/`.
2. Build normalized ARM Thumb-2 function diff to remove branch/address-shift noise.
3. Diff `adas` startup/config/license/ringbuffer/IPU/TSR/ScreenService paths.
4. Diff `cardv` around `raw_adas`, screen, GPS and G-sensor changes.
5. Prepare the reversible runtime test: **EN working base + VI `adas` executable only**.

## Safety rule

No full NAND reflash for userspace bisecting. Preserve EN recovery and persistent config before any physical-device experiment.
