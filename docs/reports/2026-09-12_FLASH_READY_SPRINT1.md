# FLASH-READY Sprint 1 — offline firmware pipeline (FLASH-READY / NOT YET FLASH-PROVEN)

Golden baseline: `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`
SHA-256 `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`
(verified at every pipeline entry point; VI never used as a parts donor).

## 1. WHAT WAS BUILT

| workstream | artifact |
|---|---|
| WS1 package contract | `tools/fw/package_contract.py` → `docs/firmware/EN_PACKAGE_CONTRACT.json` (machine) + `EN_PACKAGE_CONTRACT.md` (human): outer TAR members/order/modes/mtimes, sysVer, MD5 relation, U-Boot script + per-load offsets/lengths/shas, 0xFF gap accounting, 24 B UNKNOWN tail, partition/write map |
| WS2 round-trip builder | `tools/fw/repack_firmware.py` (EXACT-only; `--replace-payload` fails closed): 0xFF-buffer reassembly + header-preserving TAR splice → `build/EN_REPACK_GOLDEN.tar` |
| WS3 independent validator | `tools/fw/validate_firmware.py` → JSON+MD report, verdict `VALID`/`INVALID`/`INCOMPLETE_EVIDENCE`, `--deep` re-extracts cardv/adas from the candidate itself; `tests/test_firmware_pipeline.py` (synthetic, host CI) |
| WS4 injection analysis | `docs/firmware/INJECTION_ANALYSIS.md` (FILE + LINE + INTERPRETATION + CONFIDENCE per finding) |
| WS5 ABI + minimal binary | `docs/firmware/TARGET_ABI.md`, `fw/device_minimal/` (c2m_idle.c + ARM toolchain + ELF gate + CMake), CI `arm-minimal` job (HOST-CROSS-BUILT, not device-tested) |
| WS6 candidates | `docs/firmware/FLASH_CANDIDATES.md`: A built, B/C recipes only (UBIFS-write BLOCKED) |
| CI | `tests/test_firmware_pipeline.py` in product `ci.yml` + `local_ci.py`; new `arm-minimal` CI job |

## 2. WHAT WAS PROVEN

- `repack_firmware.py` on the golden TAR → `EXACT-ROUND-TRIP-OK` (report `build/repack_report.json`).
- `validate_firmware.py --deep` on `build/EN_REPACK_GOLDEN.tar` → `VALID` (33 checks).
- `validate_firmware.py` (no `--deep`) on the same file → `INCOMPLETE_EVIDENCE` (protected hashes unverified — UNKNOWN never passed off as PASS).
- Synthetic negatives: wrong-MD5 / truncated-image / modified-payload / invalid-offset-length / missing-member / unattributed-mod → all `INVALID` (rc≠0); `--replace-payload` override fails closed.
- Corruption coverage is by an INDEPENDENT tool (validator shares no code path with the builder beyond the contract schema).
- Product CI stays green-clean-checkout (synthetic only); firmware-original paths remain in manual evidence workflows + local `--evidence`.

## 3. WHAT IS BYTE-IDENTICAL

- Rebuilt outer TAR == original TAR (SHA-256 identical, `3a703522…`).
- Rebuilt inner `SigmastarUpgradeSD_SSC8838G.bin` == original (SHA-256 `e3f24432…`, MD5 `8e69fe45…` matching `minieye_firmware.md5`).
- All 4 outer members byte-identical (inner/sysVer/md5/adas_upgrade.sh).
- Re-extracted protected components from the REBUILT package: cardv `344b4a3f…`, adas `0dcc6982…` (match golden).
- U-Boot script bytes + all 11 payload slices + 0xFF pads + UNKNOWN tail preserved.

## 4. WHAT IS ONLY STRUCTURALLY EQUIVALENT

- Nothing in candidate A: the splice preserves even the 512 B TAR headers and 1536 trailing zero bytes, so there are ZERO remaining metadata differences to normalize. (Documented for the record: a from-scratch python-tarfile rebuild WOULD differ in `ustar` magic/version + chksum — payload-irrelevant — which is why the builder splices instead of regenerating.)
- Candidate A inner layout is PROVEN byte-identical, not merely equivalent.

## 5. TARGET ABI FINDINGS

- 32-bit LE ARM EXEC (`EM_ARM=0x28`), hard-float EABI (`/lib/ld-linux-armhf.so.3`), glibc 2.30, app-profile ARMv7 + Thumb-2 + VFP (`.ARM.attributes` `Tag_CPU_arch=0x0A`, profile `A`), compilers GCC 9.1.0 (+ Linaro 4.9.4 in adas libs), kernel 4.9.227 (uImage + modules).
- Minimum build assumption: `-march=armv7-a -mfloat-abi=hard -mfpu=neon`; soft-float/armv6 UNSUPPORTED.
- Minimal binary contract: start → print → best-effort `/tmp/c2m_idle.marker` → sleep; no socket/M4/camera/ADAS/config. CI asserts ELF class/machine only.

