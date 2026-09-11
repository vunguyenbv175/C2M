# Sprint 2 fix response — F1–F3 closed with a REAL Linux chain

Chain run: `firmware-candidateB` #34599624120 (ubuntu-24.04, real EN TAR):
**GREEN end-to-end.** Product CI `c2m-ci` #34599623748: GREEN
(build-test, arm-dyn, arm-minimal).

## F1 — usable execution path (FIXED)

- Private vault `vunguyenbv175/c2m-firmware-vault` (one file: the original
  EN TAR, unmodified) + read-only deploy key (`c2m-candidateB-readonly`) +
  repo secret `FIRMWARE_VAULT_KEY`. The job clones over SSH, verifies
  `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`
  (`sha256sum -c`, fail-closed — observed `OK` in the log), then deletes key
  material. No firmware committed; artifacts are JSON/MD/TXT only
  (explicit path list, verified in the uploaded artifact set).
- Runbook: `docs/firmware/CANDIDATEB_RUNBOOK.md` (hosted dispatch +
  canonical local-Linux command list + self-hosted option).
- Two real bugs this exposed and fixed: missing system-liblzo2 fallback
  (runner has no helper binary) and missing `work/` dir for version logging.

## F2 — `/c2m` directory allowlist (FIXED)

- `mutate_customer.py` records `added: [/c2m (dir 0755 uid/gid 1001),
  /c2m/c2m-idle (reg 0755)]` + hook append (25 bytes); `mkdir` mode enforced
  explicitly (umask-independent).
- `verify_b_manifest.py` validates added DIRECTORIES by type/mode/uid/gid
  with no SHA requirement. Real-Linux result: `verdict OK, 227 checked,
  added [/c2m, /c2m/c2m-idle]`, zero violations.
- Regressions in `tests/test_candidate_b.py` (all green): allowlist without
  `/c2m` → BLOCK (`UNEXPECTED-PATHS`); extra dir → BLOCK; correct → PASS.

## F3 — hardened `_start` (FIXED)

- Rewritten against upstream glibc 2.30 `sysdeps/arm/start.S` (non-PIC):
  `fp/lr=0`, `pop{a2}`/`mov a3,sp`, stack `[fini,NULL rtld(a1 PRESERVED),
  stack_end]`, 8-aligned at the call (`-4+12=+8`), `.fnstart/.cantunwind/
  .fnend`, `.eabi_attribute 24/25` + v7/VFPv3-D16/VFP-args (no SIMD),
  `.note.GNU-stack`, abort fallback, GLIBC_2.4 pins in-object.
- One measured surprise handled honestly: the linker drops the note section
  (observed via readelf on the real `.o`/binary), so the gate now asserts
  the **PT_GNU_STACK segment** (present + RW, X clear — what the kernel
  enforces) with `-Wl,-z,noexecstack` on both toolchains. Real-binary gate:
  `ELF-GATE: OK (c2m-idle, dynamic)`; disassembly confirms
  `pop{r1}/push{r2}/push{r0}/push{r3}` + `bl __libc_start_main@GLIBC_2.4`.
- `test_startup_abi.py` (16 source-contract checks) + CI disassembly step.

## Real-chain results (run 34599624120)

| gate | result |
|---|---|
| vault fetch + EN SHA verify | OK |
| carve (inner `e3f24432…`) | OK |
| P1 no-op `mkfs.ubifs` + manifest compare | MANIFEST-OK, 227/227 identical |
| P0 dynamic idle + ELF gate | OK (NEEDED `[libc.so.6]`, max `GLIBC_2.4`) |
| P2 mutate + rebuilt verify | OK (227 + 2 added, hook sha recorded) |
| A repack + `--deep` | byte-identical golden, VALID |
| B assemble + `--deep` | **VALID (33 checks)** |
| candidate diff | **ALLOWLIST-OK, delta 0** |

Exact tool versions: `mtd-utils 1:2.2.0-1ubuntu2`
(`mkfs.ubifs` sha `66b202d3b7901eedda9dd2b4b442bccc2d967b1f90a1cd0c702c33c3026967f1`),
`gcc-arm-linux-gnueabihf 4:13.2.0-7ubuntu1`, `liblzo2-dev 2.10-2build4`,
runner `ubuntu-24.04`.

Candidate-B hashes:
- `EN_ENHANCE_IDLE.tar`: `31d6f62d4fafdd9a317e868691a98f1f6a12ae0edcd282eca4cf28db7a93ecec`
- inner: `f378dddc2c1ebd8683ab4b7d624927f8100dddc163910ca8be07c9e83453f36e`
- customer_B.es (`mkfs.ubifs` output): `6627cca79b32f0fab17913de50a7f993812ba73c086e308b007c1ade1bfa0be2` (39743488 B = same LEB count, content-only change in existing slack)
- idle binary (dynamic, 6372 B): `5f33cd1a594ac0437c4eda535d208a1e5e24c24f908e0c49c58e8f8122cc3c3b`
- no-op image (reference): `aca9866d10689dd7391bad941caa809c2fc2d69ad0b75feb6a3fa3732c9e91e9`

Semantic diff (complete, nothing else):
- ADD dir `/c2m` (0755, 1001:1001); ADD `/c2m/c2m-idle` (0755, hash above);
  MODIFY `/wifi/rcInsDriver.sh` (`855705c9…` → `3ad36a60…`, append 25 B
  `/customer/c2m/c2m-idle &`); script fatload lines changed: none (same
  sizes/offsets — delta 0); UNKNOWN tail identical; every other payload
  hash-identical.
- Protected: cardv `344b4a3f…` PASS, adas `0dcc6982…` PASS (re-extracted
  from the B image itself).

## Remaining hardware-only unknowns

`_start` runtime behaviour; hook boot-timing; `minieye_daemon` 24 h soak;
`mkfs` free-space layout vs stock (semantic-equal, byte-different by design);
watchdog behaviour. Procedure: `docs/firmware/FLASH_HW_CHECKLIST.md`
(Phase A first). No flash/boot claim is made here.
