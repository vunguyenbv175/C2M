# B2 mount-wait build — launch after /mnt/mmc mount (2026-10-14)

**Status:** HOST-VALIDATED + SD READ-BACK VERIFIED; manual device flash
pending. Separately authorized artifact; frozen A/B1/B2 hashes untouched.

## Why

Hookfix flash proved the repaired launch executes
(`START v=0.2.0-sdlog1 ... uptime=6` on the flash card), but recording-card
boots recorded normally with NO `C2M_DIAG`: the daemon initializes its SD
log stream once at startup, before the recording card finishes mounting.

## Provenance

- Pipeline `firmware-candidateB` run 38413770885: GREEN (all gates, incl. P2
  mutate + QEMU). `mutation.json`: `insert-before-terminal-exit`, hook
  `855705c9…` → `74bb9a58…` (+199 B); idle bytes IDENTICAL (`fbc2c452…`).
- Vault `deliverables/20261013-r38413770885/c2m-flash/` (LF enforced).
- Hook re-extracted from pipeline inner: 1132 B, `74bb9a58…`, exact
  mount-wait block; idle 7184 B, `fbc2c452…`.
- Version-only reversion (`tools/fw/reversion_sd_package.py`): token
  `20230803193750` → `20261014000001` (differs from stock AND installed
  `20261013000002`), ALLOWLIST-OK, 11/11 loads.
- Deep validation: VALID, 33 checks.

## Artifact identities (on-card, verified)

| File | Bytes | SHA256 |
|---|---:|---|
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `6d37bea87104843bc6e4c7b45a6dc525a75489c7c09ddf8eb724adc30b821038` |
| `sysVer.txt` (`sysVer 20261014000001`) | 26 | `9a054183223772b3649c9cf93820286f990ace3c7a0d828c3c7a2624488db3a9` |
| `minieye_firmware.md5` | 66 | `c1ea1ab8f44a8d4f4eeffb6bf477e8766f56e56dbcef6892dcc747869426d72e` |
| `adas_upgrade.sh` (stock) | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

TAR `EN_B4_MOUNTWAIT.tar`: `399ff090a6587aae42c6deb947ad02845b84185b74f46defb3ebd43676be2f96`.
Evidence (private): `build/b4-mountwait/` (pins, reversion proof, TAR +
contract, deep validation, hook/idle extraction reports,
`on_card_verification.json` = READY_FOR_MANUAL_FLASH_NOT_DEVICE_TESTED).

## SD preparation notes

- Same card (disk 1, SM3350, D: `C2M_FLASH_B`, FAT32 XINT13). NO format.
- Pre-write read showed the previous hookfix inner hash (`5034534d…`), NOT
  the earlier transient `1cb4ab1c…` 28-bit-flip read: the flip did not
  persist and `chkdsk` (read-only) found no filesystem problems. Treated as
  a transient read artifact; media retained under observation.
- The volume showed a stuck dirty bit after staging-dir cleanup; `chkdsk
  D: /f` (no problems found) cleared it. Four files then staged, flushed,
  replaced (sysVer last), read back 4/4 exact; volume cache flushed; final
  state NOT dirty, Healthy. Old `C2M_DIAG` (already archived) removed before
  writing; root now exactly four files + SVI.

## Flash / acceptance (pending)

Same procedure. Decline format prompts on the flash card. After live view:
recording card in, cold boot, run ≥6 min (covers one HB), power off, read
back `C2M_DIAG`: expect `START v=0.2.0-sdlog1` AND `HB` lines. Then full A/B2
rows + cold x5 + 24 h soak before any PASS claim. Full destructive flash;
retain frozen A recovery files.
