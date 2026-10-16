# M4 V3 finite passive hardware sample — 2026-10-16

## Result and scope

**One exact V3 observer executed, exited0 and cleaned its private RAM directory.**
Owner confirmed original app/live view, recording, Vietnamese ADAS and M4 still
normal afterward; M4 was in **3D** during the capture. No injected screen value,
warning, speed/sign command or additional application client was used.

This is a bounded **partial payload-prefix capture**, not full TCP/WS reassembly,
complete L1 schema acceptance, sign recognition or a speed/sign rendering test.
All8 data-bearing records were truncated at96B. No complete application message
was recovered. No subsequent camera access was made after postflight.

## Exact binary and reviewed execution

- Source `b40a276bf4c45c22f96d8d282c86551b4725ddba`.
- ARM workflow `38857027117`: Linux7/7, ABI gate, pure ARM self-test, stock
  QEMU absent-interface/sentinel and actual undefined-import no-transmit gates
  passed. Synthetic success-path formatter tests are separate from QEMU's
  absent-interface case.
- Schema `observer_v3`; ELF11736B SHA256:
  `58259c85dcf811174281ea2f9767d74302409efd5261021a3db95a4b41640f4e`.
- Bundle manifest SHA256:
  `fd857ebcf212aba09b03f3c5bb111dd520fd478fe2c0a6c6bd9b28dfcafaa6ff`.
- Local-only runner `build/run_m4_sniff_v3_reviewed.py` requires exact binary,
  manifest, source and run pins plus fresh owner stationary/healthy confirmation,
  bound source IPv4, UUID/SSH host pin, active finite SSH and parsed native link.
- Fresh source discovery: camera-facing Wi-Fi IPv4 verified. Dedicated SSH
  used only its key with strict existing host pin, no passwords or forwarding.
- Fresh unpredictable root-private `/tmp` directory; hash/size checked before
  execution. Pure target self-test passed. Stock `timeout -t10/25` plus
  `nice -n10`, internal time/packet/poll/output bounds and external SSH deadline.
- Raw lifecycle markers show observer exit0 and exact directory cleanup.
  Separate postflight also checked the directory was absent.
- `status_writes=0`, `transmit_bytes=0`; receive-only AF_PACKET protocol-zero
  socket bound to `usb0`, returned-ifindex checked. No promiscuous mode, extra
  `:8080`/`:26012` connection, UART/FIFO or recorder/status write.

## Initial gate correctly stopped, then current link was reverified

First preflight at13:21 (`m4_sniff_v3_20261016_132111`) had an established
camera `.123:8080` to M4 `.129` connection and an additional `.123:24012`
connection, but no established `.123:26012` at that instant. The exact runner
stopped at `Need two current native M4 legs`, **before upload or execution**.
The expected-port gate was not relaxed.

An owner-notified read-only follow-up of `netstat -anp`, `/proc/net/tcp`,
existing ADAS fd symlinks and command line established:

- `24012` listener and connection owned by the stock `adas` process.
- `26012` listener and a now-established M4 connection also owned by `adas`.
- `8080` listener and M4 connection owned by `cardv`.

The follow-up showed all three native M4 legs. A new preflight at13:22 then
passed the original `26012`+`8080` requirements. No native capture was retried
because none had started at the first failed preflight. The reason for the
initially absent `26012` connection or changed `24012` client port is unknown;
do not attribute it to the mode button, faulty ADAS or an observer connection.

This extends, not invalidates, the earlier two-leg observation: M4 can also
have an ADAS-owned `24012` connection. V3 labels `24012` records `other` because
its fixed leg names cover only26012/8080; its parser still retains ports/payload.
Do not relabel24012 as the same ScreenService or generalize topic routing from
this short sample alone.

## Finite sample

Private successful session:
`C2M_HW_20261012/07_m4/m4_sniff_v3_20261016_132219/`.

