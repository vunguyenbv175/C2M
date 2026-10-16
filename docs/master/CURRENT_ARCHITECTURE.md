# C2M Enhanced Firmware — Current Architecture

**Status:** active owner architecture, updated after EN/VI deep reverse  
**Known-good baseline:** `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`  
**Owner-requested D5 base:** `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`.
Owner clarified2026-10-16 that prior VI ADAS symptoms may have reflected
settings unfamiliarity; VI regression/incompatibility is NOT established.

**D5-VI preparation:** full VI core plus all D4 services, GPS fraction0..999
correction, key-only AP SSH with no20-minute listener deadline and on-demand
read-only health command. Device-specific config/calibration/license and vendor
greeting semantics retained; no ADB/WS injection or automatic resets. Separate
manual build/validation, private retrieval and local version preparation;
no camera access/card staging/flash authorized by package creation. See
`../firmware/CANDIDATE_D5_VI_20261016.md` for scope and hardware acceptance.
D5-VI sourcefd7bd6a/package CI38902291605/general CI38902290701 PASS; local
version20261016000001 prepared/deep VALID33/33. Owner-approved identified D:
updater card staged4/4 hash readback, no format/media changes/camera access or
flash. Separate D4 rollback20261016000002 retained on laptop. See
`../firmware/D5_VI_RELEASE_AND_CARD_20261016.md` for exact source/artifact pins.

## Decision

This project is **not** a clean-room firmware rewrite.

```text
OBSERVE STOCK
-> REUSE STOCK
-> AUGMENT
-> BENCHMARK
-> REPLACE SELECTIVELY
```

Hard preservation targets:

```text
stock recorder/media path
stock app compatibility
stock Wi-Fi behavior
stock camera/ISP path
stock M4 display
stock ADAS modules that benchmark well
persistent calibration/config compatibility
```

## Current architecture

```text
                       STOCK C2M
       ┌────────────────────────────────────┐
       │ camera / ISP / recorder / cardv    │
       │ stock app backend / Wi-Fi          │
       │ stock ADAS                         │
       │ stock M4 display                   │
       └───────────────┬────────────────────┘
                       │ observe/reuse
                       v
                 C2M ENHANCEMENT
       ┌────────────────────────────────────┐
       │ StockADASProvider                  │
       │ DisplayState / M4Adapter           │
       │ RoadIntelligence                   │
       │ VietMap API / VIETMAP LIVE         │
       │ VoiceManager                       │
       │ Web Admin / Diagnostics            │
       │ Safe modular updater               │
       │ TPMS provider                      │
       │ optional CustomADASProvider        │
       └────────────────────────────────────┘
```

Enhancement-service failure must not stop stock recording or stock-app use.

## Field status — 2026-10-16

Owner has flashed the EN-preserving D4-debug candidate. Stock recording/app/
Vietnamese ADAS are owner-reported normal. Dedicated AP-only modern SSH and
finite native ARM RAM observers have executed successfully; no stock/M4/GPS
UART control was used in those diagnostics.

- Corrected GPS reader:10/10 live samples decoded, freshness acquired. The
  installed old D4 producer is unchanged; real advisories/browser beep remain
  unaccepted. A finite shadow later loaded the valid12708-record DB and completed
  on hardware, but had two transient stale polls with unresolved cause. This
  is not stable corrected runtime or deployment; see
  `../firmware/D4_SHADOW_HARDWARE_20261016.md`. Same-poll diagnostic shadow v2
  later passed Linux/Chrome and exact stock ARM/QEMU (`38842722272` attempt2 /
  `38842731209`), with local4/4 bundle readback. V2 then completed one notified
  hardware run:10/10 GPS reads OK, fresh/ready at2–10, no stale reproduced.
  This does not explain the old transient or establish continuous reliability.
  Installed D4 remains old and untouched; owner confirmed original functions
  normal. See `../firmware/D4_SHADOW_V2_HARDWARE_20261016.md`.
