# D4 RAM shadow — prepared and stock-QEMU verified — 2026-10-16

**ARM/QEMU gates passed; one finite hardware run completed with valid DB and
transient GPS freshness loss. No production deployment or advisory acceptance.**

`fw/d4/main.c` has a compile-time `C2M_D4_SHADOW_OBSERVE` variant using the same
checked loader/core with fixed target paths,10 one-second samples and a30-second
monotonic bound. The ordinary production build path keeps its existing CLI and
status-writer behavior; the shadow build excludes the status writer entirely.
Build script: `fw/d4/build_shadow_arm.sh`. Host tests:
`tests/test_d4_shadow.py` (Windows4 passed/5 Linux fixture tests skipped;
all9 tests subsequently passed in Linux CI, including the five runtime fixtures).

The shipping shadow CLI has no fixture path override and no `--serve`. Test-only
path constants require an explicit host-test macro and are not used in the ARM
build. Output labels simulated delivery, actual completed sample count and
completion reason. Signals/errors cannot report full success. The stock-QEMU
shipping-binary no-DB/sentinel gate and exact report-to-binary packaging gate
passed in manual CI `38836577606` on source `a7cf680` (observer v1).
Later v2 same-poll diagnostics are tracked separately in
`D4_SHADOW_DIAGNOSTICS_20261016.md`; v1 build/hardware proof must not be
attributed to the changed v2 binary. V2 subsequently passed its own gates
and completed one notified live run with10/10 valid reads, fresh at2–10;
see `D4_SHADOW_V2_HARDWARE_20261016.md`. The earlier stale cause remains unknown.

## Verified delivery and evidence limits

- General Linux/Chrome CI `38836575675`: PASS on the same source
  `a7cf6800a0982e9b91876e3814b242c138b33a9b`.
- ARM32 hard-float/stock loader/GLIBC<=2.30 ELF gates, pure self-test/help and
  exact shipping shadow `--observe` runtime under the pinned stock libraries:
  PASS. Ten samples completed naturally; a synthetic existing D4 status
  sentinel retained its bytes/inode/mtime; no shared status writer existed.
- Shipping-binary QEMU case deliberately had no private DB/GPS. It proves the
  finite no-DB/no-write path, not positive private DB handling on hardware.
  Host Linux fixtures separately prove advancing GPS/raw100-200, frozen GPS,
  DB replacement invalidation, symlink rejection and interrupted sample count.
- Private delivery:
  `deliverables/20261016-ram-debug-r38836577606/ram-bundle`, vault commit
  `1e9afc802301a14f2a78c7a89b018293f380a9b5`.
- Retrieved to `build/ram-debug-r38836577606/ram-bundle/`; local **4/4** binary
  hashes, source pins, stock ARM ELF headers/loader and report-to-shadow hash
  binding verified. The manifest/SHA256SUMS match separately downloaded CI
  evidence. Public artifact audit:18 explicitly allowlisted text/report files,
  no binaries, vendor library bytes, private DB or key material.
- Shadow size26984 bytes, SHA-256
  `273ca45f544a241d2051c9689e55e3c2a7c552ba40e6ef5bfaaa8cf38fcbecb7`.
- Bundle manifest SHA-256
  `f5d404e97078cace07ace6abb50d78808b7befd19c95623f7b40be33ddb9ad05`.
- Local proof: `build/ram-debug-r38836577606/local_readback.json`.

No camera access occurred for this build or retrieval. Subsequently the owner
reconnected for the notified finite test: the exact shadow completed10 samples,
loaded the valid12708-record DB, and was cleaned without replacing the installed
producer. Freshness was `[0,1,1,1,1,1,1,0,0,1]`; samples8–9 were stale with cause
unresolved. See `D4_SHADOW_HARDWARE_20261016.md`; this is not stable-runtime,
real-advisory or beep acceptance.

The laptop-local reviewed runner `build/run_d4_shadow_reviewed.py` was used;
its default mode checks only the pinned bundle. Hardware path reverified
identity/hash/self-test, external timeout/nice, cleanup and unchanged installed
producer. It uploaded only the shadow, never `c2m-signs`. Owner confirmed stock
functions remained normal. **Hardware access is stopped. Notify owner before
any new reconnection/query/test; no automated reboot or session extension.**

The corrected GPS observer decoded10/10 actual samples and acquired freshness
on hardware. The complete corrected producer passed stock-QEMU synthetic
runtime but has not been run on hardware. Installed D4 remains unchanged.

## Why not replace the installed process immediately?

The current production producer is an unbounded `--serve` process writing
`/tmp/c2m_d4_status`. Starting a second default producer races that file;
stopping/restarting the existing process would alter live web advisory behavior
and complicate rollback. Neither is necessary to validate the next stage.

## Preferred next diagnostic: finite shadow, private output

The implemented separate diagnostic executable is not another daemon:

- Fixed package DB `/customer/c2m/signs-d4.bin` and existing regular GPS file
  `/tmp/car_info`; no UART, device node, vendor IPC, network, audio or M4 output.
- Reuse the actual D4 database/ancestry/identity checks and pure advisory core;
  do not copy a looser DB loader just to make the shadow work.
- Use the proven corrected GPS decoder and advancing-second freshness gate.
- Fixed finite sample count/time with mandatory monotonic hard bound and
  low priority. No detached process or service hook.
- Output only safe summary fields on stdout: DB validity/count (no records),
  state/freshness, code, distance/event counters if needed. No coordinates,
  raw GPS fields, speed/heading, private labels/IDs or DB bytes.
- Never write or rename `/tmp/c2m_d4_status`, never read/alter controller request
  files, never edit persistent config/calibration/license/recorder settings.
- Keep advisory status separate from the web page: a shadow event does not
  trigger browser beep and is not a same-road/legal-speed claim.
- Do not mark a shadow output as delivered to the production UI. Any local
  simulated-publication/cooldown semantics must be explicit in the report.

## Required host gates before target use

1. Shared loader validation remains descriptor-safe, no-follow and identical
   for production/shadow; symlink/link/mode/ownership/replacement/malformed DB
   tests prove no security downgrade or production behavior regression.
2. Synthetic advancing/frozen/regressing/invalid GPS tests, complete finite
   exit and no status-file mutation. No fixture overrides in the target
   shadow CLI.
3. Production `c2m-signs` all native/Chrome/end-to-end regressions still pass;
   existing installed binary is not touched during these tests.
4. Build shadow for stock ARM32 time32/off32/loader ABI, ELF gates and pure
   stock-QEMU tests. Private fixture runtime may use separate test-only
   injection, never exposed as target CLI or camera default-path writes.
5. Private RAM bundle exact source/hash evidence, owner stationary confirmation,
   fresh source-bound UUID/SSH host pin check and finite listener availability.
6. Run once, cleanup owned private RAM directory and confirm recorder/AP/ADAS.

## Alternative

If code sharing would require a broad production refactor, prefer a small
compile-time shadow mode of the existing `main.c` using exactly the same
loader. Keep it excluded from production build and explicitly tested as
finite/stdout-only/no-default-status-writer. Do not use production host-fixture
path overrides on the camera to bypass normal path trust assumptions.

## Acceptance limit

A stationary shadow may confirm DB validity, GPS readiness and clean lifecycle
without seeing a nearby directional sign. Absence of a sign is not a failure
and must not be forced with fabricated GPS or DB edits. Real-route applicability
and browser beep need later owner-controlled evidence; never ask a driver to
operate the phone/laptop while moving.
