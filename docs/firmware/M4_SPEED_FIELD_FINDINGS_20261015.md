# M4 vehicle-speed request — first live boundary finding — 2026-10-15

Owner requested actual vehicle-speed display on the M4, not substitution by
the D4 browser page, and authorized stationary observation with M4 powered on.

**Owner clarification:** M4 has two modes: **2D live video already shows vehicle
speed; vehicle speed has never been observed in3D ADAS.** The actual feature
request is to retain/show vehicle speed in the3D layout. Earlier wording
“3D has no speed region” describes observed behavior, not proof that the
renderer lacks or cannot support a widget. It is not a failure of the2D mode.

On2026-10-16 the owner supplied2D/3D photos plus advertising illustrations and
clarified that **a top warning bar does exist, appearing during warnings; the
main value seen is collision-related seconds/countdown**. A photo with the bar
hidden does not prove a missing bar or broken layout. A later annotated ad
labels `0.5` “Chỉ số khoảng cách an toàn”; owner confirms collision-related
seconds, not vehicle speed. Exact native TTC/headway mapping remains unknown.
M4 has one top button for2D/3D switching and no reported version-menu access;
do not request hidden-menu/long-press/reset experiments. See
`M4_OWNER_VISUAL_FINDINGS_20261016.md`.

This narrows the missing behavior to the 3D presentation path, but does not by
itself prove which process draws the 2D digits. They may be camera-burned video
OSD or a native M4 overlay. Do not assume the 2D speed proves M4's 3D receiver
has a usable speed model. Preserve the working 2D and all ADAS layers.

## 2026-10-16 native M4-path update (supersedes old transport uncertainty)

Finite V4 AF_PACKET capture on proven RNDIS `usb0` retained10 COMPLETE native
camera `.123:8080`→M4 `.129` `GPSSpeed` WebSocket JSON messages without adding
an application client. The exact `type`/`uuid`/`speed` shape and integer speed
field were independently inspected offline; no observed speed values are
published. This proves camera emission onto the current M4 link, not that the
M4 app accepts/applies the value or draws it in3D. Missing3D speed is no longer
explainable solely as “camera never sends GPSSpeed”. Do not inject another copy.

V4 kept all42 sampled payload records untruncated; strict unchanged-connection
postflight FAILED because26012's native client port changed. Camera8080 stayed
connected, original processes/recording/AP/D4 assets remained healthy in snapshots,
and owner reported no screen flicker or original-function problem. Cause of
26012 reconnect is UNKNOWN. No retry or further hardware access. See
`M4_SNIFF_V4_HARDWARE_20261016.md`; this is not unconditional preservation pass.

## Historical first-client observation

After the laptop joined the expected camera AP, its camera-facing IPv4 was
explicitly bound for HTTP/WS. The authorized stock UUID was verified before
other camera operations. Native :8099 returned HTTP200 and corrected D3.1
same-origin policy; this is not exact installed-token attestation.

A bounded 18-second passive `minieye-websocket` connection to `:8080/`
received 17 stock `GPSSpeed` frames (type1601) among21 JSON frames. Frame
shapes were exactly `type`, `uuid`, `speed`; observed raw values1..5. No text/
binary speed/setting/warning command was sent. Stock speed-unit CGI returned
`KM/H`. The GPS monitor getter returned `no this key`; HTTP200 alone is not
success. Stationary values1..5 may reflect GPS drift or another source/rounding
artifact, not proof of moving vehicle speed.

**Important observer correction:** static analysis shows EN `cardv` uses one
global WebSocket client pointer. A second observer connection can overwrite
the native M4 client pointer; when the observer closes, cardv can clear that
pointer without comparing the closing connection. Therefore this capture is
valid evidence that cardv emits speed to *a* client, but it is not proof the
M4 received it, and the observer may have temporarily disrupted the M4 stream.
The observer was closed and must not be run again with M4 attached. Reconnect
M4 itself while stationary before further correlation.

Private sanitized capture:
`C2M_HW_20261012/06_candidate_D4/live_m4_speed_20261015_173255/capture.json`.
No camera settings, M4 payload, UART, FIFO or warning injection was performed.

## Static native sender proof

Read-only analysis of EN production `cardv` SHA256
`344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c`
shows the native path:

