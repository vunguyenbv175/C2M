# VI raw_adas Upstream Prerequisites and Gating V1

**Mode:** static, read-only. No firmware modification, no flash.
**Inputs:** `build/fw_bin_en/cardv` (`344b4a3f…`, 1225780 B),
`build/fw_bin_vi/cardv` (`56db44d9…`, 1225780 B),
`build/fw_bin_en/adas` / `build/fw_bin_vi/adas` (hashes per compat report).
**Tool limits:** no `readelf` / `llvm-objdump` / ARM `objdump` on this Windows host;
`capstone` 5.0.7 only. All counts/offsets below are pure-Python byte-exact.
Branch/channel/device/port/format immediates that require disassembly are marked
UNKNOWN where appropriate. Prior accepted `send()` / `adas_minieye_send_frame_task()`
normalized identity (219 + 874 insns, `CARDV_RAW_ADAS_CONTRACT_V1.md`) is cited, not redone.

## 1. Verdict

```text
RAW_ADAS_UPSTREAM: RUNTIME_DEPENDENT (static API/surface SAME, live gating UNKNOWN)
```

No material upstream API/endpoint/count delta was found. Whether VI starts the producer
thread, configures sensor→VIF→ISP→SCL identically, allocates shared buffers, and delivers
1920x1440@10Hz frames with identical stride/format/timestamps is UNKNOWN without runtime.

## 2. Deep-compare table (cardv producer + adas consumer)

`SAME` means identical `bytes.count`; offset movement is layout noise (VI cardv layout
shifted; VI adas `.text` shifted `-0x18` after `SystemInit`, tail shifted `+0x45c6`).

| PARAMETER | EN | VI | SAME/DIFFERENT | Relevance | Confidence |
|---|---|---|---|---|---|
| `raw_adas` token | 1 @ `0xFF340` (cardv), 2 @ `0x15d3d4,0xb18860` (adas) | 1 @ `0xF5794` (cardv), 2 @ `0x15d370,0xb1ce26` (adas) | SAME counts | endpoint not renamed | CONFIRMED |
| `fortest` companion | 1 @ `0xFF34C` | 1 @ `0xF57A0` | SAME | ctor `r1=fortest, r2=raw_adas` (prior) | CONFIRMED |
| `CRingBuf` | 5 (cardv), 8 (adas) | 5, 8 | SAME | ctor/request/commit surface | CONFIRMED |
| `RequestWriteFrame` | 2 / 2 | 2 / 2 | SAME | write contract | HIGH-CONFIDENCE (prior normalized) |
| `CommitWrite` | 1 / 1 | 1 / 1 | SAME | commit contract | HIGH-CONFIDENCE |
| `MI_SYS_Init` | cardv 2, adas 1 @ `0x2194b` | cardv 2, adas 1 @ same | SAME | platform init entry | CONFIRMED (string layer) |
| `MI_SCL_CreateDevice` / `SCL_CreateDevice` | cardv 1 @ `0x23b58` / adas 1 @ `0x21b3c` | cardv 1 @ `0x23b28` / adas 1 @ same | SAME | SCL device creation | CONFIRMED |
| `MI_SYS_ChnOutputPortGetBuf` | cardv 1 @ `0x23e89`, adas 0 | cardv 1 @ `0x23e59`, adas 0 | SAME | cardv owns GetBuf; adas consumer uses `CRingBuf`/CameraReader path | CONFIRMED |
| `MI_SYS_MemcpyPa` | cardv 1, adas 0 | cardv 1, adas 0 | SAME | phys copy in producer | CONFIRMED |
| `MI_SYS_MMA_Alloc` | cardv 1 @ `0x2413d`, adas 3 @ `0x2196c,0x15cf48,0x15cf6c` | cardv 1 @ `0x2410d`, adas 3 @ `0x2196c,0x15cf30,0x15cf54` | SAME counts, `.text` anchor `0x2196c` identical | contiguous allocation | CONFIRMED counts; return-code handling UNKNOWN |
| `MI_SYS_Mmap/Mmap` | cardv 1, adas 2 | cardv 1, adas 2 | SAME | mapping | CONFIRMED counts |
| `MI_SCL` / `MI_VIF` / `MI_ISP` (cardv) | 12 / 12 / 86 | 12 / 12 / 86 | SAME | SCL/VIF/ISP API surface | CONFIRMED |
| `MI_SYS` (cardv) | 31 | 31 | SAME | sys API surface | CONFIRMED |
| `MI_SCL` (adas) | 4 | 4 | SAME | adas SCL surface | CONFIRMED |
| `mmap/munmap/lseek/select/pthread_create` (cardv) | 6/2/2/12/8 | 6/2/2/12/8 | SAME | mapping/thread/select surface | CONFIRMED |
| `pthread_create` (adas) | 2 @ `0x1f223,0x15bf30` | 2 @ `0x1f223,0x15bf18` (`-0x18`) | SAME | thread-start surface | CONFIRMED counts |
| `CameraReader` (adas) | 14 | 14 | SAME | frame acquisition | CONFIRMED |
| `LaneCalib/RunLane/UpdateInstallCalibState` (adas) | 23/1/1 | 23/1/1 | SAME | downstream consumption | CONFIRMED |
| `ringbuf_vehicle` (adas) | 1 @ `0xb18841` | 1 @ `0xb1ce07` (`+0x45c6`) | SAME | consumer input name | CONFIRMED |
| Branch immediates (channel/device/port/format/geometry/stride/timeout/select-fd/bufsize/physaddr/cache) | prior normalized `send`+`send_frame_task` identical | same prior | SAME (checked region) / UNKNOWN (unchecked upstream setup) | live geometry/cadence | HIGH-CONFIDENCE for checked helpers; UNKNOWN for sensor→SCL setup |
| Thread-start guards (camera mode/sensor/screen/GPS/enable-flags/calib-state/recording/config/variant/front-rear) | `pthread_create` counts same; guard predicates not recovered | same | SAME surface / UNKNOWN predicates | can VI skip thread while preview works? UNKNOWN | UNKNOWN |