- AP+STA remains UNKNOWN: single/ordinary wiphy query advertises an empty
  interface-combinations payload. Exact RTL8821CS module has VIF code but no
  proven safe concurrent runtime. Do not force STA at the cost of AP.
- Bluetooth HCI/transport/RF and M4 3D speed/sign rendering remain unproven.
  M4 L0 link is now proven: RNDIS `usb0`, camera `.123` ↔ M4 `.129`, native
  legs to both `adas:26012` and `cardv:8080`. No injection was performed;
  L1 decode and any replay remain gated. See
  `../firmware/M4_TRANSPORT_L0_20261016.md`.
  Sniffer V2 build/QEMU passed (`38852345666`) but was HELD before upload:
  static review found invalid-offset/header leakage and Ethernet-padding
  payload errors, plus insufficient exact-run/current-link runner gates.
  Do not use V2 for hardware or treat its tests as successful capture proof.
  V3 fixes payload bounds, protocol-zero interface attach, nonblocking receive,
  actual output-byte budget and explicit prefix truncation/seq/ack metadata.
  Final V3 Linux7/7 + ARM/QEMU/import gates passed (`38857027117`, source
  `b40a276`); ELF11736B `58259c85…640f4e`, exact bundle/source readback and
  local pinned-runner checks passed. The13:14 SSH refusal was left alone;
  owner later reconnected/reported normal functions for a fresh session.
  V3 then ran once at13:22:15 records,768B retained payload, all8 data records
  truncated, exit0 and exact RAM cleanup verified. Native recording/AP/D4 and
  all three observed M4 legs remained healthy in pre/post snapshots; owner
  confirmed normal with M4 in3D. ADAS-owned24012 carries a `lane` prefix in this
  sample;26012 has `ped`/`vehicle` prefixes. No complete frame/schema,8080
  status message, speed/sign widget or injection proven. Hardware access stopped;
  see `../firmware/M4_SNIFF_V3_HARDWARE_20261016.md` and
  `../firmware/M4_SNIFF_L1_PLAN_20261016.md`.
  V4 final CI `38866208565` passed; exact source/bundle readback then one
  owner-confirmed12s native capture retained42 full payload records,0 truncated.
  Offline decoded39 complete server messages:10 GPSSpeed,16 laneWarningRes,
  5 vehicleWarning,4 vehicleMeasure,2 pedestrians and2 additional unknown ped
  keys (redacted). Native GPSSpeed emission to M4 link now proven, not3D render.
  **V4 unchanged-connection gate FAILED:**26012 peer port changed, with a valid
  new HTTP Upgrade captured. Cause unknown; no retry/injection/extra WS client.
  Recorder/AP/D4 healthy in snapshots; owner reports normal/no M4 flicker.
  Hardware access stopped; see `../firmware/M4_SNIFF_V4_HARDWARE_20261016.md`.
  Offline follow-up now decodes original stdout directly with bounded HTTP
  Upgrade matching;2 additional ped messages identified as `pedWarning`
  (`ped_on`/`pcw_on`, bool/bool), receive schema only, replay still default-DENY.
  No M4 receiver binary/layout/widget control found; public C2M manual confirms
  safe-distance seconds, not speed-in3D support. Active value/render trial has
  NOT occurred: support is UNKNOWN, not disproved, and needing new firmware is
  not established. Native harmless setter+restore is being traced; saved USB
  `.2` descriptor `ff/42/01` matches ADB but no authorized readback is proven.
  Fresh16:10 owner-approved READ-ONLY sysfs check reconfirmed iface2 ff/42/01
  bulk04/85,512B, no adb binary/daemon; no USB transaction/native upload/UI
  change, recorder advanced, connections/D4 PID unchanged. Owner subsequently
  approved ONE finite active CNXN identify handshake. CI38881250082 passed;
  native16:59 request returned AUTH-required in7ms,31B TX, released/cleanup/exit0.
  **Preservation FAILED:**24012/26012 absent postflight;8080/recorder/AP/PIDs
  healthy in snapshots, owner reports M4 normal. No auth reply/key/shell/UI,
  no retry; see `../firmware/M4_ADB_AUTH_STOP_HARDWARE_20261016.md`.
  Owner later approved NEW standard one-public-key authorization request.
  CI38889073536/source141cbc6 passed; one17:56 request sent766B, waited33.271s,
  no response/no authorization/no visible dialog; USB released/RAM cleaned.
  All three native connections/recording/AP/PIDs/hashes preserved in snapshots;
  owner normal. Private key stayed on laptop; no shell/service/sign injection.
  Owner reconfirmed onlyONE button and NO touch: do not assume Android-style
  tap-Allow UI or invent hidden/input sequences. No retry/further camera access.
  GPS2D icon briefly unlit then owner reported GPS returned BEFORE prepared
  read-only diagnostic ran; cause UNKNOWN, no verified GNSS fault or repair.
  See `../firmware/M4_STANDARD_AUTH_HARDWARE_20261016.md`.
  EN/VI review found no demonstrated new M4 sign route; VI extra speed function
  is a tail-jump alias toWSSetGPSSpeed, not new widget evidence. No VI flash.
  See `../firmware/M4_RECEIVER_LAYOUT_GAP_20261016.md`,
  `../firmware/M4_ACTIVE_TEST_BOUNDARY_20261016.md` and
  `../firmware/M4_ADB_IDENTIFICATION_PLAN_20261016.md`,
  `../firmware/M4_STANDARD_AUTH_REQUEST_PLAN_20261016.md` and
  `../firmware/M4_EN_VI_RENDER_TEST_ASSESSMENT_20261016.md`.
  Owner photos/clarification confirm a conditional M4 top warning bar (mainly
  collision-related seconds), not a permanently absent toolbar. Neither that
  value nor advertising artwork proves3D speed/sign support; see
  `../firmware/M4_OWNER_VISUAL_FINDINGS_20261016.md`.
