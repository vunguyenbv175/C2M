# PROMAX / VietMap runtime protocol — deep reverse V2 (C2M, no extra HW unless proven)

Research-only. No firmware built/flashed/executed. No Candidate A/B modified.
Evidence labels: **CONFIRMED / HIGH-CONFIDENCE / MEDIUM / LOW / UNKNOWN**.
All offsets are flash-file offsets unless stated. SHA256 are full file hashes.

## 0. Repository / deliverable discipline — CONFIRMED

- Prior report commit (original local): `529c6eb302128721de407c552103f0ebb65a51c1` — `docs: assess ProMax VietMap HUD feasibility`
- Prior report commit (rebased + pushed): `1f176697110736f921c1d36821e64feb7412877f` — same content on top of `d19a2b3`
- Push proof: `git push origin main` → `d19a2b3..1f17669 main -> main`, then remote advanced to `f91afdb`
- Current analysis base SHA (HEAD at start of V2 work): `f91afdb090df60bcc571970b0faf7cff3d5b28ad` — `reverse: deep EN-VI ADAS regression evidence analysis`
- Upstream backup SHAs (via `git ls-remote HEAD`, read-only, repos NOT modified):
  - `vunguyenbv175/kimdung-promax-backup` → `fd581971ac86475763e1ac0380e9f5cb8c0630e6` — identical to `kimdung/promax.git` HEAD — **CONFIRMED**
  - `vunguyenbv175/kimdung-promax-xl-backup` → `f678b2c25b90df0989fa0ae2bf9e954b3de662ac` — identical to `kimdung/promax_xl.git` HEAD — **CONFIRMED**
