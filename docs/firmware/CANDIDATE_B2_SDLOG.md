# Candidate B2 — EN + c2m-idle with SD diagnostics (0.2.0-sdlog1)

**Date:** 2026-10-12. **Status:** IMPLEMENTED + HOST-TESTED, NOT device-tested.
Frozen B1 (`EN_ENHANCE_IDLE.tar` `247e9a82…`, idle `0.1.0-sprint1`) is UNCHANGED
and remains the reference. B2 is a separate, owner-authorized variant for one
reason: without USB data or a device shell, B1's `/tmp` marker is unobservable,
so B1 acceptance cannot be completed on this bench.

## Why B2 exists

- C2M Type-C exposes no USB data on the tested host/cable (no enumeration:
  no mass storage, no serial, no RNDIS). HOST observation only.
- Stock app Wi-Fi API (see `docs/reverse/APK_UTOUR_GO_WIFI_API_V1.md`) has NO
  endpoint for arbitrary file read or process listing — CONFIRMED absence.
- B1's marker proves nothing by itself (written once, no heartbeat) and cannot
  be retrieved without a shell.
- B2 adds a best-effort diag log on the SD card so evidence can be collected
  by powering off, moving the card to a PC reader, and hashing the log dir.

## Exact delta vs B1 (source only, same mutation pipeline)

| Item | B1 (frozen) | B2 (this variant) |
|---|---|---|
| `fw/device_minimal/c2m_idle.c` | print version, write `/tmp` marker, sleep 60s | + best-effort SD diag (START + heartbeat) |
| `C2M_IDLE_VERSION` | `0.1.0-sprint1` | `0.2.0-sdlog1` |
| `/tmp/c2m_idle.marker` | `c2m-idle 0.1.0-sprint1` | `c2m-idle 0.2.0-sdlog1` (same path) |
| hook `/customer/wifi/rcInsDriver.sh` | append `/customer/c2m/c2m-idle &` | IDENTICAL (no change) |
| new libc symbols | — | `fread`, `mkdir`, `getpid`, `memset`, `raise` (libgcc soft-div `%`/`/` zero path), `__printf_chk`, `__fprintf_chk`, `fopen64` (Ubuntu fortify/LFS redirects, all pinned `@GLIBC_2.4` in `glibc_compat.h`; CI ELF gate proves max need ≤ 2.30). Deliberately ABSENT: `time()` (would bind `__time64@GLIBC_2.34`, missing on the 2.30 device) and stack protector (`__stack_chk_guard` binds from ld-linux itself, breaking NEEDED==[libc]; disabled via `-fno-stack-protector` — daemon has no hostile input) |
| stock services touched | none | none |

## Diag design (fail-safe, bounded, no PII)

```text
/mnt/mmc/C2M_DIAG/boot.seq      decimal counter (ring 0..7)
<dir>/boot-<i>.log              START + HB lines, 64 KB cap per file
<dir>/boot-fb.log               fallback when counter unusable
```

- START: `v pid boot(up to 8 hex of /proc/.../boot_id) uptime marker=(ok|fail)`.
- HB: every 5th 60 s wake (300 s) with uptime + sequence.
- No card / full card / read-only / missing mount → diag silently disabled;
  **daemon keeps running, stock boot never blocked** (host-proven fail-safe test).
- Ring of 8 + per-file cap + shared fallback → storage strictly bounded.
- Logged fields only: version, pid, boot-id fragment, uptime, marker result.
  Ordering across boots comes from uptime + boot counter + card file mtimes
  (no wall clock: `time()` is deliberately unused — see toolchain notes).
  No serials, keys, credentials, memory dumps.
- SD mount path `/mnt/mmc` is CONFIRMED from stock `adas_upgrade.sh`; whether
  it is mounted when `rcInsDriver.sh` runs at normal boot is UNKNOWN — the
  code degrades gracefully either way, and the first field trial will settle it.

## What B2 logs prove (and do not prove)

PROVEN by SD logs (after card read-back + hash):
```text
- exact idle version booted, per boot (START lines, boot counter)
- daemon alive at least until last HB of each boot file
- reboot count and per-boot uptime progression
- marker creation result per boot
- kill test signature: HBs stop with NO new boot file until next reboot
  (vs reboot signature: HBs stop AND a new boot file appears)
```

STILL NOT proven without a shell:
```text
- exactly-one-instance (two writers would share/overwrite ring slots;
  pid-per-boot narrows but does not close this)
- /tmp marker content (same inaccessibility as B1)
- sub-minute liveness (300 s heartbeat granularity)
```

Therefore B2 acceptance can reach STRONG-PARTIAL (liveness/version/stability
over x5 reboots + 24 h soak, all from SD), but FULL PASS still requires a
shell for the process-list and kill/no-respawn rows. Do not relabel.

## Build / hashes (to fill after CI + candidate pipeline)

- Host behavioral test: `python3 fw/device_minimal/test_sdlog.py`
  (13 checks: version/marker/START+HB/seq/cap/fail-safe) — wired into
  `ci.yml` and `tools/ci/local_ci.py`.
- ARM cross-build + ELF gate: GitHub `c2m-ci` arm-dyn job (proves glibc ≤ 2.30).
- B2 image assembly uses the SAME `firmware-candidateB.yml` pipeline with the
  new source; record the resulting TAR/inner/c2m-idle hashes here before any
  flash. Do NOT reuse B1 hashes.

```text
B2 TAR SHA256:        96b8bcda65c8a95281513931dd6b92d7db789383a5d689e398892df5e80dd03f
B2 inner SHA256:      74baee7b6e2340e38993115952ce024a5867a7e6b56e2cd96d22b6e5c011ee53
                      (C2M_FLASH_B/SigmastarUpgradeSD_SSC8838G.bin, 58,359,832 bytes)
B2 c2m-idle SHA256:   TBD-on-device (build-time work/c2m_idle.sha256 in vault
                      BUILD_EVIDENCE; exact idle bytes verified under QEMU)
B2 marker string:     c2m-idle 0.2.0-sdlog1
B2 flash siblings:    sysVer.txt 7cc07969…582e (26 B, same as A),
                      adas_upgrade.sh 0e18c91f…a05b (2972 B, same as A),
                      minieye_firmware.md5 f9d3321b…97e8a5 (66 B, B-specific)
Pipeline:             firmware-candidateB run 38203185874 (2026-10-12),
                      vault deliverables/20261012-r38203185874/c2m-flash/,
                      QEMU-RUNTIME PASS on stock glibc-2.30 userspace.
```

## Rules

- B1 frozen image is NOT rebuilt or modified by this work.
- B2 must not be flashed until its hashes are recorded above AND a dedicated
  B2 SD card is prepared + verified per `C2M_FLASH_B_RUNBOOK.md` §0 adapted
  (same 4-file layout, B2 payload).
- Single-card reuse policy applies (see `C2M_HW_20261012/01_recovery/`):
  recreate media from vault + manifest, verify on-card SHA256.
- Soak I/O impact of diag writes on recording is an open acceptance watch
  item (writes are ~25 B/300 s + START; negligible by design, confirm on bench).
