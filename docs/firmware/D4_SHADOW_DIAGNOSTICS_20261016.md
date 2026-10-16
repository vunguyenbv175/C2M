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
Linux fixtures and exact ARM/QEMU gates must pass before preparing a new
independently pinned RAM bundle. A passing build is not target acceptance.
No further camera session is requested by this document.