- Local analysis copies (read-only, pre-existing from V1, re-verified in V2):
  - `C:\Users\Admin\AppData\Local\Temp\opencode\promax-research\promax-work\` (23 files: `firmware\`, `firmwarebeta\`, `*.html`, `manifest*.json`, `adapter.*`)
  - `C:\Users\Admin\AppData\Local\Temp\opencode\promax-research\promax-xl-work\` (18 files: `firmware\`, `*.html`, `manifest_*.json`)
  - Bare mirrors: `promax-research\promax.git` @ `fd58197`, `promax_xl.git` @ `f678b2c`
- All new work in C2M tree only: `docs/research/*V2*.md`, `docs/research/*V1*.md` (adapter/nav/transport/version/arch), `docs/research/promax_image_inventory.json`, `docs/research/EVIDENCE_PROMAX_PROTOCOL_V2.json`, `tools/reverse/promax/*.py`
- Branch discipline: V2 work committed on top of `f91afdb`; backup repos never written.

## EXECUTIVE VERDICT (V2, supersedes V1 high-level verdict)

- C2M HUD feasibility: **MEDIUM**
  - Offline road-intelligence HUD (GPS speed, offline limit/camera DB, ADAS fusion, status) on stock M4 after gates: HIGH sub-feasibility
  - Full VietMap LIVE arrows/road/lane on stock M4 today: LOW sub-feasibility (runtime nav value-plane not in firmware)
- VietMap protocol recovery: **PARTIALLY RECOVERED**
  - Management plane + handshake vocabulary + framing fully recovered; live nav value packets **NOT RECOVERED**
- Need for external ESP32: **NOT JUSTIFIED** (downgraded from V1 OPTIONAL-bridge)
  - V1 recommended ESP32-C3 BLE→USB/UART bridge for isolation. V2 static evidence proves phone-side BLE is the only HUD data-plane, but also proves an Android companion *can* translate the same semantic state to C2M Wi-Fi without new MCU. ESP only becomes OPTIONAL if three gates all prove true (see §19); today they do not.
- Need for hardware sniffing: **NOT YET JUSTIFIED**
  - Static analysis still has unexplored binary regions (code sections, GATT handler tables, FreeRTOS task lists) recoverable offline via Ghidra/IDA Xtensa+RISC-V. Sniffing is USEFUL LATER, not the next step.

Best architecture (V2): **Architecture A — direct Android → C2M Linux over Wi-Fi** (companion app posts neutral `nav/1` JSON to C2M AP on a new port; `NavigationProvider → DisplayState → M4Adapter → stock M4`; framebuffer only on documented M4 gate failure).

Best phone→C2M transport: **C2M Wi-Fi AP + TCP/WebSocket/HTTP on a new port (not 26012/8080)**, e.g. `:8099` prototype pattern; heartbeat + seq + allowlist + stale-expire.

Best C2M display path: **stock M4 via `DisplayState → M4Adapter` after L0/L1/responsibility/L2/L3 gates**; Linux framebuffer/OSD is fallback only.

## 1. Primary question — which path carries VietMap nav state?

| Candidate path | Verdict | Key evidence |
|---|---|---|
| VietMap app → BLE directly (HUD as peripheral) | **HIGH-CONFIDENCE** (handshake proves BLE intent; live values unproven) | `firmware.bin@0x18025D` dev JSON `"transport":"ble"`, `"want":{rate:4,fields:[nav,spd,lim,trn,dst,exit,st,eta,rmin,rkm,avg,avgL,alrs,lan]}` + `VIETMAP_HUD@0x1804E4` + `FFF0/FFF1/FFF2/FFF3` + 3×`8a7e0001/2/3` service block — **CONFIRMED strings** |
| VietMap app → Android companion → BLE | **POSSIBLE** (cannot distinguish from firmware alone) | `want`/`can` negotiation implies a capable sender (app or companion); no APK in repos — **UNKNOWN** |
| VietMap → notification/accessibility → companion | **POSSIBLE but UNPROVEN**; semantic `want` fields suggest pre-normalized feed, not raw notification dump | No `NotificationListener`/`AccessibilityService` strings in firmware (phone-side); inference only — **UNKNOWN** |
| Phone → Wi-Fi (ProMax) | **EXCLUDED (HIGH-CONFIDENCE)** | Zero SSID/AP/STA/HTTP-server/captive strings in ProMax classic; only `WIFI ESP_ERR`/`coex` noise; no `192.168.*`, no `vietmap.*`, no API — see `scan_protocol_constants.py` net group |
| Phone → classic BT SPP | **EXCLUDED (HIGH-CONFIDENCE)** | Only IDF example remnant `ESP32SPP@0x253AB8` + `btc_spp.c/rfcomm/a2dp` lib refs; zero `BluetoothSerial/SerialBT/esp_spp_init/RFCOMM_DATA` app code; OBD path is BLE not SPP |
| Phone → BLE GATT | **CONFIRMED for mgmt; HIGH for nav intent** | Mgmt proven via Web-BT JS (see §6); nav intent proven via dev/want JSON; live nav GATT writes **UNKNOWN** (no `nav/spd/lim` value encoder found) |
| Phone → USB | **EXCLUDED for runtime** | USB-serial only in adapter flash instructions (`adapter.html:83-99` Silabs/WCH drivers); no `tinyusb/cdc_acm` in ProMax classic |
| Cloud → device | **EXCLUDED (HIGH)** | No VietMap URLs/DNS/TLS-SNI/certs/API/User-Agent/Bearer in any ProMax image; XL cloud endpoints are GitHub OTA + OpenAI TTS leftover + `192.168.4.1` portal only |
| ESP32 adapter → another controller (runtime) | **UNKNOWN, leaning NOT runtime-critical** | Adapter is BLE-central scanner (`Service FFF0 not found@0x10123`, `/target_mac.txt@0x1013C`) + config FS; zero `hello/want/8a7e/IMG/DTBK-nav` strings; flasher role CONFIRMED, runtime bridge UNPROVEN — see `PROMAX_ADAPTER_REVERSE_V1.md` |

Ranked interpretation (**HIGH-CONFIDENCE**): phone (VietMap LIVE or companion holding LIVE semantics) acts as BLE-central/writer; HUD acts as BLE-peripheral/server exposing `FFF0` mgmt + `8a7e0001/2/3` nav-intent services; handshake is JSON+LF (`ping/pong/dev/want/can/rate:4`); live value encoding is absent from all 16 images → must be captured OTA *if* ever needed, but C2M does not need to replicate it if companion posts to Wi-Fi instead.

## 2. Upstream scope — what was actually inspected

- `promax-work\manifest.json` v7.6: ESP32→`firmware/firmware.bin` 4MiB, S3→`firmware_s.bin` 16MiB, C3→`firmware_c.bin` 4MiB — **CONFIRMED**
- `manifest_no_bl.json` v7.17 → `firmware_no_bl.bin` 3,796,784B (name misleading: still contains bootloader @0x1000 + app @0x10000, NVS erased @0x9000=`FC`, truncated trailing FF) — **CONFIRMED**
- `manifestbeta.json` → `firmwarebeta\firmware*.bin` (beta bootloader hash differs, app entry `0x40083644` vs stable `0x40083764`) — **CONFIRMED**
- `adapter.json` v7.15 → `firmware/firmware_adapter.bin` ESP32 4MiB, app entry `0x40082B24` (5 segs) vs main `0x40083764` (6 segs) — **CONFIRMED distinct binary**
- XL `manifest_guition_v1/v2.json`, `manifest_waveshare_v1/v2.json` v2.30 → 4× full `16711680B (0xFF0000)` S3 + 4× OTA `~5.9MiB` app-only — **CONFIRMED**
- HTML/JS: `promax-work\index.html` (obfuscated Web-BT config), `index_raw.html` (readable, `LOAD/DTBK/FFF*`), `baodiem.html`, `file_transfer.html`, `flash*.html`, `adapter.html`; `promax-xl-work\index.html` (IMG_* uploader), `index_raw.html`, `flash.html` — **CONFIRMED**
- History (bare mirrors, `git log --oneline`): promax 119 commits (`firmware 7.13/7.15/7.16/7.17/7.18`, `172705a adapter`, `73b430e beta`, `653afff LOAD config`, `60c638b DTBK raw + Dasai Mochi`); XL 53 commits (`2.17→2.24`, `d4a7539 scan service uuid`) — **CONFIRMED**
- Compared versions, not just newest: stable vs beta vs no_bl vs adapter vs XL v1/v2 × guition/waveshare × full/OTA — see `PROMAX_VERSION_DIFF_MATRIX_V1.md`

## 3. Hardware topology from binaries (not assumptions)

Method: `tools/reverse/promax/parse_esp_image.py` (header chip_id @+12, flash-size byte, partition `0x50AA`) + `scan_protocol_constants.py` + manifest `chipFamily`. Full per-image table in `docs/research/promax_image_inventory.json`.

| Image (size, sha256-prefix) | Chip verdict | Proof |
|---|---|---|
| `firmware.bin` 4MiB `790605ea..` | **ESP32 CONFIRMED** | Boot `E9@0x1000 chip0 entry 0x400805E4`, app `E9@0x10000 chip0 entry 0x40083764`, `esp-idf v4.4.7@0x10030`, `xtensa`, `btc_gap_ble`, no riscv/esp32s3/c3 |
| `firmware_c.bin` 4MiB `08f84ac2..` | **ESP32-C3 CONFIRMED** | `E9@0x0 chip5 entry 0x403CC710`, app `chip5 0x4038254C`, `esp32c3@0x28F`, `riscv`, no xtensa |
| `firmware_s.bin` 16MiB `bfeec41b..` | **ESP32-S3 CONFIRMED** | `E9@0x0 chip9 0x403C98D4`, app `chip9 0x40377094`, `esp32s3@0x278`, xtensa, no riscv |
| `firmware_no_bl.bin` 3.79MiB `5180a86c..` | **ESP32 CONFIRMED** | Same entries as stable; `FF@0x0`, `E9@0x1000`, NVS erased |
| `firmware_adapter.bin` 4MiB `7b7c0b8e..` | **ESP32 CONFIRMED** | Same boot, distinct app `0x40082B24/5segs`, `v4.4.7`, central strings |
| `firmwarebeta/firmware.bin` `4b184a6f..` | **ESP32 CONFIRMED** | Boot hash `2165b846..` differs, app `0x40083644`, `v4.4.4` |
| `firmwarebeta/firmware_c.bin` `62c92d50..` | **ESP32-C3 CONFIRMED** | chip5, `esp32c3`, `riscv` |
| `firmwarebeta/firmware_s.bin` `7a32dbca..` | **ESP32-S3 CONFIRMED** | chip9, `esp32s3` |
| XL 4× full `16711680B` `1398d9c6/e63cdc28/81e1a47e/50371233` | **ESP32-S3 CONFIRMED** | Boot `E9@0x0 chip9 4segs 0x403C88AC sf0x4F`, app `5segs 0x4037E630` (guition) / `0x4037E648` (waveshare), `v5.3.2-282-gcfea4f7c98-dirty`, `NimBLE×14`, `esp32s3@0x953` |
| XL 4× OTA `~5.9MiB` | **ESP32-S3 CONFIRMED, OTA-app** | `E9@0x0 chip9 5segs` same app entries, `AA50 valid=0`, offsets −0x10000 vs full |

Partitions: ProMax classic single-slot `nvs(0x9000:0x5000)/app0(0x10000:0x3D0000)/spiffs(0x3E0000:0x10000)/coredump(0x3F0000:0x10000)` — **CONFIRMED** (`0x8000` dump in §evidence). XL full dual-OTA `nvs/otadata/app0(0x10000:0x640000)/app1(0x650000:0x640000)/spiffs(0xC90000:0x360000)/coredump@0xFF0000-beyond-EOF (truncated)` — **CONFIRMED**. XL OTA dumps have no valid `AA50` (app-only) — **CONFIRMED**. FS label is `spiffs`; littlefs/fatfs are lib refs only; content not carved (no keys proven) — **MEDIUM**.

Distinction: main HUD vs adapter vs bootloader vs web vs OTA proven by entry/segcount/hash/manifest/strings — see inventory `notes`.

## 4–5. ESP firmware structure + executable code (beyond strings-only)

- Deterministic inventory per image via `parse_esp_image.py` → `promax_image_inventory.json` (sha256, chip, headers, partitions, fs, sdk) — **CONFIRMED artifact**
- App code sections located by `E9` + entry + segcount: classic ESP32 `0x40083764/6segs`, C3 `0x4038254C/5segs`, S3 `0x40377094/5segs`, adapter `0x40082B24/5segs`, XL `0x4037E630/48/5segs` — **CONFIRMED**
- ELF metadata reconstruction: **NOT RECOVERED** (merged flash images strip ELF/SH; no `.elf` in repos) — **CONFIRMED limitation**
- String-xref helper: `extract_strings_xrefs.py --scan` gives offset + 64B-before/160B-after context for every protocol token; neighbouring-module attribution (e.g. `dev/want` adjacent to `FFF*/VIETMAP_HUD/8a7e*` @0x180200 block; `IMG_START` adjacent to `/logo.jpg` + `[JPG] PSRAM` in XL) — **HIGH-CONFIDENCE** substitute for true xrefs
- FreeRTOS/BT/Wi-Fi/UART tasks identified by symbol-remnant strings, not disassembly: `ObdBleTask@firmware_c:0x159460` (**MEDIUM**), `SupervisorTask@/littlefs (adapter)`, `ble_gap/ble_gattc/ble_hs/ble_gattc_rx_mtu/nimble_bond` (XL NimBLE), `btc_gap_ble/btm_ble_gap/hciblecmds` (classic Bluedroid), `BLECharacteristic.cpp/BLEUUID.cpp`, `uart_driver/vfs_uart`, `Audio.h/audioI2S` (XL TTS leftover) — **MEDIUM** (names prove linkage, not call-graph)
- Control-flow / GATT handler tables / packet parser loops: **NOT RECOVERED** statically with available tooling (opaque Xtensa LX6/LX7 + RISC-V, no symbols, no Ghidra run in this pass). Remaining offline work (not hardware): load app segments in Ghidra+Xtensa/RISC-V, heuristic function split, xref `dev/pong/FFF/8a7e/DTBK/IMG` data refs → handlers. Explicitly **not** a strings-only stop; just not completed in V2 window.

## 6–8. BLE / classic BT / Wi-Fi (summary; full tables in TRANSPORT doc)

Management GATT (Web-BT proven, both families share `FFF0` container — **CONFIRMED**):

| Svc/Char | UUID | Dir | Props | Size | Handler (`file:line`) | Purpose |
|---|---|---|---|---|---|---|
| Svc | `0000fff0-…34fb` | — | primaryService | — | `promax/index_raw.html:230,330,354`, `xl/index.html:233,251,268,290` | config+file container |
| FFF1 (ProMax) | `0000fff1-…` | HUD→phone notify | startNotifications+valuechanged | ~150–250B `DTBK;…` | `index_raw.html:232,331,333,344`, `baodiem.html:85,173,201` | push config after LOAD |
| FFF2 (ProMax) | `0000fff2-…` | phone→HUD writeWoResp | writeWithoutResponse | `LOAD`=4B, DTBK~200B | `index_raw.html:231,338-341,353`, `baodiem.html:84,189,218` | query + submit |
| FFF3 (ProMax) | `0000fff3-…` | phone→HUD write+WoResp | writeValue 128B + WoResp(DTBK) | <100KiB 240×240 JPEG | `index_raw.html:233,336,417,436,440,452` | boot/logo JPEG |
| 180A/2A26 | `0000180a/00002a26-…` | HUD→phone read | readValue→TextDecoder | 5–8B (`v@7.6`) | `index_raw.html:234,311,314,317` | fw rev |
| FFF1 (XL) | `0000fff1-…` reused as WRITE | phone→HUD write | writeValue | `IMG_START;size`+256B×N+`IMG_END`, <512KiB 360×360 | `xl/index.html:234,367-386` | boot/watchface |
| Adv | `VIETMAP_HUD` / `Promax XL` | advertise | name-filter (ProMax) / service-filter (XL) | — | `index_raw.html:228,295`, `xl/index.html:268` | discovery |

Nav-intent UUIDs (firmware-only, no JS): `8a7e0001/2/3-4d6e-4c48-9a9d-484c504c0001` contiguous @`firmware.bin:0x1803D7/0x1803FC/0x180421`, XL `@0x68CAA/0x68C7B/0x68C56` — existence **CONFIRMED**, svc/char split **MEDIUM**, props/dir/handlers **LOW/UNKNOWN** (no JS binds them).

Classic BT/SPP: **EXCLUDED (HIGH)** — only `ESP32SPP` demo remnant + IDF `btc_spp/rfcomm/a2dp` lib refs; zero app SPP init/service/channel/parser.

Wi-Fi/network: ProMax **EXCLUDED (HIGH)** (no SSID/AP/portal/IP/API/certs); XL endpoints **CONFIRMED**: `https://kimdung.github.io/promax_xl/@0x68DE8` (OTA manifest/bin, :443, client, public), `192.168.4.1:80` SoftAP WiFiManager portal + `http://192.168.4.1/update` (server, open, local OTA), `api.openai.com:443/v1/audio/speech` + `Bearer` placeholder + `nArija/1.0` via `Audio.h` (TTS leftover, EXCLUDED from nav). Zero `*vietmap*/.vn/api/MQTT/WSS` — **HIGH**. Consequence: C2M cannot reach HUD nav over IP; C2M-side IP is for *phone→C2M*, not HUD emulation.

