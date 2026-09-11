# ProMax / ProMax XL / VIETMAP HUD to C2M Feasibility V1

Research-only feasibility report. Evidence labels used throughout: **CONFIRMED**, **HIGH-CONFIDENCE**, **HYPOTHESIS**, and **UNKNOWN**.

## Executive verdict

**HIGH-CONFIDENCE:** Do not port or flash the opaque ProMax firmware onto C2M. Treat the upstream repositories as protocol and product-design evidence, not as reusable source code. The best architecture is a phone-assisted navigation input feeding C2M's existing normalized `DisplayState`, with output sent through the stock M4 only after passive protocol capture and harmless replay prove that route. Keep a Linux framebuffer/OSD renderer as the fallback.

The most practical first transport is the repository's already-proposed bridge: **VIETMAP LIVE on phone -> BLE -> ESP32-C3 bridge -> USB/UART -> C2M**. It isolates phone BLE behavior from the embedded Linux system and provides a controllable, observable boundary. The highest-value next experiment is a passive BLE capture from a real VIETMAP navigation session to a genuine ProMax/ProMax XL, correlated with screen changes and audio events.

## Scope and non-actions

- **CONFIRMED:** No Candidate A or Candidate B content was modified.
- **CONFIRMED:** No firmware was built, flashed, patched, or executed.
- **CONFIRMED:** Upstream repositories were cloned and inspected independently of their READMEs.
- **CONFIRMED:** This report is the only intended C2M repository change.

## Upstream identity, branches, tags, and history

| Repository | HEAD | Visible branches | Tags | Commit count | Assessment |
|---|---|---:|---:|---:|---|
| `kimdung/promax` | `fd581971ac86475763e1ac0380e9f5cb8c0630e6` | `main` only | none observed | 119 | **CONFIRMED** |
| `kimdung/promax_xl` | `f678b2c25b90df0989fa0ae2bf9e954b3de662ac` | `main` only | none observed | 53 | **CONFIRMED** |

**HIGH-CONFIDENCE:** The repositories are distribution/configuration repositories rather than complete firmware source trees. Their tracked contents are primarily Web Bluetooth configuration pages, ESP Web Tools manifests, and opaque firmware binaries. No build system or embedded application source tree was observed.

History gives useful product evolution evidence:

- **CONFIRMED:** ProMax history includes firmware-labelled changes such as `firmware 7.13`, `add 7.15`, `add 7.16`, `add 7.17`, and `add 7.18`, plus many opaque `daily commit` updates.
- **CONFIRMED:** Commit `653afff` introduced current-configuration loading, while `60c638b` introduced the `DTBK`-based raw configuration page and a Dasai Mochi firmware variant.
- **CONFIRMED:** Commit `172705a` added a separate adapter firmware and Web flasher.
- **CONFIRMED:** Commit `73b430e` added a beta firmware channel.
- **CONFIRMED:** ProMax XL history contains product-version commits through `add 2.24`; commit `d4a7539` is explicitly titled `scan service uuid`.
- **UNKNOWN:** There is no upstream tag structure tying every binary to a formal immutable release.

## Upstream content and dependencies

### Web-side dependencies

**CONFIRMED:** Configuration uses the browser Web Bluetooth API. Flash pages use ESP Web Tools manifests. The adapter flashing instructions reference Silicon Labs USB-to-UART VCP drivers, supporting an ESP-class serial bootloader workflow.

**CONFIRMED phone/browser requirements:**

- Desktop Chrome with Web Bluetooth is directly recommended.
- Android with a Web Bluetooth-capable browser is directly suggested.
- iPhone is directed to the Bluefy BLE browser application.
- **UNKNOWN:** No native Android or iOS application source exists in these repositories.
- **UNKNOWN:** Background operation, reconnect policy, screen-off behavior, and navigation notification permissions are not specified.

### Binary inventory

