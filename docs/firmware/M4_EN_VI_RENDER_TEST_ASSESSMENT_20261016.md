# M4 EN / VI render test assessment — 2026-10-16 (offline, no flash)

## Scope and boundary

- OFFLINE ONLY on `C:\Code\C2M`. No camera / SSH / private-network / radio /
  flash / download-firmware / commits / subagents in this check.
- Do NOT execute vendor binaries/scripts. No raw bytes / disassembly /
  vendor code / audio / keys / calibration data published here.
- This report gives safe evidence only: SHA-256, sizes, symbol names,
  file offsets, addresses with Thumb bit cleared where noted.
- User phrase `cần thì flash fw vi thử` is a **conditional** authorization.
  It does NOT authorize blind flashing, reset / calibration forcing, or
  recording-media staging.
- Recommendation in this report is **NO FLASH now**. One controlled A/B is
  described only with explicit go / no-go gates. See §7.
- Time-bounded check (~10 min target). `llvm-objdump` was unavailable, so the
  full call-graph diff was not re-run here; prior call-graph results are cited
  with confidence and the symbol / contract / package deltas below were
  re-derived this run from hash-verified binaries.
- Documentation correction: current status only, no extra agents spawned.

## Ground truth carried in

- Owner: 2D speed works; 3D speed / sign **never observed**.
- Owner later clarified the top bar is conditional (appears with warnings;
  mainly collision seconds/countdown). An empty 3D snapshot is one UI state,
  not proof of a missing bar / renderer build.
- Annotated ad `0.5` = safe-distance indicator (collision seconds), NOT
  vehicle speed. Do not reuse TTC / headway / countdown / vehicle-speed slots
  for legal limits.
- Native V4 (EN camera, proven RNDIS `usb0`): **39 complete server
  application messages** — 10 `GPSSpeed` (:8080), 16 `lane / laneWarningRes`,
  5 `vehicle / vehicleWarning`, 4 `vehicle / vehicleMeasure`,
  2 `ped / pedestrians`, 2 `ped / pedWarning` (:24012/:26012). V4 mode was
  NOT contemporaneously confirmed as 3D. The strict unchanged-26012
  connection gate **FAILED** (client reconnect, cause UNKNOWN). No retry.
- EN camera already emits `GPSSpeed` to the M4 link. Missing 3D speed is not
  explainable as "camera never sends GPSSpeed". Do not inject another copy.
- New ADB: signature `ff/42/01` observed on saved USB evidence; one
  identification handshake elapsed ~7 ms, exit 0, RAM cleanup. **Not**
  access: no AUTH reply / shell / keys; 24012 / 26012 not established after
  (owner M4 normal). No hardware. Standard-auth preparation is with parent
  agents; no hardware in this check.

## 1. Source identity re-derived this run

| Artifact | EN | VI |
|---|---|---|
| Outer TAR | `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`, 58368000 B, SHA-256 `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` | `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`, 58122240 B, SHA-256 `f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa` |
| Inner `SigmastarUpgradeSD_SSC8838G.bin` | 58359832 B, `e3f2443294f71588297821ee99ebccb54559ce3660c61fde338c210903639517` | 58105880 B, `9ec1c85ec0d8b69ee4cfbe3ae557c882439d3a5a6c99c5998b7a81ec7b87c53a` |
| `adas_upgrade.sh` | 2972 B, `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bb2f7da05b`, **identical EN/VI** | same |
| `sysVer.txt` | `sysVer 20230803193750` | `sysVer 20230920185743` |
| `cardv` (`bootconfig/bin/cardv`) | 1225780 B, `344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c` | 1225780 B, `56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23` |
| `adas` (`/minieye/adas/adas`) | 11636008 B, `0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043` (per `EVIDENCE_VI_ADAS_FAILURE.json`) | 11653870 B, `997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1` (re-extracted + hashed this run) |
| `lib/libflow.so` | `a6bfcbf6be07d08d39c74a924b232da76c355d0d753089212bdc10b027dc8d42` (per `CUSTOMER_MANIFEST_EN.json`) | same hash re-derived from VI `rootfs.es` this run => **identical EN/VI** |
| VI `customer.es` inventory | — | 227 files; no `m4` / `screen` / `display` receiver binary, layout asset, or M4 update package (only `adas_upgrade.sh`, `config_upgrade.sh`, USB modules matched the keyword sweep) |

