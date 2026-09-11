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

Most of the visible feature delta is concentrated in GPS parsing, G-sensor/power handling and restart/logging rather than the core ADAS frame-forwarding functions.

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

This looks like a substantial GPS parser refactor.

### Screen GPS changes

`SendGPSInfoToScreen` shrinks from 112 to 92 bytes and no longer calls `SetGPSLevel()` twice.

VI adds a new exported:

```text
SendGPSSpeedToScreen(int)
```

Together with the VI-only 8 MiB framebuffer bootarg, this is strong evidence that the September build included M4/display work.

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

This does **not** prove byte-for-byte equivalence, but it lowers the probability that VI completely rewrote the `raw_adas`/Flow data path.

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

This is valuable for M4 reverse engineering.

### Confirmed `SendADASInfoToScreen` sequence

Both builds retain the same call sequence and state accessors, including `GetADASStatus`, `SetADASStatus`, `GetADASCalibStatus` and `SetADASCalibStatus`. So the basic `cardv -> screen` ADAS status plumbing did not disappear in VI.

## G-sensor/power changes

VI changes `GsensorSetSensitivity` substantially and `main` gains a call to `GsensorSetPowerOnByInt`.

`GsensorSetPowerOnByInt` itself gains multiple `system()` calls plus `sleep()`.

This matches the firmware-level change from `Camera.Menu.GSensorSensitivity` to `Camera.Menu.GSensor` and the changed `sc7a20.ko` module.

This path is relevant to startup/power behavior but is not yet proven causal for ADAS failure.

## Regression ranking after cardv diff

### Higher priority

1. ADAS appended payload / `m0` and other data constants.
2. GPS/screen integration only if the user's observed “ADAS dead” was actually a display/output failure.
3. Kernel/driver/memory integration.

### Lower than before

A wholesale `cardv` ADAS-frame pipeline rewrite is now less likely because the core resolved call sequences are stable.

## Runtime tests required

On EN and VI, distinguish:

```text
ADAS process dead
ADAS process alive but no raw_adas frames
ADAS inference alive but no warning output
ADAS output alive but M4/display path broken
```

## Confidence

- **CONFIRMED:** symbol additions/removals and size deltas.
- **CONFIRMED:** VI adds `SendGPSSpeedToScreen(int)`.
- **CONFIRMED:** core resolved call sequences listed above are unchanged.
- **HIGH-CONFIDENCE:** VI contains a real GPS/NMEA + screen refactor.
- **UNKNOWN:** whether that refactor caused the user's ADAS failure.
