# D4 shadow v2: same-poll GPS diagnostic trace — 2026-10-16

## Purpose and scope

The prior finite hardware run (source `a7cf680`, bundle `38836577606`) loaded
the valid private DB but reported stale on samples8–9 before recovering on10.
See `D4_SHADOW_HARDWARE_20261016.md`. Its logs cannot establish the cause.
A later independent GPS observer is not a synchronized explanation.

Owner authorized continuing local diagnostic development. No new camera
connection, query, reboot, upload, radio operation or deployment is part of this
change. The installed old D4 producer remains untouched. Do not reuse the prior
hardware lease, stationary confirmation or producer-bundle pins for a new run.

## Observer v2 schema

The finite shadow still uses fixed paths,10 one-second samples,30-second
monotonic bound and stdout only, with no shared status writer or fixture CLI.
Each existing sample row adds only:

| Field | Meaning |
| --- | --- |
| `gps_result` | Exact same-poll adapter result: `ok`, `invalid`, `io_error`, `unstable`, `unsupported` (defensive default `unknown`). Parent-path rejection maps to `io_error`, as before. |
| `poll_dt_ms` | Relative interval between timestamps actually fed to the core; first row0. Includes prior work/sleep, not an absolute monotonic clock or read duration. |
| `utc_step` | Relative to the **pre-update freshness anchor**: `unavailable`, `first`, `repeat`, `one_step`, `jump`, `regress`. No absolute UTC or numeric delta. Invalid/missing samples report `unavailable`. |
| `freshness_reason` | Branch actually taken by that poll's shared freshness update, not inferred later from advisory state. |

Reasons: `no_state`, `no_sample`, `invalid_sample`, `first_anchor`,
`monotonic_regression`, `timeout`, `utc_regression`, `repeat_unconfirmed`,
`repeat_confirmed`, `zero_elapsed`, `step_tolerance`, `reference_tolerance`,
`advancing`. `repeat_confirmed` can remain fresh until the original timeout.
Reasons describe an update outcome, not necessarily a rejection; the advisory's
latched `stale` state is separate. A first anchor can therefore occur while
advisory state is still stale after a failed poll.

`gps_result=invalid` feeds NULL to the core, so its reason is `no_sample`, not
`invalid_sample`. The latter is a defensive direct-API branch for callers that
pass an invalid snapshot; it is separately covered in pure tests. DB validity
can override advisory state without changing the GPS trace.

No raw coordinates, GPS UTC, fraction, speed, course, heading, DB record IDs or
free-form vendor data are added. Existing bounded advisory fields remain.
Every row remains explicitly `observer_simulation_not_production_delivery`;
there is no web publication, browser beep or camera speaker delivery.

## No freshness-policy or production change

- `fw/d3/gps_snapshot.c` records trace strings at the **actual existing decision
  branches**, compiled only under `C2M_D4_SHADOW_OBSERVE`.
- No duplicate decision tree, second freshness update or relaxed reader check.
  Original combined branch priority is retained, including timeout before UTC
  regression, and first anchor before clock regression.
- Static trace/accessor are single-thread finite-shadow only. `main.c` consumes
  them immediately after `c2m_d4_prepare`; no intervening update occurs.
- Snapshot/freshness/advisory struct layouts are unchanged, avoiding mixed-TU
  ABI changes. Production/GPS-probe builds exclude trace storage and accessor.
- Stale remains age>=2500ms, delta tolerance3000ms; failed reads, frozen UTC,
  regressions and cumulative replay/drift remain fail-closed. Production CLI
  and D4 status format are unchanged.

## Verification and promotion gates

`tests/fixtures/gps_freshness_reference.c` freezes the pre-trace freshness body
from `f15d1b30ad0de808ec17ac1c72f7853b59a99c66`. It was independently compared
with that revision and is pinned (LF-normalized SHA-256
`335a420c33263bdb56bb86f3558f32998617f827c0480ee6773eb871e48a3c9d`).
It is test-only, never built into shipping binaries.

`tests/test_d4_shadow_trace.py` compares production, instrumented shadow and
frozen baseline return values **and every state byte** over deterministic
branch/boundary tests plus100x100 seeded polls. It checks all reason/step
vocabularies, reset/reacquisition,2500ms timeout,3000/3001ms tolerances,
cumulative drift, NULL state, invalid snapshots and UINT64_MAX clock wrapping.
It also verifies C/Python ABI sizes and absence of trace symbols/strings in
production.

Updated Linux fixtures assert the strict per-row schema and privacy/size bound,
including missing GPS, invalid raw1000 rejection, frozen GPS, advancing GPS,
DB replacement/symlink and interruption. Exact shipping ARM/QEMU gate now
requires `observer_v2` same-poll fields on the missing-DB/GPS path and unchanged
D4 status sentinel. Packaging refuses missing/wrong v2 diagnostic proof and
pins trace tests/reference source alongside runtime sources. Both general and
manual private ARM workflows run the differential tests.

