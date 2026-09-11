# Independent Owner Delta Review — Gates A–F

**Reviewed delta:** `1eab94af132355c0d24ce131484cc6aae266fd7e..a58f697a5dd997e4d2231e7b1b77dc7e9e41ae8c`  
**Review basis:** source diff, committed firmware evidence tables/tools, and actual GitHub Actions state.  
**Decision:** **MAJOR IMPROVEMENT, but Gates A–F are not all closed.** Keep the implementation; fix the findings below before declaring the foundation complete.

## Executive verdict

The worker materially improved the project. This is no longer a superficial scaffold-only pass. The delta adds reproducible firmware tooling, a field-level evidence ledger, safer normalization, a real host executable, stricter M4 policy, tests, an OSM XML→R*Tree fixture pipeline, and explicit BLOCKED state for M4 L3.

However, several claims in the response report overstate what is proven:

1. ADAS-side schema is still partly dependent on prior disassembly because the LZO-compressed ADAS string layer remains unavailable in this delta.
2. GitHub CI is **not green**; the two actual workflow runs are failed.
3. StockADASProvider freshness is currently broken because elapsed time does not advance after `Ingest()`.
4. `is_second_crucial` is documented as not creating a lead by itself but the implementation does exactly that.
5. Gate E uses synthetic stock-compatible fixtures, not captured real stock data.
6. Road matching is heading-ranked candidate selection, not true nearest-segment matching.

These do not justify reverting the work. They require another focused delta.

---

# R1 — HIGH — StockADASProvider stale timeout does not advance after Ingest

`NormalizeStock()` computes age from:

```cpp
s.now_ms - s.last_frame_ms
```

but `StockADASProvider::Poll()` repeatedly normalizes the stored `last_` snapshot without updating `last_.now_ms` or accepting a current clock value.

Therefore:

```text
Ingest at t=1000 with last_frame=900
Poll immediately       -> age=100
Poll 30 seconds later  -> age is STILL 100
```

A dead/stalled input can remain healthy indefinitely.

`EnhanceCore::Tick(now_ms, ...)` has current time, but that value is not supplied to the provider freshness calculation.

## Required fix

Use one of:

```text
Poll(now_ms)
clock injection into StockADASProvider
UpdateNow(now_ms) before Poll
```

Prefer an explicit monotonic-clock abstraction so host tests can control time.

## Acceptance test

```text
Ingest frame at 1000ms
Poll at 1200ms -> fresh
Poll at 1601ms with stale_after=500 -> stale
No new Ingest between polls
```

This test must fail on the reviewed commit and pass after the fix.

---

# R2 — HIGH — `is_second_crucial` contract contradicts implementation

The generated schema says:

```text
vehicleMeasure.is_crucial
  SOLE lead-vehicle signal

vehicleMeasure.is_second_crucial
  secondary marker only; never invents lead alone
```

But `NormalizeStock()` does:

```cpp
if (!out.lead.present) {
  for (...) {
    if (v.is_second_crucial) {
      out.lead = LeadInfo{true, "second_crucial", ...};
      break;
    }
  }
}
```

So a second-crucial object becomes a normalized lead even when no `is_crucial` object exists.

## Required decision

Either:

1. keep `is_second_crucial` RAW/HIGH-CONFIDENCE metadata only and do **not** populate `lead`, or
2. prove from stock producer/consumer code that it is intentionally a fallback lead class, then update the schema/evidence wording.

Do not let schema and product semantics disagree.

---

# R3 — HIGH — Gate C claim “GitHub CI green” is false

Actual GitHub Actions state was checked after the worker push.

Runs observed:

```text
run #1 head a58f697...  conclusion: failure
run #2 head c94351b...  conclusion: failure
```

Therefore only the **local CI** green claim may currently stand.

There is an additional reproducibility problem in `.github/workflows/ci.yml`:

```text
python3 tools/fw/stock_adas_schema_v2.py
```

The generator requires local files such as:

```text
build/fw_bin_en/cardv
build/fw_bin_vi/cardv
build/rootfs_en_inner.bin
build/rootfs_vi_inner.bin
build/en_customer_inventory.json
build/vi_customer_inventory.json
build/adas_plain_en.json
```

Those inputs are not created by the workflow and are not committed. A clean GitHub runner therefore cannot reproduce this step as written.

## Required fix

