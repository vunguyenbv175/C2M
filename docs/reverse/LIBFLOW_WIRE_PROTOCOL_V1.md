# libflow wire protocol V1 — stock C2M ADAS ScreenService

## Why this matters

`ScreenService` does not put its inner ADAS MessagePack object directly onto a raw socket. The stock `libflow` library adds a second MessagePack envelope and transports it as a WebSocket **binary** frame.

This gives enough static evidence to implement a compatible read-only subscriber before any M4 packet capture.

## 1. Server runtime override

Generic `libflow.so` contains defaults:

```text
addr = 127.0.0.1
port = 24012
```

Those are library defaults only.

C2M `ScreenService` overrides them through:

```text
FLAGS_screen_export_addr = 0.0.0.0
FLAGS_screen_export_port = 26012
```

and constructs `AdasScreenService` using those values.

## 2. Outer outgoing frame

`flow::OutMsg::Init(...)` builds a fixed 4-field MessagePack object using these literal keys:

```text
time
source
topic
data
```

Recovered wire shape:

```text
{
  "time":   <int64>,
  "source": <string>,
  "topic":  <string>,
  "data":   <MessagePack BIN>
}
```

`data` is packed as binary bytes, not recursively embedded as a MessagePack object by libflow. For C2M ScreenService those bytes are themselves the inner ADAS MessagePack envelope.

Therefore an actual ADAS frame is logically:

```text
WebSocket binary
  -> MessagePack outer
       time
       source
       topic = vehicle | ped | lane
       data = BIN(
         MessagePack inner {
           frame_id,
           time,
           key,
           data
         }
       )
```

## 3. Subscription frame

`flow::RealClientInfo::DoSubscribe()` references exactly:

```text
source
topic
subscribe
data
```

Its constructed message is:

```text
{
  "source": <client name>,
  "topic":  "subscribe",
  "data":   <topic to subscribe>
}
```

and it is sent using WebSocket binary opcode `2`.

The corresponding server `OnRecvWSBinaryFrame()` requires `source`, `topic`, and `data`; it has explicit dispatch strings:

```text
subscribe
unsubscribe
```

and calls the subscribe/unsubscribe handlers.

Thus the read-only subscription shape is **CONFIRMED static protocol evidence**.

## 4. C2M topics discovered

Known ADAS ScreenService topics:

```text
vehicle
ped
lane
```

Known inner keys:

```text
vehicleWarning
vehicleMeasure
pedestrians
laneWarningRes
```

## 5. Practical read-only client

Repository implementation:

```text
tools/m4/libflow_protocol.py
tools/m4/libflow_subscriber.py
tools/m4/decode_payload.py
```

The subscriber sends only stock-compatible `subscribe` messages and never injects ADAS state.

Expected use on a stationary test setup:

```sh
python3 tools/m4/libflow_subscriber.py <C2M-IP>
```

Defaults:

```text
port   26012
topics vehicle,ped,lane
source c2m-re
```

## 6. Remaining unknowns

Still runtime-unverified:

- whether M4 itself connects directly to port 26012,
- whether the WebSocket URL path is `/` on the production firmware,
- exact source string emitted by `AdasScreenService`,
- physical interface carrying this socket,
- whether another proxy process sits between M4 and ScreenService.

The new client is therefore a protocol probe and passive observation tool, not yet an M4 emulator.