Local Windows:6 trace tests PASS (10,000 seeded polls plus deterministic cases),
shadow4 passed/6 Linux-only skipped, GPS16 passed/4 Linux-only skipped,
advisory4 passed/6 Linux-only skipped; packaging rejection test PASS.
## Exact v2 ARM delivery and current CI status

Manual private ARM workflow **`38842731209` PASS**, source
`85d7f2d9189084b1d3168743c5a5f88d376c007a`:

- All10 Linux shadow tests, all6 trace tests and the packaging rejection test
  passed. This includes the invalid-GPS same-poll fixture previously skipped
  on Windows, plus the10,000 seeded differential polls.
- Stock ARM32 hard-float/loader/GLIBC gates, target pure self-test/help, corrected
  production synthetic runtime and exact shipping v2 shadow runtime passed.
- Exact v2 shadow naturally completed10 samples with strict same-poll fields
  on the **missing fixed private DB/GPS** path. Existing synthetic D4 status
  sentinel retained bytes/inode/mtime. This is not a positive DB/GPS v2 ARM
  runtime or target-hardware test; host fixtures separately cover valid data.
- Private vault commit `7a438bbf530fcd0df9af0e1e7513a5b1e309081e`, delivery
  `deliverables/20261016-ram-debug-r38842731209/ram-bundle`.
- Locally retrieved to `build/ram-debug-r38842731209/ram-bundle/`. Independent
  verifier with `--require-v2` passed4/4 binary lengths/hashes, hard-float ELF
  and stock loader, source pins, exact report/binary binding and separate CI
  manifest/SHA256SUMS comparison. Public evidence remained18 explicitly
  allowlisted text/report files; no binaries/vendor bytes/private DB/keys.
- Shadow27264 bytes, SHA-256
  `45260c0c10274c851531472e2fbf573e901f6b6dfdd751842e20644d8391893e`.
- Bundle manifest SHA-256
  `6208c66d02870e89df86816b3b51c817238a1295c3ab566863d8ea447c8fc413`.
- Local proof: `build/ram-debug-r38842731209/local_readback.json`.
- Additional native production GPS assembly comparison against `f15d1b3`
  was byte-for-byte identical after removing only the `.file` source filename
  directive (MinGW GCC16.2.0, `-O2`). This proves native compilation equivalence
  for that translation unit, not universal toolchain/hardware equivalence.

General CI `38842722272` attempt1 passed all Python tests and both ARM build
jobs, but failed during isolated Chrome startup in
`test_browser_opaque_origin_remains_rejected_without_writes`: its DevTools
loopback listener never became reachable. It did **not** run the Origin
rejection assertion in that test; the next canonical-Origin form test passed.
Browser stderr was discarded by the existing harness, so the startup cause
cannot be established from these logs. No browser or Origin policy was changed
or relaxed. Attempt2 on the exact same source **PASS** for all three jobs,
including the complete browser step. Downloaded attempt2 logs explicitly show
both opaque/null-Origin rejection-without-writes and canonical-Origin form
regressions passed; D4 browser/end-to-end commands also completed in that step.
The first startup failure remains recorded, not hidden or retroactively passed.
Local CI proof: `build/ram-debug-r38842731209/general_ci_attempt2.json` and
`general_ci_attempt2.log`.

## Prepared laptop-only runner; next-session boundary

`build/run_d4_shadow_v2_reviewed.py` is prepared separately from the historical
v1 runner so old source/run/binary/manifest pins cannot silently accept v2.
Default invocation only verifies the exact bundle locally, without importing
the live channel. Explicit hardware mode additionally requires a new notified
parked/healthy owner confirmation and freshly discovered camera-facing IPv4.
The helper rechecks UUID and strict SSH host pin before each live command.

Reviewed hardware sequence, **not executed**:

- Read-only preflight debug/AP bind, tmpfs, installed producer and private DB
  hashes, recorder/ADAS presence/status and one producer PID.
- Upload **only** the independently pinned v2 shadow into a fresh0700 random
  RAM directory; recheck byte length/hash before execution permission.
- Pure target self-test, then one fixed `--observe` under BusyBox
  `timeout -t 20 nice -n 10`; exact file/directory cleanup.
- Separate bounded cleanup/health check even on an observer error. Never retry
  the observer automatically, reopen/extend SSH or replace the producer.
- Strict stdout schema parser and separate evidence directory; no v1 output
  accepted as v2. A completed run is not stable-runtime or advisory acceptance.

Local-only bundle, parser, missing-authorization block and old-bundle rejection
checks passed. Parser used exact private QEMU stdout plus **simulated** wrapper
lifecycle markers, not hardware evidence. Proof:
`build/ram-debug-r38842731209/v2_runner_local_checks.json`.

No v2 binary has been hardware-executed and no camera access occurred during
this preparation. A passing build is not target acceptance. Notify owner
before any new stationary camera session; no flash, installed D4 change,
audio/browser beep, AP/STA operation or cardv/M4 observer is needed for it.
