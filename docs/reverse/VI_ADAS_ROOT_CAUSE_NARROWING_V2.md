# VI ADAS Root-Cause Narrowing V2 (Static Last-Mile)

**Date:** 2026-09-11. **Mode:** static, read-only. No firmware / Candidate A/B /
bootargs / image / flash modification. No commit/push.
**Ground truth:** EN 2023-08-03 runs ADAS on the user's unit; VI 2023-09-20 did not.
**Scope respect:** prior accepted analyses (kernel/U-Boot/model/`m0`/scripts/
writer-contract/calibration-state-machine) are cited, not redone. No excluded cause is
revived without new evidence (section 5). New contradictory evidence: none.
**Tool limits:** Windows host, `python` 3.12.0 + `capstone` 5.0.7; no `readelf` /
`llvm-objdump` / ARM `objdump` (`shutil.which` None). Every claim below gives exact
offsets/strings/tool output or UNKNOWN.

Companion machine evidence: `docs/reverse/EVIDENCE_VI_STATIC_LAST_MILE.json`.
Detail reports: `VI_PERSISTENT_CONFIG_COMPAT_V1.md`,
`VI_RAW_ADAS_UPSTREAM_GATING_V1.md`, `VI_ADAS_OVERLAY_READER_MAP_V1.md`,
`VI_RUNTIME_FAILURE_CLASSIFIER_V1.md`.
Capture kit: `tools/fw/capture_c2m_adas_runtime.sh`,
`tools/fw/compare_c2m_runtime_capture.py`.

## 1. Six required verdicts

```text
PERSISTENT_CONFIG: SAME_SEMANTICS
RAW_ADAS_UPSTREAM: RUNTIME_DEPENDENT
OVERLAY_METADATA: PARTIAL
LICENSE_STATE: INPUT_DEPENDENT
STATIC_ROOT_CAUSE: INCONCLUSIVE
RUNTIME_CAPTURE: READY
```

- `PERSISTENT_CONFIG SAME_SEMANTICS`: 121/121 tail keys in identical order, only `m0`
  differs; `--install_calib_state`/`--enable_vehicle`/`switch_file`/`calib_file`/
  `produce_file`/`license_root_path`/`pitch`/`yaw`/`camera_height` counts + `.text`
  offsets identical; `--fx/--fy/--cx/--cy` 0 both (naive substring wobble proven to be
  overlay noise: `fx` text 0/overlay 151→153, etc.); no `config_version`/`calib_version`
  gate strings. Parser immediates UNKNOWN (needs `llvm-objdump`), but no material delta.
- `RAW_ADAS_UPSTREAM RUNTIME_DEPENDENT`: `raw_adas`/`fortest`/`CRingBuf`/
  `RequestWriteFrame`/`CommitWrite`/`MI_SYS`/`MI_SCL`/`MI_VIF`/`MI_ISP`/
  `ChnOutputPortGetBuf`/`MemcpyPa`/`MMA_Alloc`/`Mmap`/`pthread_create`/`CameraReader`/
  `RunLane`/`LaneCalib` counts SAME EN/VI (see gating report table); prior normalized
  `send` (219) + `send_frame_task` (874) identical (cited). Live thread-start, SCL
  IDs, allocation success, stride/format/cadence UNKNOWN → runtime decides.
- `OVERLAY_METADATA PARTIAL`: models (6/6 identical) + 3602 B tail have CONFIRMED
  readers (`FLAGS_m0 @ 0x25622` → `GetKey` → `UpdateFromEnv` → `DecryptNum` → AES;
  `switch_file` tail reader). Seven gaps (`+17862` total) have NO_READER_FOUND
  (`/proc/self/exe` 1/1 is dirname discovery, `mmap` 0 in adas, `lseek` 1/1 same,
  no second offset field) → downgraded.
- `LICENSE_STATE INPUT_DEPENDENT`: `Bit_SetRootPath/Login/ReadFeature/CheckOutSn/
  CheckOutFeatures`/dispatcher byte-identical (prior) + string counts SAME this run
  (`Bit_Login` 2, `CheckOutSn` 3, `SetCustomInfo` 2, `GetPlatformUuidStr` 1,
  `.bitanswer.volume` 1, `AES` 40). Identical code fed different
  `license_root_path=/customer/minieye/config` contents / UUID / custom-info /
  `.bitanswer.volume` / feature blobs (preserved dir) can diverge — concrete
  dependencies proven present, values UNKNOWN.
- `STATIC_ROOT_CAUSE INCONCLUSIVE`: no positive static proof ties any remaining delta
  to `lane never active` with camera working. See section 4 (exhaustion).
- `RUNTIME_CAPTURE READY`: `capture_c2m_adas_runtime.sh` (read-only, hashes-only,
  no secrets) + `compare_c2m_runtime_capture.py` (graceful on missing) present and
  syntax-checked (`python -m py_compile`); `tools/device/*` baseline/classifier exist.

## 2. Updated ranked table (narrowed, with exclusion respect)

