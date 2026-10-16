# M4 reverse tools

These are passive-first helpers derived from the stock C2M binaries.

## Native capture status (2026-10-16)

V3/V4 proved RNDIS `usb0` camera↔M4 with native `8080`, `24012`, `26012`.
V4 retained42 untruncated payload records;39 complete server messages,
including10 GPSSpeed. **The unchanged26012 connection gate FAILED** (client
port changed); owner reported normal/no flicker, no retry or active injection.
Transport decode does not prove3D receiver/layout capability. See
`../../docs/firmware/M4_SNIFF_V4_HARDWARE_20261016.md`.

Decode the existing PRIVATE stdout on a workstation only:

```sh
python3 tools/m4/decode_passive_records.py PRIVATE_CAPTURE --report PRIVATE_REPORT
```

The decoder now handles bounded initial HTTP Upgrade prefixes directly,
including segmented headers and RFC6455 request/accept matching on exact
reversed4-tuples. No byte search or fabricated gap filling; no key/header/speed/
warning values in safe output. `matched_passive_upgrade` means framing match,
not authenticated device, supported widget or approval to replay. Midstream
flows remain candidate boundaries. `GPSSpeed` has a receive-only schema and
remains DENY; `pedWarning` observation never enables a warning sender.

Offline synthetic regression:

```sh
python3 tools/m4/test_decode_passive_records.py
python3 tools/m4/test_ws_upgrade.py
python3 tools/m4/test_passive_upgrade.py
python3 tools/m4/test_ped_warning.py
```

All commands below are historical discovery tools, **not** authorization for a
new camera session. With M4 attached use no second application client; capture
requires a separately notified finite-session approval and exact native gates.

## 0. Prove transport before assuming it

First collect two read-only device baselines:

```sh
sh tools/device/collect_baseline.sh en_good_m4_off
sh tools/device/collect_baseline.sh en_good_m4_on
```

Copy/extract both captures to a workstation and run:

```sh
python3 tools/m4/discover_transport.py \
  c2m_capture_en_good_m4_off \
  c2m_capture_en_good_m4_on \
  -o m4_transport.json \
  --markdown m4_transport.md
```

The analyzer ranks:

```text
new network interface
new USB device / VID/PID
new ARP peer
new TCP/UDP socket
socket owner from saved process FDs
input-device delta
new process
interface carrier/operstate change
```

A new USB device + `usb0` + peer + socket owned by `adas`/`cardv` would be strong evidence for USB-network M4 transport. Absence of that combination means keep investigating other device-node/input/IPC paths.

## ADAS ScreenService / libflow

Static C2M override:

```text
bind address: 0.0.0.0
port: 26012
```

The libflow WebSocket binary message is nested MessagePack:

```text
outer {time, source, topic, data=<BIN inner>}
inner {frame_id, time, key, data}
```

A stock libflow client subscribes using a binary MessagePack frame:

```text
{source:<client>, topic:"subscribe", data:<topic>}
```

Known topics:

```text
vehicle
ped
lane
```

Run only on a stationary/test setup first:

```sh
python3 tools/m4/libflow_subscriber.py 192.168.x.x
```

Offline frame decode:

```sh
python3 tools/m4/decode_payload.py --file frame.bin
```

Synthetic smoke test:

```sh
python3 tools/m4/test_protocol.py
```

Dependencies:

```text
msgpack
websocket-client
```

## cardv status WebSocket

Static server port: `8080`  
WebSocket subprotocol: `minieye-websocket`

**Not a non-interfering observer:** EN `cardv` keeps one global WebSocket
client pointer. A second client can steal the M4 status stream, and closing
that observer can clear the pointer. Do not connect while M4 is attached.
Only with M4 physically disconnected, in an owner-approved stationary test:

```sh
python3 tools/m4/cardv_status_client.py --confirm-m4-disconnected 192.168.x.x
```

No-client observation does not prove physical M4 delivery/rendering. Do not
inject safety warnings or modify M4 firmware during discovery.
