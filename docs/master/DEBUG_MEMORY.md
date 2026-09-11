# C2M Debug Memory — Canonical Project Memory

**Purpose:** long-lived technical memory for debugging, reverse engineering, owner review, and coding-agent handoff.

**Project:** `vunguyenbv175/C2M`

**Rule:** this is an index of the current truth, not a substitute for original firmware or reproducible evidence. If this file conflicts with direct evidence, the evidence wins and this file must be updated.

---

# 0. Mandatory evidence order

```text
ORIGINAL FIRMWARE / DEVICE RUNTIME
        ↓
REPRODUCIBLE TOOL OUTPUT
        ↓
CANONICAL EVIDENCE JSON / REVERSE REPORT
        ↓
THIS DEBUG MEMORY
        ↓
IMPLEMENTATION / MOCKS / SYNTHETIC TESTS
```

Never reverse this order.

A synthetic test proves that code matches its own assumptions. It does **not** prove that those assumptions match the C2M firmware.

Use evidence labels consistently:

```text
CONFIRMED
HIGH-CONFIDENCE
RAW-ONLY
HYPOTHESIS
UNKNOWN
SUPERSEDED
```

When evidence changes:

1. keep enough history to understand what was superseded;
2. update the canonical evidence/report;
3. update this memory;
4. do not let future agents revive stale conclusions.

---

# 1. Product mission

The project goal is:

# C2M Enhanced Firmware / C2M Enhanced AI Platform

It is **not** to repair the VI firmware as the final product.

Strategy:

```text
OBSERVE STOCK
→ REUSE STOCK
→ AUGMENT
→ BENCHMARK
→ REPLACE SELECTIVELY
```

Preserve working stock capability where possible:

```text
camera / ISP
front + rear recording
hardware encoder
stock app compatibility
stock Wi-Fi workflow
working stock ADAS
M4 stock display
stock audio
calibration
existing drivers
```

Enhancement targets:

```text
StockADASProvider
DisplayState
M4Adapter
RoadIntelligence
VietMap / VIETMAP LIVE
VoiceManager
TPMS
Web Admin / PWA
Diagnostics
Safe Updater
Event black box
Selective custom AI
```

The enhancement layer must be able to fail without taking down critical stock recording/ADAS behavior.

---

# 2. Firmware ground truth

## EN — GOLDEN WORKING BASELINE

```text
filename: V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
role: GOLDEN; ADAS confirmed working on user's physical C2M
sysVer: 20230803193750
TAR SHA256: 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
inner upgrade SHA256: e3f2443294f71588297821ee99ebccb54559ce3660c61fde338c210903639517
```

## VI — DONOR / REGRESSION BUILD

```text
filename: V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
role: vendor Vietnam donor/reference; ADAS did not operate on same physical C2M
sysVer: 20230920185743
TAR SHA256: f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa
inner upgrade SHA256: 9ec1c85ec0d8b69ee4cfbe3ae557c882439d3a5a6c99c5998b7a81ec7b87c53a
```

Do not prefer VI merely because it is newer.

The original TARs may live outside Git. They do not need to be committed for analysis. When available in a lab, analyze the actual TARs directly.

Verifier:

```text
tools/fw/verify_original_firmware.sh
```

---

# 3. Reproducible extraction facts

Canonical UBIFS extractor:

```text
tools/fw/ubifs_extract_file.py
docs/reverse/UBIFS_EXTRACTION_V1.md
```

Expected ADAS outputs:

## EN `/minieye/adas/adas`

```text
inode: 136
size: 11,636,008
SHA256: 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043
blocks: 2841
  none: 1701
  LZO: 1140
```

## VI `/minieye/adas/adas`

```text
inode: 199
size: 11,653,870
SHA256: 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
blocks: 2846
  none: 1702
  LZO: 1144
```

Important rule:

> Ephemeral extracted files are working copies. Original firmware + repo tools must be sufficient to reproduce important evidence.

