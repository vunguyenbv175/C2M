# Candidate C — Vietnamese ADAS audio + TSR enable (2026-10-14)

**Status:** HOST-VALIDATED + SD READ-BACK VERIFIED + DEVICE-FLASHED
2026-10-14. Field result: VI warnings confirmed by ear (LDW/PCW/FCW group);
no startup greeting on normal boots — EXPECTED, see `audios.txt` mapping
(`calib_success` → `adas_activated.wav`, not a per-boot event). Owner chose
to keep the vendor calib sound; no custom per-boot greeting planned.

## Content vs B4 (mount-wait)

- 7 ADAS warning wavs replaced with VI donor bytes (LDW/PCW/SAG/VB/
  adas_activated/adas_fail/updating); FCW/HMW kept (byte-identical EN↔VI).
- `tlr_green_on.wav` ADDED (was md5sum-listed but absent in both EN and VI):
  Google-TTS Vietnamese "Đèn xanh", 1128 ms, PCM16/mono/24 kHz, generated
  locally, hash-pinned in the private vault.
- `md5sum.txt` refreshed for exactly the 8 touched lines; all other lines
  (incl. vendor-stale FCW/HMW/LDW lines — stock files mismatch them too, yet
  stock runs, proving `adas_checksum.sh` never gates boot) preserved.
- `audios.txt` unchanged (byte-identical EN↔VI; duration field nominal).
- Hook block extended with an idempotent TSR flag patch (decode device
  `adas.flag`, flip first `--enable_tsr=false`→`true`, rewrite both flag
  files consistently so `run.sh` sees no md5 drift; skips when absent or
  already patched). Idle daemon byte-identical (`fbc2c452…`).
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

## Flash / acceptance (pending)

Same stable-power procedure; decline format prompts. Verify in order:
1. Live view + recording + app connection normal (no regression).
2. Vietnamese warnings BY EAR: drive normally until LDW/PCW/FCW trigger, or
   wait for ADAS activation greeting (`adas_activated` in Vietnamese).
3. TSR: drive past speed-limit signs; watch app/M4 display + listen for the
   traffic-light wav. Note hit/miss/false-positive per sign.
4. Recording-card `C2M_DIAG`: START + HB expected as before (idle unchanged).
Rollback: frozen A files retained; reflash A path unchanged. TSR was vendor-
disabled for unknown reasons — treat first drives as an experiment, keep
stock expectations; any ADAS failure → report, rollback, STOP.
