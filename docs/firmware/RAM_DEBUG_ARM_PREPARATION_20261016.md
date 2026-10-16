# RAM-only ARM debug preparation — 2026-10-16

Owner authorized proceeding after the first D4 hardware session. This work
prepares **RAM diagnostics**, not another updater/flash or persistent install.
The installed D4-debug producer still has the GPS subsecond-range defect.

## Bundle scope

Exactly three newly built binaries, plus manifest and SHA256SUMS:

- `c2m-signs`: corrected D4 producer, built for stock ABI. Included for a later
  independently reviewed RAM evaluation; **do not replace/restart the installed
  producer merely to run the first diagnostic**.
- `c2m-gps-probe`: fixed-path, finite read-only observer of `/tmp/car_info`, using
  the corrected production decoder/freshness gate. No coordinates, speed,
  course, private IDs, status-file writes or competing GPS UART reader.
- `c2m-nlprobe`: read-only nl80211 GET interface/wiphy structural inventory.
  No scan, interface creation/type/address change, association, DHCP, routes,
  supplicant, Bluetooth transport initialization or M4 client.

No private DB, audio, firmware image, updater trigger, credentials, client key
or server host key is part of this bundle. All binaries are owner-private in
the existing firmware vault; only explicitly allowlisted hashes, source pins,
synthetic test output and runtime proof are public CI artifacts.

## Build and gates

Manual workflow: `.github/workflows/ram-debug-arm.yml`.

1. Native Linux synthetic GPS/D4/probe/parser/privacy tests.
2. Fetch independently pinned EN TAR from private vault. Extract **only** four
   required runtime files (loader/libc/libm/libgcc_s) and their exact three
   local links, with SHA-256 pins; never extract vendor programs/licenses.
3. ARMv7-A hard-float, VFPv3-D16, no PIE, stock loader,
   explicit time32/off32 and old-glibc imports/startup. Independent ELF checks
   enforce ARM/loader/import/GLIBC<=2.30 constraints.
4. Execute each binary's pure self-test and help via actual stock loader/libc
   under QEMU. Never execute live nl80211/GPS-observe modes in CI.
5. Run the actual updated ARM D4 producer against synthetic regular DB/GPS
   fixture files under stock QEMU: raw100/200 advances acquire; fraction-only
   churn ages stale; raw1000 fails closed; raw300/999 re-acquire only after
   advancing seconds; bounded SIGTERM publishes disabled status and exits.
6. Bind the QEMU report to the exact tested D4 binary SHA-256 and recheck all
   four stock runtime pins at gate entry. Build a manifest binding source
   commit, input source hashes, binary sizes and SHA-256s; publish only the
   exact RAM-only bundle to the private vault.
7. Retrieve that exact private bundle on the owner laptop and verify every
   hash/ELF header before asking for a new stationary camera session.

Source and fixture tests are not radio or physical-device acceptance. The
Linux compile path of the Wi-Fi probe is not a live AP+STA demonstration.
The prior32KiB SSH script roundtrip is not proof of new native ELF execution.

### QEMU fixture namespace correction

Initial manual runs `38831001784` / `38831397763` passed all three ARM
cross-builds, ELF gates and pure stock-QEMU tests, but the descriptor-safe D4
producer fixture did not create a status file. Synthetic syscall trace showed
`open("/")` resolving to QEMU's prefix while `openat(rootfd,"tmp")` returned
ENOENT: the minimal library-only prefix had no `tmp`, and descriptor-relative
lookups cannot use QEMU's host-path fallback. This was a host fixture setup
failure, not evidence that the camera runtime was fixed or broken.

The gate now creates a real root-owned sticky `prefix/tmp` and private fixture
children, uses corresponding guest `/tmp/...` paths, and runs the bounded
synthetic test as root. No symlink bypass, target permissions relaxation,
`stat` ABI replacement or production source change was used to make it pass.
QEMU report success is still required; those failed runs did not publish a
bundle.

## Next hardware session (not started by this preparation)

- Notify owner before reconnection; confirm stationary vehicle and normal
  recording/app/VI ADAS. Do not reboot automatically or extend the finite
  debug window to keep access.
- Bind the actual camera-facing laptop source address, verify exact stock
  UUID, require the existing dedicated strict host pin and client key.
- Use a fresh random root-private `/tmp` directory, no predictable-path reuse
  or links. Verify uploaded length/SHA-256 before any execution; pure tests
  first, bounded `timeout -t` and `nice -n 10` thereafter.
- Run the GPS observer first without touching the installed D4 process/status.
  It can prove live decoding/freshness, not real-route advisory applicability.
- Run interface + single wiphy GET only; dump/split-dump separately only if
  needed. Preserve AP/recorder. Never bypass absent/malformed capabilities by
  forcing a VIF or AP-to-STA switch.
- Stream safe reports to the laptop; remove only exact owned RAM files via a
  trap and verify cleanup. Recheck AP/recording/ADAS. No persistent changes.
- A later producer evaluation needs a separate bounded plan to avoid two
  writers of `/tmp/c2m_d4_status`; do not run two production producers or
  weaken the path/security/freshness checks.

## Evidence status

All preparation gates passed in manual CI **`38831681720`** on source
`291cc3ed89a718e073104912918d0925cba02c0c`. General Linux/Chrome CI
`38831681303` passed on the same source. All three ARM ELF checks and
pure self-tests/help ran against the pinned stock libraries. The actual
updated ARM D4 producer passed all six synthetic runtime checks listed above.
A subsequent owner-controlled hardware session executed the two finite native
observers successfully; see `RAM_OBSERVERS_HARDWARE_20261016.md`. The updated
D4 producer itself was not uploaded or executed.

Private delivery:
`deliverables/20261016-ram-debug-r38831681720/ram-bundle`, vault commit
`c5efe860b5b33e7b11cca1dce0c5961d12dd8fe9`. Retrieved to
`build/ram-debug-r38831681720/ram-bundle/`; local readback **3/3 PASS**, plus
manifest/SHA256SUMS equality against the separately downloaded evidence.
Every source pin matches the stated source commit. The QEMU runtime report
is bound to the exact `c2m-signs` SHA-256 and all four stock runtime hashes.

| Binary | Bytes | SHA-256 |
| --- | ---: | --- |
| `c2m-signs` | 22868 | `0c5e5f08c100f5e8f734807e6f79f3d7b75245edaf20834ec2f7e1ba0c0a0512` |
| `c2m-gps-probe` | 12144 | `9e5b8cca747b6be889822673a3e99485f99c3f9d7b0c7e99465a6c88bdfd3628` |
| `c2m-nlprobe` | 25200 | `d4130a78e3d798fa901cffc6ef7e373b649677ad7909091eafad5e4be0393d15` |

Manifest SHA-256:
`1b5c9c51d85b027b03106d555d1ade79b73affd3ae52825eb0ce31701fe145cf`.
Local proof: `build/ram-debug-r38831681720/local_readback.json`.

The reviewed laptop-local helper `build/run_ram_observers_reviewed.py` was
used in the later session to execute the finite GPS and interface/single-wiphy
observers. A separate reviewed bounded command obtained dump/split-dump
responses. Every exact private RAM object was removed. The helper never ran
the included `c2m-signs` producer or changed persistent configuration. No camera
network request was made during build preparation; the later hardware session
is separately documented in `RAM_OBSERVERS_HARDWARE_20261016.md`.
