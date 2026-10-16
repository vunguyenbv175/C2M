# M4 traffic-sign display — evidence boundary — 2026-10-15

## Owner's actual request and observation

- M4 **2D live video shows vehicle speed**; owner has never observed vehicle
  speed in3D. That does not prove the renderer lacks widget capability.
- Later owner photos and clarification confirm a **conditional top warning
  bar**: it appears during warnings, mainly showing collision-related seconds.
  Do not interpret a screenshot without the bar as a permanently missing UI.
  Advertising numbered badges/`0.5` are not live sign/speed evidence; see
  `M4_OWNER_VISUAL_FINDINGS_20261016.md`.
- Owner additionally requested checking how traffic signs appear on M4.
- Owner reports **never having seen a traffic-sign icon/value on this M4**.
  This is not the same as the vehicle-speed number and is not evidence of a
  broken sign widget: the widget/receiver support itself is still unproven.
- Camera Wi-Fi is disconnected. Continue offline; ask before another live
  camera session. No device/card/network probe is part of this investigation.

## 2026-10-16 V4 native capture update

A finite receive-only RNDIS capture retained complete small native TCP payloads,
including GPSSpeed on8080 and lane/vehicle/pedestrian scene messages on24012/
26012. No sign result was established by this bounded stationary sample;
absence in it is not proof of absent TSR/receiver capability. No replay or
injection was performed. The strict unchanged26012 connection gate failed
(client reconnect), despite normal owner-visible behavior and healthy recorder/
AP/D4; no unconditional preservation acceptance. See
`M4_SNIFF_V4_HARDWARE_20261016.md` for schema counts and limits.

## Separate the three paths

| Data/output | Confirmed evidence | Not established |
|---|---|---|
| Vehicle speed | Stock camera emits outbound `GPSSpeed` type1601; camera also has a GPS-speed-to-text RGN drawing path | Actual M4 receive/render behavior in 3D; whether the observed 2D digits are that RGN canvas |
| Camera TSR signs | Native detector/reporter/result-publishing code exists for limit-related results | Correct real-sign recognition, physical M4 delivery, sign icon/value rendering and expiry |
| D4 offline area advisories | Dedicated GPS/private-DB producer and AP `/signs` browser presentation | No D4-to-M4 adapter or physical M4 sign output is implemented |

D4 currently deploys only directional R.420/R.421 records. It does not emit a
numeric legal limit, overspeed result, or persistent residential-area state.
A browser advisory is not camera detection and is not M4 acceptance.

## Existing screen contract is not a generic sign renderer

The statically recovered ScreenService scene messages are:

- `vehicle / vehicleWarning`: vehicle warning fields;
- `vehicle / vehicleMeasure`: semantic vehicle measurements;
- `ped / pedestrians`: semantic pedestrian measurements;
- `lane / laneWarningRes`: lane geometry/LDW fields.

`ScreenWarningRes` is the `laneWarningRes` carrier type, not proof of a generic
traffic-sign warning. Those recovered maps do not contain a verified sign
slot. Do not repurpose vehicle class, warning level, lane label, distance or
pedestrian fields to paint a fake sign.

The cardv JSON templates include `GPSSpeed`, GPS quality and system status;
none of the currently recovered templates is a verified traffic-sign icon
command. `GPSSpeed` denotes vehicle speed, not a legal limit.

See `docs/reverse/M4_STATIC_PROTOCOL_V1.md` and
`docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json` for existing contract boundaries.

## Direct static TSR export proof (independently checked)

Exact EN ADAS SHA-256:
`0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043`.
Code addresses below clear the Thumb bit.

- `VehicleRun::ReadTsr()` at `0x6d488` has concrete calls at `0x6d79e` and
  `0x6d7c8` to CollectService trace/warning serializers.
- `TsrWarning` serializer `0x74480` emits a five-entry map: `height_limit`
  (float32), `weight_limit` (float32), `speed_limit`, `release_speed_limit`,
  `tsr_warning_level` (integer encoders). Units, sentinels, enum meanings and
  validity/lifetime rules remain unverified on the actual camera.
- `TsrTraceRes` serializer `0x75bdc` emits nine named fields: `det_rect`,
  `confidence`, `tsr_class`, `tsr_id`, `tsr_speed_limit`, `track_cnt`,
  `longitudinal_dist`, `lateral_dist`, `height`. Nested geometry layout and
  complete scalar typing are not established; names do not prove semantics.
- The topic/key references are `tsr / tsr_trace_res_list` and
  `tsr / tsr_warning`, not the recovered ScreenService scene messages.