---

# 4. Major stock findings already established

## 4.1 ADAS models — CONFIRMED

The six model blobs referenced by encrypted `m0` are byte-identical EN/VI.

`m0` is the six-record `(offset,size)` directory and is internally consistent.

Therefore:

```text
VI failed because the six CNN/model weights changed
```

is excluded by current evidence.

Canonical references:

```text
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
tools/fw/adas_m0_directory.py
```

Old suspicion that the seven interstitial package regions were license/protection data is **not proven**. Do not revive it without a real reader/xref.

---

## 4.2 BitAnswer / licensing — CONFIRMED + SUPERSEDED claim

Canonical report:

```text
docs/reverse/BITANSWER_LICENSE_PATH_V1.md
```

Deep EN/VI BitAnswer functions were found byte-identical after address shift:

```text
Bit_SetRootPath
Bit_Login
Bit_ReadFeature
Bit_CheckOutSn
Bit_CheckOutFeatures
internal dispatcher
```

Important historical addresses:

```text
Bit_Login        EN 0x163e2c size 140 / VI 0x163e14 size 140
Bit_ReadFeature  EN 0x1640ac size 148 / VI 0x164094 size 148
Bit_CheckOutSn   EN 0x16542c size 274 / VI 0x165414 size 274
```

`/proc/self/exe` is **not** evidence that the whole ADAS executable is hashed. It is used to obtain executable location; another helper constructs `.bitanswer.volume`.

Thus:

```text
VI changed the BitAnswer implementation
```

is strongly downgraded/superseded.

The same code may still behave differently with different runtime license/config state.

---

## 4.3 raw_adas producer — HIGH-CONFIDENCE stable contract

Canonical report:

```text
docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
```

Visible EN/VI producer path remains largely the same around:

```text
CRingBuf "raw_adas"
RequestWriteFrame
CommitWrite
send()
adas_minieye_send_frame_task()
```

Stock ADAS expected input config includes:

```text
camera_input=ringbuf_vehicle
ringbuf_name=raw_adas
1920x1440
vehicle_run_freq=10
npu_buffer_size=5620000
use_imu_move=true
```

Deliberate redesign of the raw_adas writer contract is low probability. Runtime input can still fail upstream in camera/media/kernel paths.

---

## 4.4 M4 / screen sender — core static sender largely stable

Canonical reports:

```text
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/reverse/SCREEN_ADAS_PATH_DIFF_V2.md
```

Important static anchors:

```text
ScreenService
MessagePack
libflow
WebSocket-capable transport
screen_export_addr=0.0.0.0
static default port string 26012
```

`ScreenService::Init()` EN/VI is byte-identical.

Vehicle-warning / vehicle-measure / pedestrian sender executable prefixes are effectively unchanged; differences were in trailing literal/data pools.

cardv screen task order observed:

```text
WSGetConnectStatus
SendADASInfoToScreen
GetADASStatus
SendGPSInfoToScreen
SendBacklightLevelInfoToScreen
SendDisplayModeToScreen
SendStorageInfoToScreen
SendWifiStatusToScreen
SendAudioRecordStatusToScreen
```

`cardv::SendADASInfoToScreen()` mainly checks:

```text
ps | grep 'adas --fs' | grep -vE 'sh|grep'
grep 'install_calib_state=2' /customer/minieye/config/calib_de.flag
```

So cardv screen status is not the full object transport.

Still UNKNOWN until runtime capture:

```text
physical M4 interface
whether M4 directly uses :26012 / :8080
proxy/bridge existence
WebSocket URL path/source
wire units/enums
```

Do not invent these.

---

# 5. cardv / rootfs / kernel facts

## cardv hashes

```text
EN size 1,225,780
SHA256 344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c

VI size 1,225,780
SHA256 56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23
```

Notable symbol deltas:

