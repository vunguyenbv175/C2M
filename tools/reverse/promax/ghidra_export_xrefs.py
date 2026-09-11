# Ghidra offline run-book for ProMax 8a7e + bare-table xrefs (STUB - no Ghidra here)
# Environment in V4 had no Java/Ghidra/IDA/rizin/objdump (verified) and capstone
# lacks Xtensa, so this script documents the exact next offline experiment.
#
# 1. Extract: classic app = firmware.bin[0x10000:0x10000+0x3D0000] (ESP32, entry
#    0x40083764); XL app = guition_ota_v1.bin (ESP32-S3, entry 0x4037E630).
#    Flash VA formula (classic): VA = 0x3F400020 + (flash_off - 0x10018).
#    XL OTA: VA = 0x3C180020 + (file_off - 0x18).
# 2. Ghidra: new project -> import classic_app.bin raw + set ESP32 Xtensa
#    (needs Espressif Ghidra-Xtensa extension), language xtensa:LE:32:default;
#    add memory blocks per map_esp_segments.py/esptool table (DROM/IRAM/IROM/DRAM).
# 3. Break on data: classic bare table file 0x8281C (VA 0x3FC82824), 8a7e0001
#    file 0x803D7 (VA 0x3FC803DF); XL bare file 0x68F79 (VA 0x3C1E8F82),
#    XL IROM consumer clusters file 0x410948/0x410BB4/0x410188 (VA IROM
#    0x42000948/0x42000BB4/0x42000188).
# 4. Export: Search Memory for those VAs -> References -> dump
#    (address, function, instruction, xref type) to CSV for EVIDENCE V3.
# Usage once Ghidra exists: ghidra_export_xrefs.py <csv-from-ghidra> [--json]
"""Stub only - prints the breakpoint list."""
BPS = [
 ("classic bare table", "flash 0x18281C", "VA 0x3FC82824"),
 ("classic 8a7e0001", "flash 0x1803D7", "VA 0x3FC803DF"),
 ("XL bare table", "file 0x68F79", "VA 0x3C1E8F82"),
 ("XL IROM settings-tail", "file 0x410948", "VA 0x42000948"),
 ("XL IROM literal pools", "file 0x410BB4", "VA 0x42000BB4"),
 ("XL IROM 8a7e struct", "file 0x410188", "VA 0x42000188"),
]
if __name__ == "__main__":
    for n, f, v in BPS: print(f"{n:24s} {f:18s} {v}")