## 9. Adapter (summary; full in ADAPTER doc)

1. PC side: USB-serial data cable + picker + Silabs/WCH drivers — **CONFIRMED** (`adapter.html:83-99`)
2. Far side: BLE-central hypothesis (**MEDIUM**) — `Service FFF0 not found@0x10123`, `/target_mac.txt@0x1013C`, `VIETMAP_HUD@0x1017C/FFF0@0x10188/FFF1/FFF2`, `Dump scan/connect/registerForNotify/writeValue` — but zero `BLEDevice/BLEClient/BLEScan/doConnect` app symbols (only `BLEUUID.cpp` + IDF) → central role **UNPROVEN/LOW**
3. BLE↔UART: **UNKNOWN/LOW** (generic `uart_driver/vfs_uart/uart_set_pin` only; no `uart_read→ble_write` loop proven)
4. BLE↔USB-serial: **UNPROVEN/LOW** (no `tinyusb/cdc_acm` in adapter)
5. USB↔proprietary HUD bus: **EXCLUDED/MEDIUM** (standard serial + public drivers)
6. Flasher-only vs runtime bridge: flasher **CONFIRMED** (`adapter.json` + `esp-web-install-button`); runtime bridge **UNKNOWN/UNLIKELY** (zero hello/want/8a7e/IMG/DTBK-nav, no FFF3)
7. Carries nav at runtime: **UNKNOWN, leaning NO** — do NOT call it runtime bridge; do NOT add to C2M design on its account.