```text
EN-only:
Is_Gps_info(unsigned char*)
nmea_satinfo(...)
nema_calc_checksum(...)
g_zkw_gps_module

VI-only:
nmea_BDGSV2info_na(...)
SendGPSSpeedToScreen(int)
```

VI contains meaningful GPS/NMEA/M4 and G-sensor/power changes and is useful as a donor/reference.

## Rootfs

Earlier rootfs comparison found only:

```text
bootconfig/bin/cardv
bootconfig/modules/4.9.227/sc7a20.ko
```

different among the compared rootfs files.

## Kernel

```text
EN uImage SHA256: c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030
VI uImage SHA256: 8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314
load/entry: 0x20008000 both
```

Important VI bootargs delta:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

This adds an 8 MiB framebuffer reservation and remains relevant if kernel/media/memory behavior is debugged later.

Do not infer semantic kernel changes from compressed-byte diff alone.

---

# 6. SC7A20 / G-sensor memory

```text
EN sc7a20.ko
SHA256 2d8121dd245d88684a5ece8e5647dfd04571a3184beca2a01fcac7743bbc797a
size 24,196

VI sc7a20.ko
SHA256 5d020616c2b67909a6bc5db19245bfedaf1301d875ae7c117c4d1888de566d64
size 24,204
```

Same vermagic:

```text
4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8
```

Known semantic delta in `Gsensor_int2_enable_store`:

1. VI calls `gsensor_clear_interrupt_status_register()`.
2. relevant register `0x32` write changes `0x02 -> 0x08`.

Current interpretation: likely INT2/sensitivity tuning, not proven ADAS root cause.

---

# 7. Historical VI regression ranking

Retained only for future debugging; product work must not center on it.

Approximate last ranking:

```text
1. kernel/media/memory/frame integration
2. runtime startup/config/calibration state
3. same license code acting on different runtime state/data
4. M4 transport/runtime if ADAS inference is proven alive
5. package interstitial bytes only if a reader is proven
6. deliberate raw_adas writer rewrite — very low
7. changed BitAnswer implementation — strongly downgraded
8. different CNN model weights — excluded
```

Most decisive reversible experiment if ever needed:

```text
EN known-good kernel/rootfs/cardv/config
        +
VI adas executable launched temporarily
```

Canonical historical conclusion:

```text
docs/reverse/EN_VI_ADAS_REGRESSION_CONCLUSION_V1.md
```

---

# 8. Firmware-grounded stock schema — current state

Corrective worker commit:

```text
a58f697a5dd997e4d2231e7b1b77dc7e9e41ae8c
```

New canonical files:

```text
docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
docs/reverse/EVIDENCE_CARDV_CONTRACT.json
docs/reverse/EVIDENCE_CARDV_SYMDIFF.json
```

What was genuinely re-derived from original firmware in that delta:

```text
TAR hashes / partition carve
rootfs/customer inventories
cardv hashes / byte-context / symbol diff
libflow.so EN/VI identity
customer audio/model inventory
```

Important nuance (updated 2026-09-11 delta):

> The ADAS-side key/field layer was **not fully re-derived independently yet** in `a58f697`, because relevant ADAS `.rodata` lives in LZO-backed UBIFS blocks. `stock_adas_schema_v2.py` explicitly falls back to prior callsite disassembly for those HIGH-CONFIDENCE rows.

Resolution 2026-09-11 (post-`a58f697` delta, unreviewed): minilzo helper route
extracted both adas binaries with exact expected hashes; direct string proof in
`docs/reverse/EVIDENCE_ADAS_STRINGS.json` (68/71 tokens BOTH, identical counts);
key routing upgraded to CONFIRMED; schema regenerated (53 fields). Producer/
consumer xref depth and TSR-enablement/wire-units remain open — see the new
delta report. Gate A status change needs owner confirmation.

Therefore Gate A is currently:

```text
PARTIAL PASS
```

not fully closed.

Highest-value static next step:

