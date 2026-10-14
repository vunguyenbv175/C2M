# Candidate C — Vietnamese ADAS audio + TSR enable (2026-10-14)

**Status:** HOST-VALIDATED + SD READ-BACK VERIFIED + DEVICE-FLASHED
2026-10-14 (owner-reported). Vietnamese warning audio was heard; the owner
selected the LDW/PCW/FCW warning group, not an individual-slot test. This
is partial audio acceptance, not proof that every slot passed. FCW/HMW
assets are unchanged. No startup greeting was heard, consistent with
`audios.txt` mapping `calib_success` → `adas_activated.wav`, not a per-boot
event. Owner chose to keep vendor behavior; no custom greeting planned.
TSR, individual audio-slot completeness and long-term persistence still
require separate evidence. Read-only recording-card capture found five
cumulative diagnostic boot slots, including three older pre-C slots.
Two newer slots (associated with C by flash chronology) show `marker=ok`:
`91e64ec7` has START at uptime 7 + HB at 307; `f9150f37` has START at uptime 7.
The 10:28–10:29 recording gap aligns with the owner-confirmed deliberate
power cycle, not an unexpected reboot. Eight newer MP4 files (10:22–10:29)
opened successfully; full proxy video + AAC decoding and sparse 4K samples
passed. Daemon version is shared B/C, so logs alone cannot identify firmware.
This is useful evidence of recording health, not a 24-hour soak or full
primary-stream proof. Frozen A/B1/B2 hashes remain untouched.

## Content vs B4 (mount-wait)

- 7 ADAS warning wavs replaced with VI donor bytes (LDW/PCW/SAG/VB/
  adas_activated/adas_fail/updating); FCW/HMW kept (byte-identical EN↔VI).
- `tlr_green_on.wav` ADDED (was md5sum-listed but absent in both EN and VI):
  Google-TTS Vietnamese "Đèn xanh", 1128 ms, PCM16/mono/24 kHz, generated
  locally, hash-pinned in the private vault.
- `md5sum.txt` refreshed for exactly the 8 touched audio lines; untouched
  vendor-stale FCW/HMW entries preserved. The LDW line is refreshed in C.
  Stock running with stale entries supports a non-gating checksum path on
  observed boots, not a universal claim that the script is never used.
- `audios.txt` unchanged (byte-identical EN↔VI). Several donor wavs exceed
  listed durations; complete playback/preemption still needs testing.
- Hook block extended with a TSR flag patch: decode device `adas.flag`,
  use `sed` to replace the first `--enable_tsr=false` occurrence on EACH
  matching line, then rewrite both flag files. Repeated runs with `true`
  already present do not change it, but every boot can re-enable a later
  `false`; duplicate/comment lines are not rejected. This changes persistent
  device configuration, has no built-in backup/disable path, and does not
  prove TSR reaches the display.
  Idle daemon byte-identical (`fbc2c452…`).
- Full mechanism record: `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md`.

## Provenance

- Pipeline `firmware-candidateC` run 38505113273: GREEN (fetch-gate caught a
  SHA256SUMS path-prefix bug on the first attempt; dir-mtime verifier fix;
  final run all gates incl. P2 mutated rebuild + QEMU).
  `mutation.json`: `insert-before-terminal-exit`, `tsr_patch: true`,
  9 replaced paths.
- Vault `deliverables/20261014-r38505113273/c2m-flash/` (C2M_FLASH_C).
- Version-only reversion: token `20230803193750` → `20261014000002`
  (differs from stock AND installed `20261014000001`), ALLOWLIST-OK.
- Deep validation: VALID, 33 checks. Final-payload re-extraction: hook with
  TSR+mount-wait, 8/8 wavs match VI/TTS bytes, idle unchanged.

## Artifact identities (on-card, verified)

| File | Bytes | SHA256 |
|---|---:|---|
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `ce8969f849629a90081c80ec67792a34d7e828a41512ca35db0e8a9edd0be3b9` |
| `sysVer.txt` (`sysVer 20261014000002`) | 26 | `d5cfa1fcc07e9855206ee24db46b7a56b8cdecd5f791737e76b806fda10843d5` |
| `minieye_firmware.md5` | 66 | `db8f6c8897b0e7297cc4d2a4d099292f1281218cbf479e6f2862a46d64dbbddb` |
| `adas_upgrade.sh` (stock) | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

TAR `EN_C_VIAUDIO_TSR.tar`: `884fdbfae640f54f52f7b3f46f20440f0734445cc5277f06599e1ae80bcb9112`.
Evidence (private): `build/candidate-c/` (pins, reversion proof, TAR +
contract, deep validation, extraction reports, `on_card_verification.json`).

## SD preparation notes

Same card (disk 1, SM3350, `C2M_FLASH_B` label kept for the single-card
policy, FAT32 XINT13). NO format. Leftover B4 logs archived before removal;
a stuck dirty bit from that cleanup was cleared via `chkdsk /f` (no problems
found). Four files staged, flushed, replaced (sysVer last), read back 4/4
exact; volume cache flushed; final NOT dirty, Healthy. Root exactly four
files + SVI.

## Acceptance (flash reported complete; recording check partial PASS; remaining checks pending)

1. Live view + recording + app connection: compare with baseline; validate
   recorded clips for gaps/corruption, not only the presence of files.
2. Vietnamese audio: owner reports warning audio. Confirm individual slots
   and complete speech in safe, normal operation; do not induce hazardous
   warning scenarios or recalibrate merely to hear a prompt.
3. TSR: record speed-sign detection/display separately from traffic-light
   detection/audio. Neither output has been confirmed. Use a passenger or
   recordings for observations, never operate the app while driving.
4. Recording-card `C2M_DIAG`: START + HB observed in one newer session and
   START in the next (idle unchanged). Those logs alone do not prove ADAS
   health or recording continuity. Private capture + scoped decoding evidence
   is in `C2M_HW_20261012/04_candidate_C/acceptance.md` (gitignored); 6/6 diag
   files were byte-identical between archive and final card read.

Rollback WARNING: frozen A files are retained, but flashing A alone does
NOT guarantee config rollback: the updater preserves `/customer/minieye/
config` and C writes TSR flags there. A reviewed, separately authorized
config recovery is required; never reset calibration/license wholesale.
TSR was vendor-disabled for unknown reasons. Any recording/ADAS regression
blocks further feature work. See `C2M_NEXT_UPGRADE_PLAN_20261014.md`.