Exact framing recovered (bytes CONFIRMED, length-field MEDIUM): ASCII `A55A37C3…@0x102A0` (91B) decodes to `MODEL:H1V,HW:1.6.4,FW:1.3.6,PROTOCOL:2.2.2,OBDV:,COMPILE:Feb 27 2021-12:13:56`; `A5 5A 37 C3 | 00 00 00 5C (len 92 BE) | 64 E2 2D CA (id) | 0E | ASCII…`; no CRC proven. No baud/`UART_NUM`/pins/`AA55`-sync proven.

## 10–12. Nav vocabulary / state / display (summary; full in NAV-STATE doc)

- Handshake JSON (byte-exact, both families, **CONFIRMED**):
  - `{"v":1,"t":"pong"}\n` (16B, `firmware.bin@0x180230`, XL `@0x68AFE`)
  - `{"v":1,"t":"dev","name":"Promax"(" XL"),"fw":"1.0.0","proto":[1],"want":{"rate":4,"fields":["nav","spd","lim","trn","dst","exit","st","eta","rmin","rkm","avg","avgL","alrs", "lan"]},"can":["speed","limit","turn","street","eta","avgzone","alerts"],"transport":"ble"}\n` (~210B, `@0x18025D` / XL `@0x68B2B`)
  - `"t":"ping"` keepalive fragment
  - Only `t ∈ {ping,pong,dev}` present; `nav/spd/…` are `want.fields` (subscription request), not live packets — **CONFIRMED distinction**