Prior `cardv_ringbuf_contract.py` evidence (cited): ctor `r1=fortest, r2=raw_adas,
r3=0x400, [sp]=2, [sp+4]=0, [sp+8]=0`; `send()` 219 normalized insns identical;
`adas_minieye_send_frame_task()` 874 normalized insns identical; literal-pool divergence
only. This run re-confirms the string/API layer identically without re-disassembling.

## 3. Thread-start guards — can VI skip the producer while preview works?

Statically: UNKNOWN (no guard predicate recovered on this host).

- `cardv` has 8 `pthread_create` sites both builds (offsets `0x2376c,0xf0477,0xf1c40…`
  EN vs `0x2373c,0xf5994,0xf59dc…` VI — layout shift, same count). `adas` has 2 both.
- No `camera mode / sensor / screen / GPS / enable-flags / calib-state / recording /
  config / variant / front-rear` gate-string delta was found: `enable_vehicle` etc. live
  in `adas`, not `cardv`; `cardv` has no `BitAnswer`/license strings (0 both) and no
  `CameraReader/RunLane/LaneCalib` strings (0 both) — confinement proof that ADAS-side
  gating logic is not duplicated in `cardv` at string layer.
- Preview/recording working while `raw_adas` starves is *architecturally possible* if the
  `raw_adas` task is a separate thread/branch gated on SCL channel/port, allocation
  success, or startup order, while preview uses a different SCL channel/port or direct
  display path. Static counts cannot exclude this; runtime thread enumeration is required
  (section 7 probe map).
- Therefore: `VI skips thread start while preview works` remains UNKNOWN and
  RUNTIME_DEPENDENT. Do NOT claim a guard change without `llvm-objdump` CFG + runtime
  thread list.

## 4. SCL module/device/channel/port/format/res/fps — raw_adas vs preview/recording

Exact IDs: UNKNOWN (require `llvm-objdump` immediates around `MI_SCL_CreateDevice`,
`MI_VIF_*`, `MI_ISP_*`, `MI_SYS_ChnOutputPortGetBuf` — unavailable here; prior work did
not recover them either).

What IS proven:

- Consumer expectation (packaged tail + strings, both builds identical):
  `--camera_input=ringbuf_vehicle --ringbuf_name=raw_adas --image_width=1920
  --image_height=1440 --vehicle_run_freq=10` (see compat report; `EVIDENCE_ADAS_STRINGS`
  + tail).
- Producer endpoint spelling identical (`raw_adas` + `fortest` adjacent, both).
- `MI_VIF` (12) / `MI_ISP` (86) / `MI_SCL` (12) / `MI_SYS_ChnOutputPortGetBuf` (1) /
  `MI_SYS_MemcpyPa` (1) counts identical — the *vocabulary* of the media pipeline is
  unchanged, but which device/channel/port/format/res/fps values are passed at each call
  site is UNKNOWN.
