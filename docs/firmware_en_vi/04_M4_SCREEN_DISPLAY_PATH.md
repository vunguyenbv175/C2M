# 04 — M4 / Screen / Display Path

## Why this module is high value

The stock M4 is potentially reusable as the primary enhanced HUD/display.

Static firmware evidence is stronger than a generic “USB screen” hypothesis.

## ADAS-side ScreenService

The ADAS executable contains:

```text
AdasScreenService
ScreenService::Init()
ScreenService::Send<C1VehicleWarning>()
ScreenService::Send<vector<C1VehicleMeasureRes>>()
ScreenService::Send<vector<C1PedRes>>()
SendScreenMsg<sdk::ScreenWarningRes>()
SdkOutputService::Send<ScreenAudioMsg>()
sdk::GetScreenAudioMsg(...)
```

This is strong evidence that **semantic ADAS results are explicitly prepared for a screen service**.

## Serialization

The ADAS executable contains extensive `msgpack-c` code and defaults:

```text
--sdk_use_msgpack=true
--enable_screen_service=true
--screen_export_addr=0.0.0.0
```

This supports the hypothesis of semantic messages rather than only raw framebuffer output.

## Screen service port

Direct rodata inspection around the source path:

```text
/media/zac/S/code/adas/rk3566/adas/src/sdk/screen_service.cpp
```

shows:

```text
AdasScreenService
sdk addr
screen_export_addr
26012
screen_export_port
```

Therefore:

```text
default ScreenService export port string = 26012
```

is now **CONFIRMED static evidence**.

Do not yet assume:
- which interface M4 reaches it on,
- whether 26012 is the final runtime port after config override,
- exact URL/path/topic,
- whether M4 connects directly to ADAS or via cardv proxy.

## libflow transport

The exact `libflow.so` used by ADAS is byte-identical across EN and VI.

It contains WebSocket implementation strings/functions:

```text
Upgrade: websocket
Sec-WebSocket-*
Cannot connect to WS server
WebServer::OnRecvWSBinaryFrame
WebServer::OnRecvWSTextFrame
Sender::send
Receiver
```

ADAS rodata also includes:

```text
ws://
sdk_recv
```

**HIGH-CONFIDENCE interpretation:** `ScreenService` is built on a WebSocket-capable `libflow` messaging transport.

Runtime capture is still required to prove the exact M4 path.

## cardv-side screen functions

Both EN and VI `cardv` contain:

```text
DeviceSendMsgToScreenStartThread
DeviceSendMsgToScreenTask
SendADASInfoToScreen
SendGPSInfoToScreen
SendWifiStatusToScreen
SendDisplayModeToScreen
SendStorageInfoToScreen
SendAudioRecordStatusToScreen
SendBacklightLevelInfoToScreen
DisplayVideoYuv422
refresh_display_yuv422
ScreenDisplayMode
sendtoscreen_task
```

There is also a message template:

```json
{"type":1103, "uuid":"ScreenModeSet", "theme":"%s"}
```

This suggests cardv can handle both:
- semantic/status communication,
- and pixel/video display operations.

Therefore the final M4 architecture may be **hybrid**, not purely semantic.

## Major VI-specific display delta

VI `cardv` adds:

```text
SendGPSSpeedToScreen(int)
```

VI bootargs also add an 8 MiB `fb` reserved memory region.

This strongly suggests the VI release included display/GPS-to-screen work.

That makes the M4 workstream relevant to the EN/VI regression as well as to future enhancement.

## USB/network clues

Customer firmware contains:

```text
usbnet.ko
rndis_host.ko
cdc_ether.ko
ehci-hcd.ko
```

Rootfs `mdev.conf` contains behavior around `usb0` and address `192.168.32.123`.

These are clues, not proof that M4 uses RNDIS/CDC.

## Questions coding agent must answer

1. Does connecting M4 create/remove `usb0`?
2. Which side is USB host?
3. Which peer IP is visible?
4. Does M4 connect to port 26012?
5. Is 26012 a WebSocket endpoint?
6. Does `cardv` proxy messages between M4 and ADAS?
7. Is live-view video sent as YUV/raw/compressed stream?
8. Are lane/vehicle/pedestrian objects encoded as MessagePack?
9. Does M4 render the 3D scene itself?
10. How is the top button reported?

## Highest-value capture

On a working EN unit:

```sh
ss -lntup
netstat -anp
ip addr
ip neigh
cat /proc/net/arp
ps
```

with M4 disconnected vs connected.

If a M4-associated interface appears:

```sh
tcpdump -i <verified-iface> -s 0 -w /mnt/mmc/m4.pcap
```

Then correlate:
- lead vehicle,
- distance change,
- FCW,
- LDW,
- pedestrian,
- 3D/live switch,
- GPS,
- screen button.

## Target artifact

Build an `M4Adapter` only after protocol evidence exists.

Desired normalized path:

```text
Stock ADAS --------\
RoadIntelligence ----\
VietMap --------------> DisplayState -> M4Adapter -> stock M4
TPMS ----------------/
System Health -------/
```
