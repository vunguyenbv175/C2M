# FLASH-READY Sprint 2 — Owner closeout

Reviewed implementation SHA: `826eb33fe6922cfc2eede70598c1e8320425260e`

## Verdict

**PASS / CLOSED.**

Project state remains deliberately:

`FLASH-READY / NOT YET FLASH-PROVEN`

Candidate B is now a real Linux-built firmware candidate derived from the hash-verified EN golden input. The remaining uncertainty is hardware/runtime execution on the physical C2M, not a missing offline firmware-build step.

## Evidence independently rechecked

### Product CI

GitHub Actions `c2m-ci` run `34599901654` is SUCCESS on implementation SHA `826eb33fe6922cfc2eede70598c1e8320425260e`.

All three jobs pass:
- `build-test`
- `arm-dyn`
- `arm-minimal`

The dynamic path includes startup-disassembly evidence and the strong ELF gate.

### Real EN Linux Candidate-B chain

GitHub Actions `firmware-candidateB` run `34599624120` is SUCCESS. It ran against the real EN TAR fetched from a private read-only firmware vault and verified the required EN SHA-256 before use:

`3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`

Observed gates from the job log:

1. EN TAR SHA verification: PASS.
2. Stock customer geometry recovered: `min_io=2048`, `leb_size=126976`, `leb_cnt=313`, image size `39743488`.
3. Stock UBIFS manifest: 227 entries = 197 regular + 28 directories + 2 symlinks.
4. No-op extract/rebuild: `MANIFEST-OK`, 227/227 semantically identical.
5. No-op rebuilt image: size unchanged (`39743488`).
6. Dynamic `c2m-idle` build: ELF gate PASS with:
   - ELF32 little-endian ARM ET_EXEC
   - EABI5 hard-float
   - ARMv7-A / VFPv3-D16
   - no Advanced SIMD requirement
   - align8 needed/preserved
   - PT_GNU_STACK RW and non-executable
   - interpreter `/lib/ld-linux-armhf.so.3`
   - NEEDED = `[libc.so.6]`
   - max GLIBC need = `GLIBC_2.4` <= stock 2.30
7. Startup-object disassembly confirms the expected non-PIC glibc-2.30-style register/stack setup and call to `__libc_start_main@GLIBC_2.4`.
8. Narrow mutation manifest explicitly adds:
   - `/c2m` directory, mode 0755, uid/gid 1001
   - `/c2m/c2m-idle`, mode 0755
   and modifies only `/wifi/rcInsDriver.sh` by appending `/customer/c2m/c2m-idle &`.
9. Rebuilt Candidate-B UBIFS manifest: 229 entries, verifier verdict `OK`, zero violations.
10. Candidate A: byte-identical golden, deep VALID.
11. Candidate B: deep VALID.
12. Candidate B diff: `ALLOWLIST-OK`, customer size unchanged (`delta 0`), no fatload offset/size changes required.

### Candidate-B identity

Recorded candidate hashes from the real chain:

- `EN_ENHANCE_IDLE.tar` SHA-256:
  `31d6f62d4fafdd9a317e868691a98f1f6a12ae0edcd282eca4cf28db7a93ecec`
- inner image:
  `f378dddc2c1ebd8683ab4b7d624927f8100dddc163910ca8be07c9e83453f36e`
- rebuilt `customer_B.es`:
  `6627cca79b32f0fab17913de50a7f993812ba73c086e308b007c1ade1bfa0be2`
- dynamic `c2m-idle`:
  `5f33cd1a594ac0437c4eda535d208a1e5e24c24f908e0c49c58e8f8122cc3c3b`

Protected `cardv` and `adas` checks PASS from the Candidate-B image itself. All non-customer payloads remain hash-identical to EN golden. Unknown tail bytes remain preserved.

### Firmware confidentiality

The full-chain workflow uploads only an explicit evidence list (JSON/MD/TXT/hash data). Run `34599624120` uploaded one `candidateB-evidence` artifact of 27,068 bytes; no firmware TAR/BIN path is in the upload list.

## Findings F1-F3 disposition

### F1 — usable real-Linux path

**CLOSED.** Private read-only firmware vault + mandatory SHA gate is demonstrated in a successful GitHub-hosted Linux run. Local/self-hosted paths are documented separately.

### F2 — `/c2m` directory allowlist

**CLOSED.** The directory is now a first-class allowed addition, validated by type/mode/uid/gid, and the real UBIFS rebuild passes with exactly 229 entries.

### F3 — ARM dynamic startup contract

**CLOSED for static/offline evidence.** The implementation now follows the relevant glibc 2.30 ARM non-PIC startup contract, preserves loader `rtld_fini`, preserves call-boundary alignment, and produces a non-executable GNU stack. Runtime execution remains correctly classified as hardware/runtime evidence, not statically proven behavior.

## Minor observation, not a blocker

The successful real-chain run predates the final `mkdir -p work` housekeeping fix and logged a failed attempt to write `work/tool_versions.txt`; the command was non-fatal due to `|| true`. SHA `826eb33` adds the missing directory before version capture. This affects evidence bookkeeping only and does not alter Candidate-B image construction or validation logic.

## Binding hardware order

Do not flash Candidate B first.

1. Capture known-good stock EN baseline.
2. Flash `EN_REPACK_GOLDEN` (Candidate A).
3. Require stock-equivalent boot/camera/recording/ADAS/M4/Wi-Fi and cold reboot checks.
4. Only if A passes, flash `EN_ENHANCE_IDLE` (Candidate B).
5. Require all stock checks again plus `c2m-idle` process/marker and daemon-failure isolation.
6. Stop immediately on any regression and preserve logs/evidence before rollback.

## Remaining UNKNOWN / hardware-only

- actual execution of the custom `_start` on the C2M loader/kernel
- hook timing in the real boot sequence
- daemon process lifetime and interaction with stock watchdog behavior
- device acceptance of the semantically equivalent but byte-different rebuilt UBIFS
- long-run stability / reboot / power-cycle behavior

These are legitimate hardware gates and must not be relabeled PASS before device evidence exists.

## Owner decision

**ACCEPT `826eb33` and close FLASH-READY Sprint 2.**

Do not spend another implementation round polishing Candidate B without new runtime evidence. The highest-value hardware-independent follow-up is to execute the dynamic `c2m-idle` under QEMU user-mode against an extracted EN userspace/sysroot, plus package a bench bring-up/recovery evidence kit. This can reduce loader/startup uncertainty but does not replace physical flash proof.
