# D4-debug — first owner-controlled hardware session — 2026-10-16

## Scope and acceptance state

Owner reported that D4 was flashed and the laptop joined C2M Wi-Fi. This is
**owner-reported flash plus observed authenticated SSH**, not full D4, STA,
Bluetooth, M4, audio or calibration acceptance.

Before any RAM execution or Wi-Fi change, the agent requested confirmation of
recording, stock-app live view and Vietnamese ADAS audio. Live GPS showed
nonzero vehicle speed during the initial read-only session, so the agent
explicitly told the owner not to interact while driving and stopped access.
The owner subsequently confirmed the vehicle was stationary and all original
functions were normal; only then was the bounded RAM roundtrip below run.
No interface/configuration change, Bluetooth radio activation, UART access,
warning injection or `:8080` WebSocket client was used.

Private raw evidence remains in the ignored hardware capture directory:
`C2M_HW_20261012/06_candidate_D4/live_20261016_070130/`.
Do not publish raw GPS samples, recording filenames or private assets.

## Confirmed observations

- Bound HTTP and SSH to the laptop's actual camera-facing IPv4 address, not the
  historical address. Read-only stock CGI returned the authorized exact UUID.
- HTTP `:8099/api/status` and `/api/signs` responded on the camera AP.
- SSH banner: `SSH-2.0-dropbear_2026.94`.
- First contact sent no client credential and recorded an Ed25519 host key.
  A no-key authentication attempt was rejected with `Permission denied
  (publickey)`. The observed key was pinned in the dedicated laptop-local
  `C:\Users\DrVu\.ssh\c2m_debug_known_hosts`; authenticated connections then
  required strict checking of that file and the dedicated owner key.
- Host fingerprint: `SHA256:Sp3VCG13OerdY/FIU3cftqi8h0BqLgVqM/wXHJ1pJEk`.
  `dropbearkey -y` on the camera printed the same public-key fingerprint.
  This is owner-controlled AP + verified UUID **TOFU**, not an independent
  out-of-band cryptographic verification. No host/private key bytes were read
  or copied to the laptop. The private client key was not printed or copied.
- Public-key authentication succeeded as UID/GID 0. Initial uptime was about
  six minutes; the supervisor status was `active/listening`, with a 1,200-second
  window and explicit `192.168.1.1:2222` binding. `/proc/net/tcp` independently
  showed the listener bound to that address, not wildcard.
- Private debug directories were root-owned `0700`. The runtime reports a
  missing `/home/root` when starting a shell; this did not prevent bounded
  read-only commands. No home directory/account file was modified.
- Live SHA-256 values for six files matched the exact final updater extraction:
  `dropbear`, `dropbearkey`, `c2m-debug`, `debug_boot.sh`, `libnss_files.so.2`,
  and `c2m-signs`. Private proof: `live_asset_hash_comparison.json`.
- `cardv`, `adas`, lane accelerator/postprocessor, D3 web/controller, D4 producer
  and debug supervisor were running. Front-camera recording metadata advanced
  to a new segment; the previous segment was larger in the later listing. This
  supports recording activity but proves neither finalization nor successful
  playback/decoded-video acceptance.
- The stock public FWVersion string remains the EN base version. The updater
  token is not expected to replace that string; runtime hash comparison is
  stronger evidence of the installed debug assets.

## D4 GPS blocker found

`/tmp/car_info` exists as a regular file and is being updated. Five bounded,
one-second-apart reads of only the documented `0x330..0x4ef` GPS region showed:

- Five advancing UTC seconds, RMC mask present, signal 1, fix 3;
- Nonzero finite speed and coordinates;
- The raw integer at GPS-relative offset `0x1c` took values
  `0, 100, 200, 200, 300`.

The current decoder treats that integer as hundredths and rejects values over
99 (`fw/d3/gps_snapshot.c`). D4 nevertheless reported `state=stale`,
`gps_fresh=0`, `active=0` through both SSH and HTTP. The live discrepancy is a
concrete decoder-contract blocker; its precise vendor unit/range must be
proven statically before changing validation. Do not weaken freshness checks,
normalize GPS data on the camera, or claim D4 advisories/beep work on this build.
Local investigation and replay tests can proceed without camera access.

## Stationary RAM roundtrip and listener observation

After explicit owner confirmation of stationary vehicle and healthy stock
functions:

- Created a random private `0700` directory on `/tmp` (confirmed tmpfs).
- Uploaded exactly32,768 binary bytes through SSH stdin; checked size/SHA-256.
- Wrote a reviewed tiny shell script in that private RAM directory, verified
  its SHA-256, and executed it with stock BusyBox `timeout -t 5` and `nice -n 10`.
  The script only printed a success marker, byte count and payload hash.
- Downloaded the binary through SSH stdout, compared exact bytes and SHA-256.
- A trap removed only the two test files and the directory; a separate SSH
  command confirmed cleanup. No firmware/config/card file was written.
- Private proof: `ram_roundtrip_report.json`, verdict PASS. This proves the
  exec/stdin/stdout debug path with a reviewed script, not a newly uploaded
  native ELF/ABI acceptance.
- Near the expected20-minute end of the debug window, a later source-bound
  TCP check received connection refused on2222 while the verified UUID and
  AP HTTP still responded. This is consistent with expiry, but the supervisor
  reason could not be read after shutdown, so the TCP observation alone is not
  causal expiry proof. No listener restart/extension was attempted.

## Other capabilities still unproven

- AP remains usable. STA is `unknown`, with
  `last_error=capability_missing_or_malformed`; no saved network/connection/IP.
  This is not proof that AP+STA is unsupported. The next diagnostic should be
  an isolated read-only nl80211 structural probe, not interface creation or an
  AP-to-STA switch.
- Bluetooth V2 report completed with
  `NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE`. SDIO context includes the Realtek
  device and the bundled `8821cs` module, but no kernel HCI/transport helper was
  observed. This is not proof that physical Bluetooth hardware is absent.
- M4 rendering/sign handling was not exercised. No second cardv WebSocket
  client or GPS-speed sender was attached.

## Remaining acceptance

1. Owner reports recording/app/VI ADAS normal and vehicle stationary. Specific
   normal calibration/greeting behavior and independent playback review were
   not instrumented; do not infer these from process/file metadata alone.
2. The bounded `/tmp` binary roundtrip plus reviewed shell execution and cleanup
   passed. Uploaded native ELF execution, wrong-key/password/forwarding
   negatives and causal listener expiry/AP-loss behavior remain hardware gates.
   Do not extend/restart the debug window just to keep access.
3. Prove and test the GPS subsecond contract locally; only then propose a
   stationary RAM-only evaluation. Preserve two advancing UTC seconds and
   stale/future/integrity protections.
4. Run the isolated read-only nl80211 probe while preserving AP and recording.
5. Do not promote real-route advisories, browser beep, AP+STA, Bluetooth RF or
   M4 3D speed/signs until each is actually observed.
