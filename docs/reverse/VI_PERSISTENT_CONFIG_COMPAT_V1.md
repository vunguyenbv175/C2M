# VI Persistent Config / Calibration-Parser Compatibility V1

**Mode:** static, read-only, no firmware modification, no flash, no device files.
**Inputs (hash-verified):** `build/fw_bin_en/adas` (`0dcc6982…`, 11636008 B),
`build/fw_bin_vi/adas` (`997b71c2…`, 11653870 B), `build/run_en.sh` /
`build/run_vi.sh`, `build/checkcalib_en.sh` / `build/checkcalib_vi.sh`.
**Tool limits (honest):** Windows host, `python` 3.12.0, `capstone` 5.0.7 available;
`readelf` / `llvm-objdump` / ARM `objdump` absent (`shutil.which` returns None for all).
Therefore branch/immediate disassembly comparison below the string layer is marked
UNKNOWN where it would require those tools. All string/offset claims are pure-Python
byte-exact (`bytes.find` / `bytes.count`) and reproducible with
`C:\Users\Admin\AppData\Local\Temp\opencode\keyscan.py`,
`lastmile_scan.py`, `ctx_scan.py`.

Prior accepted analyses are NOT redone: `run.sh` / `adas_checkcalib.sh` identity,
writer-contract identity, kernel/U-Boot/model/`m0`/scripts/calibration-state-machine
conclusions are cited, not re-litigated. New contradictory evidence: none.

## 1. Verdict

```text
PERSISTENT_CONFIG: SAME_SEMANTICS (HIGH-CONFIDENCE at key/default/order layer;
parser branch/immediate/threshold internals UNKNOWN without llvm-objdump + device files)
```

No material parser-key, default-value, key-order, path, or migration-gate delta was found.
The earlier naive `fx/fy/cx/cy` count wobble is proven to be high-entropy overlay noise,
not a parser change (section 4).

## 2. Key table (byte-exact)

Method: `bytes.count` + first offsets. `EN .text` means offset `< 0x172b1c` and identical
EN/VI (code section); `tail` means packaged gflags tail near EOF; `rodata` means
`0x15xxxx` range (shifted by `-0x18` text shrink); overlay means `>= 0x172b1c`.