- `IMX415` string 0 both (sensor name not embedded as ASCII); sensor identity comes from
  prior docs (`docs/firmware_en_vi/05_CAMERA_MEDIA_IMU.md`), not from these ELFs.

Architecture (static shape, values UNKNOWN where marked):

```text
sensor (IMX415 MIPI, per prior docs; no ASCII in ELFs: UNKNOWN)
  → VIF (MI_VIF_* x12 vocab SAME)
  → ISP (MI_ISP_* x86 vocab SAME)
  → SCL (MI_SCL_CreateDevice x1 SAME; MI_SCL_* x12 SAME)
      ├─→ [preview/recording channel/port: IDs UNKNOWN] → display/muxer (works per symptom)
      └─→ [raw_adas channel/port: IDs UNKNOWN] → MI_SYS_ChnOutputPortGetBuf (x1 SAME)
           → MI_SYS_MemcpyPa (x1 SAME) → CRingBuf(raw_adas, fortest, 0x400, 2, 0, 0)
           → RequestWriteFrame → CommitWrite → adas CameraReader → RunLane/LaneCalib
  MI_SYS_Init (cardv x2 / adas x1 SAME) → MI_SYS_MMA_Alloc → MI_SYS_Mmap
  pthread_create (cardv x8 / adas x2 SAME) → send task (normalized SAME per prior)
```

Preview vs `raw_adas` SCL channel/port/format divergence is the precise UNKNOWN that
runtime must close (capture SCL attrs + GetBuf return codes + frame metadata).

## 5. Buffer / memory math — 1920x1440@10Hz (PROVEN vs ESTIMATED)

PROVEN (static):

- Geometry: `1920x1440` (`--image_width/--image_height`), cadence `10 Hz`
  (`--vehicle_run_freq=10`) — identical EN/VI tail.
- Bootargs: `LX_MEM=0x3ffe0000`, `mma_heap=…,sz=0x1f000000`, `cma=2M@0x23800000`,
  VI-only `mmap_reserved=fb,…,sz=0x800000 (8 MiB) @ 0x3F000000–0x3F800000` (prior,
  `EVIDENCE_VI_ADAS_FAILURE.json:K02`).
- `mma_heap sz=0x1f000000` = 520093696 B = 496 MiB; `cma=2M`; `fb=8MiB` = 8388608 B.

ESTIMATED (format/stride/ring-depth not proven statically — no format string found;
`MI_*` immediates UNKNOWN):

| Format hypothesis | bpp | Stride hypothesis (ESTIMATED) | Frame bytes (ESTIMATED) | Ring-depth hypotheses (ESTIMATED) | Total (ESTIMATED) | vs fb 8 MiB / CMA 2M / MMA 496M |
|---|---|---|---|---|---|
| YUV420 planar (likely for CNN) | 12 | 1920 (no pad) | 1920*1440*1.5 = 4147200 B (3.95 MiB) | 2 → 8294400 B (7.91 MiB); 3 → 12441600 B (11.87 MiB); 4 → 16588800 B (15.82 MiB) | fits MMA easily; 2-frame ring ≈ fb size | PROVEN geometry, ESTIMATED format/stride/depth |
| YUV422 / YUYV | 16 | 3840 | 5529600 B (5.27 MiB) | 2 → 11059200 B (10.55 MiB) | exceeds fb, fits MMA | same labels |
| RGB888 | 24 | 5760 | 8294400 B (7.91 MiB) | 2 → 16588800 B (15.82 MiB) | single frame ≈ fb | same labels |
| RAW8 | 8 | 1920 | 2764800 B (2.64 MiB) | 3 → 8294400 B | fits | same labels |
| RAW10 packed (5B/4px) | 10 | 2400 | 3456000 B (3.30 MiB) | 2 → 6912000 B | fits MMA | same labels |

Stride alignment is ESTIMATED: SigmaStar SCL often pads to 16/32 B; 1920 is already
32 B-aligned so no pad assumed, but NOT proven. Ring depth is ESTIMATED: ctor
`r3=0x400, [sp]=2` (prior) suggests depth/size `2` and `0x400` but field mapping is
UNPROVEN without header. Cache/physaddr handling UNKNOWN.

Conclusion: memory *capacity* does not statically prove starvation — even a 2–4 frame
ring of the largest hypothesis fits the 496 MiB MMA heap. The VI `fb` 8 MiB reservation
is comparable to *one* frame (3.9–7.9 MiB) but overlap/consumption/order is UNPROVEN.
Do NOT claim `fb` causes starvation without `/proc/iomem` + `/proc/meminfo` +
`MI_*` return codes (prior `KERNEL_RESERVED_MEMORY_ANALYSIS_V1.md` cited).