Separate CI concerns:

### Product CI — must run on every push

```text
CMake configure/build
CTest
standalone headers
Python protocol/normalizer/policy/road fixture tests
fixture generation
```

No dependency on proprietary/original firmware files.

### Firmware-evidence verification — explicit/local/artifact-backed

```text
original TARs or pre-extracted evidence supplied deliberately
verify expected SHA-256
run carve/extract/generator
compare generated evidence against canonical committed JSON
```

Do not make normal GitHub CI depend on uncommitted firmware-derived build artifacts.

Also make `tools/ci/local_ci.py` support a strict mode in which missing `g++` or CMake is a failure rather than a successful `SKIP`; otherwise “green” can be misleading on a poorly provisioned host.

---

# R4 — MEDIUM/HIGH — Gate A is improved but not fully independent of prior reports

The worker did genuine new firmware-grounded work:

```text
TAR SHA verification
partition/rootfs/customer inventory
cardv extraction/hash/context
cardv symbol diff
libflow identity
customer audio/model inventory
```

This is accepted and valuable.

However `tools/fw/stock_adas_schema_v2.py` explicitly defines the ADAS-side basis as:

```text
"direct string proof pending LZO decompression"
"Key routing is HIGH-CONFIDENCE via prior callsite disassembly
 (M4_STATIC_PROTOCOL_V1 §2)"
```

Therefore the statement that Gate A is now derived from original firmware **without relying on old reports** is too strong.

Correct status:

```text
cardv/rootfs/libflow/customer inventory: newly re-derived from original images
ADAS key/field routing: HIGH-CONFIDENCE, still partly inherited from earlier disassembly until LZO extraction or runtime capture closes it
```

This is acceptable if labeled honestly. It is not yet a fully closed F0 gate.

The proposed next step — LZO extraction of the original ADAS executable — is indeed the highest-value static task.

---

# R5 — MEDIUM — Read-only is safe for current M4Adapter, but capability model is weaker than documented

The current `M4Adapter::Render()` is safely planning-only and calls `RenderEx(..., false)`. The zero-sender test is useful and accepted.

But the architecture claims a capability object while the actual transmit method takes:

```cpp
RenderEx(const DisplayState&, bool allow_transmit)
```

and `AllowTransmit` declared in core is unused.

Also `EnhanceCore` accepts generic `IDisplayAdapter` and calls `Render()`. The interface contract itself does not enforce that every future adapter's `Render()` is non-transmitting.

Thus "zero transmission by construction" is currently true for the reviewed M4Adapter implementation, not universally enforced by the type system.

## Recommended fix

Split interfaces, for example:

```text
IDisplayPlanner          // pure/read-only
IStockTransmitter        // explicit write capability
```

or require an unforgeable/explicit capability token in the transmitting API instead of a boolean.

Keep the core dependent only on the read-only interface.

---

# R6 — MEDIUM — DisplayState leaks unverified units into field names

Schema V2 correctly states that units/signs of several stock quantities remain unknown.

But product-facing fields include names such as:

```text
DisplayObject.lateral_m
DisplayObject.longitudinal_m
NavState.distance_m
ego_speed_kmh
```

while stock `lateral_dist`, `longitude_dist`, and GPS-speed unit semantics are still declared unverified.

Copying an unverified raw number into a field ending `_m` or `_kmh` silently upgrades an assumption into API semantics.

## Required fix

Until units are proven, use raw/neutral representation, e.g.:

```text
longitudinal_raw
lateral_raw
raw_value + Evidence/unit metadata
```

Only expose `_m`/`_kmh` once runtime/static evidence supports the conversion.

OSM speed limits can remain km/h after proper OSM parsing/conversion because that is a separate, defined data source.

---

# R7 — MEDIUM — Gate E is a valid fixture integration test, not “real-data path” proof

`make_fixture.py` constructs MessagePack frames itself using assumed stock-compatible shapes. `test_real_data_path.py` explicitly says these are stand-ins until a hardware pcap exists.

That test is useful and should remain.

Correct classification:

```text
CONFIRMED: decoder→normalizer consumer pipeline handles the project's stock-compatible fixture contract
UNKNOWN: a captured EN device frame passes the same pipeline unchanged
```

Rename/document the gate accordingly to avoid future agents confusing fixture compatibility with captured stock wire proof.

Gate E should become fully hardware-grounded only after L1 passive capture.