| Measurement | Observed |
| --- | --- |
| Received/output records |15/15 |
| Data-bearing / empty-payload records |8/7 |
| Records labelled ADAS26012 |13 (7 data +6 empty) |
| Records on ADAS-owned24012, labelled `other` |2 (1 data +1 empty) |
| Records on cardv8080 |0 in this sample, NOT proof of no status data |
| Retained payload bytes |768 (8×96) |
| Advertised TCP payload bytes in data records |1162 |
| Data records truncated |8/8;394 advertised bytes not retained |
| Record-text bytes |4219, within6144B budget |
| Full SSH stdout with lifecycle/preamble/summary |4887B, below8192B |
| Completion |`poll_limit_partial` |
| Native exit |0 |
| Directory cleanup |verified by lifecycle and separate postflight |

The15 poll calls were consumed by traffic-ready receives. The run is NOT a
15-second recording: preflight/postflight uptime went191.11→197.06s including
checks, upload, self-test, capture and the2s postflight wait. No finer capture
duration is claimed because V3 does not emit start/end timestamps.

Private stdout SHA256:
`aa7aed4b596468365d4cb4f8d1146e7e32f62e4f039e418d6ec1361ec4a1510c`.
Final private evidence manifest covers20 files; SHA256:
`e14c1d7559467c25053f5b55131cfa764153f58c635db221a5a743e9d6a9d82c`.
Raw payload bytes, MACs, precise coordinates, semantic numeric values, keys,
DB and binaries are not copied into public reports.

## Offline decode — useful prefix evidence, no complete message

The existing strict offline inspection of each individual prefix found:

-8 data prefixes with WS FIN/binary-shaped headers (RSV0); advertised body
 lengths106–200B exceed the92/94B captured after the WS header.
- Structural parsing of those available bytes finds an outer four-entry
 MessagePack map with `time`, `source`, `topic`, `data` (BIN), then the start of
 an inner four-entry map containing `frame_id`, `time`, `key` keys.
- Topic strings retained in the prefixes: `ped` (4 records) and `vehicle`
 (3) on26012, `lane` (1) on24012.
- None contains the full inner key value or complete inner payload, so do not
 assign a full `vehicleWarning/vehicleMeasure/pedestrians/laneWarningRes`
 schema or numeric units from this sample.

These are **partial structural observations** consistent with the static
libflow envelope, not an authenticated handshake, proven WS boundaries across
an entire TCP stream or full schema validation. Prefixes were NOT concatenated
across TCP gaps or filled with guessed bytes. No traffic on8080 was sampled,
so GPS speed/status delivery and whether/how3D displays it remain unverified.
The sample cannot prove the absence of a sign topic or receiver/widget.

## Preservation and owner confirmation

Pre/post checks passed:

- Stock `cardv` PID640, `adas` PID2089 (wrapper2085), installed D4 PID921
  unchanged. No stop/restart/replacement was commanded.
- Installed D4 executable and private DB hashes unchanged from the approved
  baseline. Installed D4 remains old; this is NOT a corrected D4 deployment.
- Recording status1 and actual recorder segment metadata advanced; only
  directory metadata was read, no media contents or fabricated markers.
- AP active before/after. All three native M4 service/peer port pairs
  (8080/24012/26012) remained the same in the pre/post snapshots. This does
  not claim continuous connectivity between snapshots.
- Owner selected **“Vẫn bình thường, M4 3D”** after the run: original functions
  normal and M4 in3D. No deliberate warning induction or moving test requested.

## Next evidence needed — offline preparation before any new hardware run

96B prefixes are still insufficient for L1. A later capture design should
preserve complete bounded small TCP payloads/WS frames and skip ACK-only rows
from the useful-data quota, while retaining a separate bound on all received
packets, total bytes, time and CPU work. Keep sequence/direction/truncation
metadata and account separately for stock services8080/24012/26012; never
silently stitch omitted bytes. Do not merely increase an unbounded dump or
claim a guaranteed time window from a poll-count limit.

Any changed observer needs new synthetic/ARM/import/QEMU checks and an exactly
pinned bundle, then a separately notified stationary session. No second M4
application client, semantic/warning injection, speed-as-limit substitution,
M4 firmware change or live replay is authorized by this capture result.
