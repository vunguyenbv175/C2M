# ProMax ADAPTER reverse V1 (C2M research-only)

No firmware built/flashed. Adapter repo files read-only. C2M tree only changed.

## Identity — CONFIRMED

- Source: `promax-work/adapter.json` v7.15 → `firmware/firmware_adapter.bin` 4MiB — CONFIRMED (`adapter.json:1-11`)
- Full SHA256: `7b7c0b8e6b35d148…` (see `promax_image_inventory.json`), size 4194304 — CONFIRMED
- Chip: **ESP32 CONFIRMED** — boot `E9@0x1000 chip0 entry 0x400805E4`, app `E9@0x10000 5segs entry 0x40082B24` (vs main `6segs 0x40083764`), `esp-idf v4.4.7@0x10030`, `xtensa`, `btc_gap_ble` — tool `parse_esp_image.py`
- Partitions: `nvs/app0/spiffs/coredump` single-slot (same as main) — CONFIRMED
- Flashing: `adapter.html:83-99` data cable + USB-serial picker + Silabs/WCH drivers + `esp-web-install-button manifest=./adapter.json` — **flasher role CONFIRMED**

## The 7 adapter questions

1. **PC side?** USB-serial data cable to PC browser — CONFIRMED (`adapter.html:83-99`).
2. **Far side?** BLE-central hypothesis — MEDIUM: `Service FFF0 not found@0x10123`, `/target_mac.txt@0x1013C`, `VIETMAP_HUD@0x1017C`, `FFF0@0x10188/FFF1@0x10190/FFF2@0x10198`, `Dump scan/connect/registerForNotify/writeValue@0x109D4/0x10CB3`. BUT zero `BLEDevice/BLEClient/BLEScan/doConnect` app symbols (only `BLEUUID.cpp@0x10A94` + IDF) → central role UNPROVEN/LOW.
3. **BLE↔UART?** UNKNOWN/LOW. Generic `uart_driver@0x11DB5/vfs_uart@0x13E71/uart_set_pin@0x11E85/hal uart.c@0x10E86` only; no `uart_read→ble_write` loop, no `UART_NUM`/pins/baud value proven.
4. **BLE↔USB-serial?** UNPROVEN/LOW. No `tinyusb/cdc_acm/usb_serial` in adapter (HW CDC only in XL).
5. **USB↔proprietary HUD bus?** EXCLUDED/MEDIUM. Standard serial + public drivers; no proprietary VID/PID/frame proven.
6. **Flasher-only or runtime bridge?** Flasher CONFIRMED; runtime bridge UNKNOWN/UNLIKELY. Zero `hello/want/8a7e/IMG/DTBK-nav` strings; no FFF3; `/poi.jpg@0x1036C` + `LittleFS@/littlefs+spiffs+SupervisorTask@0x108B4` show config/image FS, not nav relay.
7. **Carries nav at runtime?** UNKNOWN, leaning NO. Do NOT call it runtime bridge unless code proves it.

## Exact framing recovered

- ASCII info frame @0x102A0 (91B, bytes CONFIRMED):
  `A55A37C30000005C64E22DCA0E4D4F44454C3A4831562C48573A312E362E342C46573A312E332E362C50524F544F434F4C3A322E322E322C204F4244563A2C434F4D50494C453A46656220323720323032312D31323A31333A353600…`
- Decoded: `MODEL:H1V,HW:1.6.4,FW:1.3.6,PROTOCOL:2.2.2,OBDV:,COMPILE:Feb 27 2021-12:13:56`
- Structure (MEDIUM): `A5 5A 37 C3 | 00 00 00 5C (len 92 BE) | 64 E2 2D CA (id) | 0E | ASCII…` (`hex fields @0x101CC`). No CRC proven. No `AA55` sync, no COBS/SLIP, no seq proven.
- `fileBlockCharacteristic` / `FFF3` absent; `LOAD/DTBK` nav keys absent.

## OBD relevance

Adapter `MODEL:H1V…PROTOCOL:2.2.2` + main-firmware OBD BLE block (`AT D/Z/E0/S0/SP/RV/IOS-Vlink/Viecar/OBD BLE/FAKE_OBD/18F0/2AF0/2AF1/ObdBleTask`) are consistent with an OBD-dongle commissioning/scanning role (Vgate iCar Pro 4.0 per `index.html:202-210`), NOT HUD nav relay — HIGH-CONFIDENCE inference, MEDIUM proof.

## Verdict for C2M

- Adapter is **support/flashing (+likely OBD-scan) hardware, NOT proven runtime-critical** for VietMap nav.
- Do NOT add ESP32 to C2M design on adapter's account. Architecture A needs no adapter; Architecture D (if ever) would be a *new* from-scratch bridge, not this binary.
- Reuse: wire facts (FFF names, A55A shape) SAFE TO REIMPLEMENT; binary/HTML/JPEGs DO NOT COPY (no license).