- Agent defaults remain read-only/bounded private RAM tests; no broad root
  commands, shared status writers, calibration/recorder changes or second
  cardv `:8080` observer.

Current evidence:
`../firmware/RAM_OBSERVERS_HARDWARE_20261016.md`,
`../firmware/RAM_DEBUG_ARM_PREPARATION_20261016.md`,
`../firmware/RTL8821CS_CONCURRENCY_STATIC_20261016.md`,
`../firmware/D4_RAM_SHADOW_EVALUATION_PLAN_20261016.md`.
Historical priorities below remain design context, not approval to replace
ADAS or activate unverified transports during the current debug work.

## Current owner priorities

### P0 — recovery and evidence

Before destructive experiments:

```text
full backup
persistent config backup
known-good EN recovery
UART/boot evidence where available
```

No bootloader/kernel changes during discovery.

### P1 — EN/VI ADAS regression

Known runtime truth:

```text
EN 2023-08-03 -> ADAS works
VI 2023-09-20 -> ADAS did not work on same unit
```

Static reverse has already proven:

```text
rootfs: 526/528 files identical
only cardv + sc7a20.ko differ in rootfs
ADAS subtree: 98/112 files identical
same ADAS symbol-name surface
six embedded CNN/model blobs are byte-identical EN vs VI
VI m0 encrypted model directory points to valid moved offsets
all +17,862 bytes of VI adas growth are outside model blobs
```

Current regression ranking:

```text
1. VI adas package/interstitial metadata or validation path
2. cardv / raw_adas runtime integration
3. output-only GPS/M4 regression if inference is actually alive
4. kernel / memory / driver integration
5. config/license/calibration interpretation
```

Most decisive safe experiment:

```text
working EN base + VI adas executable temporarily
```

No NAND replacement required.

### P2 — M4 reverse

M4 is a high-value stock asset and should be exhausted before considering replacement display hardware.

Static anchors already recovered:

```text
ADAS ScreenService default port: 26012
sdk_use_msgpack=true
libflow WebSocket binary transport
nested MessagePack envelopes
known semantic topics: vehicle / ped / lane
cardv WebSocket candidate port: 8080
cardv subprotocol: minieye-websocket
```

