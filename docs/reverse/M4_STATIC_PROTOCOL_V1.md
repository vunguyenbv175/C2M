# M4 Static Protocol V1 — C2M stock screen paths

**Scope:** static reverse of EN golden firmware, cross-checked against VI where noted.  
**Goal:** produce protocol facts that can directly drive a passive decoder and later `M4Adapter`.

## Executive result

The firmware exposes **two distinct screen-facing application paths**:

```text
ADAS process
  -> AdasScreenService / LibflowServer
  -> MessagePack semantic ADAS messages
  -> default bind addr 0.0.0.0
  -> default port 26012

cardv process
  -> libwebsockets server
  -> JSON device/status/control messages
  -> port 8080
  -> protocol name "minieye-websocket"
```

The exact physical path from C2M to M4 (USB Ethernet/RNDIS/CDC or something else) is still runtime-unverified. Static analysis does **not** justify claiming that `usb0` is definitely the M4 transport yet.

This dual-path result makes a hybrid architecture likely: ADAS semantic objects are exported separately from device/status/display-mode JSON.

---

# 1. ADAS ScreenService transport

## 1.1 Service construction

The stock ADAS executable contains:

```text
ScreenService::ScreenService()
ScreenService::Init()
LibflowServer::LibflowServer(string const&, string const&, string const&)
AdasScreenService
fLS::FLAGS_screen_export_addr
fLS::FLAGS_screen_export_port
```

The constructor loads the `screen_export_addr` and `screen_export_port` flag strings and passes them with service name `AdasScreenService` into `LibflowServer`.

Static defaults:

```text
screen_export_addr = 0.0.0.0
screen_export_port = 26012
```

`libflow.so` contains WebSocket support (`Upgrade: websocket`, WS receive/send paths). Therefore **application-layer WebSocket-capable libflow transport is HIGH-CONFIDENCE**; the exact on-wire handshake must still be captured.

## 1.2 MessagePack envelope

The `ScreenService::Send<T>` serializers build a 4-entry MessagePack map (`0x84`).

Confirmed envelope:

```text
{
  "frame_id": <uint32>,
  "time":     <int64>,
  "key":      <string>,
  "data":     <typed payload>
}
```

At the end, the serializer invokes:

```text
LibflowServer::Send(topic, sbuffer_data, sbuffer_size)
```

Thus the first string passed by callers is a **topic**, and the second is the envelope `key`.

---

# 2. Confirmed ADAS topic / key pairs

Static callsites establish:

| Producer | Topic | key |
|---|---|---|
| `VehicleRun::ReadVehicle()` | `vehicle` | `vehicleWarning` |
| `VehicleRun::ReadVehicle()` | `vehicle` | `vehicleMeasure` |
| `VehicleRun::ReadPed()` | `ped` | `pedestrians` |
| `LaneRun()` | `lane` | `laneWarningRes` |

These are **CONFIRMED** from PC-relative string references at the actual send callsites.

---

# 3. `vehicleWarning` schema

Serializer:

```text
ScreenService::Send<sdk::C1VehicleWarning>
```

The `data` object is a fixed MessagePack map of 7 entries (`0x87`).

Confirmed keys:

```text
vehicle_id
headway
warning_level
fcw
headway_warning
vb_warning
sag_warning
```

Recovered schema:

```text
vehicle / vehicleWarning
{
  frame_id,
  time,
  key: "vehicleWarning",
  data: {
    vehicle_id:       int32,
    headway:          float32,
    warning_level:    int32,
    fcw:              int32,
    headway_warning:  int32,
    vb_warning:       int32,
    sag_warning:      int32
  }
}
```

The numeric interpretation/enums of warning fields still need correlation against live events.

---

# 4. `vehicleMeasure` schema

Serializer:

```text
ScreenService::Send<vector<sdk::C1VehicleMeasureRes>>
```

`data` is an array; each vehicle is a fixed 8-entry MessagePack map (`0x88`).

Confirmed per-vehicle keys:

```text
vehicle_class
vehicle_id
vehicle_width
longitude_dist
lateral_dist
ttc
is_crucial
is_second_crucial
```

Recovered logical shape:

```text
vehicle / vehicleMeasure
{
  frame_id,
  time,
  key: "vehicleMeasure",
  data: [
    {
      vehicle_class,
      vehicle_id,
      vehicle_width,
      longitude_dist,
      lateral_dist,
      ttc,
      is_crucial,
      is_second_crucial
    }, ...
  ]
}
```

Static pack operations indicate distance/TTC/width values are floats and the two `is_*` fields are booleans. Exact units must be verified at runtime. `longitude_dist` is the vendor spelling and should be preserved in a decoder.

This message is a major reuse target because it exposes the stock vehicle measurement output needed for enhanced ADAS/M4 integration.

---

# 5. `pedestrians` schema

Serializer:

```text
ScreenService::Send<vector<sdk::C1PedRes>>
```

`data` is an array; each pedestrian is a fixed 8-entry MessagePack map (`0x88`).

Confirmed keys:

```text
id
world_x
world_y
is_key
is_danger
ttc_m
ttc
have_bike
```

Recovered logical shape:

```text
ped / pedestrians
{
  frame_id,
  time,
  key: "pedestrians",
  data: [
    {
      id,
      world_x,
      world_y,
      is_key,
      is_danger,
      ttc_m,
      ttc,
      have_bike
    }, ...
  ]
}
```

The serializer confirms exactly eight fields; nearby strings such as `det_rect` and `confidence` are **not** sufficient evidence that they belong to this screen message.

