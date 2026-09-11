# Flash Release Owner Review — Candidate A + B

**Date:** 2026-09-11  
**Reviewed worker head:** `4e150d9ae9a70c30bee423b92f0a9134e399da30`  
**Build/publish run:** `34603664629`  
**Decision:** **PASS / RELEASE FROZEN**

## Scope

Independent owner review of the final physical-flash deliverables only. This review does not claim hardware flash, boot, or runtime proof on the real C2M.

## Candidate A

`EN_REPACK_GOLDEN.tar`

SHA-256:

`3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`

This equals the golden vendor EN TAR SHA-256 exactly. The private-vault Git blob is also the same blob as the original EN firmware. Deep validation is PASS.

**Verdict:** PASS — byte-identical stock control image.

## Candidate B

`EN_ENHANCE_IDLE.tar`

SHA-256:

`247e9a82a6a8d6972488b24a1c54456521dc170640b59556eebb1e7ac807756a`

Inner `SigmastarUpgradeSD_SSC8838G.bin`:

`e2746d45a80f51f0007b709bf485e9309aebc7d198efc58e458bd6480f29ff05`

Rebuilt `customer.es`:

`da2adbf0d1e2488e056ed90e5da2bc33425f79c83ad490ef0b20d33d0af314e0`

Inserted `c2m-idle`:

`5f33cd1a594ac0437c4eda535d208a1e5e24c24f908e0c49c58e8f8122cc3c3b`

Allowed filesystem delta only:

- ADD `/c2m` (0755, uid/gid 1001:1001)
- ADD `/c2m/c2m-idle` (0755)
- MODIFY `/wifi/rcInsDriver.sh` by appending `/customer/c2m/c2m-idle &`

`candidate_B_diff.json` verdict is `ALLOWLIST-OK`, `blocks=[]`, `customer_delta=0`.

Deep validator verdict is `VALID`; protected `cardv` and `adas` re-extract to the golden EN hashes. Kernel, rootfs, CIS, IPL, IPL_CUST, U-Boot, miservice, misc, oneed_cust, sysVer, adas_upgrade.sh and unknown tail remain protected/unchanged as required.

The exact inserted dynamic binary passes the ARM ELF gate and executes under QEMU using the stock EN rootfs/glibc-2.30 userspace, producing the expected version string and marker.

**Verdict:** PASS — minimal enhancement image, offline validated.

## Private deliverables

Canonical private vault directory:

`deliverables/20260911-r34603664629/c2m-flash/`

Contains:

- `EN_REPACK_GOLDEN.tar`
- `EN_ENHANCE_IDLE.tar`
- `C2M_FLASH_A/`
- `C2M_FLASH_B/`
- `SHA256SUMS.txt`
- `FLASH_README.txt`
- `BUILD_EVIDENCE/`

The flash folders contain exactly four stock-layout files:

- `SigmastarUpgradeSD_SSC8838G.bin`
- `sysVer.txt`
- `minieye_firmware.md5`
- `adas_upgrade.sh`

## Hardware status

Official status remains:

**FLASH-READY / NOT FLASH-PROVEN**

Do not rebuild or modify Candidate A/B before the first hardware session unless a new owner review explicitly supersedes these hashes.

Physical order is fixed:

1. Baseline current working stock EN.
2. Flash Candidate A.
3. A must pass boot/camera/recording/ADAS/M4/Wi-Fi/reboot checks.
4. Only then flash Candidate B.
5. B must repeat all stock checks and prove `c2m-idle` process + marker across repeated cold boots and soak.

No Candidate C or feature expansion belongs in these frozen A/B images.