**CONFIRMED:** ProMax includes 4 MiB full-flash images, a 16 MiB variant, a 3,796,784-byte no-bootloader image, beta images, and an adapter image. ProMax XL includes four 16,711,680-byte full images and four OTA images around 5.9 MiB, split across Guition and Waveshare display variants.

**HIGH-CONFIDENCE:** The `E9` image magic observed in some images and the ESP Web Tools flow are consistent with ESP firmware packaging. Some full images begin with erased `FF` bytes because their first application or boot component is located at a nonzero flash offset.

**UNKNOWN:** Exact chip models, partition-table offsets, secure-boot state, flash-encryption state, signing keys, and OTA validation rules were not proven from the compact evidence set.

## Proven BLE configuration protocol

### GATT layout

| Purpose | UUID | Direction | Status |
|---|---|---|---|
| Device name filter | `VIETMAP_HUD` | advertisement | **CONFIRMED** |
| Private service | `0000fff0-0000-1000-8000-00805f9b34fb` | service | **CONFIRMED** |
| Notifications | `0000fff1-0000-1000-8000-00805f9b34fb` | HUD -> client | **CONFIRMED** |
| Command/config write | `0000fff2-0000-1000-8000-00805f9b34fb` | client -> HUD | **CONFIRMED** |
| File block | `0000fff3-0000-1000-8000-00805f9b34fb` | client -> HUD | **CONFIRMED** |
| Device Information service | `0000180a-0000-1000-8000-00805f9b34fb` | standard service | **CONFIRMED** |
| Firmware revision | `00002a26-0000-1000-8000-00805f9b34fb` | read | **CONFIRMED** |

### Command and notification exchange

```text
Client                                         HUD
  |-- connect to advertised name VIETMAP_HUD -->|
  |-- read 0x2A26 firmware revision ------------>|
  |-- subscribe FFF1 notifications ------------->|
  |-- write-without-response FFF2: "LOAD" ------>|
  |<------------- FFF1 UTF-8 config string -------|
  |-- write config string to FFF2 -------------->|
```

Exact proven command bytes:

```text
LOAD = 4C 4F 41 44
DTBK = 44 54 42 4B
```

**CONFIRMED:** Current configuration is requested by writing ASCII `LOAD` without response to FFF2. The response is decoded as text from an FFF1 notification.

**CONFIRMED:** Configuration is a semicolon-separated ASCII key/value string beginning with `DTBK`. A proven example assembled from the page defaults is:

```text
DTBK;display_rotation=2;show_clock=1;led_color=0xff0000;led_brightness=9;logo_text=MAPVIET;speed_limit_offset=0;welcome_text=;show_text_kmh=1;obd_scan_duration=0;night_brightness=5;show_speed=1;show_number_marker=1;beep_limit_change=0;screen=0;boot_screen_duration=0
```

**HIGH-CONFIDENCE packet interpretation:**

```text
Offset  Size      Meaning
0       4         ASCII discriminator "DTBK"
4       variable  Repeated ';key=value' fields
end     0 or N/A  No terminator, length supplied by BLE write
```

No CRC, checksum, sequence number, or length field is present in the Web client representation.

### Image transfer

```text
for offset = 0; offset < image_size; offset += 128:
    write up to 128 raw JPEG bytes to FFF3
    wait approximately 100 ms
write-without-response ASCII "DTBK" to FFF3
```

- **CONFIRMED:** Browser accepts JPEG files only.
- **CONFIRMED:** Maximum accepted browser-side file size is 100 KiB.
- **CONFIRMED:** Blocks are at most 128 bytes, written with response, with an approximately 100 ms pacing delay.
- **CONFIRMED:** End-of-transfer marker is ASCII `DTBK` on FFF3.
- **UNKNOWN:** There is no proven image header, total-length field, checksum, acknowledgement payload, resume mechanism, or atomic rollback.
- **RISK:** A JPEG containing the four-byte value `DTBK` is safe only if the receiver treats it as a terminator based on write boundaries, not a stream substring. Receiver behavior is unavailable.