| KEY | EN count / offsets | VI count / offsets | Type / default (tail) | Range/sentinel/reject/fallback/consumer | Delta | Confidence |
|---|---|---|---|---|---|---|
| `--install_calib_state` | 1 @ `0xb188f8` | 1 @ `0xb1cebe` | gflags tail, default `0` (`--install_calib_state=0` context both) | script accepts `1`/`2`, only `0` blocks; consumer `UpdateInstallCalibState` / `LaneCalib` (prior) | SAME key, SAME default, offset delta `+0x45c6` = file-size delta | HIGH-CONFIDENCE SAME |
| `--enable_vehicle` | 1 @ `0xb18103` | 1 @ `0xb1c6c9` | tail default `true` (`--enable_vehicle=true` context both) | `run.sh` exits if `false`; consumer vehicle pipeline gate | SAME, delta `+0x45c6` | HIGH-CONFIDENCE SAME |
| `pitch` | 32, e.g. `0x329f9,0x35962,0x37523` | 32, same first 10 offsets byte-identical | symbols `FLAGS_min_valid_pitch_val`, `FLAGS_nopitch`, `FLAGS_nomin_valid_pitch_val`, tail `--pitch=0.0` | range/threshold immediates UNKNOWN (needs objdump); consumer autocalib/lane | SAME counts + SAME `.text` offsets | HIGH-CONFIDENCE SAME surface |
| `yaw` | 30, e.g. `0x2ae64,0x2f16d,0x2f30d` | 30, same 10 offsets | symbols `FLAGS_autocalib_yaw_range`, `FLAGS_yaw`, `FLAGS_noyaw_precision`, tail `--yaw=0.0` | same caveat | SAME | HIGH-CONFIDENCE SAME surface |
| `roll` | 5 @ `0x309d3,0x37c2d,0x156efb,0x158078,0xb17fce` | 5 @ `0x309d3,0x37c2d,0x156ee3,0x158060,0xb1c594` | `.text` first two identical; `rodata` shifted `-0x18`; tail shifted `+0x45c6` | consumer horizon/roll | SAME, layout noise only | HIGH-CONFIDENCE SAME |
| `camera_height` | 21, e.g. `0x28ad2,0x2a4de,0x2c24a` | 21, same first 10 | symbols `FLAGS_nocamera_height_precision`, `FLAGS_nocamera_height`, `FLAGS_min_valid_camera_height` | UNKNOWN immediates | SAME | HIGH-CONFIDENCE SAME surface |
| `intrinsic` | 0 | 0 | absent both | N/A | SAME (absent) | CONFIRMED |
| `extrinsic` | 2 @ `0x3e66c,0x470e3` | 2 @ same | symbols only | consumer `get_extrinsic` (prior) | SAME | CONFIRMED |
| `--fx/--fy/--cx/--cy` | 0/0/0/0 | 0/0/0/0 | no dashed keys either build | N/A | SAME (absent) | CONFIRMED |
| `distortion` | 0 | 0 | absent both | N/A | SAME | CONFIRMED |
| `vehicle_autocalib_on` | 4 @ `0x29153,0x431c3,0x15e9e4,0xb18952` | 4 @ `0x29153,0x431c3,0x15e980,0xb1cf18` | `.text` identical; `rodata` `-0x18`; tail `+0x45c6` | consumer autocalib enable | SAME | HIGH-CONFIDENCE SAME |
| `heavy_lane_calib_mode` | 7 (see scan) | 7, `.text` `0x2610a,0x2c27b,0x3b35a,0x3e5e1` identical | tail `heavy_lane_calib_mode=tr…` both | consumer heavy/regular mode | SAME | HIGH-CONFIDENCE SAME |
| `switch_file` | 3 @ `0x4138a,0x157f20,0xb17f18` | 3 @ `0x4138a,0x157f08,0xb1c4de` | symbol `FLAGS_switch_file`, desc `Additional switch flag files (like gflags)`, tail `--switch_file=/customer/minieye/config/adas_de.flag` both | open→decode→parse→validate→default→assign→consume entry | SAME, `-0x18`/`+0x45c6` noise | CONFIRMED SAME |
| `calib_file` | 3 @ `0x2da62,0x157f58,0xb17f4c` | 3 @ same `.text`, `0x157f40,0xb1c512` | `FLAGS_calib_file`, tail `--calib_file=/customer/minieye/config/calib_de.flag` | same | SAME | CONFIRMED SAME |
| `produce_file` | 3 @ `0x4092d,0x157f64,0xb17f80` | 3 @ same `.text`, `0x157f4c,0xb1c546` | `FLAGS_produce_file`, tail `--produce_file=/customer/minieye/config/produce_de.flag` | same | SAME | CONFIRMED SAME |
| `license_root_path` | 3 @ `0x256db,0x1619d8,0xb18b10` | 3 @ same `.text`, `0x161970,0xb1d0d6` | `FLAGS_license_root_path`, src `.../license/license_service.cpp`, tail `--license_root_path=/customer/minieye/config` | BitAnswer root (see overlay report) | SAME | CONFIRMED SAME |
| `config_version/calib_version/schema_version/checksum` | 0/0/0/0 | 0/0/0/0 | no migration/version gate strings in `adas` | N/A | SAME (absent) | HIGH-CONFIDENCE (no gate found) |
| `calib_de.flag` | 2 | 2 | paths only | decode target | SAME | CONFIRMED |
| `adas_de.flag` | 1 | 1 | path only | decode target | SAME | CONFIRMED |
| `produce_de.flag` | 6 | 6 | paths | produce gate | SAME | CONFIRMED |
| `/customer/minieye/config` | 16, first `0x1573e8` | 16, first `0x1573d0` (`-0x18`) | 16 refs both | persistent root convergence | SAME | CONFIRMED |
| `model_root_dir/camera_input/ringbuf_name/image_width/image_height/vehicle_run_freq/enable_lane/ped/fcw/hmw/ldw/tsr` | counts identical (see `keyscan.py`: 2/3/3/6/6/4/4/4/4/7/4/4) | identical | tail defaults identical (only `m0` differs per `extract_tail_flags.py`: 121/121, 1 diff) | consumer geometry/freq/gates | SAME | CONFIRMED |

