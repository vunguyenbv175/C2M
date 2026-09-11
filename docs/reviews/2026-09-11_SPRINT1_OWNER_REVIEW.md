# Independent Owner Review — C2M Enhanced Sprint 1

**Reviewed commit:** `4d70f22773a959980f2a080729b753c96ba88d22`  
**Baseline:** `95b92b66f1006cca6609aeb336be59847fa84ff9`  
**Decision:** **REJECT claim that EF-A01..A06 are DONE. ACCEPT as architecture scaffold / host prototype.**

## Executive assessment

The commit is directionally good: provider-neutral state, mockable interfaces, no stock firmware mutation, and reuse-first boundaries are appropriate. However, the sprint report overstates completion. Most work is header-only scaffolding or synthetic host simulation; no C++ target was compiled in CI, no real stock transport is integrated, no actual `c2m-enhance` daemon exists, Web V0 is mock-only, and RoadIntelligence is a hard-coded sample rather than an OSM preprocessing pipeline.

The most important defect is that the advertised **read-only safety gate is not enforced**.

---

## F1 — CRITICAL — `read-only` mode is decorative, not a hard gate

`EnhanceConfig` declares:

```cpp
std::string mode = "read-only";  // hard gate V0
```

but `EnhanceCore::Tick()` never checks `cfg_.mode`. It always calls:

```cpp
bool ok = disp_->Render(d);
```

A real `M4Adapter` with a configured sender can therefore perform writes while the core still says `mode=read-only`.

### Required fix

Use capability-based policy, not a string comment. In read-only mode:

- no adapter method capable of stock-device writes may be invoked;
- planning/encoding must be separable from transmission;
- an explicit owner-approved transition must be required for replay/injection;
- tests must prove zero sender calls in read-only mode.

**Acceptance:** unit test with a sender that increments/fails if called; `EnhanceCore` read-only tick must call it exactly zero times.

---

## F2 — HIGH — M4 L2 policy contradicts replay guard

`replay_guard.py` explicitly classifies `GPSSpeed`/`GPSLevel` as **DENY for L2**, requiring semantic proof/L3.

`M4Adapter::PlanMessages()` nevertheless emits `GPSSpeed` unconditionally before checking `allow_semantic_injection`:

```cpp
if (s.ego_speed_kmh >= 0)
  out.emplace_back("cardv:8080", StockJson_GPSSpeed(s.ego_speed_kmh));
if (!cfg_.allow_semantic_injection) return out;
```

So the C++ safety policy and Python guard disagree.

### Required fix

Create one canonical policy table/library. Until runtime proof exists, L2 must default-deny `GPSSpeed`, `GPSLevel`, ADAS state and semantic libflow keys.

**Acceptance:** policy parity tests must assert the same verdict in C++ and Python for every known UUID/key.

---

## F3 — HIGH — `M4Adapter` is not L3 semantic injection yet

With `allow_semantic_injection=true`, the implementation adds no semantic M4 messages. It returns the same vector produced before the gate. No vehicle/lane/pedestrian/navigation/TPMS/speed-limit semantic encoder is implemented.

Therefore EF-A02 must be reported as:

```text
M4Adapter interface + known JSON helpers + safety scaffold
```

not “M4 L3 adapter complete”.

### Required fix

Keep L3 BLOCKED until passive runtime decode proves transport/path/schema. Then add explicit semantic encoders and golden-capture tests.

---

## F4 — HIGH — `StockADASProvider` warning normalization makes unproven semantic assumptions

Current FCW logic is:

```cpp
out.fcw.active = (fcw_raw != 0 || warning_level != 0);
```

But `vehicleWarning` also has headway/VB/SAG-related state. A non-zero generic `warning_level` is not yet proven to mean FCW. This can convert another warning class into FCW.

PCW is likewise inferred from:

```cpp
p.is_danger || p.is_key
```

`is_key` has not been proven to mean a pedestrian collision warning.

LDW is inferred from `deviate_state != 0` while the enum is explicitly runtime-unverified.

### Required fix

Preserve raw stock fields separately. Only expose normalized safety warnings after runtime semantics are confirmed. Until then mark them `UNKNOWN`/unverified rather than inventing meaning.

Add negative tests:

- headway warning without FCW must not become FCW;
- key pedestrian without proven warning flag must not become PCW;
- unknown lane enum must not silently become LDW.

---

## F5 — HIGH — Runtime classification conflates transport state with process state

The normalizer maps:

```text
libflow disconnected -> A_ProcessAbsent
```

A disconnected socket does not prove the ADAS process is absent. It may be alive with ScreenService disabled/unreachable or transport broken.

Likewise a connected libflow endpoint with no first frame can appear healthy because the default timestamps can produce age zero.

### Required fix

Separate observations:

```text
process_present
screen_service_reachable
subscription_active
frame_seen
frame_age
cardv_reachable
```

Only the device runtime collector/process evidence may classify `A_ProcessAbsent`.

