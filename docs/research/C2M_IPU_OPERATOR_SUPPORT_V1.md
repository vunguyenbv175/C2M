# C2M IPU Operator Support V1 — Quant, Layout, Compat, Substitutions

**Status:** RESEARCH ONLY. **Date:** 2026-09-11.
**Rule:** no TOPS/RAM/op invented. Family-level docs are MEDIUM at best; chip-exact needs SDK drop + `dla_simulator` proof.

## 1. Quantization

| Format | Verdict | Evidence | Confidence |
|---|---|---|---|
| INT8 | LIKELY SUPPORTED (quantized deploy is the norm) | DLA tool doc: `Calibrator ... quantize SGS Float to 8bit/16bit fixed`; lib `eElmFormat` + `INT8/INT16` handling; stock blobs high-entropy (quantized+encrypted) | MEDIUM (chip-exact proof needs _fixed.sim + board run) |
| UINT8 | UNKNOWN (likely as image input, not tensor) | `input_formats` includes `RAWDATA_U8_*`; image path is uint8 | LOW |
| INT16 | LIKELY (converter + runtime path) | `8bit/16bit` doc; lib `The output data isn't int16 type while ... transformed to float, eElmFormat=%d, bFP32Out=%d`; `_MI_IPU_GetTensorUnitDataSize: INT16→short, INT32→int, INT8→char, FP32→float` (demo) | MEDIUM |
| FP16 | UNKNOWN | No FP16 string in lib/adas; doc does not state FP16 | UNKNOWN (do not claim) |
| FP32 | SUPPORTED as I/O (not necessarily compute) | Demo casts output to `float*`, `GetTopN(float[])`, `bFP32Out` flag; `input_config` dequant | MEDIUM (compute is fixed-point; FP32 is dequantized edge) |
| Symmetric/asymmetric, per-tensor/per-channel, QAT/PTQ, mixed | UNKNOWN | Tool doc §4.3 not fetched; no local evidence | UNKNOWN |
| Calibration dataset | REQUIRED (rep set, e.g. `ilsvrc2012_calibration_set32`, `coco2017_calibration_set32`) | Calibrator `-i <images> -c Classification|Detection` | HIGH (flow), UNKNOWN (C2M rep-set recipe) |

Guidance (from prior hardware study, not new proof): FP16 ~free if present; INT8-PTQ ok for large boxes/binary-seg; small/distant bikes, sign color, TL state, lane-regression jitter need heads-FP/QAT/two-stage. Keep heads dequantized (`dequantizations=TRUE`) first.

## 2. Tensor layout / pixel formats

| Layout | Verdict | Evidence | Confidence |
|---|---|---|---|
| NCHW / NHWC | BOTH appear (converter uses NHWC `1,H,W,C`; runtime `TensorShape[1]=H,[2]=W,[3]=C` in demo; API has `eLayoutType/bOutputNCHW`) | ConvertTool `--input_shapes 1,300,300,3 (NHWC)`; demo `shape[1..3]`; API rev adds `eLayoutType` | MEDIUM |
| RGB / BGR | SUPPORTED (model input requirement) | `dla_classify` requires `RGB or BGR`; `dla_detect` same; `input_config training_input_formats/input_formats ∈ RGB,BGR,RGBA,BGRA`; adas `GetPixelFormat(ELEMENT_FORMAT)`, `Bgr2YuvNv12`, `COLOR_BGR2RGB` | HIGH |
| RGBA / BGRA | SUPPORTED | input_config list; `dla_simulator -f BGRA` (note: ARGB→BGRA reversed on SSTAR) | MEDIUM-HIGH |
| YUV / NV12 / NV21 | SUPPORTED as input_format; stock path is YUV | `input_formats=YUV_NV12`; adas `InputYuv`, `ImageYuvAddress`, `GenerateGrayMat`, `DumpYuv2jpg`, `RingbufImageConsumer::Consume(ImageYuvAddress)` | HIGH (presence), MEDIUM (exact C2M tensor format) |
| GRAY | SUPPORTED (newer) | API rev 02-2022 adds `MI_IPU_FORMAT_GRAY` | MEDIUM |
| RAWDATA_S16/U8 | SUPPORTED (bypass) | input_config list; demo `RAWDATA` file-input branch (`s32AlignedBufSize` length check) | MEDIUM |

Stock preprocessing (traced, HIGH unless noted):