EN `cardv` bytes used here: `m4trace_fw\cardv` (hash matches EN above).
VI `cardv` bytes: gunzip + `iter_cpio` extraction of `bootconfig/bin/cardv`
from `work\carve_vi\rootfs.es...bin` to TEMP only (hash matches VI above).
No vendor binary was executed.

## 2. Precise EN / VI differences (re-derived + cited)

### 2.1 `cardv` symbol delta — RE-DERIVED (`cardv_symdiff.py`)

- EN dynsyms 4478 / VI 4476 / common 4474.
- EN-only (4): `Is_Gps_info`, `nmea_satinfo`, `nema_calc_checksum`,
  `g_zkw_gps_module`.
- VI-only (2): `nmea_BDGSV2info_na`, `SendGPSSpeedToScreen`.
- Size-changed common (9):

| Symbol | EN | VI |
|---|---|---|
| `nmea_parse1` | 792 | 680 |
| `nmea_pack_type1` | 388 | 616 |
| `SendGPSInfoToScreen` | 112 | 92 |
| `GsensorSetSensitivity` | 1304 | 1624 |
| `GsensorSetPowerOnByInt` | 1048 | 1104 |
| `nmea_parser_real_push1` | 1408 | 1436 |
| `cardv_cmd_handler_system_restar` | 344 | 612 |
| `cardv_cmd_handler_GsensorSensitivity` | 148 | 140 |
| `minieye_init` | 1212 | 1216 |

Matches `CARDV_STATIC_DIFF_V1.md` / `EVIDENCE_CARDV_SYMDIFF.json`; this run
reproduced the counts, name sets, and all nine size pairs from the two
hash-verified ELFs.

### 2.2 `cardv` contract tokens — RE-DERIVED (`cardv_contract_evidence.py`)

- `minieye-websocket`: 1x both. `raw_adas`: 1x both
  (EN file off `0xFF340`, VI `0xF5794`). `fortest`: 1x both.
- All screen JSON UUIDs present BOTH: `GPSLevel`, `DispBrightSet`,
  `StorageStatus`, `ClientConn`, `RecordVoice`, `ScreenModeSet`,
  `AdasStatus`, `HeavyCalibStatus`.
- `GPSSpeed`: EN 2x (`0x34204`, `0xF342e`) vs VI 3x
  (`0x341B7`, `0x387FA`, `0x10066A`). The JSON template
  `{"type":1601,"uuid":"GPSSpeed","speed":%d}` exists in **EN too**; VI adds
  a sender occurrence, not the message type.
- `SendGPSSpeedToScreen`: EN 0x / VI 1x (`0x387F6`). **VI-ONLY**.
- `nmea_BDGSV2info_na`: VI-ONLY. `nmea_satinfo`: EN-ONLY.
- `26012` / `8080` numeric literals: ABSENT as ASCII in both `cardv`
  (ports are immediate constants, cf. `0x1F90`=8080 before `lws_create_context`;
  26012 is adas-side). Not a delta.

### 2.3 Screen / ADAS transport paths — UNCHANGED core

- `SendADASInfoToScreen`: 380 B both
  (EN VA `0x83185`, VI VA `0x9A20D` incl. Thumb bit; i.e. `0x83184` /
  `0x9A20C` cleared). Same polled strings (`adas --fs` presence,
  `install_calib_state=2`). Status plumbing only, not 3D object transport.
- `DeviceSendMsgToScreenTask`: 80 B both; same call order
  (`WSGetConnectStatus`, `SendADASInfoToScreen`, `GetADASStatus`,
  `SendGPSInfoToScreen`, backlight / display-mode / storage / wifi / audio).
  VI does NOT insert `SendGPSSpeedToScreen` into this task sequence per
  `CARDV_STATIC_DIFF_V1.md` (call-sequence equality; `llvm-objdump`
  unavailable this run, so cited HIGH-CONFIDENCE, not re-derived).
- ADAS `ScreenService::Init`: 120 B, byte-identical EN/VI (cited from
  `SCREEN_ADAS_PATH_DIFF_V2.md`).
- `ScreenService::Send` vehicle-warning (584 B), vehicle-measure (2112 B),
  pedestrian (2116 B): executable prefixes identical through the code /
  literal-pool boundary; only trailing literal-pool bytes differ (moved
  rodata targets, not sender logic). Cited; consistent with identical
  `libflow.so` above.