---

## F6 — MEDIUM/HIGH — No real `c2m-enhance` daemon exists

The commit creates an `EnhanceCore` header class but no production `main`, lifecycle, signal handling, configuration loading, watchdog behavior, deployment layout or service script.

`CMakeLists.txt` builds only:

```text
smoke_enhance
```

Thus EF-A04 is an in-process library prototype, not a daemon.

### Required fix

Create an actual host-buildable daemon target first, with mock providers by default. Add embedded integration only after cross-toolchain is known.

---

## F7 — MEDIUM/HIGH — C++ code has no verified build/CI

The sprint report states the developer environment had no `g++`; therefore `smoke_enhance.cpp` was not compiled there. GitHub has no CI status for this commit.

Header self-containment also needs checking; e.g. `event_bus.hpp` uses `std::uint64_t` without including `<cstdint>`, and `display_state.hpp` uses `std::max({...})` without including `<algorithm>`. The current smoke include order can hide such defects through transitive includes.

### Required fix

Add CI:

```text
cmake configure
cmake build
ctest
standalone-header compile checks
Python unit tests
```

No sprint may be marked DONE while required build targets have never compiled.

---

## F8 — MEDIUM — Web Admin V0 is a mock host demo, not integrated Web Admin

`src/web/web_admin.py`:

- binds only `127.0.0.1`;
- generates mock ADAS data;
- returns mock/zero diagnostics;
- is disconnected from `EnhanceCore` and device collectors.

This is useful as a schema/UI prototype but is not deployable C2M Web Admin.

### Required fix

Rename/status it clearly as `host demo` until it consumes a real local read-only status API. Preserve the JSON contract if useful.

---

## F9 — MEDIUM — RoadIntelligence preprocessing is not implemented yet

`tools/road/osm_preprocess.py` imports XML parsing but does not parse OSM XML/PBF. It inserts two hard-coded rows. The database uses a normal multi-column index, not SQLite R*Tree, and there is no map matching.

`FuseSpeedLimit()` is priority selection, not real multi-source confidence fusion.

### Required fix

Treat A06 as interface/schema prototype. Next implementation should include a real small OSM fixture -> preprocessing -> spatial index -> query/map-match test before attempting Vietnam-scale data.

---

## F10 — MEDIUM — Lead-object fallback can select an invalid object

When stock does not mark a crucial/second-crucial object, fallback chooses the minimum `long_dist` across all vehicles. If signed/behind/off-route objects can occur, this can choose an invalid lead vehicle.

### Required fix

Do not invent lead semantics until sign/unit/on-route behavior is proven. Prefer no lead over a potentially wrong lead, or require validated positive/on-route criteria.

---

## F11 — LOW/MEDIUM — Dry-run display reports success and can mask missing transport

`M4Adapter::Render()` returns `true` when no sender is configured. `EnhanceCore` then records `render-ok`/healthy. A missing transport can therefore look healthy.

### Required fix

Represent at least:

```text
DRY_RUN
UNCONFIGURED
CONNECTED
SEND_OK
SEND_FAILED
```

Do not collapse dry-run into successful rendering.

---

# Ticket status after review

| Ticket | Agent claim | Reviewer status |
|---|---|---|
| EF-A01 StockADASProvider | DONE | **PARTIAL** — normalization scaffold; runtime semantics/transport not proven |
| EF-A02 M4 consolidation | DONE | **PARTIAL/BLOCKED** — adapter scaffold only; L2 policy conflict; L3 absent |
| EF-A03 DisplayState | DONE | **ACCEPT WITH FIXES** — useful abstraction; compile/self-containment tests needed |
| EF-A04 c2m-enhance core | DONE | **PARTIAL** — library core only, no daemon, read-only gate broken |
| EF-A05 Web Admin V0 | DONE | **PROTOTYPE** — host mock only |
| EF-A06 RoadIntelligence | DONE | **PROTOTYPE** — interface + hard-coded sample only |

# What is genuinely good and should be retained

- provider-neutral ADAS/Display interfaces;
- mock providers and host-first design;
- stock code is untouched;
- raw M4 packet knowledge is largely isolated behind adapter boundary;
- no heavy runtime/framework introduced;
- report openly records several unknown units/enums;
- default direction remains reuse-first.

# Required next delta

Do **not** start VietMap/TPMS/custom AI yet.

First close the foundation gate:

1. enforce true read-only capability gate;
2. unify replay/M4 policy and remove L2 semantic writes;
3. add CI and compile all headers/targets;
4. correct unproven safety-warning semantics;
5. create actual `c2m-enhance` executable in mock/read-only mode;
6. make Web V0 consume real core status (still host/mock transport allowed);
7. replace hard-coded road DB generator with a real tiny OSM fixture pipeline;
8. keep M4 L3 blocked until real passive capture validates transport/schema.

Only after these pass should Sprint 1 be marked COMPLETE.
