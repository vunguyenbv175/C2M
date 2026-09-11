# Flash release — final C2M packages (FLASH-READY / NOT YET FLASH-PROVEN)

Built by `firmware-candidateB` run `34603664629` (ubuntu-24.04, EN TAR from
the private vault with mandatory SHA gate) + independent local
re-validation. No flash/boot claim is made here.

## Source

- EN golden: `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`
  `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`
  (verified on runner `sha256sum -c` OK; local copy identical).

## Deliverables (private, NOT in this repo)

Local/private path (private vault checkout):
`D:\CODE\backups\vault-work\deliverables\20260911-r34603664629\c2m-flash\`
(SHA256SUMS.txt verified ALL-OK locally, 10/10 files.)

- `EN_REPACK_GOLDEN.tar`
  `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`
  (byte-identical to golden; inner byte-identical; deep VALID, locally
  re-validated).
- `EN_ENHANCE_IDLE.tar`
  `247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a`
- `C2M_FLASH_A/` + `C2M_FLASH_B/` (4 stock-layout files each, exact sizes
  58359832/26/66/2972; B `minieye_firmware.md5` regenerated for the B inner).
- `SHA256SUMS.txt`, `FLASH_README.txt` (A=control, B=idle-only, A-first
  flashing sequence), `BUILD_EVIDENCE/` (contracts, validations, diff,
  mutation, QEMU output, tool versions).

## Candidate B identity

- inner image: `e2746d45a80f51f0007b709bf485e9309aebc7d198efc58e458bd6480f29ff05`
- customer.es (`mkfs.ubifs` 2.2.0-1ubuntu2 output):
  `da2adbf0d1e2488e056ed90e5da2bc33425f79c83ad490ef0b20d33d0af314e0`
  (39743488 B — same LEB count as stock, content-only change in UBIFS slack)
- inserted `c2m-idle` (dynamic, 6372 B):
  `5f33cd1a594ac0437c4eda535d208a1e5e24c24f908e0c49c58e8f8122cc3c3b`
  (byte-identical across independent builds: candidateB run, isolated QEMU
  run, mutation record).
- Filesystem diff (complete): ADD dir `/c2m` (0755, 1001:1001), ADD
  `/c2m/c2m-idle` (0755, hash above), MODIFY `/wifi/rcInsDriver.sh`
  (`855705c9…` → `3ad36a60…`, append 25 B `/customer/c2m/c2m-idle &`).
  Nothing else: no-op baseline was 227/227 identical; B verify 227 + 2 added.

## Validation (all PASS)

- A deep validator: VALID (local re-run confirms).
- B deep validator: VALID, 33 checks (local re-run confirms), incl.
  cardv `344b4a3f…`, adas `0dcc6982…` re-extracted from the B image;
  kernel/rootfs/CIS/IPL/U-Boot/sysVer/adas_upgrade.sh unchanged;
  UNKNOWN tail verbatim.
- Candidate diff: ALLOWLIST-OK, delta 0, no fatload changes required.
- QEMU stock-rootfs proof (TWO runs, same binary bytes):
  isolated `prehw-qemu-stock-runtime` PASS (stdout + marker + strace with
  zero `socket(` calls) and inline chain QEMU PASS
  (`c2m-idle 0.1.0-sprint1` + marker `c2m-idle 0.1.0-sprint1`).
  Scope: stock glibc-2.30 userspace execution, not SoC/hardware boot.

## Status

`FLASH-READY / NOT YET FLASH-PROVEN`. Next: hardware checklist Phase A,
then Phase B (`docs/firmware/FLASH_HW_CHECKLIST.md`).
