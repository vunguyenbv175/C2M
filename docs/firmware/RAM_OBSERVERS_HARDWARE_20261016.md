# RAM-only observers — hardware evidence, 2026-10-16

## Scope

Owner instructed continuing after the RAM-only/stationary plan. A fresh boot
was observed (uptime about192 seconds); laptop source IPv4 was rediscovered
and all requests bound to the current camera-facing address. Exact authorized
stock UUID and existing dedicated SSH host pin matched. No unattended reboot,
listener restart/extension, flash, firmware/config/card write or AP/STA change.

Private evidence directory:
`C2M_HW_20261012/06_candidate_D4/ram_20261016_080327/`.
Raw GPS supporting data and recording filenames stay private. Do not publish
them with this report. A single GPS sample reported near-zero speed, supporting
the prior stationary context; this alone is not proof that a vehicle is parked.

## Exact bundle and execution discipline

Used the already verified private bundle from CI `38831681720`, source
`291cc3ed89a718e073104912918d0925cba02c0c`. Manifest pin and all binary hashes
were checked locally again before access. This is not the installed firmware.

| Executed native ARM binary | SHA-256 |
| --- | --- |
| `c2m-gps-probe` | `9e5b8cca747b6be889822673a3e99485f99c3f9d7b0c7e99465a6c88bdfd3628` |
| `c2m-nlprobe` | `d4130a78e3d798fa901cffc6ef7e373b649677ad7909091eafad5e4be0393d15` |

Each upload used a fresh random private0700 directory on confirmed tmpfs
`/tmp`, checked length/SHA-256 before execute permission, then pure on-target
self-test before observation. Runs used stock `timeout -t 10` and `nice -n 10`.
Traps deleted only exact created files/directories; successful commands
independently checked path absence before printing cleanup verification.
The extra dump/split-dump upload was also private, size/hash-checked and cleaned.
No new native executable remained running in the final process inventory.

The included updated `c2m-signs` binary was **not uploaded or executed**. The
installed `/customer/c2m/c2m-signs` hash remained
`761b6ab98e59da15fedf65883d6cb5f95ac66319a45aba1648fbd078f90361c0`, with the
same producer PID before/after. There were never two status writers.

## GPS result: corrected reader observed live freshness

The finite GPS observer sampled the existing regular `/tmp/car_info` file
10 times at500ms intervals. It does not open a UART, emit vendor IPC, print
location/speed/heading/UTC, or write a status file.

- On-target pure self-test: PASS.
- Decode results: **10/10 OK**.
- Freshness: `[0,0,1,1,1,1,1,1,1,1]` — two initial warmup polls, then8 fresh
  observations. Final freshness was1.
- Exit0, cleanup verified.

This proves execution of the exact corrected ARM decoder/freshness observer on
hardware. It does **not** prove updated D4 producer behavior, database/road
applicability, a real-route advisory or browser beep. The installed old D4 was
briefly `ready` at preflight, then `stale` later; that is consistent with the
known raw-subsecond guard defect, not evidence that it repaired itself.

## Wi-Fi result: no usable combination advertisement

- On-target pure self-test: PASS.
- Fixed `wlan0` GET_INTERFACE: ifindex2, phy0, iftype3(AP),5180MHz.
- Single GET_WIPHY: one reply,32 top attrs, `INTERFACE_COMBINATIONS` explicitly
  present with **zero payload bytes**. Summary `stage=absent`,
  `detail=combos_empty_absent`, zero parsed combinations.
- Ordinary GET_WIPHY dump:6 replies, DONE received; same zero-byte combination
  attribute; no parsed combination. Exit0 and cleanup verified.
- Explicit split dump:59 replies, DONE received, but bounded text output
  truncated (`stage=truncated`,200-line/8192-byte budget). Its zero count is
  **not a complete absence proof** and must not overrule the truncation marker.
- Source version text still says `linux_live_validated=no`; that is a compile-
  time label, not dynamically rewritten by a successful individual hardware
  run. The exact live modes/results above are the actual evidence.

D3 remained `sta_supported=unknown`,
`last_error=capability_missing_or_malformed`. The new observation resolves the
specific reason behind this generic error: single/ordinary dump responses
contain an empty capability list, not a proven AP+STA combination. Do not
infer physical/driver impossibility or switch off AP to try STA. No VIF,
scan, association, supplicant, DHCP, route, firewall or module change was made.

## Passive driver context

- Installed module `/customer/wifi/lib/8821cs.ko` SHA-256:
  `81323242c6fa1e60296921395063a2124ed2a8af330ac5568cfa5e20d80734cc`.
- Only interface names `lo`, `usb0`, `wlan0` were exposed.
- Listed module parameter names and the driver proc-directory name only;
  no parameter writes or potentially state-changing proc handlers were read.
  Generic parameter names such as `if2name` or `rtw_btcoex_enable` do not prove
  usable concurrency/Bluetooth hardware.
- Static review of already local exact module bytes may proceed without
  camera access; do not use a generic Realtek source tree as target proof.

## Health and remaining work

Final AP HTTP returned `ap_active=true`; SSH listener remained in its normal
finite window. Recording status was1, new video segment filenames/metadata
advanced, and stock `cardv`, ADAS and lane workers were present. This supports
continued operation but is not decoded-video/audio/calibration acceptance.
No audio/warning/M4 control or second cardv `:8080` observer was used. After
the probes and final read-only checks, the owner explicitly confirmed that
app/live view, recording and Vietnamese ADAS were still normal. Camera access
was stopped before local driver/source analysis.

Next tasks:

1. Source now distinguishes `capability_combinations_empty` from
   `capability_combinations_unadvertised`, keeping both UNKNOWN and blocked;
   this diagnostic clarification is not installed on the camera and does not
   make an AP+STA combination valid.
2. Finish exact-driver static concurrency analysis; AP+STA remains unproven.
3. Any updated producer test needs a separate implementation/build/runtime
   gate. Prefer finite shadow output in a
   private RAM path/stdout; never two producers writing the shared D4 status,
   no stopping recorder/ADAS and no weakening production path checks. A plan
   only is recorded in `D4_RAM_SHADOW_EVALUATION_PLAN_20261016.md`; no shadow
   producer is implemented or run by this session.
4. Real-route D4 advisories/beep, Bluetooth RF and M4 3D speed/sign rendering
   remain unaccepted. Notify owner before another hardware session.
