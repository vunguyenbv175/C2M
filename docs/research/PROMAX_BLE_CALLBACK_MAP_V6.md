# ProMax BLE callback map V6 — final (no new bindings; threshold audit)

ANALYSIS-ONLY. Required FUNCTION/ADDRESS/CALLSITE/STRUCT-OFFSET/CONSTANT/
INTERPRETATION/CONFIDENCE rows below. Prior structural evidence cited, not re-derived
(V2 GATT reverse, V5 descriptor table). String adjacency is NOT proof (§17).

## 1. Registration chain (8a7e0001/0002/0003)

| UUID | FUNCTION | ADDRESS | CALLSITE | STRUCT OFFSET | CONSTANT | INTERPRETATION | CONFIDENCE |
|---|---|---|---|---|---|---|---|
| 8a7e0001 | UNKNOWN | XL DROM ref `0x4200018C` area (V5 table neighbourhood) | UNKNOWN | UNKNOWN | none bound | string present in init-table region | UNKNOWN (role) |
| 8a7e0002 | UNKNOWN (candidate `0x42167668` unnamed) | XL record `0x4200017C–84` | UNKNOWN | record slots +0x00 str / +0x04 num / +0x08 CODE (offsets positional, NOT field-proven) | `0xFFF1` numeric in same record | registration-structure PARTIAL; service-vs-char UNPROVEN | PARTIAL-structure / UNKNOWN-semantics |
| 8a7e0003 | UNKNOWN | XL DROM ref `0x42000188` (V5 table) | UNKNOWN | UNKNOWN | none bound | string present in init-table region | UNKNOWN (role) |

Properties READ/WRITE/WRITE_NR/NOTIFY/INDICATE, permissions, callback pointers,
object/global addresses, registration order: **all UNKNOWN** (no symbols, no analyzer).

## 2. Callback binding

```text
phone → ProMax write callback:  UNKNOWN (no handler address recovered)
ProMax → phone notify/send:      UNKNOWN (pong/dev notify path unproven)
setValue/notify/indicate/onWrite/onRead/NimBLE/Arduino wrappers: none bound by behavior
```

Required verdicts:

```text
RX_ROLE = UNKNOWN
TX_ROLE = UNKNOWN
```

## 3. Evidence-threshold audit (§17)

PROVEN requires callback-registration+behavior, parser-branch+state-write,
state-write+reader, or switch-table+output-call. **Zero rows meet the bar.**
Strongest item remains the V5 XL descriptor-table record (PARTIAL structure).
V6 adds nothing. Recovery contribution of this doc: none (honest carry-forward).
