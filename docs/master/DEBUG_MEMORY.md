# C2M Debug Memory — Canonical Project Memory

**Purpose:** long-lived technical memory for future debugging, reverse engineering, owner review, and coding-agent handoff.

**Authority:** this file is the first human-readable memory index for the project. It does **not** replace the original firmware binaries or reproducible reverse tools. When a statement here conflicts with directly reproduced evidence, the evidence wins and this file must be updated.

**Project:** `vunguyenbv175/C2M`

**Current product direction:** build **C2M Enhanced Firmware / C2M Enhanced AI Platform** on top of the most reliable stock components. Do not turn the project into a permanent investigation of the bad VI firmware.

---

# 0. Rules for future agents/reviewers

Before coding or debugging, read this file first.

Evidence priority:

```text
ORIGINAL FIRMWARE / DEVICE RUNTIME
        ↓
REPRODUCIBLE TOOL OUTPUT
        ↓
CANONICAL REVERSE REPORT
        ↓
THIS DEBUG MEMORY
        ↓
IMPLEMENTATION / MOCKS / SYNTHETIC TESTS
```

Never reverse the priority.

A synthetic test only proves that code matches its own assumptions. It does **not** prove that the assumptions match stock firmware.

Every technical claim must be classified as one of:

```text
CONFIRMED
HIGH-CONFIDENCE
HYPOTHESIS
UNKNOWN
SUPERSEDED
```

When new evidence disproves an old conclusion:

1. do not silently delete the historical conclusion;
2. mark the old conclusion `SUPERSEDED`;
3. link the new evidence/report;
4. update this file so future agents do not revive stale hypotheses.

---

# 1. Product mission

The product goal is **not** to repair the VI firmware.

The strategy is:

```text
OBSERVE STOCK
→ REUSE STOCK
→ AUGMENT
→ BENCHMARK
→ REPLACE SELECTIVELY
```

Preserve working stock capabilities whenever possible:

```text
camera / ISP
front + rear recording
hardware encoder
stock app compatibility
stock Wi-Fi workflow
working stock ADAS
M4 stock display
stock audio path
calibration
existing drivers
```

Enhancement layer targets:

```text
StockADASProvider
DisplayState
M4Adapter
RoadIntelligence
VietMap integration
VIETMAP LIVE integration
VoiceManager
TPMS
Web Admin / PWA
Diagnostics
Safe Updater
Event black box
Selective custom AI
```

The enhancement layer must fail independently without taking down recording or other critical stock functions.

---

# 2. Firmware ground truth

Two vendor firmware images define the current stock evidence base.

## EN — GOLDEN WORKING BASELINE

```text
filename: V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
role: GOLDEN / ADAS confirmed working on user's physical C2M
sysVer: 20230803193750
SHA256: 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
```

Inner upgrade image SHA256:

```text
e3f2443294f71588297821ee99ebccb54559ce3660c61fde338c210903639517
```

## VI — DONOR / REGRESSION BUILD

```text
filename: V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
role: vendor Vietnam donor/reference; ADAS did not operate on same physical C2M
sysVer: 20230920185743
SHA256: f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa
```

Inner upgrade image SHA256:

```text
9ec1c85ec0d8b69ee4cfbe3ae557c882439d3a5a6c99c5998b7a81ec7b87c53a
```

Do not infer that VI is preferable because it is newer.

The two original TARs may be supplied outside the Git repository. They do not need to be committed to Git for analysis. When available in a working lab, analyze the actual TARs rather than relying only on reports.

Verifier:

```text
tools/fw/verify_original_firmware.sh
```

---

# 3. Reproducible extraction / reverse assets

Important tools already in repo include:

```text
tools/fw/carve_upgrade.py
tools/fw/ubifs_extract_file.py
tools/fw/string_symbol_diff.py
tools/fw/elf_dynsym_diff.py
tools/fw/elf_function_diff.py
tools/fw/thumb_callgraph_diff.py
tools/fw/thumb_literal_strings.py
tools/fw/cardv_ringbuf_contract.py
tools/fw/adas_m0_directory.py
tools/fw/adas_gap_report.py
tools/fw/overlay_anchor_map.py
```

