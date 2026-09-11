# M4 reverse tools

These are passive-first helpers derived from the stock C2M binaries.

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

Passive receive:

```sh
python3 tools/m4/cardv_status_client.py 192.168.x.x
```

Do not inject safety warnings or modify M4 firmware during discovery.