```text
GPS parser/cache -> GpsSetInfo2Chunk()
-> DeviceSendMsgToScreenTask() at about 1 Hz
-> SendGPSInfoToScreen()
-> WSSetGPSSpeed()
-> cardv WebSocket server -> connected client
```

The JSON template is `{"type":1601,"uuid":"GPSSpeed","speed":%d}`.
The sender is stock outbound cardv→client traffic; cardv has no verified
inbound 1601 setter/relay. It uses one global client pointer and the runtime
M4 peer/path/interface were unverified at that earlier static review (now
proven by RNDIS capture above). On invalid GPS cardv maps cached
65535 to0; the JSON has no validity/timestamp, so speed0 cannot distinguish
stationary from invalid GPS. For normal RMC input the cached value is integer
km/h after knots×1.852 conversion, though the M4 render/unit behavior remains
unknown.

No verified stock “show speed” setting was found. `GPSMonitor` gates UDP GPS
telemetry, not the native speed sender. `ScreenModeSet` is day/night theme,
not a proven speed-layout switch. Do not infer that changing SpeedUnit or
sending another GPSSpeed JSON creates an M4 widget.

## Camera OSD capability is separate from the 3D layout

Static EN `cardv` analysis also proves a GPS-speed-to-text-to-RGN canvas path:
`OSD_DrawVideoStamp()` reads the GPS chunk speed, applies the configured speed
unit, formats `" %d%s"`, and calls `mid_OSD_UpdateTextWidget_Rgn()` for speed at
code VA `0x67136`. This is separate from the outbound WebSocket message path.

Corrected menu-table mapping: `SpeedStamp` is index44/config `+0xb0`;
`SpeedUnit` is index59/config `+0xec`. These table mappings do **not** prove
that SpeedStamp gates that drawing function or that its canvas is attached
to the owner's 2D view or any 3D composition. The earlier draft's identical
`+0xec` offsets and timestamp draw-call attribution are not retained as proof.

The camera-side renderer could explain why speed is visible on live video
but absent from 3D. It is not proof of the actual hardware composition.
Do not add an OSD attachment or change a display buffer on this evidence.

## Missing implementation prerequisite

Local search found no identified M4 receiver/renderer source, M4 firmware dump
or update package, 3D layout assets, or documented speed-in-3D control. The
camera firmware and host-side `M4Adapter` scaffold are not M4 UI firmware.
The earlier lack of physical-link capture is now superseded by V3/V4 native
RNDIS captures; synthetic fixtures alone never counted. Those native captures
still do not identify the actual3D rendering component or speed widget control.

Needed next: identify the actual renderer/receiver and obtain a verified stock
speed/sign display control or matching renderer documentation/source. A renderer
update is not assumed necessary; any later update would need its own proven
recovery path. Owner has now supplied2D/3D photos and confirmed the single top
button only switches modes; no version menu is reported, so stop asking for
one and keep M4 version UNKNOWN. Continue offline from known firmware/sender
paths. An existing recorded clip could distinguish video-burned OSD from a
screen-only overlay without inducing warnings or another camera session.

Owner has disconnected camera Wi-Fi and asked to be notified before it is
needed again. Continue offline; no further camera probes until explicitly
requested and identity/source binding is re-established.

## Decision

No code has been added to transmit another speed packet. The existing M4
policy remains default-deny for semantic `GPSSpeed`; no UART/FIFO/M4 injection,
cardv command, guessed CGI set, or second :8080 observer is authorized.

Safe next hardware correlation, only with owner control and camera/M4
stationary:

1. Reconnect/reboot the M4 alone so its native connection is restored.
2. Use only an already-proven native capture mechanism that cannot create a
   second cardv client, or observe the physical M4 while cardv naturally emits
   its own frames. Do not attach a second WS client to :8080.
3. Native GPSSpeed now reaches the proven M4 link. If3D digits remain absent,
   investigate receiver handling, validity/display policy and actual layout;
   do not declare missing renderer capability or prescribe firmware replacement
   from the transport packet alone.
4. If native frames remain zero/invalid, resolve genuine camera GPS fix first.

D4 remains a separate offline GPS nearby-area advisory displayed in `/signs`
with optional phone/browser beep; it does not claim M4 speed or camera-speaker
output. Native traffic-sign display is investigated separately in
`M4_SIGN_DISPLAY_FINDINGS_20261015.md`; owner has never seen a sign on M4.