```text
extract EN/VI ADAS with working LZO support
verify exact expected SHA256
re-run strings/xrefs/ELF evidence directly
upgrade/downgrade schema verdicts accordingly
```

---

# 9. Current C2M Enhanced foundation status

Latest owner review:

```text
docs/reviews/2026-09-11_GATES_A_F_DELTA_REVIEW.md
```

Current status after independent review of `1eab94a..a58f697`:

```text
Gate A firmware schema       PARTIAL PASS
Gate B safety/normalization  PARTIAL PASS
Gate C remote CI             FAIL / RED
Gate D host/mock daemon      PASS as skeleton
Gate E fixture integration   PASS as SYNTHETIC stock-compatible test
Gate F M4                    PASS; L3 correctly BLOCKED
RoadIntelligence             PARTIAL PASS / prototype matcher
Web                          HOST PROTOTYPE
```

Do not call the foundation COMPLETE yet.

---

# 10. Current critical implementation findings

These findings must survive future context resets.

## R1 — HIGH — stale/freshness clock is broken

Current `StockADASProvider::Poll()` normalizes the stored snapshot using the same `StockSnapshot.now_ms` captured at `Ingest()`.

If no new frame arrives, elapsed age does not increase.

Example:

```text
Ingest at now=1000, last_frame=900 -> age=100
Poll 30 seconds later              -> still age=100
```

A dead/stalled provider can therefore remain healthy indefinitely.

Required fix: provider needs current monotonic time at Poll or injected clock. Add an advancing-time stale test.

Resolution 2026-09-11 (unreviewed): `PollAt(now_ms)` + `IClock`/`ManualClock`;
`EnhanceCore::Tick` passes caller time; C++/Python advancing-time tests
(Ingest@1000/last_frame@900 → fresh@1200, stale@1601) pass in local CI.

---

## R2 — HIGH — `is_second_crucial` schema/implementation contradiction

Schema V2 says:

```text
is_crucial        = sole lead signal
is_second_crucial = secondary marker; never invents lead alone
```

Current C++ provider nevertheless falls back to `is_second_crucial` and creates normalized `LeadInfo`.

Either prove that stock semantics intentionally permit second-crucial fallback, or keep it raw and do not create `lead` from it.

Resolution 2026-09-11 (unreviewed): option 1 chosen — `is_second_crucial` is
metadata only (`raw.second_crucial_count`), never creates `lead`; schema wording
and both normalizers + tests updated. No stock proof of fallback exists.

---

## R3 — HIGH — GitHub CI is red

Actual GitHub Actions runs observed after `a58f697`:

```text
run #1 head a58f697...  FAILURE
run #2 head c94351b...  FAILURE
```

Therefore:

```text
"GitHub CI green"
```

is false as of this memory update.

The workflow also calls:

```text
python3 tools/fw/stock_adas_schema_v2.py
```

on a clean checkout, while that generator requires uncommitted/prebuilt `build/...` firmware-derived inputs.

Normal product CI must not depend on unavailable proprietary/original firmware artifacts.

Recommended split:

```text
Product CI on every push:
  cmake/build/ctest/headers/python fixture tests

Firmware-evidence verification:
  explicit/local/artifact-backed job with original TARs or extracted evidence inputs
```

Also make local CI strict: missing compiler/CMake should fail in verification mode instead of silently SKIP and return green.

Resolution 2026-09-11 (unreviewed): product CI split (`ci.yml` clean-checkout
only; `firmware-evidence.yml` manual); `local_ci.py --strict` fails on missing
toolchain; `--evidence` regenerates + diffs canonical JSON. Remote-green needs
owner confirmation after push (no local GitHub Actions access).

---

## R4 — MEDIUM/HIGH — read-only improved, but type-level capability is incomplete

Current `M4Adapter::Render()` is planning-only and zero-sender test is useful.

But transmit API still takes:

```text
bool allow_transmit
```

and the declared `AllowTransmit` token is unused.

`EnhanceCore` also depends on generic `IDisplayAdapter::Render()`, whose interface does not itself forbid future adapters from transmitting.

