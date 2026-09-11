# Flash candidates (Sprint 2 — FLASH-READY, NOT FLASH-PROVEN)

No image here is claimed booted, flashed, or hardware-compatible. Candidate A
is a bit-exact rebuild. Candidate B's full tooling chain is implemented and
proven up to (not including) the `mkfs.ubifs` execution, which needs Linux;
C stays a recipe behind B. See INJECTION_ANALYSIS §5.

## A. EN_REPACK_GOLDEN — BUILT (bit-exact)

- Recipe: `python3 tools/fw/repack_firmware.py --tar
  firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar --contract
  docs/firmware/EN_PACKAGE_CONTRACT.json --out build/EN_REPACK_GOLDEN.tar
  --report build/repack_report.json`
- Result (reproduced): TAR SHA-256 identical to golden
  `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`;
  inner image byte-identical; all 4 members hash-identical.
- Validate: `python3 tools/fw/validate_firmware.py --tar
  build/EN_REPACK_GOLDEN.tar --contract docs/firmware/EN_PACKAGE_CONTRACT.json
  --report-json build/validate_deep.json --report-md build/validate_deep.md --deep`
  → `VALID` (33 checks incl. cardv `344b4a3f…` + adas `0dcc6982…` re-extracted).
- Purpose: proves the packaging path on hardware later (flash + boot + compare).

## B. EN_ENHANCE_IDLE — TOOLING READY, image execution pending Linux (Sprint 2)

Status: every step is implemented, fail-closed, and proven EXCEPT the
`mkfs.ubifs` execution, which needs Linux (absent on the dev box: no
WSL/Docker/mtd-utils) — run one command or dispatch
`firmware-candidateB.yml` (manual workflow) on a Linux box with the TARs.

Proven locally (no mkfs needed):
`compute_b_layout` cascade on real EN data (fake-enlarged customer):
inner reassembly + TAR + B-contract + `--deep` VALID (cardv/adas PASS) +
`candidate_diff` ALLOWLIST-OK with exactly fatload lines [8,9,10] changed.

1. Take candidate A inner bytes; carve `customer.es` (offset/size per contract).
2. (LINUX STEP) UBIFS-write: add `/c2m/c2m-idle` (product-CI `arm-dyn`
   binary: ET_EXEC, stock loader, GLIBC max 2.4, no SIMD tag) + append one
   hook line to `/wifi/rcInsDriver.sh` (image path; = `/customer/wifi/rcInsDriver.sh`
   on device): `/customer/c2m/c2m-idle &`.
3. Recompute NOTHING else: all other `customer.es` bytes, all other inner
   payloads, outer members except the rebuilt `customer.es` + regenerated
   `minieye_firmware.md5` stay untouched. (The MD5 file MUST be regenerated
   over the new inner image — flashing with a stale MD5 makes
   `adas_upgrade.sh` delete the package.)
4. Re-run `validate_firmware.py --deep` — expected verdict after a correct
   B build: package-layer rows PASS for changed members against a NEW
   B-contract, protected cardv/adas rows still PASS (untouched).
5. EXECUTION BLOCKED ON: Linux + mtd-utils (`rebuild_customer.sh`
   fail-closed driver ready). Do NOT hand-assemble UBIFS bytes.

## C. EN_ENHANCE_READONLY — RECIPE ONLY (conditional on B)

- Same as B, plus the idle daemon is allowed READ-ONLY observation:
  read `/tmp/*` status files and log to its own `/tmp/c2m/` log.
- Still forbidden: M4 transmit, ADAS replacement, camera interception,
  kernel changes, calibration/config writes, network transmission.
- Additionally BLOCKED ON: proving on hardware that read-only polling does
  not trip `minieye_daemon.sh` stall logic (static analysis says it cannot —
  it only reads — but timing proof needs the device).

## What is intentionally absent

- No CIS/IPL/U-Boot/kernel/rootfs modifications in any candidate.
- No stock `cardv`/`adas` replacement; no semantic M4 injection.
- No per-device calibration/license/config carried into any image.
- No vendor binaries committed (all built from local-only TARs).