## Runtime navigation protocol

**UNKNOWN:** The inspected Web pages prove management/configuration characteristics, not VIETMAP LIVE runtime navigation packets. No exact turn, distance, speed-limit, GPS, lane, camera, or audio runtime packet layout was proven.

**HIGH-CONFIDENCE:** Because both ProMax families expose the same device name and FFF0-FFF3 management scheme, they share a management-plane contract. This does not prove an identical navigation data plane.

**Do not conflate:**

```text
Proven: browser -> HUD configuration and JPEG upload
Unproven: phone navigation app -> HUD live guidance protocol
```

The absence of proven live packets is the main reason not to implement a direct C2M BLE client yet.

## Display logic and product behavior

Configuration fields prove the following reusable product concepts:

1. **CONFIRMED:** display rotation selection.
2. **CONFIRMED:** day and night brightness controls.
3. **CONFIRMED:** selectable color.
4. **CONFIRMED:** current speed visibility.
5. **CONFIRMED:** speed-limit offset and optional number marker.
6. **CONFIRMED:** clock visibility.
7. **CONFIRMED:** boot-screen selection/duration and user-uploaded JPEG assets.
8. **CONFIRMED:** optional beep on speed-limit change.
9. **CONFIRMED:** configurable welcome/logo text.
10. **CONFIRMED:** an OBD scan-duration setting.

**UNKNOWN:** Pixel dimensions, display bus, frame rate, anti-aliasing, font licensing, sensor-driven auto brightness, and whether navigation graphics are composed locally or transmitted as semantic states.

## Audio, GPS, connectivity, startup, and online/offline split

### Audio

- **CONFIRMED:** A `beep_limit_change` setting proves at least a local beep feature.
- **UNKNOWN:** Codec, amplifier, DAC/I2S/PWM path, voice assets, text-to-speech, priority mixing, and volume protocol.
- **Recommendation:** Keep C2M safety audio local and independent of phone connectivity. Do not claim ProMax voice portability without firmware source or captures.

### GPS

- **UNKNOWN:** No proven GPS or NMEA protocol is exposed by the configuration pages.
- **HIGH-CONFIDENCE:** The phone navigation app likely supplies route context, but whether speed and GPS are phone-derived, OBD-derived, or locally fused is unproven.
- **Recommendation:** C2M road intelligence remains functional from local GPS/offline data; phone navigation is optional enrichment.

### Connectivity

- **CONFIRMED:** BLE management plane and USB serial flashing exist.
- **HIGH-CONFIDENCE:** An ESP32-C3 BLE-to-USB/UART bridge offers the best observability and fault isolation for C2M V1.
- **UNKNOWN:** Wi-Fi, cellular, cloud endpoints, authentication, and background OTA are not proven.

### Startup

- **CONFIRMED:** Boot screen and boot-screen duration are configurable.
- **UNKNOWN:** cold-start time, reconnect deadlines, navigation-app launch coupling, and degraded-mode behavior.
- **Recommendation:** C2M must boot to stock-safe behavior without waiting for phone, BLE, network, or road database.

### Offline/online split

```text
OFFLINE / SAFETY-CORE
  local GPS -> road intelligence/cache -> DisplayState -> HUD/audio
  stock ADAS ---------------------------> DisplayState

OPTIONAL ONLINE/PHONE ENRICHMENT
  VIETMAP LIVE -> BLE bridge -> NavigationProvider -> DisplayState.navigation
  external road API -> bounded cache -> VietMapProvider
```

**HIGH-CONFIDENCE:** This split maximizes graceful degradation and avoids making safety warnings dependent on handset power, permissions, cellular coverage, or app lifecycle.

## C2M evidence correlation