Runtime/M4 tools include:

```text
tools/device/collect_baseline.sh
tools/device/classify_adas_state.py
tools/device/compare_baselines.py
tools/device/capture_interface_pcap.sh

tools/m4/discover_transport.py
tools/m4/libflow_protocol.py
tools/m4/libflow_subscriber.py
tools/m4/decode_payload.py
tools/m4/cardv_status_client.py
```

Important rule:

> A future debug session must be able to regenerate important extracted binaries and claims from original firmware + repo tools. Ephemeral `/mnt/data` artifacts are convenient working copies, not the permanent source of truth.

---

# 4. Stock ADAS executable facts

## EN ADAS

```text
path inside customer: /minieye/adas/adas
inode: 136
size: 11,636,008
SHA256: 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043
UBIFS blocks: 2841
  none: 1701
  LZO: 1140
```

## VI ADAS

```text
path inside customer: /minieye/adas/adas
inode: 199
size: 11,653,870
SHA256: 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
UBIFS blocks: 2846
  none: 1702
  LZO: 1144
```

Canonical extraction report:

```text
docs/reverse/UBIFS_EXTRACTION_V1.md
```

---

# 5. ADAS model package findings

## CONFIRMED

The six CNN/model blobs referenced by encrypted `m0` are byte-identical between EN and VI.

`m0` decodes into six `(offset,size)` records and is internally consistent in both builds.

Therefore:

```text
"VI broke ADAS because the six model weights changed"
```

is excluded by current evidence.

Relevant reports/tools:

```text
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
tools/fw/adas_m0_directory.py
```

## SUPERSEDED / DOWNGRADED

Earlier suspicion that the seven interstitial non-model regions were likely licensing/protection data is **not established**.

No proven second pointer table or concrete reader/xref has established those gaps as the ADAS failure cause.

Treat them as package differences only until a real reader is proven.

---

# 6. BitAnswer / license path

Canonical report:

```text
docs/reverse/BITANSWER_LICENSE_PATH_V1.md
```

## CONFIRMED

Deep BitAnswer functions are byte-for-byte identical EN vs VI after address shift:

```text
Bit_SetRootPath
Bit_Login
Bit_ReadFeature
Bit_CheckOutSn
Bit_CheckOutFeatures
internal dispatcher
```

Important addresses/sizes from the reverse session:

```text
Bit_SetRootPath
  EN 0x1659ac size 52
  VI 0x165994 size 52

Bit_Login
  EN 0x163e2c size 140
  VI 0x163e14 size 140

Bit_ReadFeature
  EN 0x1640ac size 148
  VI 0x164094 size 148

Bit_CheckOutSn
  EN 0x16542c size 274
  VI 0x165414 size 274

Bit_CheckOutFeatures
  EN 0x165654 size 292
  VI 0x16563c size 292
```

## SUPERSEDED

`/proc/self/exe` is **not** evidence that the whole ADAS executable is hashed or validated.

The helper uses `readlink("/proc/self/exe", ...)` to obtain executable location and another helper constructs `.bitanswer.volume` under the executable directory.

Therefore:

```text
"VI changed BitAnswer implementation"
```

is strongly downgraded.

The same license code may still behave differently if runtime data/config/license state differs.

---

# 7. raw_adas producer contract

Canonical report:

```text
docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
```

## HIGH-CONFIDENCE

EN and VI show the same visible stock producer contract around:

```text
CRingBuf "raw_adas"
RequestWriteFrame
CommitWrite
send()
adas_minieye_send_frame_task()
```

The first large executable portions of the relevant functions normalize identically.

Therefore deliberate redesign of the `raw_adas` producer contract is a low-probability VI regression cause.

Runtime can still differ because the upstream camera/media/kernel path may fail to feed frames.

