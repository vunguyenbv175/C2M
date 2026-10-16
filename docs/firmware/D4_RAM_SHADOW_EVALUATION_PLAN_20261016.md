# Proposed D4 RAM shadow evaluation — 2026-10-16

**Plan only. Not implemented, built or executed by this document.**

The corrected GPS observer decoded10/10 actual samples and acquired freshness
on hardware. The complete corrected producer passed stock-QEMU synthetic
runtime but has not been run on hardware. Installed D4 remains unchanged.

## Why not replace the installed process immediately?

The current production producer is an unbounded `--serve` process writing
`/tmp/c2m_d4_status`. Starting a second default producer races that file;
stopping/restarting the existing process would alter live web advisory behavior
and complicate rollback. Neither is necessary to validate the next stage.

## Preferred next diagnostic: finite shadow, private output

Implement a separate diagnostic executable, not another daemon:

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
