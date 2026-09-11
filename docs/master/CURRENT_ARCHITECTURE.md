# C2M Enhanced Firmware — Current Architecture

**Status:** active owner architecture, updated after EN/VI deep reverse  
**Known-good baseline:** `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`  
**Regression/donor build:** `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`

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
