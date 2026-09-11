# C2M Owner Review — FLASH-READY Sprint 1 Closeout

Date: 2026-09-12
Reviewed implementation commit: `923476df8de7c3992cb62bb987a829e7d3a72775`
Prior owner review: `docs/reviews/2026-09-12_FLASH_READY_SPRINT1_OWNER_REVIEW.md`

## Decision

**ACCEPT / CLOSE FLASH-READY SPRINT 1**

Project status remains deliberately:

`FLASH-READY / NOT YET FLASH-PROVEN`

No hardware boot or flash claim is made.

## Independent verification

GitHub Actions run `34582791778` for commit `923476d` completed successfully.

- `build-test`: PASS
- `arm-minimal`: PASS
- ELF gate executed on the clean GitHub runner and finished with:
  `ELF-GATE: OK (c2m-idle, static+tu-proof)`

The clean-runner cross build used:

- absolute GitHub workspace path for the CMake toolchain file;
- explicit Ninja generator and `ninja-build` dependency;
- `-march=armv7-a`;
- `-mfloat-abi=hard`;
- `-mfpu=vfpv3-d16`;
- static linking for the minimal idle binary.

## Findings from the requested delta

### F1 — clean-runner ARM CI

**CLOSED.**

The former CMake path/generator failure is resolved and both CI jobs are green.

### F2 — unsupported NEON assumption

**CLOSED.**

`tools/fw/arm_attributes.py` now derives the stock ABI from measured `.ARM.attributes` bytes.

Current evidence supports:

- ARMv7-A application profile;
- Thumb-2;
- VFPv3-D16 (`Tag_FP_arch=4`);
- hard-float (`Tag_ABI_VFP_args=1`, hard-float ELF flag);
- no stock evidence for `Advanced_SIMD_arch`/NEON in `cardv` or `adas`.

The build therefore no longer enables NEON.

### F3 — ELF compatibility gate

**CLOSED for offline evidence.**

The gate now verifies the expected ARM ELF class/machine/ABI/FPU contract and distinguishes static vs dynamic compatibility paths.

The static linked final binary inherits an `Advanced_SIMD_arch=1` attribute from Ubuntu static libc objects. The implementation does **not** hide this. Instead it independently gates the project translation unit and proves that the C2M-owned object itself is built VFPv3-D16 and does not carry the Advanced SIMD tag.

This is acceptable as an **offline FLASH-READY** result, but it is not proof that every reachable path in the Ubuntu static libc is safe on the physical SoC. That remains a hardware/runtime question.

Binding consequence for later firmware Candidate B:

- the static binary may be used only as a bring-up candidate with this residual risk recorded; or
- preferably, a stock-rootfs/sysroot-linked device build should be produced before final Candidate B so the daemon inherits the same userspace ABI family as the EN firmware.

Do not upgrade this residual risk to CONFIRMED compatibility before device execution.

### F4 — toolchain reproducibility wording

**CLOSED.**

Documentation now correctly says `runner-pinned + version-recorded`, not fully pinned.

## Sprint 1 deliverables accepted

The following are accepted as the offline firmware foundation:

1. EN package contract and byte accounting.
2. EXACT/no-modification round-trip builder.
3. Independent firmware validator with fail-closed negative tests.
4. `EN_REPACK_GOLDEN` Candidate A, byte-identical to the known-good EN firmware when built from the original local TAR.
5. Customer/UBI identified as the preferred enhancement layer.
6. Candidate B/C correctly withheld as recipe-only because no proven UBIFS writer exists yet.
7. Target ABI evidence grounded in stock EN binaries.
8. Minimal ARM bring-up binary and clean-runner cross-build path.
9. Product CI green.

## Candidate status

### A — EN_REPACK_GOLDEN

**OFFLINE READY.**

This is the first image to test on hardware.

Its purpose is only to validate that the repository round-trip/repack process is accepted by the physical C2M. It must not be confused with an enhanced firmware feature test.

### B — EN_ENHANCE_IDLE

**NOT BUILT / BLOCKED.**

Blockers:

- no proven UBIFS/customer writer/rebuilder yet;
- runtime execution of the minimal daemon remains unproven;
- static-libc inherited SIMD attribute remains a residual hardware risk.

### C — EN_ENHANCE_READONLY

**NOT BUILT / BLOCKED behind B.**

## Next highest-value work

The next sprint should target **Candidate B creation**, not new product features.

Order of work:

1. Build a device userspace/sysroot contract directly from the EN firmware and produce a stock-ABI-compatible minimal daemon if feasible.
2. Implement and independently validate customer UBIFS unpack -> no-op rebuild -> compare pipeline.
3. Only after no-op UBIFS rebuild is structurally proven, implement a narrowly scoped mutation that adds `/customer/c2m/c2m-idle` and the minimum startup hook.
4. Rebuild the full EN package while keeping every protected stock component unchanged except the explicitly authorized `customer.es` bytes.
5. Independently validate Candidate B and generate a complete manifest/diff proving exactly what changed.
6. Keep Candidate C blocked until Candidate B is hardware-proven.

## Binding safety rules for Sprint 2

- Preserve EN as the golden base.
- Do not touch CIS/IPL/IPL_CUST/U-Boot/kernel/rootfs/cardv/adas/models/calibration/license state.
- Do not add M4 writes, camera hooks, ADAS replacement, Road/VietMap/TPMS/AI feature work.
- Never commit vendor firmware or extracted proprietary blobs to the public repository.
- Any unsupported UBIFS rebuild or unexplained byte drift must fail closed.
- Do not call Candidate B `flash-proven` until it boots on the physical device.

## Final owner verdict

Sprint 1 achieved its intended purpose: the project now has a reproducible, validated path back to the known-good EN firmware and an evidence-grounded target ABI contract.

**Sprint 1: PASS / CLOSED.**

**Overall project: FLASH-READY / NOT YET FLASH-PROVEN.**
