# Candidate D2 TSR experiment — corrected config LF gate — 2026-10-14

**Status:** HOST-VALIDATED + SD READ-BACK 4/4 VERIFIED; READY FOR OWNER'S
MANUAL EXPERIMENTAL FLASH, not device-tested. D token `20261014000003` was
superseded and replaced on the same flash card by D2 token
`20261014000004` on the still-connected card. Owner has not reported any
D1 device flash; no automatic camera update occurred.

## Correction

Review found that D1's AWK/grep comparison could normalize an unterminated
final unrelated config line by appending LF, making the preservation check
falsely pass. D2 adds a pre-transform `wc -l` vs AWK `NR` equality gate and
returns `MISSING_FINAL_LF` before profile generation, backup or config write.
A negative host test covers unterminated unrelated flag/comment/TSR inputs.
D2 status version is `D2`; profile SHA256 is
`63b7179bfd3983219f51f91159ce9c730dd84f6ec8c810d1ba31a96c2b91a37d`.

## Build and validation

- Source commit `09150d8` after owner-requested correction.
- Corrected workflow `firmware-candidateD`, run `38526298792`: GREEN.
- 7/7 profile host tests; stock BusyBox QEMU gates; independent exact C WAV
  pins; no-op/mutated rebuild; ARM ABI/idle QEMU; deep/diff gates.
- Corrected profile source passed final extraction; legacy C patch absent;
  all C audio/list/md5/idle bytes exact; protected loads unchanged.
- Customer semantic delta vs C: added `/c2m/tsr_profile_boot.sh`, changed
  `/wifi/rcInsDriver.sh`, no removed paths, existing metadata unchanged.
- D2 TAR `EN_D2_TSR_EXPERIMENT.tar`: SHA256
  `93b4aafe91ec326165b121408c11578420458eedd2da68a1770afcad10429715`.
- Local reversion: stock `20230803193750` → `20261014000004`; report
  `ALLOWLIST-OK`, bytes outside 14-byte token unchanged, deep `VALID` 33.
- Final host extraction verdict:
  `PASS_HOST_FINAL_PAYLOAD_NOT_DEVICE_TESTED`.

## Current on-card identities

| File | Bytes | SHA256 |
|---|---:|---|
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `db203cb1e10a8c643d269e868269a6c5f6d8c22b2dca0b2ad67a0dc35c0a9c91` |
| `sysVer.txt` (`sysVer 20261014000004`) | 26 | `e78f0c3c0257d447f6ce20df8edb873bd325a53feea6d33b241add9c5a15c78d` |
| `minieye_firmware.md5` | 66 | `5b72ca978fd45ba6f354205ebfa2ce8b57f9fa75657e5d2533944a69b1fff989` |
| `adas_upgrade.sh` (stock) | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

D2 profile script is repository source code; raw device config/backups,
firmware bytes, audio bytes and sign database remain private. On-card root remains
four payload files plus retained SVI/C2M_DIAG.

## Experiment scope

D2 is still an experimental static gflag profile, not a new detector/model and
not proof that camera TSR recognizes or displays a sign. It targets:

```text
--enable_tsr=true
--tsrw_interval=5
--tsrw_sli_over_min_ratio=10
--tsrw_sli_over_min_thresh=5
--tsrw_sli_host_speed_min_thresh=20
```

The script backs up pre-D/post-C encoded config if it must change it, modifies
only encoded `adas.flag` using checked same-filesystem stage/rename, and lets
stock `run.sh` reconcile decoded config. D2 can reapply at later boots;
flashing C/A alone is not config rollback. A reviewed recovery must account
for the running hook before restoring any flag. Never reset calibration/license.

## Flash/acceptance

Card is the verified 32GB `C2M_FLASH_B` USB SM3350 card, not 59GB MINIEYE
recording card. It was written without format, fsync/readback verified 4/4,
cache flushed, final NOT dirty and Healthy. Owner still performs manual
stable-power flash.

After flash:
1. Confirm live view, recording, app/Wi-Fi and Vietnamese warning audio.
2. Record at least 6 minutes and read `C2M_DIAG/tsr-profile-D.txt` plus
   START/HB. `APPLIED_WAIT_STOCK_REDECODE` means config script completed; it
   does not prove recognition.
3. Test lawful real signs with a passenger/video observer; do not operate app
   while driving or create dangerous warnings. Record sign, display, warning,
   miss/false positive and latency.
4. Any reboot loop, recording/ADAS regression or distracting alerts: STOP,
   preserve card/logs, do not try another profile.

Static follow-up found `/tmp/car_info` may provide a future non-consuming GPS
snapshot via read-only `pread`; D2 does not include that reader. Stock TSR
collector defaults loopback `127.0.0.1:25012`; a missing external frame is not
proof of detector failure. GPS database/Warner remains separate and private.
