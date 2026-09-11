# ProMax transport protocols V1 (BLE / BT-classic / net / UART / framing)

All offsets flash-file. Tools: `scan_protocol_constants.py`, `extract_strings_xrefs.py --scan`, `parse_esp_image.py`.

## BLE — CONFIRMED mgmt, HIGH nav-intent

Base `0000XXXX-0000-1000-8000-00805f9b34fb` (BT-SIG 16→128 expansion; `BLEUUID.cpp` + `%02x…` format strings prove dynamic construction — CONFIRMED).

ProMax classic (Bluedroid: `btc_gap_ble/btm_ble_gap/hciblecmds` + `BLECharacteristic.cpp` in C/S builds):
- Svc `FFF0`, FFF1 notify (~150–250B `DTBK;…`), FFF2 writeWoResp (`LOAD`=4B `4C 4F 41 44` query + DTBK ~200B submit), FFF3 file (128B JPEG + `DTBK` EOF, <100KiB 240×240, ~100ms pacing), 180A/2A26 read (`v@7.6`).
- Handlers: `promax/index_raw.html:230-341` (`connect/loadCurrentConfig/send/handleCharacteristicChange`), `baodiem.html:83-218`.
- Adv `VIETMAP_HUD` name-filter (`index_raw.html:228,295` + `firmware.bin@0x1804E4`).

XL (NimBLE-Arduino: `NimBLE×14/nimble×33/ble_gap/ble_gattc/ble_hs/rx_mtu/nimble_bond`):
- Same `FFF0` container but FFF1 **reused as WRITE**: `IMG_START;size` + 256B chunks + `IMG_END` (<512KiB 360×360) — `xl/index.html:233-386`.
- Adv service-filter (`xl/index.html:268 services:[FFF0]`), `getServiceWithRetry`.

Nav-intent: `8a7e0001/2/3-4d6e-4c48-9a9d-484c504c0001` contiguous (`firmware.bin@0x1803D7/0x1803FC/0x180421`; XL `@0x68CAA/0x68C7B/0x68C56`) adjacent to `dev/want/FFF*/VIETMAP_HUD` — existence CONFIRMED; svc/char split MEDIUM; props/dir/handlers UNKNOWN (no JS binds them). Pair/bond/MTU: `simple_pairing/secure_connections/bonded/AuthMode/GATTC_ConfigureMTU/advertise instance` present; no app MTU/passkey — MEDIUM.

OBD BLE (HUD-central, NOT phone nav): `18F0/2AF0/2AF1` + `AT D/Z/E0/S0/SP/RV` + `IOS-Vlink/Viecar/OBD BLE/FAKE_OBD` + `ObdBleTask` — HIGH.

## Classic BT — EXCLUDED (HIGH)

Only `ESP32SPP` demo remnant + IDF `btc_spp/rfcomm/a2dp` lib refs. Zero `BluetoothSerial/SerialBT/esp_spp_init/RFCOMM_DATA` app code. No service name/channel/frame/reconnect/parser. C2M must not use SPP.

## Wi-Fi/network — ProMax EXCLUDED, XL OTA-only

- ProMax: `WIFI ESP_ERR/coex` + `gcc.gnu.org/https` + Adobe XMP noise only; zero SSID/AP/captive/IP/API/certs — EXCLUDED/HIGH.
- XL CONFIRMED: `https://kimdung.github.io/promax_xl/:443` OTA manifest/bin (client, public, JSON+bin); `192.168.4.1:80` SoftAP WiFiManager portal + `http://192.168.4.1/update` (server, open, local OTA); `api.openai.com:443/v1/audio/speech` + Bearer placeholder via `Audio.h` (TTS leftover, EXCLUDED from nav). Zero `*vietmap*/.vn/api/MQTT/WSS`; `AsyncUDP/lwIP` are lib refs.
- Consequence: C2M cannot reach HUD nav over IP. C2M-side IP is phone→C2M only.

## UART/USB/adapter

See ADAPTER doc. Summary: PC USB-serial CONFIRMED; BLE-central MEDIUM/UNPROVEN; BLE↔UART/USB UNPROVEN; proprietary bus EXCLUDED; flasher CONFIRMED, runtime bridge UNKNOWN; A55A info frame bytes CONFIRMED / CRC unproven; no baud/pins/sync proven.

## Framing (all ASCII+LF/GATT-boundary; no CRC — HIGH)

| Plane | Layout | Example |
|---|---|---|
| LOAD | `4C 4F 41 44` | FFF2 write |
| DTBK | `44 54 42 4B 3B k=v;…` | `DTBK;display_rotation=1;…boot_screen_duration=1` |
| ProMax file | 128B JPEG + `44 54 42 4B` EOF | `FF D8 FF E0…` |
| XL image | `IMG_START;size` + 256B×N + `IMG_END` | `49 4D 47…` |
| Nav | JSON + `0A` | `7B2276223A31…0A` (`pong` 16B, `dev` ~210B) |
| OBD | ASCII + `0D` | `AT D…` |
| Adapter | `A5 5A 37 C3 len-BE id ASCII` | `A5 5A 37 C3 00 00 00 5C 64 E2 2D CA 0E…` |

Offset|Size|Field|Meaning|Endian tables per plane are in the main V2 report §13. Numeric command IDs: none (ASCII only) — CONFIRMED.