---

# R8 — MEDIUM — OSM R*Tree pipeline is real, but query is not true nearest-segment matching

The new road pipeline genuinely parses OSM XML and builds a SQLite R*Tree. This is a real improvement over the previous hard-coded two-row database.

However `query()`:

1. retrieves segments whose bounding boxes overlap the search window;
2. calculates heading difference;
3. sorts only by `heading_diff_deg`.

It does not calculate point-to-segment distance. A farther road with a perfect heading can outrank a nearby road with a slightly different heading.

Therefore the phrase `heading-aware nearest-segment query` is overstated.

## Required fix

Rank candidates using at least:

```text
point-to-segment distance
heading compatibility
oneway compatibility
road class / continuity optional later
```

Add a fixture where the closest segment and best-heading segment are different, and assert the intended score chooses correctly.

Also treat complex OSM `maxspeed` values (`mph`, `signals`, conditional/multiple values) explicitly before Vietnam-scale preprocessing.

---

# R9 — LOW/MEDIUM — `TickResult.planned_messages` is never populated

`TickResult` exposes `planned_messages`, but `EnhanceCore::Tick()` always returns:

```cpp
TickResult{d, st, 0}
```

so the field is not currently meaningful.

Either populate it from a planner result or remove it until the planner interface exposes that information.

---

# Gate status after independent delta review

| Gate / area | Worker claim | Owner verdict |
|---|---|---|
| Gate A firmware schema | closed | **PARTIAL PASS** — major re-derivation done; ADAS-side semantics still LZO/report dependent |
| Gate B safety/normalization | closed | **PARTIAL PASS** — major fixes good; stale clock + second-crucial contradiction remain |
| Gate C CI/build | green | **FAIL remotely / PASS claimed locally** — actual GitHub runs failed |
| Gate D c2m-enhance | daemon real | **PASS as host/mock daemon skeleton** |
| Gate E data path | real-data path | **PASS as synthetic stock-compatible fixture integration test** |
| Gate F M4 | L3 BLOCKED | **PASS** — correct conservative state |
| Road | R*Tree/query | **PARTIAL PASS** — real XML/R*Tree, matching algorithm still prototype |
| Web | host prototype | **PASS classification** |

---

# What should be retained unchanged

The following direction is correct and should not be rolled back:

```text
AdasRaw + evidence tiers
transport observations separated from process presence
warning_level/is_key no longer promote warnings
no minimum-distance lead fallback
M4 L3 explicitly BLOCKED
GPSSpeed denied at L2
planning separated from M4 transmission
real CMake daemon target
standalone-header checks
stock-compatible MessagePack fixtures
OSM XML fixture + R*Tree
Web explicitly labeled HOST PROTOTYPE
```

---

# Next required delta — in priority order

## P0 — correctness

1. Fix provider freshness clock and add advancing-time test.
2. Resolve `is_second_crucial` schema/implementation contradiction.
3. Fix GitHub CI so a clean push is green and does not require uncommitted firmware artifacts.

## P1 — evidence closure

4. Use available GCC/liblzo route to extract original EN/VI ADAS binaries reproducibly.
5. Re-run direct string/ELF evidence over extracted ADAS and upgrade/downgrade schema rows accordingly.
6. Preserve old rows as history if their verdict changes.

## P2 — host architecture quality

7. Remove unverified `_m`/`_kmh` semantics from stock-derived API fields.
8. Harden capability interface so read-only is type-level, not M4Adapter convention.
9. Improve road candidate scoring with geometric distance.

## P3 — hardware evidence

10. EN known-good device: collect baseline and identify L0 physical transport.
11. Passive pcap/libflow capture to close L1 and replace synthetic Gate E fixtures with captured golden fixtures where legally/project-appropriately stored.
12. ARM cross-build after host foundation is green.

---

# Final decision

**Do not revert `a58f697`.** It is a strong corrective delta and substantially better than Sprint 1.

But do **not** mark the foundation complete yet.

The correct project state is:

```text
architecture direction: ACCEPTED
firmware-grounded evidence system: ACCEPTED, still incomplete on ADAS LZO layer
host prototype: materially functional
remote CI: RED
hardware integration: not yet proven
M4 L3: correctly BLOCKED
next static task: LZO extraction
next correctness tasks: stale clock + second_crucial + CI
```
