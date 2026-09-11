# C2M Firmware EN vs VI Reverse-Engineering Documentation Pack V1

## Purpose

This pack is a coding-agent handoff for a deep static comparison of two vendor-provided C2M firmware images:

- **EN / known-good on the user's physical C2M:** `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`
- **VI / ADAS did not operate on the user's physical C2M:** `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`

The user reported that when the device was purchased, ADAS did not work. The vendor supplied these two images; the EN image made ADAS work while the VI image did not.

That real-device observation is the strongest ground truth in this pack.

## SHA-256

```text
EN TAR  3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
VI TAR  f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa
```

## Working classification

```text
EN 2023-08-03 = GOLDEN WORKING BASELINE
VI 2023-09-20 = VENDOR VIETNAM / DONOR / REGRESSION BUILD
```

Do **not** treat the VI build as the baseline merely because it is newer.

## Key conclusions

1. Both packages are in the same SigmaStar vendor full-upgrade format.
2. The top-level updater script is byte-identical.
3. CIS, IPL and IPL_CUST payloads are byte-identical.
4. VI changes U-Boot, kernel, rootfs `cardv`, SC7A20 accelerometer driver, many kernel modules in `customer`, ADAS executable, locale audio, Wi-Fi configuration and default CGI configuration.
5. Rootfs is otherwise extraordinarily stable: **526/528 files are identical**; only `cardv` and `sc7a20.ko` differ.
6. The ADAS subtree contains **112 files; 98 are identical and only 14 differ**. The AI model, lane binaries, IPU firmware, Ped library, most third-party libraries and startup scripts are identical.
7. The main ADAS executable is therefore a prime regression suspect.
8. `cardv` is another prime suspect because it changed and VI adds `SendGPSSpeedToScreen(int)` while removing older GPS helper symbols.
9. VI bootargs add an **8 MiB framebuffer reserved-memory region**, making display/M4 changes a first-class part of the VI delta.
10. Stock ADAS contains real TSR, TTC, distance, pedestrian, lane, ScreenService and traffic-light related code.
11. `ScreenService` is backed by `libflow`; static evidence indicates WebSocket-capable transport and a default screen export port string **26012**.
12. The persistent `/customer/minieye/config` directory is deliberately backed up/restored by the updater. That makes a pure "different adas.flag after flashing" explanation less likely if the same device/config was used for both vendor images.
13. The apparent `h--switch_file=...` string in VI is **not a malformed flag**. Exact byte inspection shows the proper substring `--switch_file=/customer/minieye/config/adas_de.flag`; `h` is merely the preceding byte in the appended payload.

## Documents

- `01_PACKAGE_FLASH_LAYOUT.md`
- `02_BOOT_KERNEL_ROOTFS.md`
- `03_ADAS_ENGINE_TSR_AND_REGRESSION.md`
- `04_M4_SCREEN_DISPLAY_PATH.md`
- `05_CAMERA_MEDIA_IMU.md`
- `06_WIFI_APP_WEB_API.md`
- `07_CONFIG_LICENSE_CALIBRATION.md`
- `08_AUDIO_VIETNAM_LOCALIZATION.md`
- `09_REGRESSION_BISECT_PLAN.md`
- `10_CODING_AGENT_WORKPLAN.md`

Evidence:
- `EVIDENCE_FILE_DIFFS.csv`
- `EVIDENCE_PARTITION_HASHES.csv`
- `EVIDENCE_ADAS_OVERLAY.json`

## Rule for future work

Every new statement must be tagged as:

```text
CONFIRMED
HIGH-CONFIDENCE
HYPOTHESIS
UNKNOWN
```

Do not convert a string hit into a protocol claim without runtime or call-graph evidence.