- **CONFIRMED:** `docs/design/ROAD_INTELLIGENCE_DESIGN.md:5` requires C2M to run without phone/cloud.
- **CONFIRMED:** `docs/design/ROAD_INTELLIGENCE_DESIGN.md:39-41` distinguishes VietMap road/API data from the VIETMAP LIVE navigation protocol and proposes `VIETMAP LIVE -> BLE -> ESP32-C3 bridge -> USB/UART -> C2M`.
- **CONFIRMED:** `include/c2m/road/road_provider.hpp:49-63` implements priority `camera >= 0.6`, then VietMap `>= 0.6`, then OSM.
- **CONFIRMED:** `docs/firmware_en_vi/04_M4_SCREEN_DISPLAY_PATH.md:5,211` identifies stock M4 as potentially reusable and describes `VietMap -> DisplayState -> M4Adapter -> stock M4`.
- **CONFIRMED:** `docs/master/CURRENT_ARCHITECTURE.md:113-147` requires exhausting stock M4 reverse engineering before replacement display hardware.
- **CONFIRMED:** `docs/master/CURRENT_ARCHITECTURE.md:193-197` requires local GPS/offline road intelligence and local safety voice while treating VIETMAP LIVE as optional.
- **CONFIRMED:** `docs/master/CURRENT_ARCHITECTURE.md:268-281` prohibits replacement display before M4 reverse is exhausted and requires passive decode plus harmless replay before M4 writes.
- **CONFIRMED:** `docs/reports/2026-09-12_FLASH_READY_SPRINT1.md:96` explicitly blocks VietMap feature work until Candidate A/B foundation work is complete.
- **CONFIRMED:** Candidate A is byte-preserving; Candidate B remains blocked by the absence of a proven UBIFS writer. Neither should be altered for this research.

## Architectures A-D

| Model | Description | Feasibility | Safety isolation | Maintainability | Product value | Overall /5 |
|---|---|---:|---:|---:|---:|---:|
| A | Directly reuse/modify ProMax firmware or hardware as C2M HUD | 1 | 2 | 1 | 2 | **1.5** |
| B | C2M Linux talks BLE directly to VIETMAP LIVE and renders through stock M4 | 3 | 3 | 3 | 5 | **3.5** |
| C | Phone -> BLE ESP32-C3 bridge -> USB/UART -> C2M -> `DisplayState` -> stock M4 | 4 | 5 | 4 | 5 | **4.5** |
| D | Same bridge/input, but Linux framebuffer/OSD drives a replacement/alternate display | 3 | 4 | 4 | 3 | **3.5** |

### Model A

**Verdict: reject.** Binary-only firmware, unclear licensing, unknown hardware coupling, and no maintainable source boundary make this unrealistic and hazardous.

### Model B

**Verdict: future simplification, not V1.** It avoids bridge hardware but binds Linux to phone BLE quirks and an unproven runtime protocol. Use only after captures establish stable semantics and reconnect behavior.

### Model C

**Verdict: best architecture.** It follows current C2M design, preserves stock M4 investment, and gives a passive capture point plus watchdog-resettable isolation.

### Model D

**Verdict: rollback/fallback architecture.** A Linux framebuffer/OSD renderer is attractive if stock M4 transport or rendering cannot be safely controlled. It carries mechanical, optical, thermal, brightness, and certification cost.

## Stock M4 versus Linux framebuffer/OSD

| Criterion | Stock M4 | Linux framebuffer/OSD |
|---|---|---|
| Existing optics/enclosure | **HIGH-CONFIDENCE advantage** | New hardware risk |
| Known transport | **UNKNOWN** pending reverse engineering | Depends on existing Linux display path |
| Product integration | Best if protocol proven | Potentially less integrated |
| Recovery isolation | Must prove harmless replay | Can be process-supervised |
| Rendering freedom | Unknown/limited | High |
| Schedule | Capture-dependent | Driver/hardware-dependent |

