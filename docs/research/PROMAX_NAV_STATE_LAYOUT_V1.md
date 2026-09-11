# ProMax nav state layout V1 (withheld — no proven offsets)

Analysis-only. This document exists to record that §12 was attempted and to
prevent invented structs from entering the tree.

## Attempt

Pointer-scan (XL) + string-structure (classic) + renderer-backtrace were all
applied to anchor parsed values (`spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/
unix/hi`) to RAM destinations. Consumer CODE words were located (XL IROM
`0x42000948…`, `0x42000BB4…` clusters) but cannot be decoded without Xtensa
disassembly, so no writer→field→reader edge is proven.

## Table (§12 required shape, honest content)

```text
OFFSET | FIELD | TYPE | WRITER | READERS | CONFIDENCE
   —   |  —    |  —   |   —    |   —     | UNKNOWN (no row proven)
```

Key-name vocabulary (HIGH) must NOT be mistaken for layout. The neutral C2M
`NavigationState` proposal (V2 arch doc) remains the only usable schema, fed
by handshake vocabulary + offline sources, never by these unproven offsets.

## What would fill this in

Ghidra Xtensa run per `ghidra_export_xrefs.py` breakpoints: name the CODE
words in the two XL clusters, follow their stores into DRAM globals, then
cross to display-task loads. Classic needs the same after solving its
literal-pool addressing.
