# C2M Flash B Runbook — Candidate B (EN + isolated c2m-idle)

**Safety:** `FLASH` for flash; rest `READ_ONLY` / `SAFE_WRITE_OUTPUT_ONLY`.
**Freeze:** Candidate B = `EN_ENHANCE_IDLE.tar` SHA256 `247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a`. Gate: `CANDIDATE_A = PASS` else BLOCKED.

## 0. Preconditions (READ_ONLY)

```text
[ ] CANDIDATE_A = PASS (evidence in 02_candidate_A/) ................ READ_ONLY
[ ] EN_ENHANCE_IDLE.tar SHA verified (see below) ................... READ_ONLY
[ ] C2M_FLASH_B/ root holds 4 files (B minieye_firmware.md5 regenerated) READ_ONLY
[ ] RECOVERY_READY still YES ....................................... READ_ONLY
```

```sh
sha256sum EN_ENHANCE_IDLE.tar
# expect 247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a
ls -l C2M_FLASH_B/
# expect: SigmastarUpgradeSD_SSC8838G.bin / sysVer.txt / minieye_firmware.md5 / adas_upgrade.sh
```

Card prep `SAFE_WRITE_OUTPUT_ONLY`: copy `C2M_FLASH_B/*` contents (NOT outer TAR) to FAT32 microSD root.

## 1. Flash (FLASH — manual)

Identical SD path to A. Power off → insert → power on → wait → live view → remove SD. Never interrupt. STOP on boot loop / stall reboots / panic / thermal event.

## 2. Acceptance = ALL of A + idle checks

Repeat every A system + ADAS check in `C2M_FLASH_A_RUNBOOK.md` §2 `READ_ONLY`. Any stock regression BLOCKS B and reverts unit to A (rollback §5).

Idle checks `READ_ONLY` (device shell, BusyBox):

```sh
ps | grep c2m-idle        # expect exactly one instance
cat /tmp/c2m_idle.marker  # expect: c2m-idle 0.1.0-sprint1 (B1 frozen; see §6 for B2)
```

Then `READ_ONLY` / `BENCH_ONLY` (killing idle is BENCH_ONLY, never during driving):

```text
[ ] cold reboot x5: idle present every boot + stock unaffected ..... READ_ONLY
[ ] kill c2m-idle (kill -9 <pid>): stock recorder/ADAS/display unaffected; no respawn expected (no watchdog by design) ..... BENCH_ONLY
[ ] reboot restores idle ........................................... READ_ONLY
[ ] soak (powered, recording; compare minieye.log vs A): no daemon stall reboot attributable to idle ..... READ_ONLY
```

Log to `03_candidate_B/acceptance.md` `SAFE_WRITE_OUTPUT_ONLY` (boot/activation/calibration times + B3–B7 rows).

## 3. Verdict

```text
CANDIDATE_B: PASS / FAIL / PARTIAL
```

`FLASH-PROVEN` status requires repeated successful boots (x5 + soak). One boot is NEVER sufficient.

## 4. Next allowed step

On PASS: EN runtime baseline capture (`C2M_EN_VI_ADAS_RUNTIME_RUNBOOK.md`). On FAIL/PARTIAL: rollback §5, STOP.

## 5. Rollback

Re-flash Candidate A (FLASH) via verified `C2M_FLASH_A/` SD. Do NOT edit calibration/license/config. Preserve `03_candidate_B/` evidence before rollback.

A dedicated A card is NOT required. Owner decision (2026-10-12): reuse the same microSD for A then B. Before overwriting A on the card, retain an accessible private copy of the frozen A files and SHA256 manifest on the workstation (or verify private-vault access). If rollback is needed: power off C2M, return the card to the workstation, prepare FAT32 as needed, replace the B payload with the four frozen A files, verify their on-card SHA256 values, then follow `C2M_FLASH_A_RUNBOOK.md`. This recreates the recovery media; it does not rebuild or modify Candidate A. Verify the current drive identity before any formatting or writes.

## 6. B2 variant note (additive, does NOT change B1 above)

B2 (`0.2.0-sdlog1`, `docs/firmware/CANDIDATE_B2_SDLOG.md`) is a separate
source tree on the same frozen B1 mutation pipeline. Marker expectation for
a B2 flash is `c2m-idle 0.2.0-sdlog1`, PLUS SD diagnostics at
`<diag>/boot-<i>.log` (START + heartbeat) retrievable by card read-back.
B2 acceptance = full B1 rows above + SD-log evidence per its doc.
B2 must NOT be flashed until its hashes are recorded in
`CANDIDATE_B2_SDLOG.md` § "Build / hashes".
