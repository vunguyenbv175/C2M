# 03 — ADAS Engine, TSR and Regression Analysis

## Real-device ground truth

User report:

```text
VI 2023-09-20 -> ADAS did not operate
EN 2023-08-03 -> ADAS operated
```

Treat this as stronger evidence than version naming.

## ADAS version delta

### EN

```text
protocol: 1.4.0
commit: 00780a5784ae5b7e8975007a220b6f498f932919
version: c2m-feature-c2m-00780a5-230729
version_for_app: V23.07.29.1
BuildID: 5acaac94878db61c34c1f7f76708bc4a9162281d
file size: 11,636,008
SHA-256: 0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043
```

### VI

```text
protocol: 1.4.0
commit: e534310526de352fdbe278a6775a4a186d043c69
version: c2m-feature-c2m-e534310-230804
version_for_app: V23.08.04.1
BuildID: 4e07a0e13018f54e3462ce537153aa8171a123aa
file size: 11,653,870
SHA-256: 997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1
```

Protocol version did not change, but implementation did.

## ADAS subtree comparison

```text
total files: 112
identical:    98
different:    14
```

The 14 differences are:

```text
adas executable
version metadata files
7 localized ADAS WAV files
integrity/filesize metadata
```

### Important identical components

The following are byte-identical:

```text
params/model.img
params/model.txt
ipu_firmware.bin
lib/libPedDetect.so
lane_release/bin/lane_accelerator
lane_release/bin/lane_postprocess
lane_release/bin/calib_service
all lane configuration files checked
mutualism launcher
run.sh
adas_service.sh
adas_guard.sh
license/check scripts
most third-party libraries
OpenCV libraries
libflow
libringbuf
libshared_env
```

This sharply narrows the regression search.

## Main ADAS binary has a large appended payload

A strict ELF file-backed boundary analysis places the appended-payload start at:

```text
0x1755e4
```

Measured appended region:

```text
EN overlay size: 10,106,692 bytes
VI overlay size: 10,124,554 bytes
```

Canonical hashes:

```text
EN 7c14be61f3f1618602dd020db4e5bf9960d7e34ffcb35547a2ac60c13ee62f2d
VI 8f0841496c7d5f42ca5fd8e67dd3aeea985ebe0af031c1dcd1e3d15e5825a423
```

Both overlays have entropy around 7.9767 bits/byte. Their exact container/encoding is still unknown.

The final area contains plaintext default flags including:

```text
--switch_file=/customer/minieye/config/adas_de.flag
--calib_file=/customer/minieye/config/calib_de.flag
--produce_file=/customer/minieye/config/produce_de.flag
--enable_vehicle=true
--enable_ped=true
--enable_lane=true
--enable_fcw=true
--enable_hmw=true
--enable_ldw=true
--enable_screen_service=true
--enable_sound_alert=true
--enable_tsr=false
--sdk_output_warning=true
--sdk_use_msgpack=true
--camera_input=ringbuf_vehicle
--ringbuf_name=raw_adas
--vehicle_run_freq=10
--npu_buffer_size=5620000
--protocol=1.4.0
```

### Important correction

A naïve `strings` diff shows:

```text
EN: --switch_file=...
VI: h--switch_file=...
```

This is **not** evidence of a malformed VI switch-file flag. Exact byte inspection proves the VI file contains the correct byte sequence:

```text
--switch_file=/customer/minieye/config/adas_de.flag
```

The preceding `h` is simply byte `0x68` from the high-entropy payload with no NUL separator. Do not pursue this as a bug.

## ABI/symbol stability and `SystemInit`

A `readelf -Ws` comparison finds 3,875 symbols on each build, with all 3,875 symbol names common and zero EN-only/VI-only symbols. This makes same-name function matching especially useful.

Only one function changes reported symbol size:

```text
SystemInit(unsigned int)
EN: 124 bytes
VI: 100 bytes
```

`.text` shrinks by exactly 24 bytes. Thumb-2 disassembly plus PLT relocation mapping shows both builds retain the essential startup sequence:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

The visible `SystemInit` delta is mainly the failure logging path: EN uses `google::LogMessage` and C++ stream insertion, while VI uses a shorter direct `fwrite` path. Therefore `SystemInit` itself is now a lower-probability explanation for complete ADAS failure.

Raw per-function byte hashes over-report differences because the 24-byte code shrink moves later addresses and changes branch immediates/PC-relative references. A normalized ARM/Thumb semantic diff is required before ranking same-sized functions.

