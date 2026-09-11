# ProMax executable memory map V1 (esptool-proven, V4)

Tool: `esptool v5.4.0 image-info` on extracted app images + pure-python fallback
`tools/reverse/promax/map_esp_segments.py`. Upstream SHAs: promax
`fd581971ac86475763e1ac0380e9f5cb8c0630e6`, promax_xl
`f678b2c25b90df0989fa0ae2bf9e954b3de662ac`. No firmware modified.

## Classic ESP32 app (`firmware.bin` app0 @flash 0x10000 len 0x3D0000)

`arduino-lib-builder`, ESP-IDF `v4.4.7-dirty`, built Mar 5 2024 (app-info; note:
rebuilt Aug 2026 per git history — compile stamp lags content), entry
`0x40083764`, chip 0, 6 segments, checksum+hash valid:

| Seg | Length | Load VA | File off (image-rel) | Flash off | Type |
|---|---|---|---|---|---|
| 0 | 0x2637E8 | 0x3F400020 | 0x18 | 0x10018 | DROM (rodata: handshake, UUIDs, bare table, config keys) |
| 1 | 0x4 | 0x3FF80000 | 0x263808 | 0x273808 | RTC_DRAM |
| 2 | 0x5C5C | 0x3FFBDB60 | 0x263814 | 0x273814 | DRAM |
| 3 | 0x6B98 | 0x40080000 | 0x269478 | 0x279478 | IRAM (entry 0x40083764 inside) |
| 4 | 0x110B1C | 0x400D0020 | 0x270018 | 0x280018 | IROM (app code) |
| 5 | 0x1570C | 0x40086B98 | 0x380B3C | 0x390B3C | IRAM |

VA formula (DROM): `VA = 0x3F400020 + (flash_off - 0x10018)`.
Worked: bare table flash `0x18281C` → VA `0x3FC82824`; 8a7e0001 flash
`0x1803D7` → VA `0x3FC803DF`; dev JSON flash `0x180244` → VA `0x3FC8024C`.

## XL ESP32-S3 OTA app (`guition_ota_v1.bin`, app-only)

`arduino-lib-builder`, app `2f061cb`, ESP-IDF `v5.3.2-282-gcfea4f7c98-dirty`,
built Jan 6 2025, entry `0x4037E630`, chip 9, 5 segments:

| Seg | Length | Load VA | File off | Type |
|---|---|---|---|---|
| 0 | 0x4031F0 | 0x3C180020 | 0x18 | DROM |
| 1 | 0x6004 | 0x3FCA4900 | 0x403210 | DRAM |
| 2 | 0x6DF4 | 0x40374000 | 0x40921C | IRAM |
| 3 | 0x17ADD4 | 0x42000020 | 0x410018 | IROM (consumer clusters live here) |
| 4 | 0x19ACC | 0x4037ADF4 | 0x58ADF4 | IRAM (entry inside) |

VA formula (DROM): `VA = 0x3C180020 + (file_off - 0x18)`.
Worked: bare table file `0x68F79` → VA `0x3C1E8F82`; 8a7e0001 file `0x68CAA`
→ VA `0x3C1E8CAD`; IROM cluster file `0x410948` → VA `0x42000948`.

XL full `firmware_guition_v1.bin` app0 @flash 0x10000 len 0x640000 has the same
app bytes shifted by `0x10000` (OTA = app-only dump, `AA50` invalid — V2).

## Disassembler status (honest)

No Java/Ghidra, no IDA, no rizin/radare2, no `xtensa-esp32-elf-objdump`
(verified absent); pip `capstone==5.0.7` has NO `CS_ARCH_XTENSA` (only
RISCV/X86/ARM/…); `esptool` present and used above. Xtensa code
disassembly was therefore NOT performed this pass. RISC-V path exists in
capstone but the C3 (RISC-V) build carries no nav stack (zero 8a7e/bare),
so it cannot answer 8a7e questions. `ghidra_export_xrefs.py` pins the exact
breakpoints for the next offline Ghidra run.
