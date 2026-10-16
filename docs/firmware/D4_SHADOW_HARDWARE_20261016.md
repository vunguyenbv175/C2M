# D4 finite shadow — positive DB hardware run, 2026-10-16

## Scope and identity

Owner reconnected camera Wi-Fi after notification for the finite stationary
shadow plan. Reidentified actual source IPv4/interface, verified the exact
stock UUID and required the existing dedicated SSH host pin. A fresh camera
boot was observed at uptime about75 seconds, with the normal finite debug
window active. A bounded GPS context read reported valid signal/fix and
near-zero speed; this supports the requested parked context but does not
independently prove physical vehicle state.

No automated reboot, flash, listener restart/extension, persistent configuration
change, AP/STA switch, UART, vendor IPC/audio command or cardv `:8080` observer
was used. The agent stopped hardware access after the final checks. The owner
then explicitly reported app/live view, recording and Vietnamese ADAS still
normal.

Private evidence:
`C2M_HW_20261012/06_candidate_D4/shadow_20261016_091244/`.
Preflight GPS supporting capture:
`C2M_HW_20261012/06_candidate_D4/shadow_preflight_20261016_091230/`.
Raw GPS bytes and recording filenames remain private, not in this report.

## Exact target execution

Private RAM bundle CI `38836577606`, source
`a7cf6800a0982e9b91876e3814b242c138b33a9b`, was independently pinned again.

| Executed binary | Bytes | SHA-256 |
| --- | ---: | --- |
| `c2m-d4-shadow` | 26984 | `273ca45f544a241d2051c9689e55e3c2a7c552ba40e6ef5bfaaa8cf38fcbecb7` |
| `c2m-gps-probe` | 12144 | `a7a2fa1fa13b25b5593029db08ed1ec2a1e5ff9f47377797bca0a339c403fa80` |
| `c2m-nlprobe` | 29360 | `0b5c54d8f93a9f6ce803f2eb946f1154e9a9f614a79981b50b8062493678939f` |

Uploads were into fresh random root-private0700 tmpfs directories. Length and
SHA-256 were checked before execute permission; exact target pure self-tests
ran first. Shadow used `timeout -t 20 nice -n 10`, the other two observers
`timeout -t 10 nice -n 10`. All three executions exited0 and exact created
files/directories were deleted, with explicit cleanup verification. Shadow
cleanup was also checked in a separate source-bound SSH command.

The shadow shares the production descriptor-safe DB loader and GPS/advisory
core, but excludes the shared status writer at compile time. Its fixed CLI
contains no `--serve`, DB/GPS/status path override or shared status path. The
`c2m-signs` producer included in the bundle was not uploaded or run.

## D4 shadow result: DB valid, finite lifecycle, transient freshness loss

- On-target pure D4 core self-test: PASS.
- Fixed package DB: `db_valid=1`, count **12708**.
- Ten one-second samples completed naturally, `completion=complete`, exit0.
- Reported `status_writes=0`; every row explicitly labels
  `observer_simulation_not_production_delivery`.
- No selected advisory/event in this stationary observation (`active=0`,
  `code=none`, event counter0). Do not fabricate a nearby sign to force one.

| Samples | State | GPS fresh |
| --- | --- | --- |
| 1 | warming_up | 0 |
| 2–7 | ready | 1 |
| 8–9 | stale | 0 |
| 10 | ready | 1 |

The positive DB/loader/selection lifecycle is now observed on hardware, but the
shadow was **not continuously GPS-fresh**. The cause of samples8–9 is not
established by this capture: this shipping shadow does not report the GPS
adapter result, relative observation timing or UTC deltas. Failed/unstable
reads, invalid samples, timestamp/poll gaps, regressions or freshness delta
checks are possible code paths, not proven explanations. Do not relax
freshness/validation to hide this observation.

A separate finite GPS observer ran afterwards:10/10 decode results were `ok`,
freshness `[0,0,1,1,1,1,1,1,1,1]`. This supports later valid advancing GPS, but
it was not synchronized with the shadow and cannot explain samples8–9.
Any further diagnosis should use privacy-preserving same-poll result/reason
and relative timing, not raw coordinates/UTC/heading or a competing UART read.
The smallest useful same-poll fields are GPS adapter result, relative monotonic
poll interval, UTC-step class (`first/repeat/one_step/jump/regress`, not absolute
UTC), and the exact existing freshness rejection branch. These are a proposed
local diagnostic improvement, not new evidence explaining this run or license
to weaken the gate. A later local implementation is documented in
`D4_SHADOW_DIAGNOSTICS_20261016.md`; it adds no explanation retrospectively to
these samples. A later separately notified v2 hardware run is recorded in
`D4_SHADOW_V2_HARDWARE_20261016.md`: GPS10/10 valid, ready/fresh at2–10, no stale
reproduced. It does not establish the cause of the earlier samples. No
additional hardware test is requested by this report.

## Complete split-wiphy observation

The corrected bounded nl80211 probe completed:

- `wlan0`: AP, phy0,5180MHz.
- Split GET_WIPHY:59 target replies, no other PHY replies; DONE received.
- `parse_complete=1`, `text_truncated=0`.
- 256 top attributes, one `INTERFACE_COMBINATIONS` attribute with **zero
  payload bytes**, zero parsed combinations.
- Exit0 and private RAM cleanup verified.

This replaces the earlier truncated split capture with a complete structural
observation. The currently loaded driver does not advertise a usable
concurrent combination in these replies. It does **not** prove that physical
hardware lacks AP+STA, and it does not authorize forcing STA or reloading a
driver. Existing controller status stays UNKNOWN with no STA IP/config.

## Preservation and remaining acceptance

Read-only final hashes matched:

- Private D4 DB:
  `3bcf871956c61484858bef783187319fa5f9ae0da0c214c2c14afb1d62de411c`.
- Installed old `c2m-signs`:
  `761b6ab98e59da15fedf65883d6cb5f95ac66319a45aba1648fbd078f90361c0`.
- Installed debug supervisor:
  `45aa72969f2fb48d0e0dcef76c3325f9ecc541edcff324dadb13cea62a50e5f6`.

The same installed producer PID remained present before/after; no second
writer of `/tmp/c2m_d4_status` was started. Final process inventory contained
stock recorder/ADAS/lane workers and no surviving observer executable.
Recording status1 and advancing segment metadata were observed; AP HTTP still
reported active. Owner confirmed original functions normal after the run.
The installed old producer still reported `waiting_gps`; its source fix is
not installed by running a shadow.

**Not accepted yet:** continuously stable corrected D4 runtime, actual
nearby directional advisory, web/browser beep, any production update, AP+STA
association/DHCP/Internet, Bluetooth RF or M4 3D speed/sign rendering. A shadow
simulation is not UI delivery or road/legal-speed applicability evidence.
Notify owner before any new camera session; no need to retain Wi-Fi for local
analysis of this evidence.