- `raw_adas` producer: same `CRingBuf` ctor / `RequestWriteFrame` /
  `CommitWrite` surface; normalized `send()` +
  `adas_minieye_send_frame_task` identical (cited from
  `VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md`). Live width / height / stride /
  format / timestamps / cadence / allocation / startup order remain UNKNOWN.

### 2.4 `SendGPSSpeedToScreen(int)` semantics — extra, NOT a new widget

- `readelf -W --dyn-syms` VI: `_Z20SendGPSSpeedToScreeni`, VA `0x9A405`,
  size **4 B**. EN: absent.
- A 4-byte dynsym is a stub / veneer; the real body (if any) is not identified
  by symbol size alone. Exact caller, gating (GPS-fix / validity / frequency /
  client-connected), and whether it duplicates or replaces the existing
  `SendGPSInfoToScreen` -> `WSSetGPSSpeed` path are **UNKNOWN**.
- What is proven: (a) message type unchanged (type 1601 template pre-exists in
  EN); (b) EN already delivers 10 native `GPSSpeed` to the M4 link (V4);
  (c) an extra VI sender therefore cannot by itself create an M4 3D widget.
  Additional `GPSSpeed` would duplicate a native stream. Still prohibited to
  inject.
- `SendGPSInfoToScreen` shrinks 112 -> 92 B (no longer calls `SetGPSLevel`
  twice — cited). GPS NMEA refactor (`nmea_pack_type1` +228 B with extra
  sentence matching; `nmea_parse1` -112 B) is a real parser change with
  unknown effect on speed validity (cardv maps invalid cached 65535 -> 0;
  JSON has no validity / timestamp, so 0 = stationary OR invalid).

### 2.5 Display / framebuffer route — VI-only reservation, effect UNKNOWN

- RE-DERIVED from `upgrade_script.txt`:
  - EN `bootargs`: `... cma=2M@0x23800000 loglevel=3 ...` (no `mmap_reserved`).
  - VI `bootargs`: `... cma=2M@0x23800000 mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000 loglevel=3 ...`.
- So VI reserves an extra 8 MiB `fb` window. Proves a display-integration
  change; does NOT prove overlap with CMA / MMA / IPU / camera buffers,
  consumption at runtime, starvation, or that it fixes / breaks 3D composition.
- VI `cardv` also carries `DisplayVideoYuv422` / `refresh_display_yuv422` /
  `ScreenDisplayMode` / `sendtoscreen_task` (both builds) plus the GPS/screen,
  G-sensor (`GsensorSetSensitivity` +320 B, `GsensorSetPowerOnByInt` +56 B
  with extra `system()`/`sleep()`), and restart-handler (+268 B) deltas.
  These affect startup / power / OSD-canvas behavior, not a proven 3D widget.

### 2.6 TSR and sign path — NO proven M4 sign slot in either build

- Both `adas` contain `--enable_tsr=false` (compiled default; re-found in VI
  binary this run: 1 occurrence), `--enable_screen_service=true`,
  `--screen_export_addr=0.0.0.0`, one `26012` literal, one
  `AdasScreenService`, and `tsr_warning` (5x) / `tsr_trace_res_list` (1x) /
  `vehicleWarning` / `vehicleMeasure` / `laneWarningRes` / `pedestrians` /
  `pedWarning` (1x each). No `SendGPSSpeedToScreen` in `adas`.
- Static TSR export (`TsrWarning` 5-field map, `TsrTraceRes` 9-field map) is
  `CollectService` (`tsr / tsr_warning`, `tsr / tsr_trace_res_list`,
  compiled port 25012), NOT the `AdasScreenService` scene messages on 26012.
  No direct `ScreenService` send from `ReadTsr` / `SetTsrResult` was found in
  the bounded review (`ReadTsr` calls `SetTlrResult` at `0x6D540`); indirect
  calls remain open. There is no verified traffic-sign icon/value command in
  the recovered `cardv` JSON or 26012 scene schemas.
- Bottom line: no M4 sign renderer addition was identified in the reviewed VI
  camera assets. That is not proof of absent receiver capability. A stationary
  sample with no sign frame proves neither support nor absence.

### 2.7 Camera firmware vs M4 receiver — SEPARATE, do not conflate

- Both outer TARs contain only `SigmastarUpgradeSD_SSC8838G.bin` + `sysVer` +
  md5 + `adas_upgrade.sh`. **No M4 receiver binary / source, M4 update
  package, 3D layout asset, M4 version string, or verified speed-widget
  enable** was found in either camera package or the VI customer UBIFS.