- Hex example (`pong`, annotated): `7B 22 76 22 3A 31 2C 22 74 22 3A 22 70 6F 6E 67 22 7D 0A` = `{"v":1,"t":"pong"}\n`, LF-terminated, no CRC/len/seq/version-beyond-`v:1`, endianness N/A (ASCII) — **CONFIRMED**
- Command IDs are ASCII, not numeric: `LOAD, DTBK, IMG_START, IMG_END, pong, ping, dev(proto 1)` — **CONFIRMED**; no numeric cmd table found — **HIGH**
- True EN nav hits: only handshake keys (`turn/exit/street/alert/eta`, `speed/limit` via `can[]` + DTBK + `km/h/%.1fkm`); `lane/left/straight/uturn/roundabout/camera/radar/traffic/school/hazard/heading/compass/reroute/overspeed/tunnel/junction` ABSENT in ProMax classic — **CONFIRMED** (others are IDF/Bluedroid/mbedTLS noise)
- Vietnamese NFC: ProMax zero hits — **CONFIRMED**; XL only settings cluster (`Âm lượng/Còi cảnh báo/Nháy khi quá tốc độ/Độ sáng/Hướng…` + `120m/00:00/109°/Lê Văn Thiêm` near `brightness/orientation/volume/delay_warning/blink_screen/buzzer_enabled`) — **CONFIRMED**, no `rẽ trái/phải/đi thẳng/vòng xuyến`
- Normalized `struct NavigationState`: **NOT RECOVERED** (opaque images, no ELF/symbols) — **CONFIRMED limitation**. No offsets/sizes/writers/readers. V2 proposes neutral model instead (see §21).
- Display keys proven: `DTBK@0x3E0304` defaults (`WAZE` vs `MAPVIET`, rotation 0–7, `screen 0=full/1=limit-only`, `show_clock/kmh/number/speed/weather`, `led_color/brightness`, `night_brightness`, `boot_screen_duration 0–255`, `beep_limit_change`, `logo/welcome_text`, `obd_scan_duration`, `sleep_screen_mode/keep_awake_on_obd`); XL adds `delay_warning/blink_screen/buzzer_enabled/mute/volume/orientation/auto_turn_off`; boot JPEG via FFF3/128B+DTBK vs IMG_START/END — **CONFIRMED**. `arrow/lane/font/icon/blink` zero app hits (XL hits are CSS noise) — **CONFIRMED absence**.

## 13. Packet framing (all planes)

No `CRC8/16/32/XOR/COBS/SLIP/protobuf/nanopb/cJSON/MessagePack/TLV/magic/len/ver/seq` for nav/config (only IDF image/mesh/coredump CRCs) — **HIGH**. All planes are ASCII+LF/GATT-boundary:

| Plane | Frame | Example hex | Field table |
|---|---|---|---|
| FFF2 mgmt | `LOAD` | `4C 4F 41 44` | 0:4 ASCII discriminator, no terminator (GATT len) |
| FFF1/FFF2 config | `DTBK;…` | `44 54 42 4B 3B…` (`DTBK;display_rotation=1;…boot_screen_duration=1`) | 0:4 `DTBK`, 4:N `;k=v` repeats |
| FFF3 file (ProMax) | 128B JPEG + `DTBK` EOF | `FF D8 FF E0 …` then `44 54 42 4B` | GATT-boundary, 100 ms pacing, <100 KiB |
| FFF1 image (XL) | `IMG_START;size`+256B×N+`IMG_END` | `49 4D 47 5F 53 54 41 52 54 3B…` / `…45 4E 44` | ASCII markers, <512 KiB 360×360 |
| Nav handshake | JSON+`0A` | `7B2276223A31…0A` (see §10) | `v/t/name/fw/proto/want{rate,fields}/can/transport` |
| OBD AT | ASCII+CRLF | `AT D/SH … 0D` (`AT D@0x180550`, `ELM…@0x6E115`) | ELM327 dialect |
| Adapter info | `A55A…` ASCII | `A5 5A 37 C3 00 00 00 5C 64 E2 2D CA 0E 4D…` | ver/type/len-BE/id/field/ASCII (CRC unproven) |

## 14. Version diffs (summary; matrix in VERSION doc)