| Rank | Candidate | Proven difference (this run) | Mechanism | Supporting | Contradicting | Confidence | Next discriminating test |
|---:|---|---|---|---|---|---|---|
| 1 | VI kernel/media/CMA/IPU runtime blocks usable frames or IPU init | uImage `c1fa8f73…` vs `8261589e…` +2 B, valid `0x20008000`/CRC both; VI-only `mmap_reserved=fb 8 MiB @0x3F000000–0x3F800000`; 526/528 rootfs same (prior) | reservation/allocator order or VIF/ISP/SCL/IPU driver behavior starves GetBuf or fails `MI_SYS_Init/SCL_CreateDevice/IPUCreateDevice` at runtime | largest opaque delta; userspace media vocab SAME so kernel is natural boundary | no iomem/meminfo/dmesg/IPU log proves starvation; preview works so sensor not grossly dead | UNKNOWN | EN/VI capture: cmdline/meminfo/iomem/buddyinfo/pagetypeinfo/dmesg_filtered/lsmod/ps + `MI_*` codes + SHM/threads |
| 2 | Upstream frame starvation despite unchanged writer (thread-start/alloc/order/cadence) | `cardv` equal-size distinct-hash builds but `raw_adas` 1/1, `CRingBuf` 5/5, `MI_VIF` 12/`MI_ISP` 86/`MI_SCL` 12/`GetBuf` 1/`MemcpyPa` 1/`MMA_Alloc` 1/`pthread_create` 8 SAME; `send`+`send_frame_task` normalized SAME (prior) | SCL channel/port, allocation, thread-guard, or order race yields no/tardy/malformed frames to unchanged writer | static equality ≠ live geometry/stride/ts/cadence/mapping/order | recording works → some camera path flows; deliberate rewrite downgraded | UNKNOWN | threads.tsv + SHM + `fd.txt` + frame seq/ts/fps + alloc errors EN vs VI |
| 3 | Runtime calib/feature/warning-gate suppression (incl. license inputs) | no parser-key/default/order delta (121/121, `m0` only); `Bit_*` impls byte-identical but inputs preserved (`/customer/minieye/config` 16 refs SAME) | same bytes fail hidden thresholds OR same code gets different UUID/license/feature/volume blobs OR `install_calib_state=0`/`enable_vehicle=false` at runtime | startup converges on device-specific flags + license root; identical code can diverge (INPUT_DEPENDENT) | no parser-diff proven; generic placeholder only | UNKNOWN (values) / LOW (impl change) | private copy+decode + parser logs + sanitized `Bit_*` codes (hashes/codes only) EN vs VI |
| 4 | Interstitial package metadata interpretation | 7 gaps `+17862` exact, models 6/6 identical, `m0` self-consistent; NO reader/xref/log for gaps this run or prior | opaque records gate load/feature/calib via unidentified reader | placement around blobs suggestive | no reader; `Bit_*` SAME; `/proc/self/exe` is dirname only | UNKNOWN → DOWNGRADED | gap-xref/`mmap` trace + EN-base+VI-`adas` launch log (only with recovery) |
| 5 | Display/M4-only masking live inference | VI adds `SendGPSSpeedToScreen` (cardv VI-only `0x387f6`) + GPS/display churn + `fb` 8 MiB; core `ScreenService`/vehicle/ped senders SAME | inference runs but warnings/pixels/audio never reach screen/M4 | `cardv` owns `Send*ToScreen`; MessagePack/AdasStatus separate inference from render | no proof inference reaches display in VI; display reported normal | LOW | classify A–H first; if C–E excluded, capture ScreenService/MessagePack + M4 pcap on verified iface |
| 6 | G-sensor driver behavior | `sc7a20.ko` 24196 vs 24204, `Gsensor_int2_enable_store` + `gsensor_clear_interrupt_status_register`, reg `0x32` `0x02→0x08` (prior) | INT2/sensitivity gating motion-dependent ADAS | narrow driver delta | no mechanism to kill entire pipeline shown | LOW | IMU/interrupt capture only after 1–3 excluded |

Highest-confidence NEW finding (this run): the `fx/fy/cx/cy` count wobble is
high-entropy overlay noise, not a parser delta (`--fx` 0 both; `fx` text 0 both,
overlay 151→153; same pattern for `fy/cx/cy` with `.text` counts identical). This
removes the last prima-facie config-delta candidate and hardens `SAME_SEMANTICS`.

Top-3 candidates: (1) kernel/media/CMA/IPU runtime, (2) upstream thread/alloc/order
starvation, (3) runtime calib/feature/license-gate suppression.

## 3. Single next experiment

Physical read-only capture on EN *first* (recovery-safe), then VI only with EN recovery
proven — classify exactly one of A–H before any bisect:

```sh
# on device (BusyBox/ash), read-only, no secrets:
sh tools/fw/capture_c2m_adas_runtime.sh en
# back up out dir, then on VI (only with recovery):
sh tools/fw/capture_c2m_adas_runtime.sh vi
# offline:
python tools/fw/compare_c2m_runtime_capture.py capture_en_<ts> capture_vi_<ts> -o cmp.json --markdown cmp.md
python tools/device/classify_adas_state.py capture_en_<ts>
python tools/device/classify_adas_state.py capture_vi_<ts>
```

