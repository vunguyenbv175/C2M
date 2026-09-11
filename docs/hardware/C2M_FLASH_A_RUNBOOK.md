# C2M Flash A Runbook — Candidate A (EN vendor baseline)

**Safety:** `FLASH` section is FLASH; all verification is READ_ONLY / SAFE_WRITE_OUTPUT_ONLY.
**Freeze:** Candidate A = `EN_REPACK_GOLDEN.tar` SHA256 `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`. Do NOT rebuild. Do NOT rename inner members.

## 0. Recovery readiness gate (BLOCKING)

`READ_ONLY` prechecks on workstation + bench. Record under `C2M_HW_<date>/01_recovery/`.

```text
[ ] known-good microSD (no bad blocks; recently formatted FAT32) ............ READ_ONLY
[ ] stable external power (no USB-hub brownout risk) ........................ READ_ONLY
[ ] original EN package available: V2023.08.03.1_C2M_U_FR_WIFI_EN.tar ....... READ_ONLY
[ ] Candidate A package available: EN_REPACK_GOLDEN.tar ..................... READ_ONLY
[ ] SHA256 verified (both, see below) ...................................... READ_ONLY
[ ] flash folder root contents verified (4 files, exact names) ............. READ_ONLY
[ ] device power-cycles cleanly on current firmware ........................ READ_ONLY
[ ] recovery procedure printed and understood (rollback §6) ................ READ_ONLY
```

Hash verification `READ_ONLY`:

```sh
sha256sum V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
# expect 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
sha256sum EN_REPACK_GOLDEN.tar
# expect 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
tar -tf EN_REPACK_GOLDEN.tar
# expect exactly: SigmastarUpgradeSD_SSC8838G.bin / sysVer.txt / minieye_firmware.md5 / adas_upgrade.sh
```

Card preparation from `C2M_FLASH_A/` (private release layout, NOT in git):

```sh
# SAFE_WRITE_OUTPUT_ONLY (workstation only)
ls -l C2M_FLASH_A/
# expect: SigmastarUpgradeSD_SSC8838G.bin / sysVer.txt / minieye_firmware.md5 / adas_upgrade.sh
cp C2M_FLASH_A/* /mnt/sdcard/   # copy CONTENTS to microSD root, NOT the outer TAR
ls -l /mnt/sdcard/
```

Verdict:

```text
RECOVERY_READY = YES / NO
```

If NO: `STOP`. Do NOT flash.

## 1. Flash steps (FLASH — manual, orchestrator never automates)

```text
1. Power OFF C2M. Insert prepared microSD. [FLASH]
2. Power ON with stable supply. Do NOT interrupt for any reason. [FLASH]
3. Wait for stock upgrade completion + automatic reboot (compare with pre-flash baseline boot time). [FLASH]
4. Remove microSD only after live view returns. [FLASH]
```

Expected reboot behavior: live view within stock time budget; no boot loop; no stall reboot from `minieye_daemon.sh`.

Failure symptoms → STOP + rollback §6: boot loop, no live view >2× baseline time, repeated `minieye_daemon.sh` reboots, read-only filesystem unexpectedly, kernel panic on serial, burning smell/thermal event.

## 2. Acceptance test (READ_ONLY observation + SAFE_WRITE_OUTPUT_ONLY notes)

System (allow full boot first; do NOT judge ADAS before auto-calibration/readiness):

```text
[ ] boot to live view ............ READ_ONLY
[ ] front/rear view (if applicable) READ_ONLY
[ ] normal recording (files appear) READ_ONLY
[ ] event recording trigger ....... READ_ONLY
[ ] SD behavior (mount/rw) ........ READ_ONLY
[ ] Wi-Fi AP/STA + app connect .... READ_ONLY
[ ] M4/display (stock UI bright/mode) READ_ONLY
[ ] GPS (if available) ............ READ_ONLY
[ ] cold reboot x3, all above hold  READ_ONLY
```

ADAS (wait for normal activation; log times, do NOT fail on cold calibration):

```text
[ ] lane lines visible ............ READ_ONLY
[ ] LDW ........................... READ_ONLY
[ ] FCW ........................... READ_ONLY
[ ] PCW ........................... READ_ONLY
[ ] other stock warnings .......... READ_ONLY
```

Log `SAFE_WRITE_OUTPUT_ONLY` to `02_candidate_A/acceptance.md`:

```text
boot_time_s / adas_activation_time_s / calibration_state / unexpected_reboot / crash / display_issue / recording_issue
```

## 3. Evidence to collect (READ_ONLY)

```text
sysVer shown on device (photo/note)
pack hashes used (SHA256SUMS copy)
acceptance.md + timestamps
```

## 4. Verdict

```text
CANDIDATE_A: PASS / FAIL / PARTIAL
```

`Candidate B BLOCKED unless A = PASS.` Any FAIL → §6 rollback, STOP day.

## 5. Next allowed step

Only on PASS: `docs/hardware/C2M_FLASH_B_RUNBOOK.md`.

## 6. Rollback

Re-flash original EN vendor TAR via identical SD path (FLASH). Persistent `/customer/minieye/config`, `/config/cgi_config.bin`, `/config/net_config.bin` are preserved by updater — do NOT hand-edit them. If boot loop: power off, re-seat known-good SD with verified A contents, retry once, then STOP and preserve evidence.
