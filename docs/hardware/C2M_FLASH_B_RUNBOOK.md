# C2M Flash B Runbook — Candidate B (EN + isolated c2m-idle)

**Safety:** `FLASH` for flash; rest `READ_ONLY` / `SAFE_WRITE_OUTPUT_ONLY`.
**Freeze:** Candidate B = `EN_ENHANCE_IDLE.tar` SHA256 `247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a`. Gate: `CANDIDATE_A = PASS` else BLOCKED.

## 0. Preconditions (READ_ONLY)

```text
[ ] CANDIDATE_A = PASS (evidence in 02_candidate_A/) ................ READ_ONLY
[ ] EN_ENHANCE_IDLE.tar SHA verified (see below) ................... READ_ONLY
[ ] C2M_FLASH_B/ root holds 4 files (B minieye_firmware.md5 regenerated) READ_ONLY
[ ] RECOVERY_READY still YES ....................................... READ_ONLY
[ ] SD version eligibility reviewed (same-version gate; see §6) .. READ_ONLY
[ ] launch-hook reachability proven (existing B2 FAIL; see §8) .... READ_ONLY
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
cat /tmp/c2m_idle.marker  # expect: c2m-idle 0.1.0-sprint1 (B1 frozen; see §7 for B2)
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

## 6. SD upgrade eligibility — same-version gate (2026-10-12)

**Correction:** the earlier claim that A removed the SD trigger by changing
`bootcmd`, leaving UART as the only unblock, was incorrect. Stock EN U-Boot
checks SD upgrade eligibility separately, BEFORE it reads `bootcmd`. The
absence of SD commands in `bootcmd` does not disable this compiled-in path.
The inner upgrade script is executed by U-Boot's `sdstar`; it is not evidence
of a separate SPL upgrade trigger.

Observed on B attempts: normal boot, the four payload files remained
byte-identical on read-back, and no B2 diagnostic evidence was obtained.
These observations alone do NOT identify which bootloader branch ran.
The 59 GB card additionally had a stale FAT16 partition type byte; the
32 GB card had type 0x0C. Do not treat both as proven-compatible media.

The format prompt is not a flash verdict: it also occurred after the
successful A run (`C2M_HW_20261012/02_candidate_A/acceptance.md`, lines 12–13).
Likewise, absence of `.bak` does not prove U-Boot ignored the card; its audited
SD path does not create `.bak` files.

Static findings from the stock EN U-Boot (offsets in the decompressed binary,
linked/entry base 0x23e00000; uImage header LOAD field is 0x23f00000):
- `main_loop` calls the SD eligibility function at 0x1cd34 before fetching
  `bootcmd`. A successful eligibility result invokes `sdstar`.
- Eligibility reads environment `sysVer`, rescans MMC, and loads `sysVer.txt`.
  Only if that file load fails does it fall back to the inner image's first
  0x4000 bytes. Malformed readable metadata is rejected, not bypassed.
- `strcmp` at 0x1ced4 compares installed and candidate tokens. Equality takes
  the rejection branch with `CurVer = prvVer,no update`; a different string
  takes `ok update`. This is equality suppression, not a numeric newer-only
  comparison.
- `sdstar` sets the accepted token into environment `sysVer` and invokes
  `saveenv` before executing the script's `reset` (0x1be28–0x1be3c). These
  calls prove attempted persistence, not successful NAND saving on this unit.
- A and frozen B2 both use `20230803193750` in `sysVer.txt` and the inner
  script. If A saved that token successfully through this path, an unchanged
  B2 package is then ineligible.

**Diagnosis:** same-version suppression is the leading explanation, strongly
supported by static code plus the completed A flash. Current device
`sysVer` and a runtime rejection message have NOT been captured; MMC/FAT
load failures have not been excluded by a boot log. Do not label the failed
attempt as a directly observed version rejection.

**SD-only next step (new artifact, owner-authorized below):** retain
frozen A/B1/B2, create a separately named B2 package with a distinct, matching
14-digit token in BOTH `sysVer.txt` and the inner script, regenerate the
inner MD5, and record fresh SHA256 values. Prove all partition payloads,
load offsets/sizes, commands, tail bytes, and `adas_upgrade.sh` remain
identical to frozen B2. The existing builder/diff contract protects version
metadata; this exception must be explicit, not a silent weakening of that
contract. Do not change only one version source or hand-edit the card.

A different token makes the package eligible under the audited version
check; it does NOT guarantee successful media reads or flashing. Before a
trial, retain verified frozen A recovery files: after the distinct B token
is saved, A's original token differs and passes this equality check (media
compatibility and the rest of recovery still require verification). UART is
optional diagnostic/manual access, not established as a required unblock.

Owner authorized the separate artifact and SD write. The 2026-10-13 prepared
package, fresh hashes and read-back proof are recorded in
`docs/firmware/CANDIDATE_B2_SD_REVERSION.md`; static evidence details are in
`docs/reverse/C2M_SD_UPGRADE_VERSION_GATE.md`. Owner subsequently reported
successful manual flash (upgrade took time; UTOUR required setup again).
Post-flash flash-card read-back remains 4/4 intact; runtime logs on the
recording card and acceptance are still pending. This is not FULL PASS or
FLASH-PROVEN status.

## 7. B2 variant note (additive, does NOT change B1 above)

B2 (`0.2.0-sdlog1`, `docs/firmware/CANDIDATE_B2_SDLOG.md`) is a separate
source tree on the same frozen B1 mutation pipeline. Marker expectation for
a B2 flash is `c2m-idle 0.2.0-sdlog1`, PLUS SD diagnostics at
`<diag>/boot-<i>.log` (START + heartbeat) retrievable by card read-back.
B2 acceptance = full B1 rows above + SD-log evidence per its doc.
B2 must NOT be flashed until its hashes are recorded in
`CANDIDATE_B2_SDLOG.md` § "Build / hashes".

## 8. B2 startup defect — acceptance BLOCKED (2026-10-13)

Recording-card read-back found current recording files but no `C2M_DIAG`.
Re-extraction of the intended B2 reversion hook exposed:

```sh
exit $?
/customer/c2m/c2m-idle &
```

The configured launch is unreachable after the terminal exit. This is a
pipeline/package defect shared by the frozen B2 customer payload and its
version-only reversion. A successful flash does not prove the daemon starts.
Exact installed device bytes/process state remain uncaptured.

Do not retry the same package, format the recording card or factory-reset to
seek logs. A separate repair must move a failure-isolated background launch
to a reachable path, preserve stock exit status, pass real-hook execution
regressions and address diagnostic mount timing before another flash trial.
See `docs/firmware/CANDIDATE_B2_HOOK_FAILURE.md`. Existing B2 acceptance is
BLOCKED, not PASS / FLASH-PROVEN; no replacement package is authorized by
merely inserting the recording card for read-back.

Repair update (2026-10-14): the launch-block fix and its execution tests are
implemented (`tools/fw/mutate_customer.py`, `tests/test_candidate_b.py`; see
`docs/firmware/CANDIDATE_B2_HOOK_REPAIR.md`). The fixed firmware image itself
is NOT built yet — it requires the Linux pipeline with a fresh update token.
The inserted `C2M_FLASH_B` card still holds the defective package: do NOT
flash it.

Hookfix build update (2026-10-14): pipeline run 38409086397 GREEN, vault
image verified, fresh token `20261013000002`, card rewritten 4/4 verified
(no format). See `docs/firmware/CANDIDATE_B2_HOOKFIX_BUILD.md`. This card is
now the ONLY authorized next-flash package; the verdict above still stands
until its flash + log evidence.
