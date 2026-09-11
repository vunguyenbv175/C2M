# Independent Owner Review V2 — C2M Enhanced Sprint 1

**Reviewed implementation commit:** `4d70f22773a959980f2a080729b753c96ba88d22`  
**Prior owner review:** `docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW.md`  
**Decision:** **REJECT claim that EF-A01..A06 are DONE. ACCEPT only as architecture scaffold / host prototype.**

## Executive conclusion

The sprint moved in the correct architectural direction, but it jumped from reverse-engineering notes to abstractions too quickly. The implementation commit is dominated by headers, design documents, mock providers and synthetic host demos. It did **not** independently re-derive the safety-critical schemas and semantics it normalizes from the two original vendor firmware images before encoding those assumptions into `StockADASProvider`, `DisplayState` and `M4Adapter`.

That methodology error is now the highest-priority finding because it explains several downstream problems already present in the code: generic warning fields are converted into FCW/PCW/LDW without proof, M4 policy is inconsistent, and product interfaces are being declared complete while the actual stock wire semantics remain partially unknown.

The two vendor firmware images are not merely historical regression artifacts. They are the primary implementation reference for C2M Enhanced:

```text
EN 2023-08-03 = GOLDEN working stock baseline
VI 2023-09-20 = donor/reference build
```

Reverse engineering should stop only when the interface needed by the product is sufficiently proven. It should not stop because a previous report already contains a convenient field name.

---

# F0 — CRITICAL — Implementation was written before exhausting available stock-firmware evidence

Sprint 1 uses existing reverse reports as its practical source of truth. Its own design document explicitly cites:

```text
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
```

The implementation commit itself adds no new firmware-carving, ELF/UBIFS extraction, stock binary semantic tracing or original-firmware evidence that proves the exact meanings it then hard-codes.

This is a problem because the task is not to invent a clean abstraction from partial notes. The task is to build a stock-compatible enhanced platform from the actual firmware behavior.

Examples where more direct firmware analysis was required before normalization:

```text
vehicleWarning.warning_level
vehicleWarning.fcw
vehicleWarning.headway_warning
vehicleWarning.vb_warning
vehicleWarning.sag_warning
pedestrian is_key / is_danger
laneWarningRes.deviate_state
TSR / SpeedLimitReporter output
ScreenWarningRes / ScreenAudioMsg routing
cardv JSON message semantics
M4/libflow topic/key schemas
```

### Why this matters

The current code already demonstrates the cost of premature abstraction:

```cpp
out.fcw.active = (fcw_raw != 0 || warning_level != 0);
```

and:

```cpp
if (p.is_danger || p.is_key) pcw = true;
```

Those are product semantics inferred from incomplete evidence, not proven stock semantics.

### Required correction

Before EF-A01/EF-A02 can become DONE:

1. Re-open the original EN/VI firmware binaries as primary evidence.
2. Trace the producer/consumer code for every safety-critical field normalized by `StockADASProvider`.
3. Record exact function/symbol/string/xref evidence in a stock schema document.
4. Mark every field as one of:

```text
CONFIRMED
HIGH-CONFIDENCE
RAW-ONLY
UNKNOWN
```

5. Only `CONFIRMED` semantics may drive normalized safety warnings.
6. Unknown fields must be preserved raw, not promoted into FCW/PCW/LDW meaning.
7. Add a machine-readable schema/evidence table used by both Python and C++ tests.

### Acceptance

Create:

```text
docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
```

At minimum cover:

```text
vehicleWarning
vehicleMeasure
pedestrians
laneWarningRes
TSR/speed-limit output
ScreenWarningRes
ScreenAudioMsg
```

Each normalized field must cite its source binary/function/xref or be explicitly RAW-ONLY/UNKNOWN.

---

# F1 — CRITICAL — `read-only` mode is decorative, not a hard gate

`EnhanceConfig` declares:

```cpp
std::string mode = "read-only";
```

but `EnhanceCore::Tick()` always invokes:

```cpp
bool ok = disp_->Render(d);
```

A configured sender can therefore write to stock-facing transport while the core still advertises read-only mode.

### Required fix

Use capability-based policy, not a string label.

Read-only mode must make stock-device writes impossible by construction. Planning/encoding must be separate from transmission.

### Acceptance

A test sender that increments/fails when invoked must receive exactly **zero** calls in read-only mode.

---

# F2 — HIGH — M4 L2 policy contradicts replay guard

Python guard classifies `GPSSpeed`/`GPSLevel` as semantic and denied at L2.

C++ `M4Adapter::PlanMessages()` emits `GPSSpeed` before checking `allow_semantic_injection`.

Thus the safety model disagrees between two implementations.

### Required fix

One canonical policy source. Default-deny all unknown/semantic stock messages until runtime proof exists.

---

# F3 — HIGH — `M4Adapter` is not an L3 semantic adapter

Turning `allow_semantic_injection=true` does not encode vehicle, lane, pedestrian, speed-limit, navigation or TPMS state.

Current status is:

```text
M4 adapter boundary
+ a few known JSON helpers
+ safety scaffold
```

not Level-3 semantic injection.

Keep L3 BLOCKED until passive stock captures prove transport, schema and field meaning.

---

# F4 — HIGH — Safety warning normalization contains unproven semantics

Current mapping can misclassify stock state:

```text
warning_level != 0 -> FCW
is_key -> PCW
deviate_state != 0 -> LDW
```

These meanings are not sufficiently proven.

### Required fix

Preserve raw warning fields and confidence/evidence status separately.

Until proven:

```text
fcw = only explicit proven FCW signal
pcw = only explicit proven PCW/warning signal
ldw = only proven lane-warning enum/state
```

Prefer UNKNOWN over a false safety alert.

---

# F5 — HIGH — Runtime classification confuses transport evidence with process evidence

Current normalization effectively treats:

```text
libflow disconnected -> A_ProcessAbsent
```

A socket state cannot prove the `adas` process is absent.

Separate:

```text
process_present
screen_service_reachable
subscription_active
frame_seen
frame_age
cardv_reachable
```

Only process evidence may classify `A_ProcessAbsent`.

---

# F6 — HIGH — No real `c2m-enhance` daemon exists

The commit provides `EnhanceCore`, but `CMakeLists.txt` builds only `smoke_enhance`.

Missing:

```text
production main
config loading
lifecycle
signal handling
service/deployment layout
watchdog semantics
provider startup/shutdown
read-only capability enforcement
```

EF-A04 is a library prototype, not a daemon.

---

# F7 — HIGH — No verified C++ build or CI

The sprint report states C++ was not compiled in the developer environment, and the reviewed commit has no CI result.

A header-heavy design can hide include/self-containment failures via transitive include order.

### Acceptance

CI must run:

```text
cmake configure
cmake build
ctest
standalone header compile checks
Python tests
```

No implementation ticket may be marked DONE without a passing build.

---

# F8 — MEDIUM/HIGH — Web Admin is a host mock demo

`web_admin.py` generates mock ADAS state and mock diagnostics and binds to localhost.

It is useful for defining a JSON/UI contract but is not an integrated C2M Web Admin.

Correct status:

```text
HOST PROTOTYPE
```

---

# F9 — MEDIUM/HIGH — Diagnostics are data structures, not diagnostics implementation

`DiagSnapshot` exists, but no real device collector populates it inside `EnhanceCore`.

Web diagnostics currently return zero/MOCK values.

The repo already contains read-only device collectors; product code should reuse or port their evidence sources rather than inventing another mock-only path.

---

# F10 — MEDIUM — RoadIntelligence is still a schema/demo, not an OSM pipeline

`osm_preprocess.py` inserts two hard-coded sample roads.

Missing:

```text
real fixture parse
spatial R*Tree
map matching
heading-aware candidate selection
conditional maxspeed handling
age/source semantics
Vietnam-scale preprocessing strategy validated by sample data
```

`FuseSpeedLimit()` is currently priority selection, not meaningful multi-source fusion.

---

# F11 — MEDIUM — Lead-vehicle fallback invents semantics

When no stock crucial marker exists, the provider chooses minimum `long_dist`.

Without proven sign/on-route/unit semantics this can choose an object that should not be considered the lead vehicle.

Prefer no lead over a fabricated lead until stock criteria are proven.

---

# F12 — LOW/MEDIUM — Dry-run render reports success

`M4Adapter::Render()` returns success when no sender exists.

This can make an unconfigured transport appear healthy.

Represent distinct states:

```text
DRY_RUN
UNCONFIGURED
CONNECTED
SEND_OK
SEND_FAILED
```

---

# Revised ticket status

| Ticket | Agent claim | Owner-review status |
|---|---|---|
| EF-A01 StockADASProvider | DONE | **PARTIAL / EVIDENCE-BLOCKED** |
| EF-A02 M4 consolidation | DONE | **PARTIAL / HARDWARE+EVIDENCE-BLOCKED** |
| EF-A03 DisplayState | DONE | **ACCEPT WITH FIXES** |
| EF-A04 c2m-enhance | DONE | **PARTIAL** |
| EF-A05 Web Admin V0 | DONE | **HOST PROTOTYPE** |
| EF-A06 RoadIntelligence | DONE | **HOST PROTOTYPE** |

---

# What should be retained

The sprint should **not** be reverted wholesale. Good choices include:

```text
provider-neutral boundaries
DisplayState abstraction
mock-provider pattern
host-first testing direction
stock code untouched
M4-specific details isolated behind adapter boundary
lightweight implementation style
```

The problem is not the abstraction itself. The problem is claiming product semantics and completion before those abstractions are sufficiently grounded in stock firmware evidence.

---

# Mandatory next delta

Do **not** move to VietMap, TPMS or custom AI yet.

## Gate A — Firmware-grounded stock contract

Use the two original firmware images as primary evidence and produce `STOCK_ADAS_SCHEMA_V2`.

Trace and classify all safety-critical fields used by EF-A01.

## Gate B — Foundation safety

Fix F1/F2/F5/F12:

```text
true read-only capability gate
one M4 safety policy
honest health states
no transport-state -> process-state inference
```

## Gate C — Build reality

Add CI and prove C++ targets compile.

## Gate D — Real process skeleton

Create actual `c2m-enhance` executable in host/mock/read-only mode.

## Gate E — Minimal real-data path

Connect at least one real stock input path to the provider without writing to stock:

```text
captured libflow frame -> decoder -> StockADASProvider -> DisplayState
```

Use recorded stock payload fixtures when hardware is unavailable.

## Gate F — M4 remains passive

No semantic injection until real passive capture validates transport and message schema.

---

# Final owner verdict

Sprint 1 produced a **useful architecture skeleton**, not a completed product foundation.

The most important correction is methodological:

> **The stock firmware is the specification. Reports are indexes to evidence, not replacements for evidence.**

For every stock-facing feature, the coding agent must first prove enough of the real firmware contract, then encode that contract in the enhanced platform.

Only after Gates A–F pass should EF-A01..A06 be reconsidered for COMPLETE status.