Current M4 implementation is safe; the architecture is not yet universally read-only by type construction.

Prefer separate planner/transmitter interfaces or explicit capability token.

Resolution 2026-09-11 (unreviewed): `IDisplayPlanner` (pure) +
`IStockTransmitter::Transmit(msgs, AllowTransmit)`; core depends on planner
only; `M4Adapter` implements both; zero-sender test retained.

---

## R5 — MEDIUM — unverified units leak into product field names

Schema says stock units/signs remain unverified, but `DisplayState` uses names such as:

```text
lateral_m
longitudinal_m
ego_speed_kmh
```

Do not silently turn raw unknown units into meters/km/h through API naming.

Use neutral/raw representation until unit conversion is proven.

Resolution 2026-09-11 (unreviewed): `lateral_raw/longitudinal_raw`,
`LeadView.long_dist_raw/ttc_raw`, `ego_speed_raw`, `NavState.distance_raw`;
OSM `speed_limit_kmh` kept (defined source).

---

## R6 — MEDIUM — Gate E is synthetic, not captured stock evidence

`tools/m4/make_fixture.py` creates stock-compatible MessagePack frames itself.

`test_real_data_path.py` is useful, but it proves the project's fixture contract, not actual EN wire compatibility.

Correct interpretation:

```text
fixture decoder→normalizer path works
real captured EN frame compatibility UNKNOWN until L1 passive capture
```

Resolution 2026-09-11 (unreviewed): fixtures/tests relabeled SYNTHETIC
everywhere (docstrings, output, design note); pipeline kept.

---

## R7 — MEDIUM — road query is not true nearest-segment matching yet

The new OSM pipeline genuinely parses XML and builds SQLite R*Tree.

Current candidate query sorts primarily by heading difference and does not compute point-to-segment distance.

A farther road with better heading can beat a nearby road.

Road matcher must eventually combine:

```text
geometric distance
heading
oneway compatibility
optionally continuity/road class
```

Also handle nontrivial OSM `maxspeed` formats before Vietnam-scale processing.

Resolution 2026-09-11 (unreviewed): `score = distance_m + 1.0*heading_deg +
500m oneway-violation penalty`; fixture way104 proves closest-beats-heading;
`parse_maxspeed` explicit reasons (ok/mph-converted/non-numeric/conditional/
ambiguous-multi/missing/unparsable).

---

## R8 — LOW/MEDIUM — planned_messages currently meaningless

`TickResult.planned_messages` exists but current core returns zero unconditionally.

Populate it from a planner result or remove it until meaningful.

Resolution 2026-09-11 (unreviewed): populated from `IDisplayPlanner::Plan`
size in every `Tick`; asserted in smoke test.

---

# 11. M4 maturity gate

Use these definitions exactly:

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

This is the correct conservative state.

No warning/semantic injection during discovery.

---

# 12. StockADAS normalization policy

Do not promote raw fields merely because names look obvious.

Maintain evidence for at least:

```text
stock key
producer
consumer
wire type
raw examples
unit
semantic enum
confidence
source evidence
```

Important ADAS fields/routes include:

```text
vehicleWarning
vehicleMeasure
pedestrians
laneWarningRes
ScreenWarningRes
TsrWarning
TsrTraceRes
SpeedLimitReport
fcw
headway_warning
vb_warning
sag_warning
warning_level
is_crucial
is_second_crucial
is_key
is_danger
deviate_state
longitude_dist
lateral_dist
ttc
headway
```

Until semantics are proven, preserve RAW/UNKNOWN rather than fabricating normalized meaning.

---

# 13. TSR memory

Static firmware contains TSR-related code names around:

```text
VehicleAlgo::TsrProcess
VehicleRun::ReadTsr
TsrMsg
TsrRes
TsrTraceRes
TsrWarning
SpeedLimitReporter
Distribution::SetTsrResult
CollectService::Send<TsrWarning>
```