```text
raw_adas (1920x1440 YUV, ringbuf_vehicle) → RingbufReader::GetFrame → Ringbuf/NonblockImageBufferedConsumer::Consume(ImageYuvAddress) → vehicle::ImageResizer::Resize (default SCL StretchBuf; cpu_resize=false) / CpuResize (OpenCV cv::resize fallback) → vehicle::Cnn::InputYuv / CnnDetect::SetInput(FrameMsg, ROI) → IPU Invoke
Source pixel: YUV420 (ESTIMATED from 4.15MB/frame math; format CONFIRMED as YUV family, exact NV12/NV21 UNKNOWN)
Target tensor: BGR/RGB or YUV_NV12 per input_config (UNKNOWN for stock; GetPixelFormat mapping UNKNOWN statically)
Resize: HW via MI_SCL_StretchBuf (PROVEN import + `failed` log + mul_resize.cpp path); CPU via cv::resize + Bgr2YuvNv12 (PROVEN symbols)
Mean/std/channel-swap/quant: FUSED in model via input_config (family doc) — stock values UNKNOWN
Stride/alignment: `s32AlignedBufSize`, `u32InputWidth/HeightAlignment`, `c_align<4 neon` log, `pitch alignment error` (PROVEN strings; values UNKNOWN)
```

## 3. Operators (critical for model choice)

No chip-exact op list in hand. Table below = **family-level bound** (Pudding DLA §11 headings exist but body not fetched; Caffe/TF op names from doc TOC + CSDN/SSD examples + old-IPU risk from prior study). Every row needs `Compiler` proof.

```text
OP | SUPPORTED | EVIDENCE | RISK
Conv2D (1x1/3x3/5x5/7x7, s1/s2) | LIKELY | DLA docs + SSD/MobileNet examples + universal | LOW
DepthwiseConv (mult 1) | LIKELY | MobileNetV2 example converts | LOW-MED
PointwiseConv | LIKELY | same | LOW
BatchNorm/Scale/Bias (folded) | LIKELY (fold to Conv) | ConvertTool lossless-opt claim | LOW (fold first)
ReLU / ReLU6 | LIKELY | canonical | LOW
LeakyReLU / PReLU | PARTIAL | family IPUs often support w/ slope | MEDIUM
SiLU/Swish/Mish/HardSwish | UNKNOWN (likely UNSUPPORTED on 2022 IPU) | no evidence; many old IPUs lack LUT | MEDIUM-HIGH (SiLU→ReLU retrain)
Sigmoid (as gate) | PARTIAL | SSD examples | MEDIUM
Softmax (classifier tail / DFL) | PARTIAL (classifier ok, DFL-head risky) | lib FP32-out path; DFL = reshape+softmax+matmul | MEDIUM-HIGH for DFL
MaxPool/AvgPool/GlobalPool (2x2/3x3) | LIKELY | canonical | LOW
ResizeNearest (fixed 2x) | LIKELY | seg needs nearest | LOW-MED
ResizeBilinear/Upsample | PARTIAL | seg risk | MEDIUM (force nearest)
Concat/Add/Mul (2-input) | LIKELY | canonical | LOW-MED
FC/InnerProduct (after GAP/Flatten) | LIKELY | classifier demo | LOW
Reshape/Transpose/Slice/Split/Pad/Clip | PARTIAL | shape-inference limits | LOW-MED (fix layout/static)
Deconvolution | PARTIAL | seg | MEDIUM
Detection head (plain regression) | LIKELY | SSD concat_net pattern | LOW-MED
Box-decode + NMS | CPU FALLBACK (custom TFLite postprocess nodes) | tool doc §8 `TFLite_Detection_NMS`, `PostProcess_Unpack`, `buildBoxDecoding` | HIGH on-IPU (export raw boxes+scores, CPU NMS ≤500×8)
LayerNorm/GroupNorm/InstanceNorm | LIKELY UNSUPPORTED | no evidence; transformer-era | HIGH (use BN-only)
MatMul (attention/QKV) / Attention / Transformer | LIKELY UNSUPPORTED | no evidence | HIGH (never use)
GridSample / DeformConv / ROIGather | LIKELY UNSUPPORTED | CLRNet/CondLane rejected for these | HIGH
Dynamic shapes / Loop / If / TopK+Gather in-graph | UNSUPPORTED | static-shape toolchain (`--input_shapes` fixed, `DLA SDK对模型的限制`) | HIGH (static 1x3xHxW only)
Focus (slice+concat) | LIKELY UNSUPPORTED | v5 Focus pain | MEDIUM (use stride-conv backbones)
SPPF/ELAN/CSP | PARTIAL | v7-tiny MED | MEDIUM
```

Static-shape restrictions (PROVEN pattern): `--input_shapes` fixed at convert; `Simulator` static; `DLA SDK对模型的限制` section exists; stock `ImageResizer dest_size unexpected!` log. Assume **static 1×C×H×W only**, no dynamic batch/HW, no control-flow.

Input resolution/model-size limits: UNKNOWN chip-exact. Stock hints: full 1920×1440 never to NN (always resized); demo 299/300/480×800; `input or output buffer depth > max` + `private pool` + `5.36MB` cap suggest small-ROI practice (416×256–640×360 per prior study, UNPROVEN until bench).

