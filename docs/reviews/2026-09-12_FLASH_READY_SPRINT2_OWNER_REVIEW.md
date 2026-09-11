# Owner review — FLASH-READY Sprint 2

Reviewed commit: `ab58bed9fe4e774ac7b3fc2f03c6904ad3f45721`

Decision: **MAJOR PROGRESS / KEEP THE DELTA / SPRINT 2 NOT CLOSED YET**.

The stock-ABI dynamic build is a strong improvement and product CI is genuinely green. Run `34587385762` completed successfully with `build-test`, `arm-dyn`, and `arm-minimal` all PASS. The dynamic ELF gate proves ELF32/LE/ARM EABI5 hard-float, VFPv3-D16, no SIMD tag, interpreter `/lib/ld-linux-armhf.so.3`, `NEEDED=[libc.so.6]`, and max GLIBC requirement `GLIBC_2.4`.

Candidate A remains accepted. Candidate B is still **TOOLING-READY / NOT YET ACTUALLY BUILT FROM THE REAL EN CUSTOMER UBIFS ON LINUX**.

## F1 — HIGH — GitHub-hosted Candidate-B workflow has no usable firmware-input path

`.github/workflows/firmware-candidateB.yml` begins on a clean GitHub-hosted `ubuntu-24.04` runner, checks out the public repo, then requires:

`firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`

But `workflow_dispatch` as written has no upload action, download action, private-object-store input, or self-hosted preloaded workspace. A TAR sitting on the Windows development machine cannot exist on a clean hosted runner merely because the workflow was dispatched.

Therefore the workflow is logically fail-closed but operationally unusable in its current hosted-runner form.

Required resolution: choose one real supported input path and document it explicitly. Acceptable examples:

1. canonical local Linux execution; or
2. a self-hosted Linux runner with a pre-provisioned local firmware path; or
3. secure runtime download from private storage using GitHub secrets, followed by mandatory EN SHA-256 verification.

Do not commit vendor firmware to the public repo. Do not place firmware bytes in public Actions artifacts.

## F2 — HIGH — Candidate-B mutation manifest omits the new `/c2m` directory

`tools/fw/mutate_customer.py` creates:

- new directory `c2m/` via `idle.parent.mkdir(...)`;
- new regular file `/c2m/c2m-idle`;
- modified `/wifi/rcInsDriver.sh`.

However its mutation manifest lists only `/c2m/c2m-idle` in `added`.

`tools/fw/verify_b_manifest.py` computes:

`extra = set(actual) - set(stock) - set(added)`

The stock manifest contains directory entries, so after a real `mkfs.ubifs` rebuild the actual manifest will include `/c2m`; `/c2m` is not in stock and not in `added`, therefore the verifier should produce `UNEXPECTED-PATHS ['/c2m']`.

This means the full real-Linux mutated rebuild path has not yet been demonstrated end-to-end despite synthetic/dry-run Candidate-B assembly succeeding.

Required resolution:

- explicitly include the new `/c2m` directory in the mutation allowlist/manifest;
- enforce intended type/mode/uid/gid for the directory;
- ensure verifier handles added directories without requiring regular-file SHA fields;
- add a regression test proving omission of the parent directory BLOCKS and the correct two-added-path mutation PASSES.

Expected semantic UBIFS diff becomes:

- ADD directory `/c2m`;
- ADD file `/c2m/c2m-idle`;
- MODIFY `/wifi/rcInsDriver.sh` by exactly the approved launch line;
- no other filesystem semantic changes.

## F3 — MEDIUM/HIGH — custom dynamic `_start` needs startup-contract hardening before Candidate B is preferred

`fw/device_minimal/start.S` correctly avoids the host toolchain `crt1.o` GLIBC_2.34 dependency, but it currently passes `rtld_fini = NULL` and leaves the assembly object without a `.note.GNU-stack`, producing an executable-stack linker warning.

For the target baseline, compare against upstream glibc 2.30 `sysdeps/arm/start.S`: ARM startup preserves the loader-provided register value as `rtld_fini`, establishes the startup stack arguments, clears outermost frame/link state, and declares alignment attributes.

Required resolution:

- adapt the custom `_start` to the glibc-2.30 ARM startup ABI as closely as possible while retaining the deliberate old symbol-version binding;
- preserve loader-provided `rtld_fini` rather than forcing NULL;
- preserve 8-byte call-boundary alignment and test/annotate it;
- add `.note.GNU-stack` so the link no longer warns about an executable stack;
- retain `ET_EXEC`, stock interpreter, `NEEDED=[libc.so.6]`, max GLIBC <= 2.30, VFPv3-D16 hard-float, no SIMD;
- add a static/disassembly-level test for argument layout if practical.

No hardware-runtime claim is required yet.

## Accepted work — do not roll back

Keep:

- stock-compatible dynamic ELF path with GLIBC 2.4 maximum need;
- `-no-pie` ET_EXEC decision;
- VFPv3-D16/no-NEON policy;
- static binary only as fallback with inherited-libc SIMD risk documented;
- UBIFS geometry evidence and read-only manifest/extraction fixes;
- fail-closed `mkfs.ubifs` rebuild driver;
- Candidate-B package assembler and allowlist diff architecture;
- A -> B hardware checklist;
- public CI independent of proprietary firmware.

## Manager state

```
Candidate A                 READY / offline-proven
stock-ABI dynamic binary    STRONG PASS, startup hardening pending
UBIFS read/extract/geometry PASS
UBIFS no-op real Linux      NOT YET EXECUTED
UBIFS mutated real Linux    NOT YET EXECUTED; manifest parent-dir bug exists
Candidate-B assembler       PASS as tooling/dry-run
Candidate B real image      NOT YET BUILT
hardware flash/boot         NOT YET TESTED
```

## Next delta

Do not start Candidate C or feature work.

Fix only F1-F3, then execute the full **real EN TAR -> real customer.es -> no-op mkfs -> semantic compare -> mutate -> mkfs -> semantic compare -> assemble B -> deep validate -> candidate diff** chain on an actual Linux environment.

Sprint 2 closes only after that chain passes with evidence. Hardware flash remains a later gate.