Stock ADAS expected input configuration includes:

```text
camera_input=ringbuf_vehicle
ringbuf_name=raw_adas
1920x1440
vehicle_run_freq=10
npu_buffer_size=5620000
use_imu_move=true
```

---

# 8. M4 / screen path

Canonical reports:

```text
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/reverse/SCREEN_ADAS_PATH_DIFF_V2.md
```

## CONFIRMED / HIGH-CONFIDENCE STATIC

ADAS-side `ScreenService::Init()` is byte-identical EN/VI.

Core executable prefixes of the vehicle warning, vehicle measurement and pedestrian sender functions are byte-identical; differences are confined to trailing literal/data pools.

Therefore a deliberate rewrite of the core semantic ADAS→M4 sender implementation is strongly downgraded as the VI ADAS failure cause.

Stock static anchors include:

```text
ScreenService
MessagePack
libflow
WebSocket-capable transport
screen_export_addr=0.0.0.0
static default port string 26012
```

cardv screen/status sender task calls, in order:

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

This means cardv can report/display ADAS state based on process/calibration state; it is not the full object transport path.

## UNKNOWN

Still not proven without runtime capture:

```text
exact physical M4 interface
whether M4 connects directly to :26012 / :8080
whether a proxy/bridge exists
exact WebSocket URL path/source
runtime unit/enum semantics
```

Do not invent these.

---

# 9. cardv facts

Extracted cardv binaries from the reverse session:

```text
EN size: 1,225,780
SHA256: 344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c

VI size: 1,225,780
SHA256: 56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23
```

Important changed areas included GPS/NMEA/M4 and G-sensor/power behavior.

EN-only symbols observed:

```text
Is_Gps_info(unsigned char*)
nmea_satinfo(...)
nema_calc_checksum(...)
g_zkw_gps_module
```

VI-only symbols observed:

```text
nmea_BDGSV2info_na(...)
SendGPSSpeedToScreen(int)
```

Functions with material size changes included:

```text
nmea_parse1
nmea_pack_type1
SendGPSInfoToScreen
GsensorSetSensitivity
GsensorSetPowerOnByInt
nmea_parser_real_push1
cardv_cmd_handler_system_restar
cardv_cmd_handler_GsensorSensitivity
minieye_init
```

These changes make VI useful as a donor/reference for newer GPS/display/localization behavior, but do not make VI the runtime baseline.

---

# 10. Kernel / boot / rootfs

Only two rootfs files were found different in the earlier EN/VI rootfs comparison:

```text
bootconfig/bin/cardv
bootconfig/modules/4.9.227/sc7a20.ko
```

Kernel images differ substantially because they were rebuilt/recompressed.

EN kernel:

```text
git-ish: ge46e0aa7
build date: 2023-07-31
uImage SHA256: c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030
load/entry: 0x20008000
```

VI kernel:

```text
git-ish: g7fcd0350
build date: 2023-09-20
uImage SHA256: 8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314
load/entry: 0x20008000
```

Important VI bootargs delta:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

This adds an 8 MiB framebuffer reservation and remains relevant when debugging kernel/media/memory integration.

Do not over-interpret compressed kernel byte differences; static compressed diff has low value here.

---

# 11. SC7A20 / G-sensor delta

Module hashes from the reverse session:

```text
EN sc7a20.ko
SHA256: 2d8121dd245d88684a5ece8e5647dfd04571a3184beca2a01fcac7743bbc797a
size: 24,196

VI sc7a20.ko
SHA256: 5d020616c2b67909a6bc5db19245bfedaf1301d875ae7c117c4d1888de566d64
size: 24,204
```

Same vermagic:

```text
4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8
```

Key semantic changes found in `Gsensor_int2_enable_store`:

1. VI inserts a call to `gsensor_clear_interrupt_status_register()`.
2. A write to register `0x32` changes value from `0x02` to `0x08` in the relevant sensitivity branch.

This currently looks more like INT2/sensitivity tuning than a wholesale driver change.

