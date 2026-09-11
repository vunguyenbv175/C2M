# C2M IPU Model Format V1 — Stock Blobs, Firmware, Offline Model

**Status:** RESEARCH ONLY. **Date:** 2026-09-11.
**Scope:** every AI blob in C2M EN firmware; no decryption attempted beyond header/entropy/strings; no weights committed.

## 1. Inventory (CONFIRMED sizes/hashes)

Embedded in `adas` executable (offsets from `ADAS_PACKAGE_LOADER_V1.md`, AES-128 `m0` directory, key `de091ce6cb35733540c86656fa1692e8`):

| ID | Offset (EN) | Size | SHA256 | Entropy | Header16 | Verdict |
|---|---|---|---|---|---|---|
| `d0` | 0x1747fe | 0x2b9000 (2854912, 2788KB) | `0b5533ee...da725d4f9` | 7.994 | `be2d6fe91166795fc28d6bb4a5e2cbe` | proprietary, HIGH encrypted/compressed |
| `v_a` | 0x431994 | 0x1ea000 (2007040, 1960KB) | `342db12a...ad23142a` | 7.982 | same 16B | same |
| `v_t` | 0x61d75c | 0x40000 (262144, 256KB) | `f63b18df...08143d0cf` | 7.901 | same 16B | same |
| `p_r` | 0x661b44 | 0x189000 (1609728, 1572KB) | `fb5795ec...a47239a9` | 7.813 | same 16B | same |
| `road` | 0x7ee408 | 0x2fe000 (3137536, 3064KB) | `4bc0e6f2...049147039` | 7.998 | same 16B | same |
| `tl` | 0xaf14bc | 0x25000 (151552, 148KB) | `ce2da363...24f00d42` | 7.911 | same 16B | same |

```text
SOURCE: build/fw_bin_en/adas (sha 0dcc6982..., 11636008 B)
VERSION: EN V23.07.29.1 (VI blobs byte-identical, offsets moved, m0 consistent)
METHOD: python header/entropy/strings (scripts in /tmp, reproducible via tools/reverse/c2m/inspect_stock_model.py)
CONFIDENCE: CONFIRMED sizes/hashes/offsets; HIGH format verdict
```

Common structure (all six):

```text
bytes 0–15:  be2d6fe91166795fc28d6bb4a5e2cbe (identical all six)
bytes 16–31: varying per model (per-model keystream/iv?)
bytes 32–63: da0edc1e497b42b68a34a138208bd118c8a9e411f3789c40e4d9d89898cdd108 (identical all six)
payload:     256 distinct byte values, ~0.5–12k zero bytes, no ONNX/TFLite/Caffe magic, header 4KB has 0–2 random-like printable runs only, full-blob printable runs are random (12k/8k/1k/5k/13k/0.6k len>=5, no words)
```

Customer files:

| File | Size | SHA256 | Entropy | Header64 | Verdict |
|---|---|---|---|---|---|
| `/minieye/adas/params/model.img` | 507040 | `07ba919be12c40f5afcb6b39f849baab52925a080059e830721d7293af303695` | 8.00 | `5fb5d1ff3aa97f5e...` random | HIGH encrypted/compressed container (comp type 0×124 blocks per UBIFS, i.e. stored raw, content itself high-entropy) |
| `/minieye/adas/params/model.txt` | 96 | — | text | `d0→1.img ... tl→6.img` | CONFIRMED mapping file |
| `/minieye/adas/ipu_firmware.bin` | 600208 | `61c4663ddef26bdfef16b1789f90d90bb6f2e9a36c10de7f6c365a9600842d55` | 7.04 | `7370043097310900938141df17...` structured, `TEa` repeats | firmware image (NOT a model), loaded via `CreateDevice` |

## 2. Format determination (HIGH PRIORITY)

