# ProMax LIVE nav value-plane V1 (analysis-only, no HW touched)

Baseline (V2, accepted): mgmt `FFF0/FFF1/FFF2/FFF3/LOAD/DTBK/JPEG/IMG_START/END/VIETMAP_HUD` CONFIRMED; nav-intent `8a7e0001/2/3` HIGH; handshake `pong/dev/want/can/rate:4/transport:ble` CONFIRMED. Target of V3: live packets carrying `spd/lim/trn/dst/street/lan/eta/rmin/rkm/avg/alerts`.

Tooling this pass: `tools/reverse/promax/find_gatt_handlers.py`, `find_nav_state_xrefs.py`, `nav_protocol_emulator.py`; no Ghidra/IDA/rizin/objdump/esptool present (verified absent); pure-python static analysis only. No C2M firmware/M4/candidates touched.

## 1. Headline result

- Live framing: **PARTIALLY RECOVERED (HIGH for key set + JSON shape, UNKNOWN for values)** — a NUL-delimited bare-key table `unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/hi` + `false/null` literals + JSON escape table `//""\\b.f.n.r.t.` proves a **custom minimal JSON parser** for a live object with `unix` timestamp, present in classic + XL only.
- Value types/units/enums/stale: **NOT RECOVERED**. No numeric live values exist in any image (values are phone-supplied at runtime).
- GATT roles for 8a7e: **UNKNOWN** (no characteristic-creation/callback strings; disassembler absent).
- End-to-end callback chain: **NOT RECOVERED**.

## 2. The bare-key table (new, highest-confidence V3 finding)

Classic `firmware.bin` @0x18281C and XL `guition_ota_v1.bin` @0x68F7A (identical sets, linker order differs):

```text
classic:  false\0 null\0 unix\0 nav\0 spd\0 lim\0 trn\0 dst\0 exit\0 eta\0 rmin\0 rkm\0 avg\0 alrs\0 hi\0 Overflow ######\0
XL:       hi\0 unix\0 nav\0 spd\0 lim\0 trn\0 dst\0 exit\0 eta\0 rmin\0 rkm\0 avg\0 alrs\0 Overflow ######\0
```

Evidence:
- `\x00unix\x00` x1 classic@0x18281B + XL@0x68F7C; `\x00hi\x00` x1 classic@0x18284F + XL@0x68F79; `\x00alrs\x00`/`\x00nav\x00`/`\x00spd\x00` x1 same images, **zero in C3/S3/no_bl/adapter/beta** — CONFIRMED (`v3_final.py`, `v3_bare2.py`).
- Preceded by `//""\\b.f.n.r.t.\0false\0null\0` (classic@0x182800, XL@0x68E27) — JSON string-unescape map + literals — HIGH-CONFIDENCE custom JSON parser (explains zero `cJSON/ArduinoJson/deserializeJson/json_parse` hits in all images — CONFIRMED absence).
- Followed by `Overflow ######` + doubles region (0x18285C+: `3FB9…/3F84…/40…/41…`) + `/littlefs/LITTLEFS Mount Failed` — numeric defaults + FS, not code — MEDIUM.
- Handshake `want` has 13 fields incl `st/avgL/lan`; bare table has 12 keys incl `unix/hi` but **excludes `st/avgL/lan`** (NUL-delimited `lan/avgL/st` zero everywhere; quoted only in handshake) — CONFIRMED. So live object ≠ want list: `st` (street), `avgL`, `lan` have no parser slot in this build (handled elsewhere / newer / display-only — UNKNOWN).

## 3. JSON vs binary (§5)

**JSON (HIGH for live shape):** bare keys + false/null + escape table + handshake JSON + `hi/unix` framing + zero protobuf/nanopb/CBOR/MessagePack/TLV strings in all images. No `strcmp/strstr/sscanf/atoi/strtol/strchr/strtok` in classic (only `strncmp`×1 VFS + `memcmp`×1 BT-stack, both IDF internals with proven non-parser contexts) — consistent with a hand-rolled key matcher over NUL table, not libc string dispatch. Binary/TLV: no evidence (no magic/len/CRC around table; surrounding 0x18261C–0x1827DC is addresses/code-like, not a binary field table) — LOW/UNKNOWN. Verdict: **live packets are JSON objects with unix+hi+nav keys (HIGH for shape); value encoding UNKNOWN**.

## 4. Dispatch (§6)