- `rk312x` USB identification is not receiver source / version evidence.
- `ScreenModeSet/theme` = day/night, not a proven 2D/3D/widget switch.
- `SpeedStamp` / `SpeedUnit` OSD (`OSD_DrawVideoStamp` -> RGN canvas) is a
  camera-side video path; it does not prove the 2D digits' composition or
  create a 3D widget.
- Therefore: **absence of M4 artifacts in camera firmware must NOT be read as
  proof that M4 cannot render speed/signs.** Receiver support stays UNKNOWN
  (no active value/render trial has been performed). A camera-only flash can
  only test camera senders / integration, never the M4 renderer version.

## 3. VI ADAS-failure / calibration risk (known risk, NOT proven incompatibility)

Per `docs/runtime/ADAS_FAILURE_CLASSIFICATION.md` (A–F) and
`docs/reverse/VI_CALIBRATION_PATH_V1.md` + `EVIDENCE_VI_ADAS_FAILURE.json`:

- User ground truth: VI 2023-09-20 ADAS did not operate where EN 2023-08-03
  operated. Static work downgrades (not eliminates): different CNN weights
  (6/6 blobs identical), stale `m0` (VI tracks moved offsets), shell-gate
  change (`run.sh` 1584 B `796e555a...` and `adas_checkcalib.sh` 1145 B
  `518f22e9...` identical), `raw_adas` rename/rewrite, broad algorithm
  rewrite (2731/2734 same call sequence), changed BitAnswer implementation.
- UNKNOWN without runtime: failure class A (absent) / B (crash loop) /
  C (input/ringbuffer) / D (IPU/model init) / E (inference alive, warnings
  suppressed incl. GPS / speed / calibration / TSR gates) / F (display/audio
  only). No `collect_baseline.sh` + `classify_adas_state.py` capture exists
  for this unit on either build.
- `adas_upgrade.sh` (identical, 2972 B) backs up and preserves
  `/customer/minieye/config` and `/config`. Same persistent
  `adas.flag`/`calib.flag` (base64 -> `adas_de`/`calib_de.flag`,
  `--enable_vehicle=false` gate) can yield different VI behavior only if the
  VI executable parses / validates ranges differently — unproven, device
  files unavailable. EN models / calibration / license / `calib_success`
  greeting (`adas_activated.wav`) / VI WAVs / AP / recording are preserved
  in the sense that the updater design preserves them, not that a flash is
  risk-free: `upgrade_script.txt` erases and rewrites NAND partitions
  (KERNEL x2, rootfs, ubi0/customer, MISC, etc.).
- VI audio: FCW/HMW identical; LDW/PCW/SAG/VB/activated/fail/updating
  re-recorded — explains sound difference, not total ADAS failure.
- Distinguish clearly: **known VI ADAS-failure observation + calibration /
  kernel / package-unknowns = risk, not a proven VI incompatibility.**
  Likewise, VI display/GPS additions are not proven to fix 3D speed/sign.

## 4. Would flashing VI help M4 speed / sign rendering? Assessment: NO (as a blind fix)

- 3D vehicle speed: VI adds no new message type and no proven widget/enable.
  EN already sends `GPSSpeed`; the 3D absence is a receiver-handling /
  validity / display-policy / layout question (or GPS-fix quality), not a
  missing camera template. VI's extra sender + parser refactor could change
  speed validity/frequency but has no mechanism to create a 3D digit.
- Traffic signs: no sign slot in either screen contract; TSR stays
  `CollectService`-side with `--enable_tsr=false` default both builds.
  VI cannot conjure an M4 sign icon.
- 3D objects/warnings: core `ScreenService` senders and `SendADASInfoToScreen`
  / `DeviceSendMsgToScreenTask` are unchanged; VI's risk lies upstream
  (kernel/fb, G-sensor/power, `raw_adas` liveness, package/interstitial
  validation, calibration/license interpretation). If VI ADAS fails to reach
  inference (the reported symptom), flashing VI would *remove* the working EN
  warnings/objects, not add speed/sign.
- Camera flash does not update M4: no M4 payload/updater in either package,
  so a VI camera flash is not an M4 firmware trial at all.

## 5. Precise differences table (safe evidence)