## 4. Candidate modern models (required table; feasibility = conversion+compute, not accuracy)

Prior shortlist reused (`C2M_AI_ADAS_*`); operator risk updated for old-IPU bound above. No weights converted here.

```text
MODEL | TASK | OPERATOR RISK | QUANT | CONVERSION RISK | C2M FEASIBILITY
YOLOX-Nano-416-ReLU | det | LOW (ReLU-swap, no DFL/Focus) | PTQ ok | LOW | HIGH (baseline)
NanoDet-Plus-m-320/416 | det | LOW (ShuffleNetV2+GhostPAN) | PTQ ok (~1.2MB INT8) | LOW | HIGH (ultra-light co-winner)
PP-PicoDet-S-320/416 (+NPU variant) | det | LOW | PTQ ok | LOW-MED (Paddle→ONNX friction) | HIGH (co-winner if Paddle ok)
YOLOv6-N-ReLU-RepOpt-416/512 | det | LOW (ReLU+RepOpt) / MED (SiLU+DFL) | RepOpt PTQ best story | LOW (ReLU) | HIGH (runner-up)
YOLOv10-N-512/640 (NMS-free) | det | MED (SiLU, NMS-free saves CPU) | QAT likely | MEDIUM | MARGINAL (quality pick if SiLU LUT proven)
YOLOv8n/11n-512/640 | det | MED-HIGH (SiLU+DFL+C2PSA for 11) | PTQ -1–2, QAT for DFL | MEDIUM-HIGH | MARGINAL
YOLOv5n/s, v7-tiny | det | MED (Focus/SiLU/Leaky/E-ELAN) | fixable | MEDIUM | MEDIUM (no advantage vs above)
YOLOv9t/s, RT-DETR, YOLO-World | det | HIGH (GELAN/attn/CLIP) | no recipe | HIGH | NOT PRACTICAL (reject first)
UFLDv2-R18-800x320-ROI | lane | LOW (row/col classifier, no deform) | PTQ ok | LOW | HIGH (lane winner)
LaneATT-R18 | lane | MED (anchor-gather+NMS port) | PTQ | MEDIUM | MEDIUM (runner-up)
CLRNet/CondLane/YOLOPv2/Hybrid | lane/multi | HIGH (ROIGather/bilinear/cond-conv/SiLU) | — | HIGH | NOT PRACTICAL (reject on-device)
Fast-SCNN-320x192–512x288-ROI | seg fallback | LOW (depthwise+nearest) | PTQ | LOW | MARGINAL (one only, low-Hz)
DDRNet-23-slim / PIDNet-S | seg | LOW-MED | PTQ | LOW-MED | MARGINAL (quality alts)
MobileNetV2 classifier-224 | smoke | LOW (Conv/ReLU/Pool/FC) | PTQ trivial | LOW | SMOKE ONLY (not ADAS)
EfficientNet-Lite0-48/64-crop | sign/TL classifier | LOW (ReLU6, no SE/hard-swish) | PTQ -0.7% | LOW | HIGH (cascade only, K≤3)
```

## 5. Substitution plan (prefer naturally-compatible)

```text
SiLU/Swish/Mish/HardSwish → ReLU/ReLU6 + retrain (proof: ReLU variants of v6/Nano exist)
DFL (reshape+softmax+matmul) → plain anchor regression + CPU decode (proof: SSD concat_net pattern; YOLOX-Nano has no DFL)
LayerNorm/GroupNorm → BatchNorm-only backbone (proof: MobileNetV2/ShuffleNetV2)
Dynamic resize/bilinear → static nearest fixed-2x (proof: Fast-SCNN nearest)
GridSample/Deform/Attention/Focus → remove (choose UFLDv2/NanoDet/PicoDet/stride-conv backbones that never had them)
In-graph NMS/TopK/Gather → export raw boxes+scores, CPU NMS (proof: tool §8 custom NMS nodes + CPU budget ≤500 boxes)
Transformer/RT-DETR/YOLO-World → reject (no edge path)
```

## 6. Architecture recommendation

Favor **MobileNetV2/V3-ReLU, ShuffleNetV2, GhostNet, CSP-lite, depthwise CNN, simple FPN, anchor-based raw-output detection** over transformer/DFL-heavy nets. Reason: 2022-era IPU + Caffe/TF converter lineage supports Conv/BN/ReLU/Pool/Concat/Add/FC + CPU NMS; everything else needs per-op Compiler proof that does not yet exist. Evidence: converter framework list (no ONNX/transformer), SSD postprocess pattern, `CaffeModelConfig` in adas, MobileNetV2/SSD walkthroughs.