Parser call graph (recovered from strings + `run.sh` + prior, not re-disassembled):

```text
run.sh: open adas.flag/calib.flag → base64 -d → adas_de/calib_de.flag → grep --enable_vehicle
  → ./mutualism
adas: gflags tail (--switch_file/--calib_file/--produce_file/--pitch/--yaw/--install_calib_state/…)
  → cliargs.cpp (switch_file/calib_file/produce_file descriptors @ 0x157fxx)
  → UpdateFromEnv / DecryptNum / GetKey (m0/AES path, separate)
  → LaneCalib / LaneCalibFacade / calib_service / VehicleAlgo::RunLane → UpdateInstallCalibState
  → BitAnswer Login/ReadFeature/CheckOut (license gate, separate report)
  → ScreenService / warnings / display
```

Key order: `extract_tail_flags.py` proves 121 keys in identical order both builds
(`first5 switch_file,calib_file,produce_file,pitch,yaw`, `last5 flow_listen_addr,…,
protocol,m0`); `same_keys=true`, `difference_count=1` (`m0` only). Missing-key behavior:
no static default-difference to test; device-file absence behavior is defined by `run.sh`
(exit 1), identical both.

## 3. Branch / immediate / threshold / error-path (honest limits)

- `.text`-embedded key offsets for `pitch/yaw/camera_height/extrinsic/switch_file/
calib_file/produce_file/license_root_path` are byte-identical EN/VI (e.g. `switch_file`
`0x4138a` both, `calib_file` `0x2da62` both, `license_root_path` `0x256db` both,
`pitch` `0x329f9` both). This is HIGH-CONFIDENCE that the parser call sites in `.text`
did not move, consistent with the global `-0x18` shift applying only *after*
`SystemInit @ 0x94499` (prior). Pre-`SystemInit` code is at identical file offsets.
- Normalization: string-anchored comparison (exact key bytes + 64 B context) shows
identical 64 B windows, e.g. `--install_calib_state=0.--calib_mode=1.--autocalib_on=true`
both; `--enable_vehicle=true.--enable_ped=true.--enable_tsr=false` both;
`--switch_file=/customer/minieye/config/adas_de.flag.--calib_file=…` both.
See `ctx_scan.py` output.
- Branch/immediate/threshold/error-path *inside* parser functions (e.g. pitch-range
compare constants, missing-key fallback addresses): UNKNOWN. Requires `llvm-objdump`
+ `readelf -Ws` function boundaries, absent on this host. `capstone` alone cannot
isolate function CFG without symbols. Prior `thumb_callgraph_diff` (2734 funcs,
2731 same) is cited, not redone.
- No contradictory immediate evidence appeared: no new key, no changed default
(except `m0` which is model-directory, proven), no changed path, no changed order.

## 4. `fx/fy/cx/cy` false-positive autopsy (new)

Naive substring counts differed by 1–2 (`fx` 151 vs 153, `fy` 154 vs 153, `cy` 415 vs 416).
`ctx_scan.py` proves:

```text
overlay starts 0x172b1c both
EN fx 151: text 0, overlay 151
VI fx 153: text 0, overlay 153
EN fy 154: text 12, overlay 142 / VI fy 153: text 12, overlay 141
EN cx 476: text 323, overlay 153 / VI cx 476: text 323, overlay 153
EN cy 415: text 259, overlay 156 / VI cy 416: text 259, overlay 157
--fx/--fy/--cx/--cy: 0 both builds
intrinsic/distortion: 0 both
```

All `fx` hits are in high-entropy overlay (`entropy ~7.9767` both); `.text` counts are
identical (0/12/323/259). The ±1–2 overlay wobble is expected random-bigram noise in
encrypted/compressed bytes, not a parser delta. With `--` anchoring the parser-key
hypothesis is CONFIRMED absent both.

## 5. Offline parser-behavior comparison (attempted, not isolatable)

Attempted: READ-ONLY synthetic-input matrix (`valid / missing-key / state 0-1-2 /
boundary pitch-yaw / invalid intrinsic / empty`) emulated against extracted parser.