## One meaningful default-tail delta: `m0`

The long `--m0=<hex>` value differs between EN and VI.

This is **CONFIRMED**, but its meaning is **UNKNOWN**.

Possibilities include:
- integrity/key material,
- embedded model/config hash,
- license-related material,
- build-specific cryptographic metadata.

Trace references to the gflag/symbol rather than guessing.

## TSR is real implementation, not dead strings

Exported/internal symbols include:

```text
vehicle::VehicleAlgo::TsrProcess()
VehicleRun::ReadTsr()
product::Distribution::SetTsrResult(...)
CollectService::Send<TsrWarning>(...)
CollectService::Send<vector<TsrTraceRes>>(...)
tsr::SpeedLimitReporter::Update(int, long long, float)
tsr::SpeedLimitReporter::ReportWarningState()
tsr::SpeedLimitReporter::ReportWarningLevel()
```

Queues/types:

```text
vehicle::TsrMsg
vehicle::TsrRes
TsrTraceRes
TsrWarning
```

Static strings/flags include speed-limit warning thresholds and warning-state outputs. Therefore the binary contains a genuine traffic-sign/speed-limit processing path.

## Default TSR state

Both builds contain:

```text
--enable_tsr=false
```

This is a compiled/default flag, not proof of runtime state.

Startup uses:

```text
/customer/minieye/config/adas.flag
     |
base64 decode
     v
/customer/minieye/config/adas_de.flag
```

and `run.sh` exits if required config/calibration is missing. Thus per-device persistent config can override defaults.

## Why persistent config alone is no longer the leading explanation

The vendor updater explicitly preserves `/customer/minieye/config`.

If the same physical unit was flashed VI then EN without reprovisioning, the exact same persistent ADAS config/calibration/license material can survive both flashes.

Therefore, given EN-good / VI-bad, pure config difference is less likely than:

```text
new adas executable regression
or
new cardv/kernel integration regression
or
new validation/license behavior inside the new adas executable
```

It is not fully excluded because runtime scripts may mutate persistent state.

## FCW / distance / TTC evidence

The stock executable exports substantial collision logic:

```text
afcw::DistEstimate
afcw::TTCModule
afcw::VehicleTTC
afcw::RelativeTTC
FcwState::TTCFilter
VehicleMeasureRes
Warner::Process(...)
```

Functions explicitly expose/get distance, TTC, relative speed/slowdown, on-route state and warning levels. This supports a reuse-first strategy.

## Pedestrian/lane

Evidence includes:

```text
libPedDetect.so
C1PedRes
PedWarningExport
lane accelerator
lane postprocess
LaneWarning / LDW stack
```

## Traffic-light / green-light logic

The ADAS binary also contains:

```text
TlrDetect
TlrCnnCls
tlr::GreenWarning
tsr::GreenWarningState
product::Distribution::SetTlrResult
```

and `audios.txt` declares `tlr_green_on.wav`, though the referenced WAV is not present in the compared customer trees. Treat this as codebase capability, not proven enabled C2M feature.

## Highest-probability regression suspects

### R1 — VI `adas` executable / appended payload
**Priority: highest**

Reasons:
- known-good/known-bad behavior aligns with version change,
- almost all model/libs/scripts are identical,
- executable implementation and overlay changed.

### R2 — VI `cardv` interaction
**Priority: high**

Reasons:
- only major rootfs userspace binary changed,
- ADAS consumes `ringbuf_vehicle`,
- cardv participates in ADAS/screen/GPS data paths.

### R3 — kernel / memory / module integration
**Priority: medium-high**

Reasons:
- new kernel,
- framebuffer reserved-memory bootarg,
- changed SC7A20 and USB/network modules.

### R4 — new license/calibration validation inside VI ADAS
**Priority: medium**

Scripts are identical, but code inside the executable may have changed.

### R5 — localized audio/config
**Priority: low for total ADAS failure**

Audio is clearly different, but audio alone should not normally prevent all visual ADAS processing.

## Recommended binary-diff targets

Prioritize same-name function diff on:

```text
main/init
InitAPP
VehicleAlgo::Init
VehicleRun
camera/ringbuffer acquisition
MI_IPU initialization
license/check_sn
calibration loading
ScreenService::Init
TSR init
error paths
```

Use `docs/reverse/ADAS_STATIC_DIFF_V1.md` and `tools/fw/elf_*_diff.py` as the reproducible baseline.