**Decision rule:** Stay with stock M4 through passive identification, decode, responsibility mapping, and harmless replay. Switch to framebuffer/OSD only after a documented M4 gate fails.

## Safety isolation

```text
Phone/VietMap
    |
    | BLE, untrusted and optional
    v
ESP32-C3 bridge
    |  framing + rate limits + allowlist + heartbeat
    |  USB/UART, no firmware-write command exposed
    v
C2M navigation provider
    |  validation + stale timeout + confidence
    v
DisplayState arbiter
    |  stock ADAS/safety retains priority
    +--> M4Adapter --> stock M4
    `--> local audio
```

Required controls:

- Navigation packets are data-only and cannot invoke C2M/proMax flashing.
- Reject out-of-range speed, distance, and enum values.
- Monotonic sequence or timestamp at the bridge boundary.
- Stale phone state expires to no-navigation display.
- Rate-limit display updates and audio announcements.
- Stock ADAS and local warnings override phone-originated decoration.
- Hardware or process watchdog resets only the bridge/provider, not the base ADAS stack.
- Capture and replay begin with passive or harmless states, never critical warnings.

## Licensing and reusable components

- **UNKNOWN:** No explicit software license was observed in the tracked upstream inventories. Therefore, source, HTML, images, and firmware should be treated as all-rights-reserved unless permission is obtained.
- **UNKNOWN:** Firmware dependencies and their corresponding notices/source offers are not available from the evidence inspected.
- **CONFIRMED:** ESP Web Tools and browser APIs are external mechanisms, not evidence that the firmware itself is open source.
- **Recommendation:** Reimplement only independently observed wire semantics and generic product behavior. Do not copy firmware, artwork, text assets, fonts, or opaque binaries into C2M.
- **Potentially reusable with normal compliance review:** C2M's own `DisplayState`, provider interfaces, road-fusion implementation, test patterns, generic BLE/serial libraries chosen independently, and ESP32 bridge infrastructure developed from scratch.

## Top realistically portable features

1. **Day/night brightness and visibility policy.** Portable as C2M display-state configuration, independent of ProMax code.
2. **Speed plus speed-limit presentation with offset policy.** Fits existing C2M road fusion.
3. **Optional speed-limit-change beep.** Implement locally with rate limiting and priority rules.
4. **Boot/welcome screen policy and duration.** Recreate with original assets only.
5. **Semantic navigation state integration.** Turn icon, distance, road/lane hints after live protocol capture, normalized into `DisplayState.navigation`.

## Main blockers

1. **UNKNOWN live navigation protocol.** Management GATT is proven; real-time VIETMAP LIVE frames are not.
2. **UNKNOWN stock M4 physical/logical transport and rendering responsibility.** No writes should occur before passive capture and harmless replay.
3. **Licensing/source availability.** Opaque firmware and absent upstream license prevent maintainable code reuse.

Secondary blockers include unknown phone background/reconnect behavior, unknown audio path, missing hardware captures, and Candidate B's UBIFS tooling gate.

## Phased roadmap

### Phase 0: preserve flash foundation

- Work: complete Candidate A bench validation and Candidate B UBIFS tooling separately; make no ProMax integration change.
- PASS: base image behavior and rollback are proven on hardware.
- Risk: feature work obscures foundational failures.
- Rollback: remain on known-good stock image.

### Phase 1: passive phone/HUD capture

- Work: capture BLE advertisements, service discovery, connection parameters, all GATT traffic, phone logs/screens, display video, and audio timeline during scripted routes.
- PASS: at least ten semantic events repeat with byte-stable or explainable packet mappings across reconnects.
- Risk: encryption, app-version drift, or hidden pairing.
- Rollback: disconnect sniffer/bridge; genuine phone and HUD remain unchanged.

### Phase 2: offline parser and corpus

- Work: write corpus fixtures and a read-only decoder; label unknown bytes rather than guessing.
- PASS: deterministic decoding with malformed/stale input rejection and no device access.
- Risk: overfitting one route/version.
- Rollback: retain captures; discard decoder revisions.

### Phase 3: ESP32-C3 receive-only bridge

- Work: subscribe to phone/HUD traffic where technically permitted and emit a versioned, checksummed serial envelope to a host logger only.
- PASS: 60-minute drive log without crash, bounded latency, reconnect recovery, and zero writes to M4/C2M control paths.
- Risk: BLE role incompatibility or phone app requiring a specific peripheral identity.
- Rollback: unplug bridge.

Suggested new C2M-side envelope, explicitly not an upstream packet:

```text
A5 5A | version:u8 | type:u8 | length:u16le | sequence:u32le |
payload[length] | crc32:u32le
```

### Phase 4: C2M provider integration, no display writes

- Work: bridge parser -> `NavigationProvider` -> logged `DisplayState.navigation` shadow output.
- PASS: validated state, stale timeout, rate limits, and replay tests pass; stock ADAS unchanged.
- Risk: priority inversion or stale guidance.
- Rollback: disable provider via configuration.

### Phase 5: stock M4 passive reverse

- Work: follow existing M4 capture plan and correlate stock ADAS events with transport traffic.
- PASS: physical interface, framing, rendering responsibility, and harmless states are proven.
- Risk: electrical damage or false warning injection.
- Rollback: passive probes only; remove probes.

### Phase 6: harmless M4 replay

- Work: replay noncritical clock/blank/decorative states under bench isolation.
- PASS: deterministic render, watchdog stability, and clean restoration to stock sender.
- Risk: bus contention or latched state.
- Rollback: power cycle to stock and disable injection harness.

### Phase 7: limited navigation display

- Work: allow validated turn/distance states; no safety-critical warnings from phone.
- PASS: route correlation, disconnect degradation, audio priority, startup, and soak tests.
- Risk: distracting or stale information.
- Rollback: feature flag to stock-only `DisplayState`.

### Phase 8: framebuffer/OSD fallback only if M4 gate fails

- Work: prototype display timing, sunlight readability, thermal behavior, startup, watchdog, and physical fit.
- PASS: equal-or-better legibility and safe boot/recovery without disrupting stock ADAS.
- Risk: major hardware/product redesign.
- Rollback: restore stock M4 assembly.

## Product value and maintainability

**HIGH-CONFIDENCE:** The valuable product is not a ProMax firmware transplant. It is a C2M-native, offline-first driver-information layer that can accept optional VIETMAP navigation while preserving local ADAS, road intelligence, audio, and stock display value.

Maintainability requirements:

- Provider/display contracts remain vendor-neutral.
- Protocol versions and captures are test fixtures.
- Every unknown field retains an explicit unknown label.
- Phone transport is replaceable without changing `DisplayState`.
- M4 and framebuffer implementations share the same renderer contract.
- OTA/flash domains remain completely separate from runtime navigation input.

## Final recommendation

Proceed with **Model C** as a staged experiment, not a product commitment. Use **BLE from the phone to an independently implemented ESP32-C3 bridge, then framed USB/UART into C2M**. Prefer **`DisplayState -> M4Adapter -> stock M4`** after its existing safety gates pass, with Linux framebuffer/OSD retained as a fallback. Do not reuse opaque upstream binaries or assets, and do not begin integration before the C2M flash foundation gates are closed.

## Single highest-value next experiment

Capture one controlled, repeatable real-device session containing: straight guidance, left/right turns, roundabout, lane instruction, distance countdown, speed-limit change, warning beep, reroute, phone screen-off, BLE loss, and reconnect. Record synchronized BLE packets, screen video, audio, GPS time, app/phone/HUD firmware versions, and event annotations. This single experiment resolves the largest blocker and determines whether direct Linux BLE, bridge-based BLE, semantic replay, and stock-M4 rendering are viable.
