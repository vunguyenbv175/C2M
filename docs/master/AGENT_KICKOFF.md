# C2M Coding-Agent Kickoff

You are working directly on `vunguyenbv175/C2M`.

## Mandatory read order

Read these first, in this order:

```text
docs/master/DEBUG_MEMORY.md
docs/master/CURRENT_ARCHITECTURE.md
docs/reviews/2026-09-11_GATES_A_F_DELTA_REVIEW.md
docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW_V2.md
docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/runtime/DEVICE_BASELINE_CAPTURE.md
```

Older reports are historical evidence/indexes. If an older report conflicts with `DEBUG_MEMORY.md`, a newer owner review, or reproducible evidence, do **not** revive the stale conclusion.

## Product mission

The primary goal is **C2M Enhanced Firmware / C2M Enhanced AI Platform**.

The goal is **not** to repair the VI firmware as a product.

Strategy:

```text
OBSERVE STOCK
→ REUSE STOCK
→ AUGMENT
→ BENCHMARK
→ REPLACE SELECTIVELY
```

Ground truth:

```text
EN 2023-08-03 = GOLDEN working baseline; ADAS works on user's physical C2M.
VI 2023-09-20 = vendor Vietnam donor/reference; ADAS did not work on same C2M.
```

Use VI to learn useful newer behavior/localization. Do not make VI regression archaeology the main workstream unless it directly blocks an enhancement feature.

## Evidence hierarchy

```text
ORIGINAL FIRMWARE / DEVICE RUNTIME
        ↓
REPRODUCIBLE TOOL OUTPUT
        ↓
CANONICAL REVERSE REPORT
        ↓
DEBUG_MEMORY
        ↓
IMPLEMENTATION / MOCKS / SYNTHETIC TESTS
```

Synthetic tests prove implementation consistency, not stock truth.

Every technical claim must be labeled appropriately:

```text
CONFIRMED
HIGH-CONFIDENCE
RAW-ONLY
HYPOTHESIS
UNKNOWN
SUPERSEDED
```

Do not promote RAW/UNKNOWN stock values into product semantics without evidence.

## Current foundation state

Latest owner delta review found the corrective Gates A–F work valuable but not fully closed.

Current important status:

```text
Gate A firmware schema       PARTIAL PASS
Gate B safety/normalization  PARTIAL PASS
Gate C remote CI             RED
Gate D host/mock daemon      PASS as skeleton
Gate E fixture pipeline      PASS as SYNTHETIC stock-compatible fixture test
Gate F M4                    PASS with L3 BLOCKED
RoadIntelligence             PARTIAL / prototype matching
Web                          HOST PROTOTYPE
```

Do not mark the foundation COMPLETE until the latest owner findings are closed.

## Immediate work order

### P0 — correctness first

Fix and test:

```text
1. StockADASProvider freshness/stale clock must advance after Ingest.
2. Resolve is_second_crucial schema vs implementation contradiction.
3. Make GitHub CI green on a clean checkout without requiring uncommitted firmware build artifacts.
```

### P1 — close stock evidence

Original ADAS `.rodata` is still LZO-backed in customer UBIFS.

Use the original EN/VI firmware and reproducible extraction path to obtain exact ADAS binaries and verify hashes:

```text
EN expected SHA256:
0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043

VI expected SHA256:
997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
```

Then re-derive ADAS keys/fields/string evidence directly from those binaries.

If evidence changes a schema verdict, update:

```text
docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/master/DEBUG_MEMORY.md
```

Do not silently overwrite historical conclusions; mark superseded claims.

### P2 — host architecture hardening

```text
remove unverified unit semantics from stock-derived API field names
make read-only capability type-level/generic rather than M4Adapter convention
improve RoadIntelligence candidate scoring with geometry/distance
keep Web as HOST PROTOTYPE until connected to real device status
```

### P3 — hardware evidence when device is available

```text
collect EN known-good baseline
identify M4 L0 physical transport
passive pcap/libflow capture for L1
replace/augment synthetic fixtures with captured golden frames
ARM cross-build
```

No M4 warning/semantic injection during discovery.

## M4 maturity gate

Use these terms exactly:

```text
L0 transport identified
L1 passive decode proven
L2 harmless replay proven
L3 semantic injection proven
L4 custom UI optional
```

Current state:

```text
L3 = BLOCKED
```

Do not implement or claim L3 until L0/L1 evidence and safety gates justify it.

## Hard rules

```text
READ-ONLY-FIRST
EVIDENCE-FIRST
STOCK-COMPAT-FIRST
NO INVENTED M4 FIELDS/PORTS/UNITS
NO MODEL REPLACEMENT WITHOUT BENCHMARK
NO STOCK APP BREAKAGE
NO FULL NAND FLASH FOR DISCOVERY
NO BOOTLOADER/KERNEL MODIFICATION DURING DISCOVERY
NO CLAIM THAT TSR IS ENABLED UNTIL RUNTIME EVIDENCE PROVES IT
```

## Build/test truth

A test existing is not the same as a test passing.

Before claiming DONE, verify the actual run:

```text
CMake configure
build
CTest
standalone-header checks
Python tests
GitHub Actions conclusion
```

Firmware-evidence generation that requires original vendor TARs must be separated from normal clean-checkout CI unless the artifacts are explicitly provided.

## Commit/report discipline

Prefer small commits grouped by:

```text
evidence
tool
correctness fix
test
report
```

After significant work, write/update a report containing:

```text
WHAT WAS BUILT
WHAT WAS PROVEN
WHAT REMAINS UNKNOWN
STOCK COMPATIBILITY IMPACT
PERFORMANCE IMPACT
RISKS
NEXT HIGHEST-VALUE TASK
```

Update `docs/master/DEBUG_MEMORY.md` whenever a significant stock contract, root cause, superseded hypothesis, or maturity state changes.

Do not commit user serial numbers, private license material, calibration secrets, credentials, API keys, or proprietary provider dumps.
