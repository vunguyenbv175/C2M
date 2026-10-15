# M4 vehicle-speed request — first live boundary finding — 2026-10-15

Owner specifically requested actual vehicle-speed display on the **M4**, not
substitution by the D4 browser page. Owner says M4 has **no speed region/box**,
and authorized stationary read-only observation with M4 powered on.

## Confirmed live observation

After the laptop rejoined the expected camera AP, its camera-facing IPv4 was
explicitly bound for HTTP/WS. The authorized stock UUID was verified before
any other camera operation. Native :8099 page/status returned HTTP200 and
`Referrer-Policy:same-origin`, consistent with corrected D3.1 behavior, but
not an exact installed-image token attestation.

A bounded18-second passive `minieye-websocket` connection to `:8080/`
received **17 stock `GPSSpeed` frames** (type1601) among21 JSON frames. Frame
shapes were exactly `type`, `uuid`, `speed`; observed raw values1..5.
No text/binary speed/setting/warning command was sent. Handshake and WS
protocol close/control only. A receive-only client observing data is not
proof the M4 receives/renders the same channel.

The stock read-only speed-unit CGI returned `KM/H`. This setting is context,
not an independent calibration of the wire integer or proof of M4 scaling.
The `Camera.Menu.GPSMonitor` getter returned `no this key`; HTTP200 alone
is not success. Stationary values1..5 may reflect GPS drift or another
source/rounding artifact; they must not be asserted as actual car motion.

Other live status: `ap_active=true`, `config_saved=true`, `connect_pending=false`,
`sta_supported=unknown`, `sta_state=unknown`,
`last_error=capability_missing_or_malformed`, `bt_presence=not_seen`.
No saved credential bytes were read or written, and STA association was not
requested. Saved configuration does not prove AP+STA or Internet.

Private sanitized capture:
`C2M_HW_20261012/06_candidate_D4/live_m4_speed_20261015_173255/capture.json`.

## Meaning for implementation

The stock system **already emits GPS-speed messages**. Adding another
producer or relaying the laptop-observed feed back into cardv is not a fix
for an absent M4 widget, can create competing/stale values, and is not
justified. No M4 policy was relaxed; `GPSSpeed` injection remains denied.

Need determine the actual M4 receiver/render path and whether a stock layout
or supported setting exposes the speed field. A speed-bearing JSON template
or VI-only sender symbol alone cannot prove this. If the M4 UI lacks a
supported renderer/setting, modifying only the Linux camera service cannot
create a new widget; M4 firmware/UI support will be required.

Preserve stock ADAS/video/warning channels. Do not repaint scene/speed fields,
repurpose warning-distance slots, open occupied UARTs, guessed CGI sets or
send semantic M4 data as an experiment. D4 browser advisory scope remains
separate and is not reported as fulfillment of this M4 request.