Quoted keys `"nav"…"lan"` occur **exactly once each** (classic@0x180299–0x180334 block; XL@0x68B6A–0x68C05), except `"eta"`×2 = want+can inside ONE handshake JSON — CONFIRMED (`v3_keys.py`). **No second quoted occurrence anywhere** → no string-keyed parser/dispatch/render site. Combined with bare NUL table → dispatch is via bare-table lookup (hash/index/memcmp over short keys), numeric field IDs, or a separate characteristic per field — all UNPROVEN without disassembly. Dispatch table: **NOT RECOVERED**.

| Packet/field | Parser function | Destination state | Type | Proven? |
|---|---|---|---|---|
| unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/hi | UNKNOWN (bare-table matcher hypothesized) | UNKNOWN | JSON number/string presumed | NO — key set HIGH, all else UNKNOWN |
| st/avgL/lan | UNKNOWN (no bare slot) | UNKNOWN | UNKNOWN | NO |

## 5. State object, display consumers, enums, limits, rate (§7–§13)

- State struct offsets/sizes/writers/readers/resets: **UNKNOWN (NOT RECOVERED)** — no ELF/symbols; no second key occurrence to anchor writers. Do NOT invent struct.
- Display consumers (`show_speed/speed_limit_offset/show_number_marker/show_clock/screen/beep_limit_change`): key lists proven (`/config.txt` classic@0x18064D; DTBK defaults), but render functions reading live state: **NOT RECOVERED** (no xref without disassembly).
- Turn encoding (`trn` values for left/right/straight/uturn/roundabout/exit/arrive): **UNKNOWN** — zero `left/straight/roundabout/uturn/arrow/lane/camera` in classic (only `right`×12 copyright-type noise, `beep`×5 limit-beep); XL `left`×10/`arrow`×1 are AAC-audio/LVGL-calendar noise with proven non-nav contexts — CONFIRMED absence of nav enums.
- Lane (`lan`): **UNKNOWN** — no `lan` NUL slot, no mask/shift/loop evidence near table; `lane` zero in classic.
- Alerts (`alrs/avg/avgL`): **UNKNOWN** — no camera/red-light/school/hazard/police enum strings; XL `buzzer_enabled/delay_warning/blink_screen/mute` are settings keys (@0x68E99–0x68F09), not values.
- Limit (`lim` units/sentinel/offset application/overspeed): **UNKNOWN** — `speed_limit_offset/beep_limit_change` policy keys proven, value path not.
- Rate/timeout: `rate:4` meaning **UNKNOWN** (4 Hz vs 4 s vs version vs batch — no timer proven; `timeout`×5 classic are exception/BLE-stack contexts, e.g. @0x257CA6 unwinding; `stale/heartbeat/keepalive` zero; XL `keepalive`×2 unexamined). Loss-of-data behavior (hide nav/clear limit/retain street): **UNKNOWN**.

## 6. Cross-arch + version oracle (§14–§15)

- Bare live table: classic + XL full/OTA ONLY; C3/S3/no_bl/adapter/beta/NONE — CONFIRMED. 8a7e block: classic + XL ONLY (x3 each; C3/S3/beta/adapter/no_bl zero) — CONFIRMED. `pong`: classic + XL ONLY — CONFIRMED. So **nav stack (UUIDs + handshake + live parser) ships in classic ESP32 + XL S3, stripped from C3/S3/beta/adapter/no_bl** (beta explicitly strips vs stable v7.6 — V2 HIGH finding reinforced).
- XL bare order (`hi` first) vs classic (`unix` first) = linker order only; sets identical — HIGH.
- `VIETMAP_HUD` present in all classic-family builds (incl adapter/C3/S3/beta) but XL uses `Promax XL` (x2) — device-name ≠ protocol proof — CONFIRMED.
- Web pages (`index*.html`, `baodiem.html`, both families): **zero `8a7e` hits** (FFF0/VIETMAP_HUD only) — CONFIRMED — nav services are app-only, never browser-configured.
- No APK/AAB/Kotlin/Java/Flutter app source in either upstream file set (HTML+manifests+firmware only; `git ls-tree` file sets confirm) — CONFIRMED absence (see phone-side doc).

## 7. GATT structures + tasks (summaries; details in companion docs)

