# B2 SD reversion — distinct update identity, unchanged B2 runtime

**Prepared:** 2026-10-13. **Status:** HOST-VALIDATED + SD READ-BACK VERIFIED;
manual flash OPERATOR-REPORTED SUCCESS (2026-10-13), runtime acceptance
**BLOCKED: unreachable startup hook discovered on recording-card investigation**.
See `CANDIDATE_B2_HOOK_FAILURE.md`; no diagnostic logs were found. This is a
separately authorized artifact, not a replacement for frozen A, B1 or B2.

## Purpose / authorization

Owner authorized creating a separate B2 package and copying it to the attached
`C2M_FLASH_B` card. Static stock U-Boot analysis found identical-token update
suppression before `bootcmd`; see
`docs/reverse/C2M_SD_UPGRADE_VERSION_GATE.md`. The previously asserted
loss-of-SD-trigger/UART-only diagnosis was incorrect.

Frozen A and B2 share `20230803193750`. This package uses `20261012000001`
in BOTH the sidecar and inner script, so it differs under the audited equality
gate. The date-shaped token is an update identity, not a new product/runtime
version or proof of what the camera currently stores.

## Exact authorized changes vs frozen B2

- Inner script token bytes `[0x21, 0x2f)` only (14 ASCII digits, same width).
- `sysVer.txt`: `sysVer 20261012000001\nend\n`, 26 bytes, LF and no BOM.
- `minieye_firmware.md5`: derived from the complete modified inner image.
- All 11 partition-load payloads, offsets, sizes, command lines except token,
  padding, unknown tail, vendor TAR headers/trailer and `adas_upgrade.sh` are
  unchanged. The B2 customer filesystem and `c2m-idle 0.2.0-sdlog1` are unchanged.

Original `build_candidates.py` and `candidate_diff.py` protections were NOT
weakened. The original diff appropriately rejects this separate artifact for
`outer sysVer.txt changed (protected)`. It is not an original `ALLOWLIST-OK`
Candidate B build: a separate byte-exact version-only proof covers the explicit
owner-authorized exception.

## Artifact identities

| Artifact | Size (bytes) | SHA256 |
|---|---:|---|
| Frozen B2 TAR (source) | 58,368,000 | `96b8bcda65c8a95281513931dd6b92d7db789383a5d689e398892df5e80dd03f` |
| `EN_ENHANCE_IDLE_B2_SD_V20261012000001.tar` | 58,368,000 | `1ad8c90585ff9af2028fdc772460cfabb5b12d5279a254575d14bf71a8efadd0` |
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `625839398ddbfab96e749f0a500107134acd940045f1d251b8890fd0a7978807` |
| `sysVer.txt` | 26 | `60dae902c570de78e77cb1cde4855ede8aaf12680209ebebe68063f055c88a8a` |
| `minieye_firmware.md5` | 66 | `64f6354cde880accbdcbf7fafe3d7c95297523669305a02580c24bf597941afe` |
| `adas_upgrade.sh` | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

Inner MD5: `42df84cdea9ac0e57d6b10b504567d81`.

`/customer/c2m/c2m-idle` was re-extracted from the new package locally:
7,184 bytes, SHA256
`fbc2c452e5c475ac9d4aa03bd8fbf670d99cbbdee847b196bb0d2ad3c62c451c`.
It contains `0.2.0-sdlog1` and passes the dynamic ELF gate (ARMv7-A hard-float,
VFPv3-D16, no SIMD attribute, stock loader, max GLIBC need 2.4). This is host
inspection, not proof of device execution.

## Local proof / preservation

Files are private/gitignored at
`build/b2-sd-v20261012000001/`:

- `frozen-b2/`: four source files pinned to published frozen B2 hashes.
- `frozen-a-recovery/`: four stock A files, independently read from the pinned
  original TAR and verified after copying; not a camera flash backup.
- `EN_ENHANCE_IDLE_B2_FROZEN.tar`: reconstructed from the preserved card files;
  its complete TAR SHA256 matches the published pipeline B2 TAR.
- `payload/`: four new flash files; TAR above contains exactly the same bytes.
- `contract_frozen_b2.json`, `contract_reversion_b2.json`: independently
  re-derived using `package_contract.py`.
- `independent_version_only_proof.json`: 105 checks, including direct whole
  suffix equality and all 11 partition-load hashes, offsets and sizes. TAR
  differences confined to the two token spans and the 32 MD5 hex characters.