- Promax `fix lane image ccbb393` (C-only binary tweak), `172705a adapter`, `73b430e beta`, `7.15→7.18` opaque dailies; beta ESP32 app entry `0x40083644` vs stable `0x40083764`, beta bootloader hash differs, beta **strips** `pong/dev/8a7e/proto/want` block present in stable v7.6 (`d2ace18` has `FFF0/180A/VIETMAP` but zero nav) — **HIGH** (nav presence is version-dependent, not monotonic)
- XL `2.17→2.24` OTA +~1.3 KiB, `d4a7539 scan service uuid` (XL service-filter connect), guition vs waveshare only app entry `…E630` vs `…E648` + `DTBK@` shift + `want` count 1 vs 2 — **CONFIRMED**
- `lane/road-name/roundabout/camera/VIETMAP LIVE` never appear as literals in any version; `lane` only in `want.fields` + `ccbb393` message — **CONFIRMED**
- `diff_esp_firmware.py` workflow documented for isolating future handler additions.

## 15. VietMap coupling — direct backend or phone-computed?

**HIGH-CONFIDENCE: phone-mediated, NOT direct.** Zero `VIETMAP LIVE` literals, zero VietMap URLs/DNS/TLS-SNI/certs/API-paths/JSON-keys/User-Agent/device-IDs in any of 16 images. ProMax URLs: only `gcc.gnu.org` + Adobe XMP. XL: only `kimdung.github.io/promax_xl` + `tzapu/WiFiManager` + `192.168.4.1` + OpenAI TTS. Adapter shows BLE-central scan posture, consistent with phone/value-plane mediation. `want{rate:4,fields:[…]}` + `can[…]` is a capability-subscription handshake: HUD declares interest + renderable subset; sender (phone-side LIVE/companion) computes route semantics and pushes values. Whether sender is stock VietMap app with accessory mode vs custom companion parsing notifications/accessibility cannot be distinguished from firmware — **UNKNOWN**, needs APK + BLE capture. Long-term implication: C2M must not depend on undocumented VietMap accessory API; depend on *own* companion posting neutral state.

## 16. Android-side inference

Firmware-only view: `ping/pong/dev + rate:4` + short normalized keys (`nav/spd/lim/trn/dst/exit/st/eta/rmin/rkm/avg/avgL/alrs/lan`) imply sender already normalizes (semantic extraction before TX), not raw-GPS streaming — **MEDIUM**. Cannot distinguish notification vs accessibility vs official API vs internal feed vs scraping — **UNKNOWN**. No app source in repos; background/reconnect/screen-off/permissions/mods unknown. If packets had contained raw NMEA only, architecture would differ; they do not — vocabulary is guidance-level. Needs APK decompile + runtime BLE capture for CONFIRMED.

## 17. Public corroboration

Not run beyond repo evidence in V2 window except standard BLE UUID knowledge (`180A/2A26` Device Information/Firmware Revision are Bluetooth-SIG assigned — **CONFIRMED** by spec alignment). No forum/APK/manual claims admitted as evidence. Firmware remains primary per task §17.

## 18–19. C2M reassessment + hardware-dependency decision tree

Scores (1–5, 5=best; task §18 dimensions):

|  | A Android→C2M Wi-Fi | B emulate ProMax BLE | C native C2M BLE | D external ESP |
|---|---|---|---|---|
| Usefulness | 5 | 4 | 4 | 4 |
| Effort (5=least) | 5 | 1 | 2 | 3 |
| Risk (5=safest) | 5 | 1 | 2 | 4 |
| Reverse-dep (5=least) | 5 | 1 | 2 | 2 |
| Compat | 5 | 3 | 3 | 3 |
| Latency | 5 | 4 | 4 | 3 |
| Maintainability | 5 | 1 | 3 | 4 |
| Usability | 4 | 5 | 4 | 4 |
| **AVG** | **4.9** | **2.5** | **3.1** | **3.4** |

Rank: **A ≫ D > C > B**. A is V1; D conditional; C later simplification; B reject V1.

Decision tree (evidence-backed):

```text
Is native runtime protocol IP-based?  NO (HIGH: BLE-only intent, §8)
  └─ Is protocol BLE-only?  YES (HIGH for intent; live values UNKNOWN)
       └─ Can Android companion translate BLE-derived/semantic state to Wi-Fi?
            YES → no external MCU (Architecture A). Companion already holds
                  VietMap semantics; POST neutral nav/1 to C2M AP. ← V2 PATH
            NO ↓
              Does C2M have usable BLE?  NO (CONFIRMED: no BT stack in C2M evidence)
                └─ → external ESP bridge (Architecture D) ONLY after 10+ repeatable
                     BLE events prove semantics + reconnect; if encrypted/pinned → stay A offline.
Architecture B (emulate ProMax peripheral on C2M) never except owner+legal approval:
requires cloning 8a7e services + VietMap accessory behaviour, highest reverse cost.
```

Transports for C2M (prefer existing HW): Wi-Fi AP (`ap.sh/wlan0/hostapd/8821cs` PROVEN) + TCP/WS/HTTP on **new** port (not 26012/8080) is LOW/LOW risk/complexity, LOW latency, best compat; STA is AP-XOR stock (MED); native BLE NOT SUPPORTED (HIGH cost); ESP-bridge pattern `A5 5A ver/type/len/seq/crc` exists only as proposal, not proven need; USB/RNDIS is CLUE ONLY for M4 side — do not hack.