```text
proprietary SigmaStar compiled model | SUPPORTED (only consistent hypothesis)
ONNX                                 | ABSENT (no `ONNX` magic, no protobuf strings, entropy too high for text proto)
TensorFlow/TFLite                    | ABSENT (no `TFL3`/flatbuffer identifiers)
NCNN-like                            | ABSENT (no `NCNN` / layer strings)
MStar/SigmaStar internal             | SUPPORTED (same as proprietary; CnnConfig/CaffeModelConfig wrappers suggest internal SGS container)
encrypted container                  | HIGH (common 16B prefix + per-model 16B + common 32B + 7.8–8.0 entropy + AES code in adas (`AES::DecryptECB/CBC/CFB`, `DecryptNum`, `vehicle::GetKey`, `BitAnswer::DecryptFeature`))
compressed container                 | POSSIBLE but insufficient alone (entropy alone ≠ encryption; here combined with AES symbols + common header + no decompress strings in blob path)
```

Do NOT infer from extension/name. `1.img–6.img` names come from `model.txt`, not format. `model.img` (singular, 507KB) is NOT the same as the six embedded blobs; role UNKNOWN (config? calib? secondary net?).

SGS toolchain correspondence (family-level, Pudding doc):

```text
ConvertTool → .sim (SGS Float file, flatbuffer)
Calibrator  → _fixed.sim (SGS Fixed 8/16bit)
Compiler    → _fixed.sim_sgsimg.img (SGS Offline cmd file, deployable via CreateCHN)
Simulator   → PC sim of all three; SGS Netron viewer; dla_simulator on board takes `-m *.sim_sgsimg.img`
C2M stock blobs: NO `.sim` magic visible (encrypted), so direct equality to `_sgsimg.img` is UNKNOWN. Assume stock = encrypted/offline variant tied to `b03a7d4` + firmware `T_0.0.1_210525`. Cross-SDK load: assume NO until mismatch test.
CONFIDENCE: HIGH for toolchain shape; UNKNOWN for byte-equality to stock blobs
```

## 3. Sections / tensors / quantization metadata

Attempted: header bytes, magic, alignment, section scan, tensor/operator name search, quant metadata search.

```text
RESULT: none recovered. No tensor names, no operator names, no quant params, no input/output metadata in clear.
Alignment: blob sizes are 0x1000-multiples except road? d0 0x2b9000, v_a 0x1ea000, v_t 0x40000, p_r 0x189000, road 0x2fe000, tl 0x25000 — page-aligned, consistent with mmap/MMA load.
Version: `Model version: %s` string in libmi_ipu.so, but no version field located in blobs (encrypted).
Decryption: `m0` decrypts OFFSETS only (PROVEN). Blob payload decryption (if any) uses UNKNOWN key/path — `vehicle::GetKey` proven for m0, NOT proven for blobs. Do not claim blobs use same key.
CONFIDENCE: UNKNOWN for all inner fields (honest; needs runtime dump via `tensor%d_%s.bin/.txt` debug hooks + `GetInOutTensorDesc` on HW)
```

Stock debug hooks (future HW use, not static proof):

```text
adas strings: `%stensor%d_%s.bin`, `%stensor%d_%s.txt`, `vehicle::Cnn::DebugDumpOutput{,Float}`, `Sigmastar::MMAMemory::FromFile`
lib strings: `ipu_chn%u_network`, `ipu_chn%u_desc`, `map model failed`
METHOD on HW: set dump env/flag (if compiled in) or call GetInOutTensorDesc + GetOutputTensors after Invoke with known image, compare vs Simulator.
```

## 4. Per-model role mapping (required verdicts)