## 6. Allocation-failure handling

Searched `MI_SYS_MMA_Alloc / MI_SYS_Mmap / MI_SYS_ChnOutputPortGetBuf /
IPUCreateDevice / MI_SCL_CreateDevice` error strings + `fail/error/timeout/alloc`
contexts: no EN-vs-VI handler-string delta found (counts SAME; `version/fail` contexts
identical at string layer). Retry/log/exit/alive-but-inactive semantics are UNKNOWN
without CFG (needs `llvm-objdump`).

Symptom match (honest):

```text
camera works + recording works + lane never active
  consistent with: GetBuf timeout / MMA_Alloc fail / thread never started /
                   consumer opened wrong endpoint / IPU init fail AFTER frames
  inconsistent with: sensor totally dead (preview would fail), broad writer rewrite
                     (disproven), endpoint rename (disproven)
  distinguishes: need MI_* return codes + thread list + raw_adas frame counters
                 (section 7). Static handling analysis ALONE matches no single
                 branch — all upstream-failure branches remain UNKNOWN.
```

Prior `SystemInit` delta (EN 124 B → VI 100 B, logging-path only, both retain
`MI_SYS_Init/MI_SCL_CreateDevice/IPUCreateDevice`) is cited; it does NOT prove a
changed allocation-failure policy.

## 7. Runtime probe map (minimum, read-only)

| Function / site | Success signal | Failure signal | Log / side-effect | Observable (capture script) |
|---|---|---|---|---|
| `MI_SYS_Init` (cardv x2, adas x1) | ret 0, `dmesg` MI init ok | ret !=0, `dmesg` MI fail | `dmesg_filtered.txt` | `dmesg_filtered.txt` + process alive |
| `MI_SCL_CreateDevice` | ret 0, SCL dev present | ret !=0 | `dmesg` SCL | `dmesg_filtered.txt` |
| `MI_SYS_MMA_Alloc / MI_SYS_Mmap` | physaddr non-zero, maps present | NULL/ret !=0, OOM/buddyinfo pressure | `/proc/buddyinfo`, `maps.txt` | `proc_buddyinfo.txt`, `proc_<pid>_*/maps.txt` |
| `pthread_create` (cardv 8, adas 2) | threads present | missing thread | `threads.tsv` | `proc_<pid>_*/threads.tsv` |
| `MI_SYS_ChnOutputPortGetBuf` + `select` + timeout | seq++/ts monotonic, fps≈10 | timeout/ret !=0, seq stall | `select` timeout log | infer via frame counters (needs extended capture: add GetBuf seq/ts log if available) |
| `MI_SYS_MemcpyPa` | phys copy ok | ret !=0 | `dmesg` | `dmesg_filtered.txt` |
| `CRingBuf(raw_adas)` ctor/request/commit | `/dev/shm` or SysV SHM object + `fd.txt` shm refs | no SHM object, request fail | `proc_sysvipc_shm.txt`, `list_dev_shm.txt`, `fd.txt` | all three in capture |
| `CameraReader → RunLane → LaneCalib → warnings/display` | `ScreenService :26012` + warning traffic | port absent / silent | `ports_of_interest.txt`, `proc_net_tcp.txt` | both in capture |
| `run.sh` gates | `adas_de/calib_de.flag` hashes recorded | absent/decode fail/`enable_vehicle=false` | `config_hashes.tsv` (hashes only) | `config_hashes.tsv` |

All observables are produced by `tools/fw/capture_c2m_adas_runtime.sh` except live
frame seq/ts/fps, which require the device to expose counters (if no counter exists,
record `UNKNOWN`, never synthesize).

## 8. Reproduction

```powershell
python C:\Users\Admin\AppData\Local\Temp\opencode\lastmile_scan.py
python C:\Users\Admin\AppData\Local\Temp\opencode\ctx_scan.py
python tools/fw/elf_overlay_report.py build/fw_bin_en/adas build/fw_bin_vi/adas
```

Prior (Linux-only, cited): `python tools/fw/cardv_ringbuf_contract.py
build/fw_bin_en/cardv build/fw_bin_vi/cardv`.

## 9. Conclusion

Upstream producer *code* is statically SAME where checked; upstream *liveness* is
RUNTIME_DEPENDENT. The next experiment is not another static diff but the read-only
capture in section 7 on EN then VI (see classifier report), followed by the reversible
EN-base + VI-`adas` launch only with recovery proven.