- Static attr-db (`esp_gatts_attr_db_t`/NimBLE equivalents/permission bitmask/handler pointers/buffer lengths): **NOT RECOVERED** — zero `esp_gatts_attr_db/esp_ble_gatts_create_service` in classic; `createService`×1 + `indicate`×1 + central APIs (`getServices/registerForNotify/writeValue/readValue/Dump scan/startAdvert`) prove **dual-role firmware (peripheral advertise + central scan)** — HIGH — but characteristic properties/direction/callbacks/MTU/CCCD for 8a7e: **UNKNOWN**.
- FreeRTOS: `xTaskCreate`×1/`xQueueReceive`×2/`vTaskDelay`×1 classic (names stripped except C3/S3 `ObdBleTask`, adapter `SupervisorTask`); `xQueueSend/xTimerCreate(create/xTaskCreatePinnedToCore` zero classic (XL has pinned+timer) — task graph edges NOT recoverable statically; BLE→queue→parser→display chain: **NOT RECOVERED**. OBD central block (`AT D/Z/E0/S0/AL/ST/SP/TP/RV/UNABLETOCONNECT/NODATA/IOS-Vlink/Viecar/OBD BLE/FAKE_OBD/18F0/2AF0/2AF1`) is contiguous and **distinct** from 8a7e/nav block — HIGH (separation proven).

## 8. Compressed tables (§18)

spiffs-labeled partitions + `/littlefs` + `LITTLEFS Mount Failed` + `/logo.jpg//poi.jpg/[JPG] PSRAM` + doubles region near bare table inspected; no hidden enum/icon tables proven; high-entropy 0x18261C–0x1827DC region is unexamined binary (code or tables — UNKNOWN, needs Ghidra). Absence of enums NOT concluded from strings alone — but no further ASCII structure recoverable offline beyond §2.

## 9. Success level (§24)

- LEVEL 0 (handshake): **ACHIEVED** (V2).
- LEVEL 1 (8a7e roles/properties): **NOT ACHIEVED** — UNKNOWN.
- LEVEL 2 (live framing): **ACHIEVED (partial)** — JSON shape + 13-key set + unix/hi + escape/false/null/overflow HIGH; value types/lengths/MTU/CCCD UNKNOWN.
- LEVEL 3 (field schema): **NOT ACHIEVED** — key set without types/units/sentinels.
- LEVEL 4 (turn/lane/alert enums): **NOT ACHIEVED** — UNKNOWN.
- LEVEL 5 (emulator parses synthetic live): **ACHIEVED for shape only** (`validate` accepts key set, refuses invented keys; values UNVALIDATED by design).
- **Overall: LEVEL 2 (partial, with LEVEL 1 gap).**

## 10. Sniff gate (§25)

Requires handlers recovered AND parser paths inspected AND version-diff exhausted AND live still missing. Status: handlers NOT recovered (no disassembler available — proven absent), parser inspected at string/structure level only (not control-flow), version-diff exhausted at string level, live values+enums+units still missing. **Gate NOT met → hardware sniff NOT justified yet.** Next is offline Ghidra/IDA Xtensa+S3 disassembly (attr-db + bare-table xrefs + callback chain), not capture.

## 20 answers (§27, condensed; UNKNOWNs explicit)

1. 8a7e0001/2/3: three custom 128-bit IDs in one nav block (classic@0x1803D7/FC/21, XL@0x68C56/7B/AA) — existence CONFIRMED, service-vs-char UNKNOWN.
2. Which side writes: UNKNOWN (no props/callbacks).
3. Which side notifies: UNKNOWN.
4. Properties: UNKNOWN.
5. Callback for incoming nav: NOT RECOVERED.
6. JSON or binary: JSON HIGH for live shape (§3); binary LOW.
7. Live frame format: JSON object with keys {unix,nav,spd,lim,trn,dst,exit,eta,rmin,rkm,avg,alrs,hi} + false/null literals, LF-likely (handshake precedent), lengths/checksum UNKNOWN.
8. Packet-type field: `hi` + `unix` hypothesized framing/type-time (LOW); `t`-style discriminator for live NOT proven.
9–15. speed/limit/turn/distance/street/lane/alerts encoding: key slots HIGH, value types/units/enums NOT RECOVERED (all UNKNOWN); `st/avgL/lan` have handshake intent but no bare slot (UNKNOWN handling).
16. `rate:4`: UNKNOWN (Hz/seconds/version/batch unproven).
17. Stale timeout: UNKNOWN (no timer proven).
18. VietMap direct BLE: UNKNOWN (leaning insufficient evidence — see phone-side doc, verdict C).
19. Companion required: UNKNOWN (no APK; web never touches 8a7e).
20. Translatable to C2M NavigationState now: key NAMES only (HIGH) — values/semantics NO; do NOT map beyond key vocabulary.
