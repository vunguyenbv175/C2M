# EF-A01 — StockADASProvider Design

**Status:** design V1 — implementation scaffold
**Baseline:** EN 2023-08-03 = GOLDEN, VI 2023-09-20 = donor/reference
**Nguồn stock:** `docs/reverse/M4_STATIC_PROTOCOL_V1.md`, `docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md`, `docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md`

## 1. Mục tiêu

Chuẩn hoá mọi output stock ADAS thành một `AdasState` duy nhất, để các tầng trên
(RoadIntelligence, DisplayState/M4Adapter, VoiceManager, Web Admin, black-box)
không bao giờ parse trực tiếp MessagePack / JSON stock.

```text
libflow :26012 (vehicle/ped/lane) ──┐
cardv :8080 JSON (AdasStatus/GPS) ──┼──> StockADASProvider ──> AdasState ──> DisplayState / Voice / Web / Logger
raw_adas ringbuf (nếu quan sát được) ┘
```

Nguyên tắc:

```text
REUSE-FIRST: không thay model stock nếu chưa benchmark
READ-ONLY-FIRST: provider chỉ subscribe/passive, không inject cảnh báo
STOCK-COMPAT: crash của provider không được làm dừng ghi hình stock
```

## 2. Nguồn stock đã CONFIRMED (không suy đoán)

### 2.1 libflow outer (HIGH-CONFIDENCE static, cần runtime xác nhận path/interface)

```text
WebSocket binary -> MessagePack {time, source, topic, data=BIN(inner)}
subscribe frame {source:<client>, topic:"subscribe", data:<topic>}
topics: vehicle | ped | lane
```

### 2.2 Inner envelopes (CONFIRMED key/topic)

| Topic | key | Shape |
|---|---|---|
| `vehicle` | `vehicleWarning` | map 7 keys |
| `vehicle` | `vehicleMeasure` | array of map 8 keys |
| `ped` | `pedestrians` | array of map 8 keys |
| `lane` | `laneWarningRes` | map 4 keys |

Chi tiết schema xem `M4_STATIC_PROTOCOL_V1.md` §3–6.
Tooling hiện có: `tools/m4/libflow_protocol.py`, `libflow_subscriber.py`, `decode_payload.py`.

### 2.3 cardv :8080 JSON (CONFIRMED template, HIGH-CONFIDENCE port 8080)

```text
{"type":3000,"uuid":"AdasStatus","status":...}
{"type":3001,"uuid":"HeavyCalibStatus","status":"..."}
{"type":1600,"uuid":"GPSLevel","level":%d}
{"type":1601,"uuid":"GPSSpeed","speed":%d}   # VI-only, EN không có
```

### 2.4 raw_adas ringbuf (CONFIRMED writer contract ổn định EN vs VI)

```text
CRingBuf("fortest","raw_adas",0x400,2,0,0)
RequestWriteFrame(...,0,0x48,1) / CommitWrite
send() 219 insns identical, adas_minieye_send_frame_task() 874 insns identical
```

→ VI không viết lại writer; lỗi runtime (nếu có) nằm ở validation/metadata,
config, kernel/media, hoặc output path. Provider thiết kế để chịu được
"inference sống nhưng output chết" (class E/F trong `ADAS_FAILURE_CLASSIFICATION.md`).

## 3. AdasState chuẩn hoá (C++: `include/c2m/adas/adas_state.hpp`)

```cpp
struct AdasState {
  uint64_t timestamp_ms = 0;
  uint64_t frame_id = 0;
  bool stale = true;               // true nếu quá hạn timeout
  AdasHealth health = {};          // A–F classification + process liveness

  LaneState lane;
  std::vector<VehicleObject> vehicles;
  std::vector<PedestrianObject> pedestrians;

  std::optional<float> lead_distance_m;
  std::optional<float> ttc_s;
  std::optional<int> detected_speed_limit; // TSR sau này, hiện để trống

  WarningState fcw, ldw, pcw;
  AdasStatus cardv_status = {};    // từ :8080 AdasStatus/CalibStatus
};
```

Chi tiết field:

- `VehicleObject`: `id, vehicle_class, width_m?, long_dist_m, lat_dist_m, ttc_s, is_crucial, is_second_crucial, headway_s?, warning_level?`
- `PedestrianObject`: `id, world_x, world_y, is_key, is_danger, ttc_m?, ttc_s?, have_bike`
- `LaneState`: `lanelines[], deviate_state, turn_radius, turn_frequently`
- `WarningState`: `{active:bool, level:int, source: STOCK|FUSED|...}`
- Không gán unit/enum khi stock chưa chứng minh runtime. Giữ đúng spelling vendor (`longitude_dist`).

## 4. Interface

```cpp
class IAdasProvider {
 public:
  virtual ~IAdasProvider() = default;
  virtual std::string Name() const = 0;
  virtual AdasState Poll() = 0;              // non-blocking, trả stale nếu timeout
  virtual bool Healthy() const = 0;
};

StockADASProvider(libflow_endpoint, cardv_endpoint, config)
MockADASProvider(scenario_script)   // cho host-sim + Web V0 + test
```

`StockADASProvider` gom 2 subscriber độc lập:

```text
LibflowSubscriber (:26012) -> inner decoder -> partial state
CardvStatusSubscriber (:8080) -> AdasStatus/GPS -> partial state
Fusion (trong provider) -> AdasState + stale detection + health A–F
```

Timeout gợi ý V1: `stale_after_ms = 500`, `health` suy từ tuổi frame + socket state +
`AdasStatus` (nếu có).

## 5. Mapping stock -> AdasState (V1, conservative)

- `vehicle/vehicleMeasure[is_crucial] ` → `lead_distance_m = longitude_dist`, `ttc_s = ttc` của object crucial nhất. Không đổi unit; để float gốc, tầng display làm tròn.
- `vehicle/vehicleWarning` → `fcw.active = (fcw!=0 || warning_level!=0)`, `headway` → `vehicles[id].headway`. Giữ nguyên int gốc trong `raw` để debug.
- `ped/pedestrians[is_danger||is_key]` → `pcw.active`. `ttc`, `ttc_m` giữ cả hai, không gộp.
- `lane/laneWarningRes.ldw_info.deviate_state` → `ldw.active = (deviate_state!=0)`.
- `cardv AdasStatus/HeavyCalibStatus` → `cardv_status.calibrated/adason`. Nếu mất :8080, không đánh stale toàn bộ AdasState, chỉ đánh `cardv_status.stale=true`.
- Mọi frame gốc giữ lại trong `AdasDiagnostics.last_raw_keys` (không log full payload liên tục để tiết kiệm CPU/flash).

## 6. Không làm trong V1

- Không decode `bird_view_poly_coeff` thành geometry nếu chưa có sample runtime.
- Không suy đoán enum `warning_level/label/type/deviate_state`.
- Không điều khiển stock (`unsubscribe` chỉ khi shutdown, không send warning).
- Không thay model (YOLOX/UFLD/ByteTrack để dành P14, sau benchmark).

## 7. Test/host-sim

- `tools/m4/test_protocol.py` (có sẵn): smoke outer/inner.
- Mới: `tools/m4/test_normalize_adas.py`: pack synthetic `vehicleWarning+vehicleMeasure+pedestrians+laneWarningRes` → `normalize_adas.normalize(inner)` → assert `AdasState` dict đúng (crucial-pick, pcw/ldw/fcw mapping, stale).
- `MockADASProvider` (C++ + Python mirror `src/enhance/mock_provider.py`) phát scenario `idle/lead/fcw/ldw/ped` cho Web V0 và M4Adapter test mà không cần hardware.

## 8. Rủi ro + UNKNOWN

- `UNKNOWN`: WebSocket URL path có phải `/` không; `source` string của `AdasScreenService`; interface vật lý tới M4.
- `HYPOTHESIS`: M4 có thể nghe trực tiếp :26012 hoặc qua proxy; provider phải chạy được cả khi M4 online/offline.
- `RISK`: unit distance/TTC chưa xác minh → display/voice V1 phải ghi rõ "unit chưa xác minh, hiển thị kèm raw".