Do not claim this is the ADAS root cause without runtime evidence.

---

# 12. Historical VI-regression conclusion

This section is retained for debugging history, but product development must not center on it.

After static elimination, the strongest remaining VI-regression classes were ranked approximately:

```text
1. kernel/media/memory/frame-path integration
2. runtime startup/config/calibration state
3. same license implementation acting on different runtime state/data
4. M4 transport/runtime connectivity if ADAS inference is proven alive
5. package interstitial bytes only if a reader/xref is proven
6. deliberate raw_adas writer change — very low
7. changed BitAnswer implementation — strongly downgraded
8. different CNN model weights — excluded
```

Most decisive reversible test if this regression ever needs reopening:

```text
EN known-good kernel/rootfs/cardv/config
        +
VI adas executable launched temporarily
```

Interpretation:

```text
VI adas fails on EN base
  -> focus adas executable/package/runtime config interpretation

VI adas works on EN base
  -> focus VI kernel/cardv/media/drivers/memory integration
```

Do not overwrite the golden binary for the first experiment.

Canonical conclusion:

```text
docs/reverse/EN_VI_ADAS_REGRESSION_CONCLUSION_V1.md
```

---

# 13. Current C2M Enhanced Sprint 1 status

Implementation commit reviewed:

```text
4d70f22773a959980f2a080729b753c96ba88d22
```

Owner reviews:

```text
docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW.md
docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW_V2.md
```

Current status:

```text
EF-A01 StockADASProvider   PARTIAL / EVIDENCE-BLOCKED
EF-A02 M4Adapter           PARTIAL / BLOCKED
EF-A03 DisplayState        ACCEPT WITH FIXES
EF-A04 c2m-enhance core    PARTIAL
EF-A05 Web Admin V0        HOST PROTOTYPE
EF-A06 RoadIntelligence    HOST PROTOTYPE
```

## Critical review findings to remember

### F0 — evidence ordering failure

The sprint agent implemented abstractions too quickly from existing reports instead of returning to stock firmware evidence to validate semantics.

This is the highest-level process failure.

### F1 — read-only gate was decorative

`EnhanceConfig.mode="read-only"` existed, but `EnhanceCore::Tick()` still called `disp_->Render()` unconditionally.

Read-only must be capability-enforced, not comment/config-label enforced.

### F2 — M4 policy contradiction

Python replay guard denied `GPSSpeed/GPSLevel` at L2, while C++ `M4Adapter` planned `GPSSpeed` before the semantic-injection gate.

One canonical policy must govern both.

### F3 — M4 L3 was not implemented

`allow_semantic_injection=true` did not actually add semantic encoders for vehicle/lane/ped/nav/TPMS/speed limit.

### F4 — unproven StockADASProvider semantics

Do not silently assume:

```text
warning_level != 0  => FCW
is_key               => PCW
deviate_state != 0   => LDW
```

Those mappings require stock producer/consumer or runtime evidence.

Until proven, preserve raw fields and mark semantics unknown.

### F5 — transport state != process state

`libflow disconnected` does not prove `ADAS process absent`.

Separate observations:

```text
process_present
screen_service_reachable
subscription_active
frame_seen
frame_age
cardv_reachable
```

### F6 — no real c2m-enhance daemon yet

A header class + smoke test is not a production daemon.

### F7 — C++ build/CI was not verified in that sprint

Test source existing is not equivalent to test passing.

### F8 — Web V0 was mock-only

Useful as host prototype, not device integration.

### F9 — RoadIntel was sample/interface only

Two hard-coded sample rows are not an OSM pipeline or map matcher.

---

# 14. StockADAS schema policy for future implementation

Before normalizing any safety-related stock field, build/maintain a stock schema ledger with at least:

```text
stock key
producer function
consumer function
wire type
raw value examples
unit
semantic enum
confidence
source evidence
```

Important keys/functions to trace include:

