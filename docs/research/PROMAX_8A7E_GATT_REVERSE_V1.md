# ProMax 8A7E GATT reverse V1 (roles unproven — honest gap)

Analysis-only. Disassembler absent (verified: no Ghidra/IDA/rizin/radare2/xtensa-objdump/esptool). Findings are string-structure level; no control-flow claimed.

## UUID inventory — CONFIRMED existence

Classic `firmware.bin`: `8a7e0001@0x1803D7`, `8a7e0003@0x1803FC`, `8a7e0002@0x180421`, full form `8a7eXXXX-4d6e-4c48-9a9d-484c504c0001`, contiguous with `FFF0/FFF1/FFF2/FFF3@0x1803C3…` + `VIETMAP_HUD@0x1804E4` + `dev/want` block — CONFIRMED. XL identical trio `@0x68C56/0x68C7B/0x68CAA`. C3/S3/no_bl/adapter/beta: zero — CONFIRMED (variant-gated nav stack).

## Required table (§3)

| UUID | Type | Properties | Direction | Callback | Confidence |
|---|---|---|---|---|---|
| 8a7e0001 | UNKNOWN (service or characteristic) | UNKNOWN (no props bitmask) | UNKNOWN | NOT RECOVERED | UNKNOWN |
| 8a7e0002 | UNKNOWN | UNKNOWN | UNKNOWN | NOT RECOVERED | UNKNOWN |
| 8a7e0003 | UNKNOWN | UNKNOWN | UNKNOWN | NOT RECOVERED | UNKNOWN |

No `createCharacteristic/setCallbacks/onWrite/onRead/addDescriptor/esp_ble_gatts_create_service/esp_gatts_attr_db` strings in classic (zero hits — CONFIRMED absence); only `createService`×1 + `indicate`×1 + `BLEUUID`×0 classic (`BLEUUID`×1 C3/adapter only), `esp_ble_gatts_add_char`×0 classic (×1 C3/S3). Adjacent-string inference explicitly refused: order 0001/0003/0002 in flash is storage order, not service/char proof.

## Role evidence (peripheral + central dual-role — HIGH)

- Peripheral: `startAdvert`×1 all classic-family builds + `VIETMAP_HUD` adv name + `indicate` — HIGH.
- Central: `Dump scan results` + `getServices/registerForNotify/writeValue/readValue` ×1 classic/C3/S3/no_bl/adapter/beta (XL: NimBLE equivalents, different strings) — HIGH; contiguous OBD block (`AT…/IOS-Vlink/Viecar/18F0/2AF0/2AF1`) proves the central role serves OBD dongles, distinct from 8a7e block — HIGH.
- Value buffers/max length/MTU/CCCD/subscription: UNKNOWN (no MTU/CCCD strings tied to 8a7e; `2902` zero).

## Segment/vaddr note (why no disassembly this pass)

ESP image headers verified (`E9` + chip + entries), but segment-header walk breaks after seg0 (seg1 `ABCD5432/0`, subsequent bytes decode as ASCII `esp-idf…/arduino…`), indicating hash/trailer interleave the naive linear walk (proven hexdump in V3 work). Correct reassembly needs esptool (absent, import-verified) + Ghidra Xtensa (absent, `where`-verified). `find_gatt_handlers.py` encodes the string-level ceiling and lists LEVEL 1 gaps explicitly.

## What would prove roles (offline, no sniff)

Ghidra Xtensa (classic) + RISC-V/S3 (XL): load app segments via esptool-dumped sections, heuristic function split, xref `8a7e` data refs → `createService/createCharacteristic/esp_ble_gatts_*`/NimBLE equivalents → props/perm/callback pointers → attr-db table. Until then: UNKNOWN.
