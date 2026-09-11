# ProMax 8A7E GATT reverse V2 (pointer-xref evidence; roles still unproven)

Analysis-only. No adjacency-as-proof. VA+file offsets per memory-map doc.

## Method (new in V4)

Absolute LE32 pointer scan over IRAM/IROM/DRAM segments for words landing in
the DROM ranges of the three 8a7e strings, FFF block, dev JSON, and bare
table (script `v4_xref.py`; method validators: `/config.txt`, DTBK).

## XL-S3 OTA — PARTIAL (real DATA xrefs, code semantics unproven)

8a7e0001 VA range `0x3C1E8CA2–0x3C1E8D12`: 8 hits —
IROM file `0x410188/0x410194/0x41022C/0x410234/0x41023C` (VA `0x42000170…224`)
plus far `0x4CDD4C/0x4CDF3C/0x530478`. Decoded cluster @file `0x410180–0x4101B4`:

```text
0x410180: DROM->"04c0001\08a7e0003…"   0x410184: DROM->"04c0001\0Promax XL\08a7e0001…"
0x410188: DROM->"omax XL\08a7e0001…"   0x41018C: 0x0000FFF0 (numeric FFF0 service id)
0x410190: CODE 0x4216743C              0x410194: DROM->"04c0001\0[BLE] Stopping…"
0x41019C: DROM->mbedTLS rsaEncryption  0x4101A0/1A4: DRAM 0x3FCAAD60/70 (buffers/handles?)
0x4101AC: CODE 0x42003C14              0x4101B0/1B4: small ints (handles/lengths?)
```

Interpretation (PARTIAL): one IROM setup structure co-locates 8a7e string
pointers + numeric `0xFFF0` + code pointers + DRAM buffer pointers —
consistent with a BLE service/characteristic registration block. It does NOT
prove which UUID is service vs RX vs TX, nor properties/permissions/callbacks:
no `createCharacteristic/setCallbacks/onWrite` symbols exist to label the
code pointers, and without Xtensa disassembly the two CODE words cannot be
named. `0x0000FFF0` as an integer (not string) suggests 16-bit UUID shorthand
in the same struct. Roles: still UNKNOWN; existence+registration-structure:
PARTIAL (up from UNKNOWN).

Required table (§5): UUID / DATA XREF (above) / FUNCTION (UNKNOWN — two
unnamed CODE words) / ROLE UNKNOWN / PROPERTIES UNKNOWN / PERMISSIONS UNKNOWN
/ CALLBACK UNKNOWN / VALUE BUFFER (DRAM 0x3FCAAD60/70 hypothesized, LOW) /
CONFIDENCE PARTIAL.

## Classic ESP32 — UNKNOWN (method-invalid, not absence)

Zero absolute-pointer hits for bare table, all three 8a7e strings, dev JSON
— AND zero hits for validator strings `/config.txt` (VA `0x3F480655`) and
DTBK defaults. The method itself is therefore invalid on this build
(Xtensa L32R literal pools / flash-cache addressing differ; Arduino-IDF4 vs
NimBLE-IDF5 codegen). This is a ceiling statement, NOT evidence the
references don't exist. Classic roles remain UNKNOWN.

## Service hierarchy, properties, CCCD, MTU (§6–§7)

Unproven on both targets: no props bitmask, permissions, CCCD `0x2902`
(tied to 8a7e zero), max length, initial value, MTU, or
`esp_ble_gatts_create_service/add_char/add_char_descr` /
`ESP_GATTS_WRITE_EVT/READ_EVT/send_indicate` symbols bound to 8a7e.
Dual-role firmware (advertise + central scan) and OBD-central separation
stand from V3 (HIGH), but 8a7e direction cannot be labeled from them.

## Write/notify paths (§8–§9)

GATT write handler → frame buffer → parser → state chain: NOT RECOVERED
(no handler address). Notify path for `pong/dev`: direction UNPROVEN —
sequence diagram deliberately withheld (all arrows UNKNOWN). The bare-table
consumer clusters (parser doc) prove code reads live keys, not which
characteristic delivered them.