Physical transport remains runtime-unproven.

Required progression:

```text
Level 0 transport known
Level 1 passive decoder
Level 2 harmless stock replay
Level 3 semantic injection
Level 4 optional extended UI
```

Level 3 is already a major success because it permits:

```text
Stock ADAS + RoadIntelligence + VietMap + TPMS
                   -> DisplayState
                   -> M4Adapter
                   -> stock M4
```

### P3 — stock ADAS observability/reuse

Normalize stock outputs before replacing models:

```text
vehicles / tracking
pedestrians
lane / LDW
FCW / headway
lead distance
TTC / relative TTC
TSR / speed limit
warning states
```

Provider modes later:

```text
STOCK
CUSTOM
FUSED
OFF
```

### P4 — Web Admin

Admin/engineering UI, not stock-app replacement.

Initial scope:

```text
/status
/settings
/diagnostics
/logs
/update
/road-data
```

Keep stock app functional.

### P5 — RoadIntelligence / VietMap / Voice / TPMS

Road intelligence must work without a phone using local GPS + compact offline DB.

VIETMAP LIVE provides optional navigation state after runtime BLE protocol reverse.

Voice safety alerts remain local.

TPMS is provider-neutral:

```text
ITpmsProvider
|- RF433
|- BLE
`- OBD when available
```

## Runtime evidence workflow now in repo

Read-only capture on C2M:

```sh
sh tools/device/collect_baseline.sh en_good_m4_on
sh tools/device/collect_baseline.sh en_good_m4_off
```

Offline comparison/classification:

```sh
python3 tools/device/compare_baselines.py <left> <right>
python3 tools/device/classify_adas_state.py <capture>
python3 tools/m4/discover_transport.py <m4_off> <m4_on>
```

Only after the actual M4 interface is identified:

```sh
sh tools/device/capture_interface_pcap.sh <verified-interface> <label> 60
```

## ADAS runtime classes

```text
A process absent
B crash/restart loop
C alive, input/ringbuffer path suspect
D alive, inference/IPU/model init suspect
E inference alive, warning suppressed
F ADAS alive, display/audio path suspect
```

Do not patch before classifying the runtime failure.

## Update architecture

Keep update channels independent:

```text
system firmware
AI model
road DB
web UI
config
```

Normal feature/model/data updates must not use the destructive stock full-NAND updater.

## Hard rules

```text
EVIDENCE-FIRST
REUSE-FIRST
READ-ONLY-FIRST
STOCK-COMPATIBILITY-FIRST
NO FULL FLASH FOR APP/MODEL/DATA UPDATES
NO BOOT-CHAIN CHANGES EARLY
NO INVENTED PROTOCOL FIELDS/PORTS
NO REPLACEMENT DISPLAY BEFORE M4 REVERSE IS EXHAUSTED
NO REPLACEMENT AI WITHOUT A/B BENCHMARK
NO SAFETY-CERTIFICATION CLAIMS
```

## Acceptance gates before major replacement

```text
A recovery proven
B stock app baseline proven
C M4 physical/logical transport proven
D M4 passive decode proven
E M4 rendering responsibility proven
F harmless replay/injection proven where feasible
G stock ADAS output observability proven
H read-only web admin coexists with stock services
I offline RoadIntelligence works
J VietMap runtime protocol sufficiently decoded
K voice priority system works
L AP+STA verified or fallback selected
M TPMS provider produces normalized state
```

## Source-of-truth documents

```text
docs/C2M_EN_VI_OWNER_DELTA_REVIEW.md
docs/firmware_en_vi/
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md
docs/reverse/CARDV_STATIC_DIFF_V1.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/runtime/DEVICE_BASELINE_CAPTURE.md
docs/runtime/ADAS_FAILURE_CLASSIFICATION.md
```

When an older planning document conflicts with current reverse evidence, the evidence-backed documents above win.
