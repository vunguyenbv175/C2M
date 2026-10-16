# M4 V4 native capture — complete payloads, connection gate FAILED — 2026-10-16

## Outcome

V4 retained complete small payloads from all three proven native M4 services,
resolving V3's96B truncation and missing8080 sample. Native self-test and12s
capture exited0, exact RAM cleanup verified. **Strict unchanged-connection
preservation gate FAILED:** native26012 client port changed across pre/post.
Do not present this as an unconditional hardware/preservation PASS.

No retry, second application client, injection, firmware/status replacement,
forced reconnect or subsequent camera access followed. Owner explicitly
reported **normal original functions and no M4 flicker** after the run. That
observation does not explain the native reconnect or waive the failed gate.
V4 screen mode was not reconfirmed by the after-run question; the earlier V3
mode was3D, which is not substituted as a V4 mode timestamp.

## Exact prepared artifact

- Source `43ff7c3dd2de99d47c80c71de50bc822bd9bf90e`.
- Manual ARM workflow `38866208565`: PASS on first V4 dispatch, Linux capture
  tests8/8 + decoder tests37/37, ARM ELF/ABI/pure self-test, pinned stock QEMU
  absent-interface/sentinel, actual undefined-import no-transmit gates.
- ELF11832B SHA256:
  `842014346152e2ba21f2604b486ec643de4b80b6bcb08cc642819c6e091fccc4`.
- Manifest2585B SHA256:
  `e959fa1eb167456d547d5a5e9e344ede5e19a900fea01860ccf17dc3b4042cac`.
- Private vault commit `99bfda3fb1bcf3a36162a0100312c0271ded7a86`,
  `deliverables/20261016-ram-debug-r38866208565/m4-sniff-bundle`.
- Local byte-preserving retrieval, full source checksums, public evidence
  equality and ARM ELF gate passed before exact pins filled into separate
  local `build/run_m4_sniff_v4_reviewed.py`; V3 runner/pins preserved.

Owner confirmed newly reconnected, stationary hardware and normal original
functions before capture. Fresh source IPv4, bound UUID, strict existing host
pin, active finite SSH and required current26012+8080 legs passed. Only a fresh
private `/tmp` directory was written; executable size/hash checked before run,
`timeout -t10/25`, `nice -n10`, internal work/time/byte caps, exact cleanup.
No new application connection to8080/24012/26012 was created.

## Actual capture and postflight

Private session: `C2M_HW_20261012/07_m4/m4_sniff_v4_20261016_144723/`.

| Measurement | Observed |
| --- | --- |
| Actual elapsed |12043ms |
| Received packets / poll calls |928/946 |
| Stored data records |42, no ACK-only rows stored |
| Service8080 /24012 /26012 records |10/16/16 |
| Retained TCP payload |5646B |
| Truncated records |0 |
| Skipped non-data/nonselected / quota-skipped |469/417 |
| Record text / full lifecycle stdout |18955B /19791B |
| Completion / native exit |`time_window_complete` /0 |
| RAM cleanup |lifecycle and separate absent-directory check passed |
| Native connection preservation |FAILED for26012 peer port;8080 unchanged |
| Recorder/AP/D4 preservation |checks passed; see scope below |

Stock recorder PID640, ADAS PID2103 (wrapper2100), installed D4 PID937
unchanged in snapshots; D4 and private DB hash checks passed. Recording status1
and real recorder segment metadata advanced; AP active before/after. No media
contents or fabricated recorder markers. The same test does NOT prove
continuous operation between snapshots or corrected installed D4 deployment.

Pre/post TCP shows the required26012 client port changed; capture contains the
new client's HTTP Upgrade and subsequent ADAS binary payloads. This establishes
a native reconnect happened, not why. V3's earlier preflight also saw changing
ADAS connection availability, but it is not a controlled baseline establishing
that V4 did or did not cause this change. Do not induce another reconnect as a
test or silently accept a relaxed preservation gate.

Runner raised `Native M4 connection changed` in postflight before its automatic
decode/summary path. Original raw lifecycle evidence was retained unchanged.
Offline parsing afterward verified counts, exit0 and cleanup without changing
the failed verdict, then ran the decoder locally only. The failed gate was
NOT removed or retried to manufacture a PASS.

Raw stdout SHA256:
`fda40b20f0942c50eb0cb70e9ebd8a1cc026ff88dfa6a005cfd815ac2d1fcabe`.
Raw bytes/binaries remain private. Final evidence manifest covers22 files;
SHA256 `5cc64cc60714784998e08dfe90fe30688bbe6df4970555845f17bca9998fbb4c`.
Readback checks passed after independent offline inspection; only safe counts/
hashes are public.

## Complete application data recovered (transport proof, not rendering)

Unmodified general offline decoder parsed26 complete messages immediately:
10 JSON GPSSpeed +16 lane MessagePack messages. It correctly stopped on26012's
HTTP Upgrade prelude (`invalid_rsv` when treated as WS), not corrupted frames.

A separate explicit PRIVATE offline normalization excluded client-direction
records and removed exactly ONE complete HTTP101 header-only record at the
start of26012's server flow. It did NOT scan for frame headers, alter payloads,
fill gaps or concatenate unknown bytes. The client binary record is MASKED
(the mask bit was independently checked), not an unmasked protocol violation;
client subscriptions are excluded from the server application count. Independent
offline validation also matched the101 `Sec-WebSocket-Accept` to the captured
request via RFC6455 and checked server TCP sequence continuity after the129B
response. No key/accept values are published. The remaining server bytes yielded
**39 complete application messages**, with zero observed gaps/conflicts within
the retained per-direction runs:

| Native service | Message | Complete count | Shape result |
| --- | --- | --- | --- |
|8080 |`GPSSpeed` JSON |10 |Exact `type`/`uuid`/`speed`, types int/str/int, stock type1601; raw speed not published |
|24012 |`lane / laneWarningRes` |16 |Recovered body-field shape matches |
|26012 |`vehicle / vehicleWarning` |5 |Recovered body-field shape matches |
|26012 |`vehicle / vehicleMeasure` |4 |Recovered vector shape matches |
|26012 |`ped / pedestrians` |2 |Recovered vector shape matches |
|26012 |Additional `ped` key |2 |Unknown to decoder allowlist; redacted, not guessed |

Transport fields/header keys and WS framing are not sign widgets. Empty vectors
can match a schema without proving object inference. Numeric warning fields,
speed, UTC/frame IDs, locations and arbitrary source/unknown strings are never
printed in safe reports. No sign/limit result was established; this bounded
stationary sample cannot establish absence in the full stock stream.

## Consequence for the requested3D speed/sign implementation

**Native GPSSpeed reaches the M4 USB link.** The prior “cardv emits speed only
to a laptop observer” limit is superseded by these10 native frames, without
stealing its single-client stream. This does NOT prove the M4 application
accepts the value or has a3D speed widget; receiver handling, validity/display
policy and actual renderer/layout remain the implementation gap. Sending a
second GPSSpeed copy does not create a widget and is still semantic-DENY.

The four known ADAS screen payload families now have complete native examples,
not merely V3 prefixes. Preserve their warnings; never repurpose TTC/headway or
lane/vehicle/ped slots as a sign/limit. No actual3D speed/sign rendering,
numeric legal limit, overspeed enforcement or camera-speaker output was added.

Next work is offline receiver/layout and exact additional-key analysis from
this already captured data, plus unresolved reconnect assessment. No further
hardware run or active replay is implied by owner request to accelerate work.
