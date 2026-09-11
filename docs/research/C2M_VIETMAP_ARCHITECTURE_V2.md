# C2M VietMap architecture V2 (no extra HW unless proven)

Research-only. Candidate A/B untouched. M4 writes blocked until gates pass.

## Decision

**Architecture A — direct Android → C2M Linux over Wi-Fi** (companion posts neutral `nav/1` to C2M AP new port → `NavigationProvider → DisplayState → M4Adapter → stock M4`).

```text
VietMap LIVE (phone, untrusted, optional)
  ↓ semantic state (companion app, user installs)
C2M Wi-Fi AP (existing wlan0/hostapd/8821cs) + TCP/WS :new-port (not 26012/8080)
  ↓ allowlist + seq/crc + rate-limit + stale-expire (~3s)
c2m-enhance NavigationProvider → DisplayState arbiter (ADAS overrides nav)
  ↓ M4Adapter (~2Hz, policy-gated)
stock M4  (+ local voice; framebuffer only on M4 gate failure)
```

Scores (1–5, 5=best): A 4.9 ≫ D 3.4 > C 3.1 > B 2.5 (usefulness/effort/risk/reverse-dep/compat/latency/maintainability/usability; full table in main V2 §18). B (clone ProMax BLE peripheral + 8a7e + VietMap accessory) rejected V1 (effort 1, risk 1, maintainability 1). C (native C2M BLE) blocked: no BT stack in C2M evidence (NOT SUPPORTED). D (external ESP) only if triple-gate proves true (below); today NOT JUSTIFIED.

Hardware-dependency tree:

```text
IP nav on HUD? NO (HIGH) → BLE-only? YES (intent HIGH; values UNKNOWN)
 → companion→Wi-Fi possible? YES → A, no MCU ← V2 PATH
 → NO → C2M BLE usable? NO (CONFIRMED absent) → D only after 10+ repeatable BLE events; encrypted/pinned → stay A offline.
```

## M4 mapping (PROVEN/PROBABLE/UNKNOWN/NOT SUPPORTED)

Speed PROBABLE (GPSSpeed schema PROVEN, L2 DENY, unit UNKNOWN); limit UNKNOWN (TSR `--enable_tsr=false`, fusion `cam≥0.6>vm≥0.6>osm≥0.4` ready, M4 slot missing); arrow/distance/road UNKNOWN (ADAS dist must NOT be repurposed); lane PROBABLE-for-LDW / UNKNOWN-for-nav (`laneWarningRes` PROVEN); camera UNKNOWN (`Edog=ON/SpeedCamAlert=OFF` CGI only); hazard PROBABLE-local (FCW/HMW WAVs + `ScreenAudioMsg`); clock UNKNOWN; GPS PROVEN-schema/PROBABLE-display (`GPSLevel/GPSSpeed/SendGPSInfoToScreen`); BT NOT SUPPORTED; Wi-Fi PROVEN-schema (`SendWifiStatusToScreen/ClientConn`); trip UNKNOWN; compass NOT SUPPORTED (SC7A20 IMU only); ADAS warnings PROVEN-observable/PROBABLE-displayable (`vehicleWarning/Measure/pedestrians/laneWarningRes/AdasStatus/HeavyCalibStatus` + `NormalizeStock/DisplayState`).

Plumbing: `ScreenService:26012` default CONFIRMED; libflow outer `{time,source,topic,data}` + subscribe CONFIRMED pattern, inner `{frame_id,time,key,data}` CONFIRMED; path/source/iface/proxy UNKNOWN. `cardv:8080/minieye-websocket` HIGH; 9 JSON templates CONFIRMED. L2 ALLOW=`DispBrightSet/StorageStatus/ScreenModeSet/ClientConn`, DENY rest; L3 BLOCKED. `usb0/192.168.32.123/usbnet` CLUE ONLY.

## M4 vs framebuffer

`mmap_reserved=fb,8MiB,VI-only` display HIGH, CMA/IPU/consumption UNKNOWN. M4: proven optics, LOW-MED complexity, LOW pixel load, HIGH reversibility, LOW risk if gated. FB: free layout, HIGH bring-up (fonts/YUV/CMA contention on SSC8838G), MED-HIGH risk, unproven sunlight/mech. Rule: M4 through L0/L1/responsibility/L2/L3; FB only on documented M4 failure. First FB step read-only (`/proc/cmdline|meminfo|iomem`, `/dev/fb*`, `dmesg|grep fb`).

## Audio / GPS / connectivity / boot

Audio: stock speaker+WAVs (FCW/HMW identical, VI re-recorded) V1; new `VoiceManager` needs ALSA/MI_AO probe, priority FCW>PCW/LDW>limit>nav; phone audio nav-only; reimplement `beep_limit_change` behaviour only.
GPS: C2M NMEA refactor CONFIRMED (EN→VI `nmea_pack_type1` 388→616, `SendGPSInfoToScreen` 112→92); exposure `GPSLevel/GPSSpeed` on `:8080`; node/baud UNKNOWN. Phone GPS enrichment only; no NMEA forward yet; C2M never routes/feeds back.
Connectivity: AP+TCP/WS-new-port LOW/LOW; STA AP-XOR MED; native BLE HIGH cost; ESP pattern exists as proposal only; USB CLUE ONLY.
Boot: keep `wifi/rcInsDriver.sh` EOF hook (`/customer/c2m/c2m-idle &`, hash-gated); V1 one `c2m-enhance` daemon (Tick 200ms/stale 500ms) + isolated `c2m-web` + optional serial thread; watchdog restarts enhance only.

## Neutral model + offline-first + safety

`NavigationState{active,ts,seq,source,conf,next{arrow,dist,road,lane},limit,cam/hazard/gps}` RAW units, seq+ts required, stale→inactive, range/allowlist/2Hz rate checks. OFFLINE (GPS+OSM+TSR+ADAS always) / PHONE (LIVE optional) / INTERNET (bounded cache). Phone untrusted; ADAS overrides nav; nav never sets safety fields; kill-switch to stock DisplayState; OTA/flash separate from runtime input.

## Product / maintainability

Value over dashcam/HUD-phone/Android-Auto: single windshield record+ADAS+limits+optional-nav, ADAS+nav fusion, hazard-auto-clip (all FUTURE concepts). Maintain: vendor-neutral `nav/1` envelope+fixtures, DisplayState/M4Adapter boundary, fresh ports, no boot-chain change, config backup, Gate F BLOCKED. Risks: VietMap/app/BLE-permission/firmware/cloud drift → mitigated by neutral envelope + fixtures + replaceable transport.
