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
6. Build a manifest binding source commit, input source hashes, binary sizes
   and SHA-256s; publish only the exact RAM-only bundle to the private vault.
7. Retrieve that exact private bundle on the owner laptop and verify every
   hash/ELF header before asking for a new stationary camera session.

Source and fixture tests are not radio or physical-device acceptance. The
Linux compile path of the Wi-Fi probe is not a live AP+STA demonstration.
The prior32KiB SSH script roundtrip is not proof of new native ELF execution.

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

Preparation in progress. No target hardware was accessed for this work and
no updated ARM binary has yet been uploaded to the camera. CI run and exact
private delivery pins will be recorded after the gates actually pass.