But static presence does **not** prove TSR is enabled and outputting valid speed limits on this C2M/config.

Keep `AdasState.detected_speed_limit` empty until the real runtime/output path is established sufficiently.

---

# 14. Simulator strategy

Do not prioritize a full SSC8838G QEMU machine model.

Highest-value host simulator:

```text
captured / synthetic stock inputs
        ├── ADAS/libflow
        ├── cardv JSON
        ├── GPS
        ├── M4
        └── diagnostics
               ↓
          C2M Enhanced
               ↓
          assertions/tests
```

Good host-test targets:

```text
StockADASProvider
DisplayState
M4Adapter planning
RoadIntelligence
Voice priority
Web API
stale/reconnect/failure behavior
```

Still requires real C2M eventually:

```text
camera/ISP
raw_adas producer
IPU/NPU inference
M4 physical transport
G-sensor
Wi-Fi driver/AP+STA
SD recording
power/suspend/reboot
```

QEMU user-mode + shims can be considered later for selected stock ARM userspace binaries if it has clear value.

---

# 15. Debug playbook

## If ADAS appears dead

Observe in order:

```text
1. adas process present?
2. crash/restart loop?
3. calibration/config valid?
4. raw_adas producer active?
5. frames advancing?
6. IPU/NPU/model init evidence?
7. warning outputs produced?
8. ScreenService/libflow reachable?
9. cardv/M4/audio path alive?
```

Do not infer process absence from a disconnected socket.

## If M4 appears dead

Separate:

```text
ADAS inference
semantic sender
network/IPC transport
M4 connection
M4 render
```

A blank M4 screen is not proof that ADAS inference failed.

## If an agent says DONE

Verify:

```text
actual target exists
code compiled
CI actually ran and conclusion is green
mock vs real provider clearly classified
hardware-dependent claims remain UNKNOWN until measured
firmware evidence supports normalized semantics
```

---

# 16. Current priority queue

## P0 — correctness

```text
fix stale/freshness clock
resolve is_second_crucial contradiction
fix clean-checkout GitHub CI
```

## P1 — stock evidence

```text
finish LZO extraction of original EN/VI ADAS
verify exact hashes
re-run direct string/xref/ELF evidence
update schema verdicts
```

## P2 — host architecture

```text
remove unverified unit names
harden planner/transmitter capability split
improve road geometric matching
```

## P3 — hardware

```text
EN baseline capture
M4 L0 transport discovery
L1 passive pcap/libflow capture
ARM cross-build
```

Do not jump to VietMap/TPMS/custom AI until P0 is closed and the foundation is stable.

---

# 17. Canonical entrypoints

Read in this order:

```text
docs/master/DEBUG_MEMORY.md
docs/master/CURRENT_ARCHITECTURE.md
docs/master/AGENT_KICKOFF.md

docs/reviews/2026-09-11_GATES_A_F_DELTA_REVIEW.md
docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW_V2.md

docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
docs/reverse/UBIFS_EXTRACTION_V1.md
docs/reverse/BITANSWER_LICENSE_PATH_V1.md
docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
docs/reverse/SCREEN_ADAS_PATH_DIFF_V2.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md

docs/runtime/DEVICE_BASELINE_CAPTURE.md
docs/runtime/ADAS_FAILURE_CLASSIFICATION.md
```

Older reports remain useful history but may contain superseded hypotheses.

---

# 18. Memory update protocol

Update this file when any of these changes:

```text
stock contract proven/disproven
schema confidence changes
new canonical firmware/hash
runtime capture resolves static uncertainty
critical bug/root cause found
architecture changes
feature maturity changes
CI/device test state changes materially
new authoritative reverse tool added
```

Every update should let a future reviewer answer quickly:

```text
What do we know?
How do we know it?
What was superseded?
What remains unknown?
What should be tested next?
```

This file is the project's **debugging memory and anti-regression memory**.