## 6. SAFEST INJECTION POINT

- Layer: **customer / UBI layer** (`ubi0:customer`, 80 MB, RW, persistent, executable — stock `adas_service.sh`/`mutualism` already run from it).
- Files: NEW `/customer/c2m/c2m-idle` (+ libs); hook: ONE appended line `/customer/c2m/c2m-idle &` in `/customer/wifi/rcInsDriver.sh` (executed by stock `demo.sh:99-101` after cardv start; no integrity self-check covers it).
- Zero-modification auto-start is NOT proven (no drop-in dir; full 118-line `demo.sh` read). Rootfs/`cardv`/`adas`/kernel/bootloader/calibration are REJECTED.
- Watchdogs: `minieye_daemon.sh` (stall/thermal reboot) and `adas_guard.sh` (3 s adas restart) are both blind to an extra idle process (file-content proven; hardware timing UNKNOWN). `sbin/watchdog` launcher: UNKNOWN.

## 7. GENERATED FLASH CANDIDATES / RECIPES

- **A. EN_REPACK_GOLDEN** — BUILT (`build/EN_REPACK_GOLDEN.tar`, gitignored; rebuild via §1 recipe). Purpose: prove packaging on hardware later.
- **B. EN_ENHANCE_IDLE** — RECIPE ONLY (BLOCKED: no UBIFS writer in repo; do not hand-assemble UBIFS).
- **C. EN_ENHANCE_READONLY** — RECIPE ONLY, conditional on B + hardware timing proof.

## 8. NEGATIVE TESTS

`tests/test_firmware_pipeline.py` (host, synthetic, in product CI):
clean→`INCOMPLETE_EVIDENCE`(rc≠0) / wrong-MD5→`INVALID` / truncated→`INVALID` /
modified-payload→`INVALID` (attributed to payload-sha row) / invalid-offset-length→`INVALID` /
missing-member→`INVALID` / `--replace-payload`→fail-closed rc≠0.
Result: OK.

## 9. WHAT REMAINS UNKNOWN

- 24 B tail past `oneed_cust` end (`12345678\n# File Partitio`, same shape in EN+VI): preserved verbatim, meaning UNKNOWN.
- Outer TAR `ustar  ` magic/version encoding origin (payload-irrelevant).
- Whether U-Boot pre-validates inner MD5 (script itself does not per-payload-check).
- SoC stepping/FPU beyond attribute bytes; kernel config/DT; NAND geometry beyond `mtdparts`.
- Hardware watchdog launcher; `mutualism`→`adas` launch handoff detail (run.sh runs `./mutualism`; adas exec chain below that is not fully traced — irrelevant to idle daemon but noted).
- glibc-forward-compat of runner-built ARM binary against on-device `ld-2.30` (only `printf/sleep/fopen` used to minimize risk).

## 10. HARDWARE TESTS STILL REQUIRED (in order)

1. Flash A on a bench unit via the stock SD-card path; confirm boot + `sysVer` + recording/ADAS nominal.
2. Capture `demo.sh` boot log timing around `rcInsDriver.sh` (hook latency window).
3. Deploy B (once a UBIFS writer exists): confirm `c2m-idle` starts, marker appears, stock recording/ADAS/Wi-Fi unaffected across 3 cold boots.
4. Read-only C polling soak: confirm no `minieye_daemon.sh` stall reboot over 24 h.
5. Only then: any observation deeper than idle.

## 11. RISKS

- No hardware for ~2 weeks: all boot/flash claims are explicitly NOT made.
- No UBIFS writer: any B/C image not built via a real writer is fabrication — refused.
- Runner glibc newer than device 2.30: mitigated by minimal symbol use, NOT eliminated.
- Hook edit, however small, is still a stock-file change: must be re-validated byte-for-byte on hardware (config backup path in `adas_upgrade.sh` is the model).
- Bricking risk if anyone touches CIS/IPL/U-Boot/kernel/rootfs — forbidden without separate justification.

## 12. NEXT HIGHEST-VALUE TASK

1. Implement or vendor a real UBIFS writer (with its own round-trip proof) so candidate B becomes buildable WITHOUT speculation; 2. in parallel, prepare the bench flash procedure + log-capture checklist for candidate A so day-1 hardware time is flash time, not tooling time. Do NOT start feature work (RoadIntelligence/VietMap/TPMS/Web/M4-semantics) before these two.
