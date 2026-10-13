# B2 hookfix build — repaired launch, fresh update token (2026-10-14)

**Status:** HOST-VALIDATED + SD READ-BACK VERIFIED; manual device flash
pending. Separately authorized artifact; frozen A/B1/B2 hashes untouched.

## Provenance

- Pipeline `firmware-candidateB` run 38409086397 (2026-10-13/14): GREEN, all
  gates incl. P2 mutate with the insert-before-exit fix and QEMU-RUNTIME
  (`c2m-idle 0.2.0-sdlog1` stdout + marker on stock glibc-2.30).
- `mutation.json`: `hook_mode=insert-before-terminal-exit`, hook
  `855705c9…` → `aaa17d54…` (+58 B); idle bytes IDENTICAL to prior build
  (`fbc2c452…`, 7,184 B).
- Pipeline image `EN_ENHANCE_IDLE.tar`:
  `437ef1583ec02a64c091c9c6c8678255653f58e3b2265fd6dbd9dedfd854eb31`
  (vault `deliverables/20261013-r38409086397/c2m-flash/`).
- Vault files re-fetched with LF endings enforced (`core.autocrlf false` +
  re-checkout; a first fetch had CRLF-inflated text sizes and was discarded).
- Version-only reversion via committed `tools/fw/reversion_sd_package.py`:
  token `20230803193750` → `20261013000002` in BOTH sidecar and inner script
  (span `[0x21,0x2f)`), fresh MD5, verdict ALLOWLIST-OK, 11/11 loads proved.

## Artifact identities (on-card, verified)

| File | Bytes | SHA256 |
|---|---:|---|
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `5034534de945623f3e12f619e15f743b140bfc19247add24024c12070dac5c09` |
| `sysVer.txt` (`sysVer 20261013000002`) | 26 | `8e50ab13db4a33e6db6f2673badc167b1f75849a8ea01a09812071d34f2d4a26` |
| `minieye_firmware.md5` | 66 | `2802097861c6c83deea5312b8f2dc527a31850156e873b8e0e40e8762d60adb4` |
| `adas_upgrade.sh` (stock, unchanged) | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

New TAR `EN_B3_HOOKFIX.tar` SHA256:
`e9901991a29b9d8b948405bc68ab2c7d9d08abea5d6efb159a66247ae6e4183d`
(58,368,000 B). Deep validation: VALID, 33 checks (protected cardv/ADAS
re-extracted). Hook re-extracted from final inner: 991 B, `aaa17d54…`, tail
exactly the repaired block. Idle re-extracted: `fbc2c452…`, contains
`0.2.0-sdlog1`.

## SD preparation

Same identified card (disk 1, SM3350, USB/MBR, D: `C2M_FLASH_B`, FAT32
XINT13, Healthy). NO format. Four files staged, flushed and hash-verified
before replacement, `sysVer.txt` published last; final read-back 4/4 exact;
volume cache flushed; NOT dirty. Root holds exactly the four files + SVI.
Evidence: `build/b3-hookfix/` (private, gitignored): source pins, reversion
report/proof, TAR + contract, deep validation, hook/idle extraction reports,
`on_card_verification.json` (READY_FOR_MANUAL_FLASH_NOT_DEVICE_TESTED).

## Why a new token

The camera saved `20261012000001` at the last flash, so the previous package
would now be equality-skipped. `20261013000002` differs from both the stock
token and the installed one. It is an update identity, not a product version.

## Flash / acceptance (pending)

Same stationary stable-power procedure. Decline any format prompt on the
flash card. After live view: swap to the recording card, cold boot, run
≥6 minutes (covers one 300 s heartbeat), power off, read back `C2M_DIAG`
for `START v=0.2.0-sdlog1` + `HB`. Missing logs after a REACHABLE hook
would point at SD mount timing, the remaining open condition — report, do
not reflash blindly. Full A/B2 rows + cold x5 + 24 h soak still required
for any PASS claim. This remains a full destructive firmware flash; retain
frozen A recovery files.