Display: stay **M4 semantic** (`DisplayState → M4Adapter → stock M4`) through L0/L1/responsibility/L2 gates; framebuffer (`mmap_reserved=fb,8MiB,VI-only`, display HIGH, CMA/IPU/consumption UNKNOWN) is fallback on documented M4 gate failure. M4 vs FB table in ARCH doc.

## 20. C2M M4 path (semantic translation, not transplantation)

```text
Recovered ProMax want/can vocabulary (nav/spd/lim/trn/dst/exit/st/eta/rmin/rkm/avg/avgL/alrs/lan)
        ↓ (manual semantic map, NOT binary transplant)
C2M neutral NavigationState {active,ts,seq,source,conf, next{arrow,dist_m,road,lane}, limit, camera/hazard, gps}
        ↓ (validate/expire/arbitrate; ADAS overrides nav; nav never sets fcw/pcw/ldw/lead)
C2M renderer adapter (M4Adapter rate ~2Hz, allowlist, stale>~3s→inactive)
        ↓ stock M4 (passive decode → harmless replay → limited nav)
Fallback → Linux framebuffer/OSD (same renderer contract)
```

Per-feature M4 mapping (PROVEN/PROBABLE/UNKNOWN/NOT SUPPORTED): speed PROBABLE (GPSSpeed schema PROVEN, L2 DENY), limit UNKNOWN (TSR `--enable_tsr=false`, fusion ready, M4 slot missing), arrow/distance/road UNKNOWN (no nav fields; ADAS dist must NOT be repurposed), lane PROBABLE-for-LDW / UNKNOWN-for-nav, camera UNKNOWN, hazard PROBABLE-local, clock UNKNOWN, GPS PROVEN-schema/PROBABLE-display, BT NOT SUPPORTED, Wi-Fi PROVEN-schema, trip/compass UNKNOWN/NOT SUPPORTED, ADAS warnings PROVEN-observable/PROBABLE-displayable after gates. Full matrix in ARCH doc.

## 21–22. Neutral model / offline-first / product value

```c
// PROPOSAL only (not firmware-derived); RAW units; seq+ts required
struct NavigationState {
  uint8_t  active; uint64_t timestamp_ms; uint32_t seq;
  uint8_t  source;  // 0=none 1=vietmap-live 2=vietmap-api 3=osm 4=test
  uint8_t  confidence; int32_t arrow; int32_t distance_m;
  char     road_name[64]; uint16_t lane_mask; uint8_t lane_preferred;
  int32_t  speed_limit; uint8_t cam_warn; uint8_t hazard; uint8_t gps_quality;
};
```

Adapters feed from VietMap/Google/HERE/offline/custom. Split: OFFLINE (GPS+OSM+TSR+ADAS always) / PHONE (LIVE arrow/dist optional) / INTERNET (API cache bounded). VietMap failure must not break core enhancement — **product requirement**.

Killer C2M-only value (FUTURE concepts, not current capability): single windshield device (record+ADAS+limits+optional nav, no mount), ADAS+nav priority fusion, limit+detection fusion, hazard-auto-clip recording, local voice independent of phone.

## 23. Licensing boundary

No LICENSE in either upstream tree or C2M; READMEs `# promax`; HTML comments teasing only — **CONFIRMED absence**. Classify: protocol facts/UUIDs/DTBK keys/JSON vocab = SAFE TO REIMPLEMENT (interoperability facts); binaries/HTML/JPEGs/fonts/IDF-lib code = REFERENCE ONLY / DO NOT COPY; icons/lane/mochi/animations/voice = LICENSE UNKNOWN / DO NOT COPY. No subscription bypass attempted; no credentials/keys found. ESP Web Tools/browser APIs are mechanisms, not firmware license.

## 26. Required final answers (20)

1. ProMax chip: **ESP32 (classic) + ESP32-C3 + ESP32-S3 variants** — header chip_id 0/5/9 + SDK strings + manifest — **CONFIRMED**
2. Adapter chip: **ESP32** — `E9 chip0`, `v4.4.7`, distinct app entry — **CONFIRMED**
3. Adapter runtime-critical or flashing-only: **flashing CONFIRMED; runtime bridge UNKNOWN/UNLIKELY** — do not design around it
4. Exact phone→device nav transport: **BLE GATT intent (HIGH); live value encoding NOT RECOVERED** — mgmt proven, handshake proven, values absent
5. BLE/classic/Wi-Fi/USB/multiple: **BLE mgmt CONFIRMED; BLE nav-intent HIGH; classic EXCLUDED; ProMax Wi-Fi EXCLUDED; USB runtime EXCLUDED; XL Wi-Fi only OTA-portal; cloud relay EXCLUDED**
6. BLE UUIDs: `FFF0(svc) FFF1(notif/write) FFF2(write) FFF3(file) 180A/2A26` + `8a7e0001/2/3` nav-intent block — **CONFIRMED existence** (props for 8a7e UNKNOWN)
7. Network ports/endpoints: ProMax none; XL `github:443 OTA`, `192.168.4.1:80 portal+update`, `api.openai.com:443 TTS leftover` — **CONFIRMED**
8. UART framing: adapter `A55A…` info frame (bytes CONFIRMED, len-BE MEDIUM, CRC unproven); no baud/pins/sync proven — **PARTIAL**
9. Header/len/checksum: **none for nav/config** (ASCII+LF/GATT-boundary); only IDF image/coredump CRCs — **HIGH**
10. Nav command IDs: ASCII `LOAD/DTBK/IMG_START/IMG_END/pong/ping/dev(proto 1)` — **CONFIRMED**; no numeric table
11. Internal nav state struct: **NOT RECOVERED** (opaque, no ELF) — neutral proposal instead
12. Speed/limit/turn/dist/road/lane sources: HUD *wants* them (`want[]`/`can[]`); sender is phone-side LIVE/companion (HIGH); GPS-vs-OBD-vs-fusion inside HUD **UNKNOWN** (OBD BLE scan proves OBD speed is an input option)
13. Normalized HUD state or raw data: **normalized intent** (`want` short keys + `can` renderables + `rate:4`) — **MEDIUM**; live values unproven
14. Companion mandatory: **UNKNOWN from firmware** (no APK); Web-BT pages prove browser config, not nav driving; background/reconnect/screen-off unproven
15. External ESP32 necessary: **NO — NOT JUSTIFIED** (A achieves same via Wi-Fi; D only if 3 gates prove true)
16. Can C2M Linux receive same data directly: **YES — via companion→Wi-Fi neutral feed, NOT via ProMax BLE clone** (HIGH for A; B rejected V1)
17. Preferred C2M transport: **Wi-Fi AP + TCP/WS on new port** (heartbeat/seq/allowlist/stale-expire)
18. Preferred display: **stock M4 via DisplayState→M4Adapter** (gated); FB fallback
19. Offline-without-VietMap: GPS speed, OSM/TSR limits, camera DB, hazards, day/night, ADAS+alert fusion, local voice — **all offline-capable**
20. Still needs hardware capture: **live BLE value-plane + GATT roles/props + reconnect/screen-off + M4 physical/logical transport** — but capture is USEFUL LATER, not next (see §28)

