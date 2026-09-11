# Independent Owner Review — Delta R1–R9

**Repository:** `vunguyenbv175/C2M`  
**Reviewed base:** `a865039a947445d5c1517330b1a8a2a62f35b7a4`  
**Reviewed head:** `d134af30704633fcefeb7d4de97790176109c0cb`  
**Review date:** 2026-09-11  
**Role:** independent owner-level reviewer  
**Decision:** **MAJOR IMPROVEMENT / KEEP THE DELTA, BUT DO NOT DECLARE GATES A–F FULLY CLOSED YET.**

---

## 1. Executive verdict

The worker delta is materially good and should be retained.

It successfully addresses the highest-priority correctness findings from the previous owner review:

```text
R1  stale/freshness clock              FIXED
R2  is_second_crucial contradiction    FIXED
R3  product CI clean-checkout           FIXED; remote c2m-ci GREEN
R5  planner/transmitter split           IMPROVED, but transmit boundary still needs hardening
R6  unverified stock units in API       FIXED
R7  Gate E synthetic labeling           FIXED
R8  road geometric scoring              IMPROVED / prototype
R9  planned_messages                     FIXED
```

The LZO extraction work is especially valuable. Both original ADAS executables are now extracted reproducibly with the expected canonical hashes, allowing direct ELF/string evidence instead of depending only on earlier disassembly notes.