| # | Area | EN | VI | Effect on M4 speed/sign |
|---|---|---|---|---|
| 1 | `cardv` build | 1225780 B `344b4a3f...` | 1225780 B `56db44d9...` | same size, different build; not a widget |
| 2 | `cardv` dynsym | 4478 syms | 4476 syms; VI-only `SendGPSSpeedToScreen` (4 B), `nmea_BDGSV2info_na` (988 B) | extra GPS/screen code, same message type |
| 3 | `GPSSpeed` token | 2x | 3x (+`0x387FA`); sender sym VI-only `0x387F6` | duplicates native stream; no new slot |
| 4 | `SendGPSInfoToScreen` | 112 B, 2x `SetGPSLevel` | 92 B | validity/level behavior may differ; gating UNKNOWN |
| 5 | GPS parser | `nmea_satinfo`, `Is_Gps_info`, `nema_calc_checksum` | `nmea_BDGSV2info_na`; `nmea_pack_type1` 388->616, `nmea_parse1` 792->680 | BeiDou/sentence coverage change; speed-source risk, not a renderer fix |
| 6 | `SendADASInfoToScreen` / screen task | 380 B / 80 B | identical sizes + order | status plumbing unchanged |
| 7 | ADAS `ScreenService` | `Init` 120 B; warning/measure/ped senders fixed sizes | byte-identical code prefixes; literal-pool-only tail diffs; `libflow.so` identical (`a6bfcbf6...`) | 3D object transport NOT rewritten |
| 8 | `raw_adas` | 1x `0xFF340`, same CRingBuf API | 1x `0xF5794`, same visible sequence | endpoint unchanged; liveness UNKNOWN |
| 9 | Boot `fb` reservation | none | `mmap_reserved=fb,sz=0x800000` (8 MiB) | display integration change; starvation/composition UNKNOWN |
| 10 | G-sensor / power / restart | baseline | sensitivity +320 B, power-on-by-int +56 B, restart +268 B | startup/power behavior change; ADAS-gating risk |
| 11 | `adas` package | 11636008 B `0dcc6982...`, proto 1.4.0, commit `00780a5` | 11653870 B (+17862 in 7 interstitial gaps) `997b71c2...`, proto 1.4.0, commit `e534310` | models identical; validation/package risk, no sign renderer |
| 12 | TSR default / export | `--enable_tsr=false`, CollectService topics | same | no M4 sign slot either build |
| 13 | Audio | stock WAVs | 7 WAVs re-recorded (FCW/HMW identical) | sound only |
| 14 | M4 payload in camera pkg | none | none | camera flash != M4 update |
| 15 | Config preservation | `adas_upgrade.sh` preserves `/customer/minieye/config` + `/config` | identical script | same files, possibly different VI interpretation (UNKNOWN) |

Function offsets above are ELF file offsets; VAs from `readelf -W` include
the Thumb bit on code symbols (clear bit 0 for code address, as in §2.3).

## 6. What a valid experiment would have to show (and confounders)

A VI camera-flash A/B proves something about 3D speed/sign ONLY if, with mode
contemporaneously confirmed (photo of the actual M4 state at each step, not
advertising), the following are all recorded:

- GPS fix quality + emitted `speed` validity (0 = stationary OR invalid; JSON
  has no validity/timestamp); `SpeedUnit` (KM/H); stationary vs moving
  (no hazardous induction; no deliberate speeding).
- Calibration / activation: `adas --fs` present, `install_calib_state`
  marker, `--enable_vehicle` effective value, TSR effective enable — without
  publishing secrets; redacted hashes only.
- Transport: `usb0` RNDIS legs to :26012/:8080 (+:24012) ESTABLISHED at each
  observation; which leg carries what; no second :8080 client with M4
  attached (single global client pointer).
- Display: 2D vs 3D mode per observation; warning-bar events distinguished
  from persistent speed digits and from sign icons; TTC/headway/seconds never
  relabeled as speed/limit; disappearance/expiry noted.
- PASS bar (example): same route/GPS-fix, same 3D-confirmed mode, EN shows
  no 3D speed/sign while VI shows a persistent speed digit / sign icon that
  tracks GPS / a known real sign with verified class/value, expiry on stale
  input, and intact recording/ADAS/AP — with byte-exact rollback to EN after.

Confounders that invalidate a "VI fixed it" claim: GPS-drift nonzero
stationary speeds (1..5 seen historically), invalid->0 mapping, calibration
warm-up (~60 s regular-mode behavior), M4 2D/3D mode mismatch, warning-bar
seconds mistaken for speed, live-video picture of a roadside sign mistaken
for a widget, second-observer theft of the :8080 stream, 26012 reconnect
(Failed preserve gate), G-sensor/power restart differences, audio-only
changes, and any persistent-config mutation across flashes.