```text
vehicleWarning
vehicleMeasure
pedestrians
laneWarningRes
ScreenWarningRes
TsrWarning
TsrTraceRes
SpeedLimitReport
FCW
HMW
VB
SAG
PCW
LDW
headway_warning
warning_level
vehicle_id
is_key
is_danger
is_crucial
is_second_crucial
longitude_dist
lateral_dist
ttc
headway
deviate_state
```

If semantics remain unproven, expose raw data rather than fabricating normalized meaning.

---

# 15. TSR memory

Stock ADAS contains static evidence for TSR-related paths, including names around:

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

However:

```text
stock TSR capability present in binary
```

does not automatically mean:

```text
TSR enabled and producing valid results on this device/config
```

Do not set `AdasState.detected_speed_limit` from guessed fields until the actual stock route and runtime enable state are proven sufficiently.

---

# 16. M4 development gates

Use these maturity levels consistently:

```text
L0 transport identified
L1 passive decode proven
L2 harmless replay proven
L3 semantic injection proven
L4 custom UI only if still worthwhile
```

Do not call L3 complete merely because an adapter interface exists.

L2/L3 write-capable activity requires explicit capability gates and owner approval.

Read-only/passive mode must make transmission technically impossible.

---

# 17. Recommended simulator architecture

Do not spend early effort on a full SSC8838G QEMU machine model.

Highest-value host simulator:

```text
recorded / synthetic stock captures
        ├── fake ADAS/libflow
        ├── fake cardv JSON
        ├── fake GPS
        ├── fake M4
        └── fake diagnostics
                 ↓
           C2M Enhanced
                 ↓
            assertions/tests
```

Good targets for host simulation:

```text
StockADASProvider
DisplayState
M4Adapter planning/encoding
RoadIntelligence
Voice priority
Web API
stale/reconnect/failure behavior
```

Hardware validation still required for:

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

QEMU user-mode + shims may later be useful for selected stock ARM userspace binaries, but this is optional and should be value-driven.

---

# 18. Debug playbook

## If ADAS appears dead

Do not jump straight to models/license/M4.

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
9. cardv/M4/audio output path alive?
```

Existing runtime classification A–F is useful, but classification must be based on actual evidence rather than inferring process state from socket state.

## If M4 display fails

Separate:

```text
ADAS inference
semantic sender
network/IPC transport
M4 connection
M4 render
```

Do not treat a blank/idle M4 display as proof that ADAS inference failed.

## If a coding agent says DONE

Verify:

```text
actual build target exists
code compiled
CI/test actually ran
real provider path exists vs mock-only
hardware-dependent claims are labeled UNKNOWN until measured
firmware evidence supports normalized semantics
```

---

# 19. Files that should be treated as canonical entrypoints

Read in this approximate order:

```text
docs/master/DEBUG_MEMORY.md
docs/master/CURRENT_ARCHITECTURE.md
docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW_V2.md

docs/reverse/UBIFS_EXTRACTION_V1.md
docs/reverse/BITANSWER_LICENSE_PATH_V1.md
docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
docs/reverse/SCREEN_ADAS_PATH_DIFF_V2.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md

docs/runtime/DEVICE_BASELINE_CAPTURE.md
docs/runtime/ADAS_FAILURE_CLASSIFICATION.md
```

Older reports may contain useful history but can contain superseded hypotheses. Prefer this memory + newer canonical reports when conclusions conflict.

---

# 20. Update protocol for this memory

Update this file whenever one of the following happens:

```text
new stock contract proven
old hypothesis disproven
new firmware artifact/hash becomes canonical
runtime capture proves a previously static-only assumption
product architecture changes
Sprint/feature changes maturity state
new critical bug/root cause is found
new reproducible reverse tool becomes authoritative
```

For every update, include enough detail that a future reviewer can answer:

```text
What do we know?
How do we know it?
What was disproven?
What remains unknown?
What should be tested next?
```

The purpose of this file is not to be a diary. It is the project's **debugging memory and anti-regression memory**.