`VehicleRun::ReadPed()` also contains a separate `pedWarning` representation with `ped_on` / `pcw_on`; do not conflate that path with the `pedestrians` screen array until the receiving path is traced.

---

# 6. `laneWarningRes` schema

Serializer:

```text
SendScreenMsg<sdk::ScreenWarningRes>
```

The outer MessagePack envelope is the same 4-entry map.

The `data` object itself is a fixed 4-entry map (`0x84`):

```text
lanelines
ldw_info
turn_radius
turn_frequently
```

## 6.1 `lanelines`

`lanelines` is an array. Each serialized lane-line item is a fixed 3-entry map (`0x83`):

```text
bird_view_poly_coeff
label
type
```

## 6.2 `ldw_info`

`ldw_info` is a one-entry map (`0x81`):

```text
deviate_state
```

## 6.3 Full logical shape

```text
lane / laneWarningRes
{
  frame_id,
  time,
  key: "laneWarningRes",
  data: {
    lanelines: [
      {
        bird_view_poly_coeff: ...,
        label: ...,
        type: ...
      }, ...
    ],
    ldw_info: {
      deviate_state: int32
    },
    turn_radius: float32,
    turn_frequently: bool
  }
}
```

The exact representation of `bird_view_poly_coeff`, and enum meanings for `label`, `type`, `deviate_state`, still require either deeper decompilation or captured MessagePack samples.

---

# 7. `cardv` WebSocket server

Both EN and VI `cardv` implement:

```text
WebSocketServerTask(void*)
WebSocketServerStartThread()
WebSocketServerStopThread()
WSGetConnectStatus()
```

Immediately before `lws_create_context`, both builds write `0x1f90` into the first server context field. `0x1f90` = **8080**. This is HIGH-CONFIDENCE static evidence for the cardv WebSocket listening port in both firmware versions.

The protocol table contains:

```text
minieye-websocket
```

and a callback pointer.

## 7.1 JSON messages

Confirmed JSON templates in `src/module_websocket.cpp`:

```json
{"type":1600, "uuid":"GPSLevel", "level":%d}
{"type":1100, "uuid":"DispBrightSet", "brightness":%d}
{"type":1601, "uuid":"GPSSpeed", "speed":%d}
{"type":1200, "uuid":"StorageStatus", "status":"%s"}
{"type":1502, "uuid":"ClientConn", "connected":%s}
{"type":2001, "uuid":"RecordVoice", "op":%d}
{"type":1103, "uuid":"ScreenModeSet", "theme":"%s"}
{"type":3000, "uuid":"AdasStatus", "status":%s}
{"type":3001, "uuid":"HeavyCalibStatus", "status":"%s"}
```

Related functions:

```text
WSSetBacklightLevel
WSSetGPSLevel
WSSetGPSSpeed
WSSetStorageStatus
WSSetClientConnectStatus
WSSetAudioRecordStatus
WSSetDisplayMode
WSSetADASStatus
WSSetADASCalibStatus
```

## 7.2 Periodic screen/status sender

`DeviceSendMsgToScreenTask()` keeps the same direct call sequence in EN and VI:

```text
WSGetConnectStatus
SendADASInfoToScreen
GetADASStatus
SendGPSInfoToScreen
SendBacklightLevelInfoToScreen
SendDisplayModeToScreen
SendStorageInfoToScreen
SendWifiStatusToScreen
SendAudioRecordStatusToScreen
```

VI additionally exports:

```text
SendGPSSpeedToScreen(int)
```

This is a meaningful Vietnam/newer-build screen delta and should be correlated with the added framebuffer reservation and M4 behavior.

---

# 8. Current architecture hypothesis

**HIGH-CONFIDENCE, not yet runtime-proven:**

```text
stock ADAS
  -> libflow / MessagePack semantic scene messages :26012

stock cardv
  -> libwebsockets / JSON status-control messages :8080

                     both
                      |
                      v
                 M4 ecosystem
```

Possible interpretations still to distinguish:

1. M4 connects directly to both services.
2. Another local process proxies one path to M4.
3. One service is app/debug-facing while the other is M4-facing.

Only connected-vs-disconnected socket/pcap evidence can decide this.

---

# 9. Immediate passive runtime capture plan

On the known-good EN firmware, collect with M4 disconnected and connected:

```sh
ss -lntup
netstat -anp
ip addr
ip link
ip neigh
cat /proc/net/arp
ps
```

Specifically verify:

```text
0.0.0.0:26012 or equivalent ScreenService listener
*:8080 cardv WebSocket listener
peer IP when M4 connects
which TCP connection belongs to M4
whether usb0 appears/disappears
```

If the relevant network interface is identified:

```sh
tcpdump -i <verified-interface> -s 0 -w /mnt/mmc/m4.pcap
```

Capture scenarios:

```text
idle 3D
lead vehicle appears
distance changes
FCW
LDW
pedestrian
3D <-> live switch
GPS acquire/loss
recording/SD state
M4 button actions
```

A passive decoder should first target the four confirmed ADAS topic/key pairs and the nine JSON UUID templates above.

---

# 10. Engineering implication

M4 reuse is now more promising than before. The firmware already exports the exact semantic state that an enhanced system needs:

```text
vehicle warnings
vehicle distance / lateral distance / TTC
pedestrian state / TTC
lane geometry / LDW state
GPS speed/status
display mode
ADAS status
storage/audio status
```

Therefore a future `M4Adapter` should prefer compatibility with these stock schemas rather than inventing a new display protocol.

Do not modify M4 firmware or inject critical warning packets until passive capture and harmless replay are complete.