## 7. Recommendation: NO FLASH. Single A/B only with these go / no-go gates

**NO FLASH** with current evidence. Rationale: (a) no mechanism by which VI
adds a 3D speed/sign widget; (b) EN already sends everything VI would
duplicate; (c) VI carries a user-observed total-ADAS-failure risk plus opaque
kernel/fb, parser, power/restart, package-validation, and
calibration/license unknowns; (d) ADB offers no recovery (handshake only);
(e) camera package has no M4 updater, so this is not even an M4 trial.

One controlled A/B is described ONLY if every gate below is met; otherwise it
stays NO-GO. This is not authorization to flash now:

GO only if ALL hold:

1. Exact rollback proven first: hash-verified EN package
   (`...EN.tar` `3a703522...`, inner `e3f24432...`) + `adas_upgrade.sh`
   flow + known-good SD media staged and checksum-verified offline; recorder /
   AP / D4 / license / calibration backup procedure reviewed (copies only,
   secrets redacted); owner explicitly re-confirms this exact plan
   immediately before, with camera/M4 stationary and normal functions noted.
2. Baseline captured on EN first: mode-confirmed 2D and 3D observations,
   GPS/speed behavior, warning-bar behavior, transport legs, recording/AP
   health — so a VI change (or regression) is attributable.
3. NO reset / calibration forcing / recording-media staging / guessed
   setters / second :8080 client / semantic injection / UART/FIFO writes /
   display-plane changes as part of the trial.
4. Stop rules: any recording/AP/ADAS loss vs baseline, 26012/8080 leg loss
   without recovery, M4 flicker / black-screen value, config/license mutation
   that blocks rollback, or owner request — stop and roll back to EN
   immediately; report actual outcome including restoration failures.
5. NO-GO by default if rollback media is unverified, baseline is missing,
   or the goal is "try VI and see" without the §6 observation bar.

Expected screen observations that would validate the experiment:

- If VI changed nothing for 3D speed/sign (predicted): 2D speed persists;
  3D still shows scene/warnings but no persistent speed digit and no sign
  icon under the same GPS/mode conditions; native `GPSSpeed` still emitted.
  Conclusion: VI sender/fb work does not create the widget; investigate
  receiver handling / layout / enable (vendor artifacts) and harmless
  stock visible-path checks — not another flash.
- If VI regresses ADAS (known risk): `adas --fs` absent / crash-loop /
  `raw_adas` starvation / no 26012 scene traffic where EN had it, or
  calibration-gated silence. Conclusion: class A–F per classifier; roll back
  to EN; do not attribute to M4.
- Only a mode-confirmed, GPS-valid, persistent 3D speed digit / sign icon
  with correct tracking and expiry (see §6) counts as a positive render
  result. Anything less is UNKNOWN, not support.

## 8. Reproduction (offline, read-only)

```powershell
Get-FileHash -Algorithm SHA256 work\private-vault\V2023.08.03.1_C2M_U_FR_WIFI_EN.tar,firmware\original\V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
python tools\fw\carve_upgrade.py <tar> -o <out> --no-carve   # manifest + upgrade_script.txt only
python tools\fw\cardv_symdiff.py --en <en_cardv> --vi <vi_cardv> -o <out>.json
python tools\fw\cardv_contract_evidence.py --en <en_cardv> --vi <vi_cardv> -o <out>.json
readelf -W --dyn-syms <cardv> | Select-String 'SendGPSSpeed|SendGPSInfoToScreen|SendADASInfoToScreen|DeviceSendMsgToScreenTask'
```

`cardv` bytes: EN `m4trace_fw\cardv`; VI via gunzip + `iter_cpio`
(`extract_rootfs_cpio.py`) of `bootconfig/bin/cardv` from VI `rootfs.es`
to TEMP. `adas` via `ubifs_extract_file.py` (no mount/execute).
`customer.es` via `ubifs_ls.py` (no decompression).
Canonical priors: `docs/reverse/EVIDENCE_CARDV_CONTRACT.json`,
`EVIDENCE_CARDV_SYMDIFF.json`, `EVIDENCE_VI_ADAS_FAILURE.json`,
`EVIDENCE_STOCK_ADAS_SCHEMA.json`, `docs/firmware_en_vi/*`,
`docs/runtime/ADAS_FAILURE_CLASSIFICATION.md`.