Remote product CI is confirmed green on GitHub Actions for head `d134af3` (`c2m-ci` run #6, conclusion `success`).

However, three findings remain before the project should call the current foundation complete:

1. `firmware-evidence.yml` is currently capable of false-green success.
2. the M4 transmit boundary can bypass planner/L3 policy enforcement;
3. direct string presence is being promoted too aggressively to `CONFIRMED` routing semantics.

These are focused issues. They do not justify reverting the worker delta.

---

# R1 — HIGH — `firmware-evidence.yml` is not a strict evidence verifier yet

The product CI split is correct:

```text
ci.yml
  -> clean checkout
  -> no proprietary/original firmware dependency
  -> build/test/headers/Python fixture tests
```

and remote GitHub Actions is now green.

That part is accepted.

The separate firmware-evidence workflow is not yet strict enough to be trusted as a gate.

Current workflow contains failure-swallowing constructs equivalent to:

```sh
python3 tools/fw/stock_adas_schema_v2.py || echo "needs build/ inputs ..."

git diff --exit-code docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json \
  || echo "evidence drift — review required"
```

Therefore either of these situations can still end with a successful workflow job:

```text
evidence generator failed
canonical evidence drifted
```

This defeats the purpose of an evidence-verification workflow.

There is also a design mismatch: the workflow requires original vendor TARs under `firmware/original/`, while this repository is now public and those firmware artifacts should not be committed merely to make GitHub Actions work.

## Required fix

Use one of these explicit models:

### Preferred model — local/artifact-backed evidence verification

```text
product CI                         GitHub-hosted, every push
firmware evidence verification    local or explicit artifact-backed/manual job
```

The evidence verifier must:

```text
fail on missing required TAR/artifact
fail on SHA mismatch
fail on extraction failure
fail on generator failure
fail on evidence drift
```

No `|| echo` on mandatory verification steps.

If GitHub Actions is retained for this workflow, original firmware must be supplied deliberately through an appropriate non-repo artifact mechanism; do not place vendor TARs into the public repository solely for CI.

## Acceptance criteria

The verifier must return nonzero when each of the following is intentionally induced:

```text
missing EN TAR
wrong EN SHA
LZO extraction failure
schema generator failure
modified canonical JSON
```

Until then:

```text
Product CI      PASS
Evidence CI     NOT YET A TRUSTED GATE
```

---

# R2 — HIGH — M4 transmitter can bypass planner/L3 policy

The new interface split is a genuine improvement:

```text
IDisplayPlanner      pure/read-only
IStockTransmitter    explicit write path
EnhanceCore          depends only on IDisplayPlanner
```

This correctly prevents normal core ticks from transmitting to stock M4.

However, the current write boundary is still weaker than the documentation implies.

`AllowTransmit` is publicly constructible:

```cpp
struct AllowTransmit {
  explicit AllowTransmit() = default;
};
```

and `IStockTransmitter::Transmit()` accepts arbitrary `PlannedMessage` objects:

```cpp
Transmit(msgs, AllowTransmit{})
```

`M4Adapter::Transmit()` then forwards those messages to `sender_` without re-checking `M4Policy`.

Therefore another component can construct a semantic/unknown payload directly and bypass:

```text
Plan()
M4Policy::ClassifyJsonUuid(...)
L3 BLOCKED intent
```

The current smoke test proves:

```text
EnhanceCore does not call sender
```

which is useful, but it does not prove:

```text
all stock-facing write paths are policy-enforced
```

## Required fix

Policy enforcement must exist at the final stock-facing boundary, not only in the planner.

Preferred design:

```text
DisplayState
   |
   v
IDisplayPlanner
   |
   v
Typed/validated M4 command
   |
   v
M4Policy validation
   |
   v
IStockTransmitter
   |
   v
stock transport
```

At minimum, `Transmit()` must reject any message whose channel/payload/UUID is not permitted by the active M4 policy level.

Better still, do not expose arbitrary raw payload construction to normal feature code. Use typed commands or an internal/private capability token whose construction is limited to commissioning code.

## Required negative tests

Add tests proving all of these fail while L3 remains BLOCKED:

```text
GPSSpeed direct transmit
AdasStatus direct transmit
unknown JSON UUID direct transmit
arbitrary semantic libflow payload direct transmit
```

and that an allowed harmless L2 message succeeds only when explicit transmit mode is enabled.

Until then:

```text
read-only core safety       PASS
transmit-boundary safety    PARTIAL PASS
M4 L3                       BLOCKED
```

---

# R3 — MEDIUM/HIGH — ADAS direct string proof does not by itself prove routing semantics

The LZO extraction work is accepted and important.

The worker now has direct, hash-verified ADAS ELF evidence and can prove that many tokens exist in both EN and VI binaries.

That upgrades the evidence quality for claims such as:

```text
"vehicleWarning" exists in both binaries
"vehicleMeasure" exists in both binaries
"pedestrians" exists in both binaries
"laneWarningRes" exists in both binaries
TSR-related names exist
ScreenAudioMsg exists
pedWarning-related names exist
```

This is strong static evidence.

But the current generator labels the first group as `CONFIRMED` key/topic routing using a combination of:

```text
direct string presence
+
prior callsite disassembly
```

The distinction matters:

```text
string/key presence                  can be CONFIRMED
producer -> serializer routing       needs direct xref/callsite proof
wire topic semantics                 needs call-graph or runtime capture
runtime enablement                   needs device evidence
```

A token being present in `.rodata` does not by itself prove that the runtime path used on this hardware publishes it in the assumed route.

The worker report itself correctly states that deeper producer/consumer xrefs still rely on prior work and that runtime TSR enablement / wire units remain unknown.

## Required classification change

Use separate evidence fields/verdicts, for example:

```text
presence_verdict: CONFIRMED
routing_verdict: HIGH-CONFIDENCE
runtime_verdict: UNKNOWN
```

or equivalent.

Do not collapse those three layers into a single `CONFIRMED` label.

A row may later become fully CONFIRMED when one of these is reproduced directly from the current extracted ELF:

```text
xref -> serializer -> topic/key callsite
or
captured EN runtime frame/message with correlation
```

This is primarily an evidence-quality correction; it does not invalidate the useful schema work.

---

# 2. Review of previous findings

## Previous R1 — freshness clock

**VERDICT: FIXED.**

`PollAt(now_ms)` advances age even with no new ingest. The acceptance behavior is now correct:

```text
last frame = 900
PollAt(1200) -> age 300 -> fresh
PollAt(1601) -> age 701 -> stale
```

Keep this design.

---

## Previous R2 — `is_second_crucial`

**VERDICT: FIXED.**

The implementation now preserves `is_second_crucial` as metadata and does not create `LeadInfo` from it.

`is_crucial` remains the only current normalized lead signal.

Keep this conservative behavior until stock semantics prove otherwise.

---

## Previous R3 — remote CI

**VERDICT: FIXED FOR PRODUCT CI.**

Remote `c2m-ci` is confirmed green at `d134af3`.

Clean-checkout product CI no longer depends on missing firmware-derived build artifacts.

Keep product CI and firmware-evidence verification as separate concerns.

---

## Previous R4/R5 — read-only capability model

**VERDICT: MAJOR IMPROVEMENT / PARTIAL PASS.**

Core/planner separation is now structurally better.

Remaining issue is the final write boundary described in new R2 above.

---

## Previous R6 — unit semantics

**VERDICT: FIXED.**

Stock-derived unverified values are now represented with neutral/raw naming such as:

```text
lateral_raw
longitudinal_raw
long_dist_raw
ttc_raw
ego_speed_raw
distance_raw
```

This avoids silently claiming meters/km/h before units are proven.

OSM-derived speed limits may remain km/h because that data source has defined semantics after parsing/conversion.

---

## Previous R7 — Gate E real-data wording

**VERDICT: FIXED.**

The fixture path is now correctly labeled synthetic.

Keep the current distinction:

```text
synthetic decoder/normalizer compatibility    PROVEN
captured stock EN frame compatibility         UNKNOWN until L1 capture
```

---

## Previous R8 — road matching

**VERDICT: IMPROVED / PARTIAL PASS.**

The new candidate score includes geometric distance, heading, and a one-way penalty, which is a meaningful improvement over heading-only ordering.

This is sufficient for a prototype.

Do not call the weights production-calibrated yet:

```text
1.0 * heading_deg
500m oneway penalty
```

are heuristic and require tuning on real Vietnam-scale road data.

Keep road matching separate from the current hardware/M4 gate work.

---

## Previous R9 — `planned_messages`

**VERDICT: FIXED.**

The field is now populated from planner output and is no longer a meaningless constant.

---

# 3. Gate status after this owner review

| Gate / Area | Owner verdict after `d134af3` |
|---|---|
| Gate A — firmware-grounded schema | **STRONG PARTIAL PASS** — LZO/string layer now directly proven; routing semantics need cleaner tiering/xref reproduction |
| Gate B — safety/normalization | **PASS for read-only core / PARTIAL for stock write boundary** |
| Gate C — product CI/build | **PASS / GREEN** |
| Gate D — c2m-enhance host daemon | **PASS as host/mock skeleton** |
| Gate E — decoder/provider integration | **PASS as SYNTHETIC fixture integration** |
| Gate F — M4 | **L3 remains BLOCKED; correct state** |
| RoadIntelligence | **PARTIAL PASS / useful prototype** |
| Web | **HOST PROTOTYPE** |
| Hardware integration | **NOT YET PROVEN** |

Do not label the complete C2M Enhanced foundation as finished yet.

---

# 4. What should remain unchanged

Do not roll back these improvements:

```text
PollAt(now_ms) freshness model
is_second_crucial metadata-only behavior
product CI independent of firmware artifacts
LZO extraction tooling and hash verification
raw/neutral unit names
IDisplayPlanner separation from EnhanceCore
synthetic Gate E labeling
geometric road candidate scoring
M4 L3 default-deny posture
GPSSpeed denied at L2
```

---

# 5. Required next delta

Keep the next worker delta small and focused.

## P0 — close the review findings

### 1. Make firmware evidence verification fail-closed

Remove all mandatory-step failure swallowing.

Required result:

```text
missing artifact -> RED
wrong SHA -> RED
extract failure -> RED
generator failure -> RED
evidence drift -> RED
```

Do not commit vendor firmware to the public repo merely to satisfy Actions.

### 2. Enforce M4 policy at the final transmit boundary

No raw/semantic packet may reach the stock sender merely because a caller bypassed `Plan()`.

Add explicit negative bypass tests.

### 3. Split ADAS evidence verdicts

Separate:

```text
presence
routing/callsite
runtime
```

Downgrade routing from CONFIRMED to HIGH-CONFIDENCE where only direct string proof + historical callsite analysis exists.

Re-upgrade only after direct current-ELF xref/callsite reproduction or runtime capture.

---

# 6. Next phase after the focused delta

After the three findings above are closed, the highest-value project step is no longer more host scaffolding.

It is hardware evidence:

```text
EN known-good physical device
        |
        +--> baseline collector
        +--> M4 connected vs disconnected diff
        +--> identify L0 physical/logical transport
        +--> passive ScreenService/libflow/cardv capture
        +--> obtain first captured golden frames/messages
        v
M4 L1 passive decoder
```

This should replace assumptions with actual device evidence and allow synthetic Gate E fixtures to be supplemented with captured golden fixtures.

ARM cross-build may proceed in parallel, but it should not delay L0/L1 capture.

---

# 7. Final decision

**ACCEPT `d134af3` and continue from it. Do not revert.**

The worker delta closes most of the previous software correctness debt and gives the project a substantially better foundation.

Current owner state:

```text
product CI                 GREEN
host foundation            GOOD
freshness                   FIXED
lead semantics              CONSERVATIVE / FIXED
LZO static evidence         MAJOR IMPROVEMENT
read-only core              SAFE
stock transmit boundary     NEEDS ONE MORE HARDENING DELTA
ADAS routing verdicts       SLIGHTLY OVERSTATED
hardware/M4 runtime         STILL THE NEXT REAL PROJECT GATE
```

Proceed with one focused corrective delta for the three findings above, then move to EN-device M4 L0/L1 capture rather than starting another broad feature sprint.
