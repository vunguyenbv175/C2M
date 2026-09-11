# Owner Review — C2M Pre-Hardware Bring-Up Pack V1

Reviewed commit: `dc3047e6ca75aa89d1bf62d12d397bc44e4942de`

## Verdict

**PARTIAL — good preparation pack, but not yet safe to freeze as HARDWARE-DAY READY.**

Candidate A/B remain frozen: the reviewed commit is exactly one commit ahead of `38c0923...` and changes only new bring-up docs/scripts plus `.gitignore`; no frozen release artifact is modified.

The runbooks, capture split, A–H operator card, M4/IPU/SCL passive phases, toolchain request card, and explicit manual-flash policy are directionally accepted.

## Findings

### F1 — HIGH — gate orchestrator is not fail-closed

`tools/device/c2m_hw_day.sh next` simply returns the first gate whose status is `NOT_RUN` or `UNKNOWN`. It does not evaluate prerequisite dependencies or automatic stop conditions.

Example: after `recovery_ready=FAIL`, `next` can still suggest `candidate_a_pass`. Likewise Candidate A/B/IPU failures do not automatically block downstream gates.

Required fix:
- encode prerequisite dependencies;
- `next` must return `STOP/BLOCKED` when any blocking prerequisite is FAIL/PARTIAL/UNKNOWN as appropriate;
- at minimum enforce recovery→A→B→EN→VI→A-H and SAFE→COEXIST;
- explicit fatal stop states (boot loop/panic/thermal/media instability) must block all later stages.

### F2 — HIGH — IPU smoke stub can produce a false-success exit

`tools/device/c2m-ipu-smoke/main.cpp` does not call `MI_SYS_Init`, `MI_IPU_CreateDevice`, `MI_IPU_CreateCHN`, `MI_IPU_Invoke`, or cleanup. With `C2M_IPU_HAVE_VENDOR_HEADERS` defined, `--single-invoke` only prints the intended call order and returns `0`.

The RUNBOOK currently presents that command as the real BENCH_ONLY SAFE smoke and defines PASS from MI return codes, tensor descriptors, output checksum and latency that the binary cannot produce.

Also `mi_ipu_compat.hpp` has the real vendor includes commented out, so the build flag does not actually prove header/API compatibility.

Required fix before hardware day:
- either implement the real vendor-backed smoke only after the matching SDK is supplied;
- or, for the pre-hardware pack, hard-refuse `--single-invoke` with a nonzero `NOT_IMPLEMENTED/SDK_BLOCKED` exit in all builds;
- never return 0 for a non-executed Invoke;
- update RUNBOOK to mark SAFE/COEXIST as `BLOCKED_TOOLCHAIN` until the real implementation exists;
- include real vendor headers only in the private SDK build path once available;
- add `<cstdlib>` or avoid `std::atoi` portability ambiguity.

### F3 — MEDIUM — gate state mutates the tracked template, not the evidence-day copy

`c2m_hw_day.sh record` writes directly to `docs/hardware/C2M_HARDWARE_DAY_GATES.json`, while `init_hardware_day_dir.sh` only copies an initial snapshot to `00_manifest/GATES.start.json`.

Required fix:
- treat `docs/hardware/C2M_HARDWARE_DAY_GATES.json` as immutable template;
- initialize `C2M_HW_<date>/00_manifest/GATES.current.json`;
- status/next/record operate on the active hardware-day copy (explicit `C2M_HW_ROOT` or argument);
- preserve `GATES.start.json` as immutable initial state.

### F4 — LOW — runtime capture hash manifest is not recursive

`run_c2m_runtime_capture.sh` hashes `capture_dir/*`; nested `proc_<pid>_*` files are listed by `FILELIST.txt` but not included in SHA256SUMS.

Required fix: generate a deterministic recursive hash manifest over all regular files, excluding the checksum file itself while it is being generated.

## Accepted points

- No automatic flash path was added.
- Candidate A/B hashes and manual SD-content rule are preserved.
- Existing ADAS collector remains configuration-read-only; wrapper writes only capture output.
- A–H classifier preserves UNKNOWN semantics.
- M4 L3/L4 remain blocked.
- Passive IPU/SCL topology capture is correctly separated from active experiments.
- No Candidate C, model weights, SDK archive, or feature implementation was added.

## Closeout gate

One focused fix commit is sufficient. Do not expand scope.

After F1–F4 are fixed and host syntax/JSON/diff checks pass, this pack can be re-reviewed for **PASS / PRE-HARDWARE READY**.