- A direct Thumb-call scan found no ScreenService send from ReadTsr or
  `Distribution::SetTsrResult()`, and no direct caller of SetTsrResult in the
  scanned `.text`. ReadTsr's call at `0x6d540` instead targets **SetTlrResult**.
  Prior diagrams connecting ReadTsr directly to SetTsrResult overstate this
  exact binary. Indirect calls and uninspected external receivers remain open.
- `ScreenWarningRes` has a direct caller in LaneRun at `0xa86ba`; it is not
  a recovered generic traffic-sign renderer.

These findings prove code/export capability, **not active inference, a real
recognized sign, enabled detector state, or physical display output**. No TSR
schema is promoted to a normalized/legal-limit or transmit API by this review.

## Do not conflate the three services

- `AdasScreenService`: compiled port26012 and shipped/embedded flag
  `--screen_export_addr=0.0.0.0`; recovered semantic scene messages. This is
  not a live socket-bind attestation or proof of a sign widget.
- `AdasCollectService`: compiled port25012; recovered TSR topic/key export.
  The compiled generic `flow_listen_addr` is loopback; the exact compiled
  `collect_export_addr`/`screen_export_addr` defaults were not established by
  the bounded review. The embedded flags override `flow_listen_addr` to
  `0.0.0.0` and contain no collect address override. Do not assert either
  effective live service bind from these literals. External connection
  failure alone is non-diagnostic for detector health.
- cardv `:8080` emits JSON system/GPS status. Vehicle `GPSSpeed` is not a sign
  limit. Its single-client pointer rules out another attached diagnostic client.

`tools/m4/tsr_event_lab.py` can describe captured field shapes, but its
`OBSERVED_ENVELOPES_NOT_CLASSIFIED_SIGNS` result deliberately does not assign
class/value meanings. Test-only payloads such as `signal.id` are synthetic,
not recovered vendor fields. Do not promote them to a native display API.

## Renderer ownership remains open

Actual calls in EN ADAS send semantic vehicles/pedestrians through
ScreenService, supporting a semantic scene path. Separate camera image and
media-buffer functions exist but do not establish that a camera-controlled
plane is visible over the M4 3D scene. `ScreenModeSet/theme` means day/night,
not a proved 2D/3D layout switch.

No matching M4 renderer source, firmware dump/update, layout assets or
supported speed/sign enable control was found locally. Neither “camera-only
OSD will fix it” nor “M4 firmware must be replaced” is yet proven.

## Safety and acceptance

- Do not open a second cardv `:8080` client with M4 attached: one global stock
  client pointer makes even a receive-only observer potentially disruptive.
- No guessed M4 JSON, injected TSR/vehicle/lane packets, UART/FIFO writes,
  arbitrary display-plane attachment or warning suppression.
- `TSR_PROFILE ... ALREADY_APPLIED` is profile-script state, not recognition,
  M4 rendering or exact installed-firmware-token proof.
- A real sign-display PASS requires a real sign with independently known
  class/value, a fresh decoded result of verified meaning, physical M4 output
  correlated with it, removal on stale/lost input, bounded repetition, and
  intact recording/ADAS. No deliberate speeding or hazardous warning induction.

Owner has now supplied2D/3D photos and advertising examples. A later annotated
ad identifies `0.5` as “Chỉ số khoảng cách an toàn”, not vehicle speed; owner
reports a collision-related countdown. M4 has a single top button switching2D
and3D, with no reported settings/version menu. Do not keep requesting a version
page or guess hidden button sequences; retain M4 version UNKNOWN. Continue
offline with exact firmware/sender evidence and matching renderer documentation
if available. Any later native-link observation must be genuinely non-competing
and separately authorized. Keep license/calibration IDs, precise GPS coordinates
and Wi-Fi credentials out of public photos/reports.

For a later owner-approved physical test, record separately: observed real
sign class/value; native decoded result and freshness; visible M4 icon/value
and mode; disappearance time; and any unrelated ADAS/recording effect. Do not
count the live-video picture of a roadside sign as a generated sign widget.
On2026-10-16 the RNDIS L0 link was proven (camera `.123` ↔ M4 `.129` on
`usb0`, native ESTABLISHED legs to `adas:26012` and `cardv:8080`); no packet
was sent and no schema/receiver is proven by that link alone. See
`M4_TRANSPORT_L0_20261016.md`.
Do not count a lone speed number as a recognized limit without a verified
receiver field and visual distinction from vehicle speed.
