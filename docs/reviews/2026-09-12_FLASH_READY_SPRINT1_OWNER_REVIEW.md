# C2M FLASH-READY Sprint 1 — Owner Review

Date: 2026-09-12
Reviewed commit: `adf94d2062a8a8422d63e0f40a053975671cd942`
Base: `d840abc952f36604895c390a75e82597c4de983b`
Role: independent Manager/Owner review

## Decision

**ACCEPT WITH REQUIRED DELTA — do not revert the firmware pipeline, but do not mark Sprint 1 DONE yet.**

The package/repack/validation work is valuable and materially advances the project to `FLASH-READY / NOT YET FLASH-PROVEN`. Candidate A is especially useful because the rebuilt EN TAR is byte-identical to the known-good EN vendor TAR. B/C correctly remain recipes only because no trustworthy UBIFS write/rebuild path exists yet.

However two blocking issues remain before Sprint 1 can be closed:

1. GitHub Product CI is RED at `adf94d2` because `arm-minimal` fails during CMake configure.
2. The ARM ABI build contract overclaims/assumes NEON and does not yet prove runtime-loader/glibc compatibility strongly enough.

Do not start feature work until these are closed.

---

## What is accepted

### A1 — EN package contract: PASS

`tools/fw/package_contract.py` / `docs/firmware/EN_PACKAGE_CONTRACT.*` provide a useful machine-readable contract for:

- four outer TAR members;
- exact ordering and TAR metadata;
- `sysVer.txt`;
- `minieye_firmware.md5` relation to the inner image;
- U-Boot script and load regions;
- payload offsets/sizes/hashes;
- inter-payload 0xFF gaps;
- explicit UNKNOWN tail bytes;
- byte accounting.

The UNKNOWN tail remains UNKNOWN and is preserved verbatim rather than interpreted. This is correct evidence handling.

### A2 — EN_REPACK_GOLDEN: PASS for Candidate A purpose

`tools/fw/repack_firmware.py` is intentionally EXACT-only and refuses payload replacement.

For Candidate A this is the correct behavior. It reconstructs the inner byte coverage from known regions, preserves UNKNOWN bytes, requires exact identity, and then header-preserving-splices the identical inner image into the original TAR.

Important scope note: this proves an **exact golden round-trip**, not yet a general modified-firmware builder. That limitation is acceptable in Sprint 1 and must remain explicit.

### A3 — independent validator: PASS

`tools/fw/validate_firmware.py` is separate from the builder and checks package structure, MD5 relationship, script, payload bounds/hashes, gap fill, UNKNOWN tail, accounting and protected stock components in `--deep` mode.

`VALID` requires deep evidence; without `--deep` the result becomes `INCOMPLETE_EVIDENCE`. This is the desired fail-closed behavior.

### A4 — corruption tests: PASS

Synthetic negative tests for bad MD5, truncation, payload mutation, invalid offsets/lengths and missing members are appropriate product-CI tests and do not require committing vendor firmware.

### A5 — injection analysis: PASS as static recommendation

The preferred `/customer` UBI layer is a reasonable lowest-risk injection layer. The proposed hook under `/customer/wifi/rcInsDriver.sh` is HIGH-CONFIDENCE only, not device-proven, which is correctly stated.

Editing stock `cardv`, `adas`, rootfs, kernel, bootloader, calibration or license data remains rejected.

### A6 — B/C blocked rather than fabricated: PASS

`EN_ENHANCE_IDLE` and `EN_ENHANCE_READONLY` remain recipes because the repository has no trusted UBIFS writer/rebuilder. This is the correct stopping point.

---

## Blocking findings

### F1 — HIGH — Product CI is RED

GitHub Actions run #9 for `adf94d2` failed.

`build-test` passed, but `arm-minimal` failed during CMake configure.

Observed failure:

```text
Could not find toolchain file: fw/device_minimal/toolchain-armhf.cmake
CMAKE_MAKE_PROGRAM is not set
CMAKE_C_COMPILER not set
```

The workflow passes a repository-relative toolchain path while configuring with a different source/build directory. Use an unambiguous absolute path based on `${{ github.workspace }}` or an equivalent robust CMake invocation.

Also choose/install the generator explicitly (for example Ninja + `ninja-build`, or ensure Make is installed) instead of relying on runner assumptions.