| Model | Size | Input | Output | Role | Format | Confidence |
|---|---|---|---|---|---|---|
| `d0` | 2.8MB | UNKNOWN | UNKNOWN | UNKNOWN (LIKELY vehicle/detection main by size + `vehicleWarning/Measure/TTC` correlation — NOT proof) | encrypted proprietary | UNKNOWN role / HIGH format |
| `v_a` | 1.9MB | UNKNOWN | UNKNOWN | UNKNOWN (do not guess `vehicle-attribute` from name) | same | UNKNOWN |
| `v_t` | 256KB | UNKNOWN | UNKNOWN | UNKNOWN (tiny; tracker/temporal/trigger all unproven) | same | UNKNOWN |
| `p_r` | 1.6MB | UNKNOWN | UNKNOWN | UNKNOWN (LIKELY pedestrian by `libPedDetect.so`+`C1PedRes` correlation — NOT proof) | same | UNKNOWN |
| `road` | 3.1MB | UNKNOWN | UNKNOWN | UNKNOWN (LIKELY road/lane by `lane_accelerator/postprocess`+`LDW` correlation — NOT proof) | same | UNKNOWN |
| `tl` | 148KB | UNKNOWN | UNKNOWN | UNKNOWN (LIKELY traffic-light by `TlrDetect/TlrCnnCls` correlation — NOT proof) | same | UNKNOWN |

Rule: filenames alone prove nothing. Input shapes, call sites, post-processing, labels, consumers all UNKNOWN statically (encrypted blobs hide dims). Recover on HW via `GetInOutTensorDesc` per channel + `TlrDetect`/lane/vehicle call-graph + runtime dump.

## 5. Tensor shapes / accelerator constraints from stock

```text
Shapes: UNKNOWN (all six). Cannot reveal IPU limits from sizes alone.
Counts: 6 models, ~10.1 MB total, 5.36 MB NPU buffer default, 10 Hz input cadence (`vehicle_run_freq=10`).
Invocations per frame: UNKNOWN (serial vs parallel, order, cadence all need `IPU_Statistic` + `ipu_log` + thread trace: VehicleRun/CameraLoop/VehicleAlgo threads).
Timing: UNKNOWN statically (see stack doc §7).
```

## 6. Compatibility: can vendor models run on C2M?

```text
Tied to: IPU generation + SDK/compiler version + chip revision + firmware ABI (PROVEN by `fw major/minor not matching`, `E_IPU_ERR_MISMATCH_MODEL`, `T_0.0.1_210525` checks).
Can a model compiled with another SDK run on C2M? Answer with evidence: NO evidence it can. Assume NO. Need exact `SGS_IPU_SDK` drop matching `sdk_commit.b03a7d4` + firmware `T_0.0.1_210525`.
CONFIDENCE: HIGH for tie-in; UNKNOWN for any specific cross-build (test: compile tiny classifier with candidate SDK → CreateCHN on HW → expect MISMATCH if wrong).
```

## 7. Tables

### Stock models (required)

```text
MODEL | SIZE | INPUT | OUTPUT | ROLE | FORMAT | CONFIDENCE
d0   | 2854912 | UNKNOWN | UNKNOWN | UNKNOWN (vehicle? unproven) | encrypted proprietary | UNKNOWN role / HIGH format
v_a  | 2007040 | UNKNOWN | UNKNOWN | UNKNOWN | same | UNKNOWN / HIGH
v_t  | 262144  | UNKNOWN | UNKNOWN | UNKNOWN | same | UNKNOWN / HIGH
p_r  | 1609728 | UNKNOWN | UNKNOWN | UNKNOWN | same | UNKNOWN / HIGH
road | 3137536 | UNKNOWN | UNKNOWN | UNKNOWN | same | UNKNOWN / HIGH
tl   | 151552  | UNKNOWN | UNKNOWN | UNKNOWN | same | UNKNOWN / HIGH
```

## 8. Next evidence (smallest)

```text
1. On HW: MI_IPU_GetInOutTensorDesc per stock channel (needs channel IDs from CreateCnn/InitIpu trace or /proc/mi_modules/mi_ipu/task_channel).
2. On HW: single Invoke + tensor dump (`tensor%d_%s.bin/.txt` hooks or manual GetOutputTensors dump) for one model with known input (e.g. lane ROI).
3. Host: obtain SGS_IPU_SDK matching b03a7d4 (NDA channel) → compile conv-only → compare header prefix vs stock `be2d6fe9...` (tells whether stock prefix is SGS container + encryption).
STOP if SDK unavailable: NATIVE_IPU_TOOLCHAIN_BLOCKED (do not fabricate).
```