Result: NOT ISOLATABLE — documented, not executed, for these load-bearing reasons:

1. Parser is ARM Thumb code linked against `gflags` (`cliargs.cpp`), file I/O,
   `BitAnswer`, and IPU/model init; no single-function boundary is recoverable without
   `readelf -Ws` + `llvm-objdump` (absent; `shutil.which` None).
2. `capstone` 5.0.7 can decode Thumb but cannot recover CFG/targets without relocation
   + symbol tables; synthetic-input harness would be guessing boundaries.
3. Device flag files (`adas.flag`/`calib.flag` contents) unavailable; generic image holds
   placeholder only (prior). Synthetic bytes would not be grounded.
4. No ARM userspace emulator (`qemu-arm`) on this Windows host; full-process emulation
   would also pull IPU/SCL/VIF kernel deps that do not exist off-device.
5. Prior calibration-state-machine instruction review (`UpdateInstallCalibState`,
   `PassAutoCalibCheck`, `ProcessHeavyMode/RegularMode`) is accepted and shows
   effectively identical logic; re-emulation without new evidence would violate scope.

Therefore parser *behavioral* equivalence on synthetic inputs remains UNKNOWN by
emulation, but HIGH-CONFIDENCE SAME at the static key/default/order layer. The
discriminating test is runtime: private copy+decode of device flags + EN-vs-VI parser
logs (see classifier report), never publishing secrets.

## 6. Migration / version gates

Searched `adas` + `cardv` for `config_version`, `calib_version`, `schema_version`,
`checksum`, `decoder` (adas), `schema`, `version`:

- `adas`: `config_version/calib_version/schema_version/checksum` 0/0 both; `schema` 5/5
  (offsets `0x161d17…` vs `0x161caf…`, `-0x68` string-table shift, same `license_service`
  context); `version` 10/10; `build` 1/1 @ `0x172579` both (GNU build-id note sync).
- `cardv`: `checksum` 3 vs 2 (EN `0x30dd2,0x3a98e,0x40260` vs VI `0x30d85,0x3a94a` + missing
  one) — this is inside GPS/NMEA/display churn, not a config-migration gate; `decoder`
  4/4 both; `schema` 3/3 both. No `config_version`/`calib_version` in either `cardv`.
- `sysVer.txt` differs (`20230803193750` vs `20230920185743`) but is outer-TAR metadata,
  not a parser gate (prior). No `expiry/SKU/region/vietnam/VI_VN/en_US` strings in `adas`
  (0 both); `cardv` `language` 4/4 both, no region coupling found.

```text
Migration/version-gate delta: UNKNOWN (no gate strings found) → treat as NO_GATE_FOUND
(HIGH-CONFIDENCE at string layer; semantic gate inside code without distinctive
strings cannot be excluded statically).
CONFIRMED: no `config_version`/`calib_version` key change.
HIGH-CONFIDENCE: no `checksum`/`decoder`/`schema` parser migration in adas.
UNKNOWN: hidden integer version compare without string anchor.
```

## 7. Reproduction

```powershell
python C:\Users\Admin\AppData\Local\Temp\opencode\keyscan.py
python C:\Users\Admin\AppData\Local\Temp\opencode\lastmile_scan.py
python C:\Users\Admin\AppData\Local\Temp\opencode\ctx_scan.py
python tools/fw/extract_tail_flags.py build/fw_bin_en/adas build/fw_bin_vi/adas
python tools/fw/elf_overlay_report.py build/fw_bin_en/adas build/fw_bin_vi/adas
```

Expected (this run): tail `left_count 121 right_count 121 difference_count 1 (m0)`;
overlay `0x172b1c` both; key counts per table above.

## 8. Conclusion

Persistent parser *keys, defaults, paths, order, and preservation semantics* are
statically SAME. A VI parser incompatibility that rejects EN-era persistent files can
only live in branch immediates/thresholds without string anchors (UNKNOWN) or in
*runtime values* (device-specific numbers), not in any proven key/default/order change.
Do NOT revive `run.sh` / `adas_checkcalib.sh` / `UpdateInstallCalibState(2)` deltas
without new evidence — they remain excluded.
