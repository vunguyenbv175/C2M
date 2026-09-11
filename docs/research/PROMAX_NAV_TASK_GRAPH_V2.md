# ProMax nav task graph V2 (update — no new edges)

Supersedes V1's open questions with V4 pointer evidence; topology still open.

## New in V4

- XL consumer CODE words located but unnamed (`0x4216CF9C/0x42085808/…` at
  settings-tail; literal-pool owners at `0x42000BB4…`; 8a7e-struct CODE words
  `0x4216743C/0x42003C14`). No queue/semaphore/event edge can be attached to
  them without disassembly — BLE→RX/parser→state→display chain stays
  NOT RECOVERED.
- `xTaskCreate/xQueueReceive/vTaskDelay` counts stand (V3); no
  `xQueueSend/xTimerCreate(create` on classic; XL keeps pinned+timer.
  `ObdBleTask` proven ABSENT from all 41 classic `firmware.bin` versions
  (bisect) and present only in C3/S3 — OBD task is variant-gated, and OBD
  central block stays disjoint from nav (HIGH separation, unchanged).
- Dual-role (advertise + scan) stands; 8a7e direction still unlabeled, so no
  RX/TX task can be assigned to nav.

## Graph (§26 required shape, evidence-backed only)

```text
BLE event --?--> RX/parser --?--> navigation state --?--> display task
 (dual-role     (consumers located,     (layout withheld)      (policy keys
  proven)        control-flow open)                             only)
```

No speculative edges added. Display-renderer backtrace (§27): render
functions still unidentified; field offsets/types unproven from this side too.

## Cross-architecture note (§28)

Classic↔XL agreement: identical bare-key SET (order differs), identical 8a7e
trio, identical dev shape modulo name. Parser VALUE handling: XL has located
consumers, classic has none-proven (method gap) — agreement on vocabulary,
not on code path. GATT direction agreement: none (both UNKNOWN).