## 27. Verdict categories (do not reuse V1 automatically)

- C2M HUD feasibility: **MEDIUM** (offline HIGH / full-LIVE-on-M4 LOW)
- VietMap protocol recovery: **PARTIALLY RECOVERED** (mgmt+handshake recovered; live values not)
- Need for external ESP32: **NOT JUSTIFIED** (OPTIONAL only if triple-gate proves true)
- Need for hardware sniffing: **NOT YET JUSTIFIED** (USEFUL LATER)

## 28. Hardware sniffing gate

NOT passed. Static analysis NOT exhausted: app code segments located but not disassembled; GATT handler tables, FreeRTOS task lists, `dev/pong` producers/consumers, `DTBK/IMG` writers/readers, XL `delay_warning/blink/buzzer` logic, adapter scan→connect→notify→write path all remain offline-recoverable via Ghidra/IDA (Xtensa+RISC-V) + `extract_strings_xrefs.py` context + `diff_esp_firmware.py` version isolation. Runtime value-plane remains unresolved AND no further structure *of the value-plane* can be proven offline — but value-plane is not needed for Architecture A. Therefore sniffing is deferred, not next.

## 29. Single next experiment (maximum information gain, NOT passive sniff D)

**B. Android sends one recovered nav-handshake packet to an emulator (PC harness replays `pong/dev` + `DTBK` semantics into C2M-neutral `nav/1` → shadow DisplayState, no display writes).**

- Objective: prove companion→C2M Wi-Fi path + neutral model + validation/stale logic without any BLE/M4 risk.
- Depends on: nothing hardware; uses already-recovered JSON + DTBK keys.
- PASS: deterministic `dev→want` parse, `pong↔ping` liveness, `DTBK→config` map, malformed/stale rejection, 60-min shadow log, zero M4/flash writes.
- Risk: overfitting handshake without live values (acceptable: A does not need live ProMax values).
- Rollback: delete harness; no device touched.
- Why not D (passive sniff): D resolves ProMax value-plane C2M will not consume in Architecture A; B unblocks useful product (offline HUD + companion enrichment) immediately.
- Alternatives ranked: C (decode one parser end-to-end in Ghidra) is second-best offline follow-up; A (PC reproduces phone→ProMax packet) is impossible without live values; D deferred to USEFUL LATER.

## Tooling (reproducible, pure-python, no pip)

- `tools/reverse/promax/parse_esp_image.py` — headers/partitions/chip/sdk — DIRECT REUSE
- `tools/reverse/promax/parse_partition_table.py` — 0x50AA table — DIRECT REUSE
- `tools/reverse/promax/extract_strings_xrefs.py` — offsets + `--scan` contexts — DIRECT REUSE
- `tools/reverse/promax/diff_esp_firmware.py` — version string-set diff — DIRECT REUSE
- `tools/reverse/promax/scan_protocol_constants.py` — BLE/net/UART/nav groups — DIRECT REUSE
- All REFERENCE ONLY for binary content; wire facts SAFE TO REIMPLEMENT.

## Safety / isolation (unchanged from V1, reinforced)

Phone untrusted → ingress allowlist/seq/crc/rate → provider validate/expire → DisplayState arbiter (ADAS overrides nav; nav never sets safety fields) → M4Adapter policy gate → M4 + local voice. Watchdog restarts bridge/provider only. Boot to stock-safe without phone/BLE/net/DB. Feature kill-switch to stock-only DisplayState. OTA/flash domains separate from runtime input. See ARCH doc.

---
*Evidence weights: header/partition/manifest/HTML-JS/firmware-JSON = CONFIRMED; stack/task attribution = MEDIUM; 8a7e roles/live values/phone internals = UNKNOWN. No marketing conclusions.*
