# CARDV Static Diff V1 — EN vs VI

## Why `cardv` matters

`cardv` is one of only two changed rootfs files between the known-good EN firmware and the VI regression firmware. It participates in recorder/media control, GPS, ADAS integration and M4/screen state.

## ELF/code size delta

```text
EN .text: 0x0a42bc
VI .text: 0x0a47bc
```

VI therefore adds exactly `0x500` bytes (1280 bytes) of `.text`.

Dynamic symbol comparison:

```text
EN symbols:    4477
VI symbols:    4475
common:        4473
EN-only:          4
VI-only:          2
```

### EN-only symbols

```text
Is_Gps_info(unsigned char*)
nmea_satinfo(int, _nmeaINFO*)
nema_calc_checksum(unsigned char*, int*)
g_zkw_gps_module
```

### VI-only symbols

```text
nmea_BDGSV2info_na(_nmeaBDGSV*)
SendGPSSpeedToScreen(int)
```

This confirms a deliberate GPS/NMEA + screen behavior change in VI.

## Functions with changed reported size

Only nine common functions change symbol size:

```text
nmea_parse1                          792 -> 680
nmea_pack_type1                      388 -> 616
SendGPSInfoToScreen                  112 -> 92
GsensorSetSensitivity               1304 -> 1624
GsensorSetPowerOnByInt              1048 -> 1104
nmea_parser_real_push1              1408 -> 1436
cardv_cmd_handler_system_restar      344 -> 612
cardv_cmd_handler_GsensorSensitivity 148 -> 140
minieye_init                        1212 -> 1216
```

Most visible feature delta is concentrated in GPS parsing, G-sensor/power handling and restart/logging rather than the core ADAS frame-forwarding functions.

## Call-graph comparison

A direct-call/PLT call sequence comparison across 3020 same-name functions gives:

```text
same call sequence:    2987
changed call sequence:   33
```

Several of those 33 are noise from unresolved indirect registers or literal-pool disassembly. The high-confidence semantic changes include the GPS/NMEA and G-sensor functions above.

### GPS parser changes

`nmea_parse1` removes repeated calls to the old generic `nmea_satinfo(...)` and VI introduces `nmea_BDGSV2info_na(...)`.

`nmea_pack_type1` gains eleven additional `memcmp` calls, strongly indicating expanded sentence/type matching.

`nmea_parser_real_push1` changes checksum/info parsing flow and removes calls to the EN-only `nema_calc_checksum` and `Is_Gps_info`.

This is a substantial GPS parser refactor.

### Screen GPS changes

`SendGPSInfoToScreen` shrinks from 112 to 92 bytes and no longer calls `SetGPSLevel()` twice.

VI adds:

```text
SendGPSSpeedToScreen(int)
```

Together with the VI-only 8 MiB framebuffer reserved-memory bootarg, this is strong evidence that the September build included M4/display work.

## ADAS/media path appears structurally stable

The following functions retain the same resolved direct-call sequence between EN and VI:

```text
SendADASInfoToScreen
DeviceSendMsgToScreenTask
adas_minieye_flow_image_task
adas_minieye_send_frame_task
adas_mineye_flow_vehicle_task
adas_minieye_flow_imu_task
adas_minieye_read_imu_task
minieye_adas_config_update
```

`minieye_init` also retains the same resolved call sequence despite growing by four bytes.

This does **not** prove byte-for-byte equivalence or frame-flow equivalence, but it lowers the probability that VI completely rewrote the `raw_adas`/Flow path.

### Confirmed `DeviceSendMsgToScreenTask` sequence

Both builds call, in the same order:

```text
sleep
WSGetConnectStatus
SendADASInfoToScreen
GetADASStatus
SendGPSInfoToScreen
SendBacklightLevelInfoToScreen
SendDisplayModeToScreen
SendStorageInfoToScreen
SendWifiStatusToScreen
SendAudioRecordStatusToScreen
```

### Confirmed `SendADASInfoToScreen` sequence

Both builds retain the same call sequence and state accessors, including:

```text
GetADASStatus
SetADASStatus
GetADASCalibStatus
SetADASCalibStatus
```

So the basic `cardv -> screen` ADAS status plumbing did not disappear in VI.

## G-sensor/power changes

VI changes `GsensorSetSensitivity` substantially and `main` gains a call to `GsensorSetPowerOnByInt`.

`GsensorSetPowerOnByInt` itself gains multiple `system()` calls plus `sleep()`.

This matches the firmware-level change from:

```text
Camera.Menu.GSensorSensitivity
```

to:

```text
Camera.Menu.GSensor
```

and the changed `sc7a20.ko` module.

This path is relevant to startup/power behavior but is not yet proven causal for ADAS failure.

## Updated regression ranking after ADAS package reverse

New static evidence proves all six embedded ADAS model blobs are byte-identical EN vs VI and VI's encrypted `m0` directory points to them correctly. The entire +17,862-byte `adas` growth lies in seven interstitial/protected regions.

This changes the ranking:

### 1 — VI ADAS package metadata / validation path

**Highest static priority.**

Why:
- same CNN weights;
- same model sizes;
- valid moved offsets;
- very narrow executable call-graph delta;
- all package growth sits outside the model blobs.

### 2 — `cardv` GPS/M4/output refactor

**High only if the user's “ADAS dead” observation was actually output/display failure.**

VI clearly changes GPS-to-screen behavior. Runtime must determine whether inference is alive behind a dead M4/output path.

### 3 — `cardv` `raw_adas` producer contract

**Still important, but a wholesale rewrite is statically less likely.**

The resolved call sequences remain stable. Runtime must prove whether `raw_adas` frames actually exist and advance.

### 4 — kernel / SC7A20 / memory integration

**Medium-high after userspace bisect.**

Only move this to the top if VI `adas` works correctly when launched on the EN kernel/rootfs/cardv base.

## Runtime evidence now prepared in repo

Use:

```text
tools/device/collect_baseline.sh
tools/device/classify_adas_state.py
tools/device/compare_baselines.py
```

Classification target:

```text
A process absent
B crash/restart loop
C process alive but input/ringbuffer path suspect
D process alive but inference/IPU/model init suspect
E inference alive but warning suppressed
F ADAS alive but display/audio path suspect
```

For M4 transport isolation:

```text
tools/m4/discover_transport.py
```

## Most decisive next experiment

After backing up the known-good EN executable and config, run the **VI `adas` executable temporarily on the working EN base** without replacing NAND contents.

```text
VI adas fails on EN base
    -> focus on ADAS package metadata / validation / persistent-data interpretation

VI adas works on EN base
    -> focus on cardv/raw_adas, kernel, drivers, framebuffer/memory integration
```

## Confidence

- **CONFIRMED:** symbol additions/removals and size deltas.
- **CONFIRMED:** VI adds `SendGPSSpeedToScreen(int)`.
- **CONFIRMED:** core resolved call sequences listed above are unchanged.
- **CONFIRMED:** all six embedded ADAS model blobs are identical EN vs VI.
- **HIGH-CONFIDENCE:** VI contains a real GPS/NMEA + screen refactor.
- **HIGH-CONFIDENCE:** a wholesale `cardv` ADAS pipeline rewrite is less likely than package/output/integration explanations.
- **UNKNOWN:** whether GPS/M4, `raw_adas`, or package validation is the actual runtime failure point on the user's unit.