- `reversion_tool_proof.json`: the fail-closed repository tool independently
  reproduced the staged files and final on-card bytes 4/4.
- `validate_frozen_b2_deep.json`, `validate_reversion_deep.json`: both `VALID`,
  33 checks each; protected stock cardv/ADAS re-extracted and verified.
- `candidate_frozen_b2_diff.json`: original B2 `ALLOWLIST-OK` vs stock EN.
- `candidate_reversion_diff.json`: expected original-contract rejection,
  confined to the authorized protected sidecar change.
- `media_identity.json`, `on_card_verification.json`: identified SD and final
  read-back evidence. Reports must not be interpreted as a device flash verdict.

Host synthetic checks: `tools/fw/test_reversion_sd_package.py` passes 36
unittests; `tests/test_candidate_b.py` and `tests/test_firmware_pipeline.py`
also pass. The new unittest suite is wired into product CI and local CI.
No remote CI result is claimed for these uncommitted follow-up changes.

## SD preparation result

Identified card: disk 1, SMI USB DISK, USB/MBR, serial `SM3350`, 33,201,061,888
physical bytes. Partition 1 at offset 1,048,576, type 0x0C (`FAT32 XINT13`),
33,200,013,312 bytes, drive `D:`, FAT32, label `C2M_FLASH_B`.

**No formatting performed.** All four files were staged, flushed and hash
verified before replacement; `sysVer.txt` was published last. Final read-back
matched all four SHA256 values above; Windows volume cache was flushed and
the volume is NOT dirty. Root contains exactly the four flash files plus the
existing `System Volume Information` directory. No TAR or evidence files were
copied to the card. Use Windows **Safely Remove/Eject** before removal.

## Post-flash report (2026-10-13)

Owner reports successful flash, a longer upgrade operation, and UTOUR
requesting setup again. Flash card was returned to laptop; recording card is
in C2M. Read-only flash-card capture found the four prepared payloads intact
(4/4 SHA256), no `.bak` or `C2M_DIAG`, and NOT dirty. These unchanged flash-card
files are not U-Boot completion markers. The setup prompt does not establish
calibration/license loss or normal operation after setup.

Local evidence: `C2M_HW_20261012/03_candidate_B/acceptance.md` and
`postflash_card_readback_20261013.json`. Flash is OPERATOR-REPORTED SUCCESS.
This result is consistent with the version-gate diagnosis, not a captured boot
message from the earlier failed attempt.

Subsequent recording-card read-back found 24 normal MP4 files but no
`C2M_DIAG`. Re-extraction from this package proves its launch command is after
`exit $?` in `rcInsDriver.sh`, so that configured path cannot start the daemon.
Runtime acceptance is **BLOCKED_PACKAGE_DEFECT**, not merely pending a longer
wait. See `CANDIDATE_B2_HOOK_FAILURE.md`. No replacement image was generated
by this investigation.

## Manual flash / acceptance (historical; do not repeat defective package)

**STOP:** the launch-hook defect above blocks runtime acceptance for this
artifact. The following steps describe the prior field trial, not authorization
to reflash it. A separately reviewed repair package is needed first.

1. Stationary, with stable power: power off, insert the prepared flash card,
   power on, and wait for upgrade/reboot and live view. Do not interrupt an
   upgrade. If it immediately boots normally again, report that observation;
   do not format or blindly repeat.
2. A format prompt on the FLASH card is not an upgrade verdict; decline it.
   It was observed after the accepted A run too.
3. After upgrade is complete, power off and swap to the normal recording card.
   Cold boot with that card present, check recording and stock functions, and
   leave powered for at least one 300-second heartbeat interval.
4. Power off before moving the recording card to the laptop. Read back
   `C2M_DIAG/boot-*.log`; a START line containing `v=0.2.0-sdlog1` and a heartbeat
   are runtime evidence. Missing logs are inconclusive: SD mount availability
   when the B2 hook starts remains an open device condition.
5. Continue the full A/B2 checklist, cold boots x5 and 24-hour soak. App product
   version may remain stock; the new token alone does not prove B2 is running.

This remains a full firmware flash with the original destructive upgrade
commands and power-loss risk, not a metadata-only device write. Retain frozen
A recovery files. An unequal original A token passes the audited equality
check after the candidate token is saved, but this is NOT proof of successful
recovery or environment persistence on the actual camera.