Acceptance:

- `arm-minimal` is GREEN on a clean GitHub-hosted runner;
- ELF gate executes, not skipped;
- whole `c2m-ci` run is GREEN.

### F2 — HIGH — `-mfpu=neon` is not proven by current evidence

`TARGET_ABI.md` proves ARMv7 Application profile + Thumb-2 + FP attributes, but it does **not** currently prove Advanced SIMD/NEON.

The toolchain nevertheless forces:

```text
-mfpu=neon
```

Do not assume NEON merely because the CPU is ARMv7-A.

Use the most conservative FPU target directly supported by the measured EABI attributes, or provide direct evidence for NEON before enabling it.

For the current stock attribute evidence, prefer a conservative VFP target (for example VFPv3-D16 if the decoded `Tag_FP_arch=4` interpretation is independently confirmed) rather than NEON.

Update `TARGET_ABI.md` so evidence and compiler flags match exactly.

### F3 — MEDIUM/HIGH — ELF compatibility gate is too weak

`fw/device_minimal/check_elf.py` currently proves only:

- ELF magic;
- 32-bit;
- little-endian;
- ET_EXEC;
- EM_ARM.

That is not sufficient to claim a binary is suitable for the stock userspace.

The target stock rootfs uses glibc 2.30 and `/lib/ld-linux-armhf.so.3`, while the GitHub cross compiler currently links against a newer Ubuntu cross sysroot.

Strengthen the gate to verify at minimum:

- ARM EABI / hard-float flag;
- expected interpreter if dynamically linked;
- dynamic NEEDED set;
- GLIBC symbol-version requirements do not exceed the stock glibc baseline;
- FPU attributes are compatible with the evidence-derived target.

A static minimal binary may be preferable if it can be reproducibly linked and verified, because that removes the target glibc-loader version dependency. If static linking is chosen, document its tradeoffs and prove the ELF is genuinely static/no PT_INTERP rather than assuming it.

Do not claim runtime compatibility until hardware execution occurs.

### F4 — LOW — toolchain is logged, not truly pinned

The workflow comment calls the build reproducible/pinned, but `apt-get install gcc-arm-linux-gnueabihf` without an exact package version depends on the current Ubuntu repository state.

This is not a blocker for early development, but documentation should say `runner-pinned / package-version-recorded` unless the package version or container/toolchain digest is actually pinned.

---

## Gate status after this review

| Gate | Status |
|---|---|
| Package contract | PASS |
| Golden exact round-trip | PASS |
| Independent validator | PASS |
| Negative corruption tests | PASS |
| Candidate A buildability | PASS offline |
| Candidate A hardware boot | UNKNOWN — hardware required |
| Safe injection layer | HIGH-CONFIDENCE static |
| Candidate B image | BLOCKED — UBIFS writer/rebuild path absent |
| Candidate C image | BLOCKED — depends on B |
| ARM minimal source | PASS |
| ARM CI artifact | FAIL — CI RED |
| ARM runtime compatibility | PARTIAL / NOT PROVEN |
| Overall Sprint 1 | ACCEPT WITH REQUIRED DELTA |

---

## Required next worker delta

Keep the delta narrow. Do not begin UBIFS write/rebuild work yet.

1. Fix `arm-minimal` GitHub Actions path/generator so clean CI is green.
2. Remove unproven NEON assumption or prove it directly.
3. Strengthen ELF/ABI compatibility checks for hard-float, interpreter/static state, GLIBC symbol versions and FPU attributes.
4. Update `TARGET_ABI.md` and Sprint 1 report to reflect the exact evidence level.
5. Push one commit and stop for Manager review.

After this delta is green and accepted, the next major offline sprint should be **customer UBIFS rebuild research + validator**, aimed at making Candidate B buildable without touching rootfs/kernel/bootloader.

## Owner conclusion

The firmware work is now materially closer to something worth flashing. The project should keep the rule:

> A beautiful host architecture is secondary. Every offline sprint should reduce uncertainty between repository output and a firmware image that can actually boot on the physical C2M.

Candidate A is ready as an offline golden artifact/recipe, but the project is not yet ready to close FLASH-READY Sprint 1 until the ARM CI and ABI compatibility boundary are corrected.