Do NOT run EN-base + VI-`adas` until A–H is known and EN recovery + config backup
(hashes) + baseline exist. Preserve `build/fw_bin_en/adas` golden hash `0dcc6982…`.

## 4. STATIC_ANALYSIS_EXHAUSTED: YES — recommend physical capture

```text
STATIC_ANALYSIS_EXHAUSTED: YES
```

Static last-mile surfaces (A) parser compat, (B) upstream prerequisites, (C) overlay
readers + license/custom-state have been closed at the string/key/count/order layer
with exact offsets or UNKNOWN. Remaining unknowns (parser immediates, SCL IDs,
allocation codes, thread guards, license values, gap semantics) all require either
`llvm-objdump`/`readelf` CFG (unavailable on this host and still insufficient without
live inputs) or device runtime. Further static guessing without capture would violate
evidence policy. No static root cause is CONFIRMED; narrowing is INCONCLUSIVE by design
until A–H capture.

Capture-ready: YES (`RUNTIME_CAPTURE READY`, section 1).

## 5. Excluded count + exclusion respect

Excluded (do NOT revive without new contradictory evidence): 12.

```text
1. Different CNN/model weights — CONFIRMED excluded (6/6 identical)
2. Stale m0 offsets — CONFIRMED excluded (self-consistent)
3. run.sh delta — CONFIRMED identical (1584 B 796e555a…)
4. adas_checkcalib.sh delta — CONFIRMED identical (1145 B 518f22e9…)
5. Missing UpdateInstallCalibState(2) path — MEDIUM excluded (heavy/regular same)
6. Broad lane-algorithm rewrite — MEDIUM excluded (2731/2734 same seq)
7. raw_adas API rewrite/endpoint rename — HIGH-CONFIDENCE excluded (1 token + normalized SAME)
8. M4/display transport collapse as sole proof — MEDIUM excluded (needs inference proof)
9. U-Boot comp9 decoder semantic delta — excluded (identical decoder per HEAD 4747b42)
10. DTB semantic delta — excluded (identical DTB)
11. Kernel rewrite as proven cause — excluded as proof (NEAR-IDENTICAL, fb causality UNPROVEN)
12. Changed BitAnswer/license implementation — excluded as impl change (byte-identical paths)
```

This V2 revives none of the above. It *narrows* within the still-open runtime
integration + device-state surface (ranks 1–3) and *downgrades* gaps (rank 4) and
display-only (rank 5) without excluding them.

## 6. Remaining UNKNOWNs (load-bearing)

```text
- Exact VI failure class A–H (absent/crash/starved/IPU-fail/calib-suppressed/display-only/license-blocked/decode-blocked)
- Live raw_adas w/h/stride/format/bytes/seq/timestamps/fps/drops/mapping + SCL device/channel/port/format/res/fps for raw_adas vs preview
- pthread_create guard predicates + producer/consumer startup order + allocation return codes
- Kernel config/DTB semantic delta inside opaque comp9 + CMA/MIU/fb consumer/order + IPU codes
- Device adas.flag/calib.flag/produce bytes (hashes only until capture), enable_vehicle value, parser/MD5/decode logs
- Calibration gate live inputs (movement/GPS/timing/confidence/geometry/IMU/persistence thresholds)
- Causal reader (if any) of 7 gaps; package validation logs
- Runtime license UUID/custom-info/feature/volume values + Bit_* return codes (codes only)
- Whether inference runs while screen/audio silent (E vs F)
- Parser branch immediates/thresholds without string anchors (needs llvm-objdump + device logs)
```

## 7. Files created (this task; no firmware touched, no commit/push)

```text
docs/reverse/VI_PERSISTENT_CONFIG_COMPAT_V1.md
docs/reverse/VI_RAW_ADAS_UPSTREAM_GATING_V1.md
docs/reverse/VI_ADAS_OVERLAY_READER_MAP_V1.md
docs/reverse/VI_RUNTIME_FAILURE_CLASSIFIER_V1.md
docs/reverse/VI_ADAS_ROOT_CAUSE_NARROWING_V2.md
docs/reverse/EVIDENCE_VI_STATIC_LAST_MILE.json
tools/fw/capture_c2m_adas_runtime.sh
tools/fw/compare_c2m_runtime_capture.py
```

Validation: `EVIDENCE_VI_STATIC_LAST_MILE.json` parses (`python -m json.tool`);
`git diff --check` clean; `git status --short` shows only the 8 new files (no firmware/
Candidate/bootargs/image modification); hashes re-verified (section 8).

## 8. Validation outputs (this run)

```text
EN adas 11636008 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043
VI adas 11653870 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
EN cardv 1225780 344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c
VI cardv 1225780 56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23
overlay_start 0x172b1c both; tail 121/121 m0-only; run.sh 796e555a…; checkcalib 518f22e9…
tool limits: readelf/llvm-objdump/objdump absent; capstone 5.0.7 present
```
