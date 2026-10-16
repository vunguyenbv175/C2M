# M4 transport L0 — proven RNDIS path, no injection — 2026-10-16

## Result

Owner authorized a read-only M4 path check with M4 attached and showing3D.
No data was sent to the screen. No second cardv `:8080` client was opened.
No pcap, module load, scan, RF, UART, config or firmware change was made.

**L0 transport is now proven** by live read-only evidence:

- M4 is a USB RNDIS network peer, not Wi-Fi or serial.
- Camera `usb0`: `192.168.32.123/24`, MAC `d6:29:83:c3:30:5e`, driver
  `rndis_host`, backed by USB device `1-1` (`idVendor=2207`,
  `idProduct=0013`, `manufacturer=t-chip`, `product=rk312x`).
- M4 peer: `192.168.32.129`, seen in ARP on `usb0` with MAC
  `26:23:01:df:c1:10`, and in route table `192.168.32.0/24` via `usb0`.
- Camera is TCP server; M4 is TCP client on **both** stock paths:
  - `adas` (`./adas --fs=3602`, PID2102) LISTEN `0.0.0.0:26012`;
    ESTABLISHED `192.168.32.123:26012` ↔ `192.168.32.129:43261`.
  - `cardv` (`/oneed_cust/default.ini`, PID640) LISTEN `0.0.0.0:8080`;
    ESTABLISHED `192.168.32.123:8080` ↔ `192.168.32.129:51385`.
- `/proc/net/tcp` independently shows LISTEN `0.0.0.0:659C` (26012) and
  `0.0.0.0:1F90` (8080), plus the two `192.168.32.123` ESTABLISHED legs.
- `usb0` carried traffic in `/proc/net/dev` (RX and TX packet counters
  nonzero). Exact byte counts are private capture metadata, not reproduced here.

This confirms the dual-path hypothesis: M4 connects directly to both
`adas:26012` (libflow/MessagePack semantic scene candidate) and
`cardv:8080` (minieye-websocket JSON status candidate). It does **not** prove
message schemas, which side draws2D versus3D, or any speed/sign widget.

Private evidence:
`C2M_HW_20261012/07_m4/m4_passive_20261016_111525/`
(73 files, manifest-verified, no transmit). Raw MAC/serial/IP/port details
above are limited to the M4 link already needed to prove the path; no Wi-Fi
credentials, license IDs, GPS positions or DB bytes are included.

## Why no active send yet

- `cardv:8080` uses one global client pointer. A second observer already
  proved disruptive: it can steal the M4 stream on connect and clear it on
  close. Opening another `:8080` client with M4 attached is prohibited, even
  receive-only.
- `adas:26012` multi-client behavior is unverified. Connecting a test client
  from the laptop over Wi-Fi could disturb the native M4 session or be
  silently ignored; neither outcome proves delivery.
- `tcpdump` does not exist on the camera, so a network-layer pcap on the
  verified `usb0` interface was not possible with stock tools. No package
  was installed.
- Speed/sign semantics remain L3 BLOCKED. `GPSSpeed` is vehicle speed only;
  no verified sign/limit slot exists in the recovered screen contract. The
  working collision countdown must never be repurposed as a speed/limit field.

A visible M4 change therefore needs L1 passive decode first (what the two
native legs already carry), then a separately gated harmless replay if one
exists — not a guessed packet now.

## Preservation

Final read-only check: recording status1 with advancing segment metadata,
stock cardv/ADAS/lane workers present, installed `c2m-signs` and private DB
hashes unchanged, AP active. Owner core-function confirmation after this
passive session is still pending; do not claim it until asked. Hardware
access is stopped; owner may disconnect camera Wi-Fi.

## Next safe step, offline first

Build a minimal bounded ARM RAM-only `usb0` sniffer (no transmit, no disk
write on camera except bounded `/tmp` RAM pcap, external timeout, exact
cleanup), gate it through host tests and stock-QEMU like prior observers,
then run it only in a newly notified stationary session. Only after decoded
native frames prove schema and receiver behavior can a harmless-value replay
(L2 allowlist only) be proposed with explicit owner approval and recovery.
No M4 firmware change, guessed CGI, UART/FIFO write or warning induction.
