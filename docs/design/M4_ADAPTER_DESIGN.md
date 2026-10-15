# EF-A02 — M4 Adapter Design (Level 0–3)

**Status:** design V1 + passive tooling cải tiến
**Nguồn:** `docs/reverse/M4_STATIC_PROTOCOL_V1.md`, `docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md`, `tools/m4/*`

## 1. Mục tiêu

Tái dùng màn M4 stock qua semantic injection, không thay màn hình, không sửa firmware M4.

```text
StockADASProvider ──┐
RoadIntelligence ───┼──> DisplayState ──> M4Adapter ──> stock M4 (ưu tiên semantic reuse)
VietMap/NAV ────────┤
TPMS ───────────────┤
System Health ──────┘
```

Mốc:

```text
L0 transport identified (runtime, so sánh M4 OFF vs ON)
L1 passive decoder (tools/m4, chỉ subscribe/passive pcap)
L2 safe replay trạng thái stock vô hại (vd. cùng brightness/storage status)
L3 semantic injection (speed-limit fusion, nav arrow, TPMS, cảnh báo đã fusion)
L4 custom UI (chỉ nếu L3 xong và còn giá trị)
```

L3 là định nghĩa thành công sản phẩm. Không làm L4 sớm.

## 2. Kiến trúc dual-path (HIGH-CONFIDENCE static, chưa runtime-proven)

```text
adas --libflow/MP vehicle|ped|lane :26012--> [M4 hoặc proxy hoặc app-debug] --\
cardv --lws/JSON minieye-websocket :8080--> [M4 hoặc proxy hoặc app-debug] ----+--> M4?
```

3 giả thuyết vẫn mở (xem M4_STATIC_PROTOCOL_V1 §8):

1. M4 nối trực tiếp cả 2 port.
2. Có proxy nội bộ.
3. Một port là app/debug, một port là M4.

→ M4Adapter **không được hardcode giả thuyết**. Adapter nhận `DisplayState`
trừu tượng, còn transport mapping (`:26012` vs `:8080` vs proxy) cấu hình được
và xác nhận bằng `discover_transport.py` + pcap.

## 3. Ranh giới module

```text
include/c2m/display/display_state.hpp   # provider-neutral, không biết M4
include/c2m/display/i_display_adapter.hpp
include/c2m/display/m4_adapter.hpp      # DUY NHẤT được biết packet M4/libflow/cardv JSON
include/c2m/display/mock_display_adapter.hpp
src/display/m4_adapter.cpp              # encode DisplayState -> stock schema
tools/m4/*                              # passive decoder + probe (host)
```

Quy tắc cứng: code ngoài `M4Adapter` cấm include struct packet thô
(`C1VehicleWarning`, JSON template `DispBrightSet`, ...). Vi phạm = reject review.

## 4. Encode DisplayState -> stock schema (L3)

Ưu tiên tái dùng schema stock đã CONFIRMED, không đẻ protocol mới:

| DisplayState field | Stock target | Ghi chú an toàn |
|---|---|---|
| `warning.fcw/pcw/ldw` | `vehicle/vehicleWarning`, `lane/laneWarningRes`, `pedWarning` | V1 chỉ forward trạng thái đã fusion từ StockADASProvider; không tự sinh FCW khi chưa benchmark |
| Vehicle speed / speed limit | Native `GPSSpeed` is vehicle speed only; no verified stock sign/limit widget mapping | Do not send a sign limit as vehicle speed; 3D speed/sign rendering remains unproved |
| `navigation.arrow/distance` | No verified native target; retain separate Web presentation | `ScreenModeSet/theme` is day/night, not navigation or 2D/3D layout; never repurpose warning slots |
| `tpms` | No verified native target | Do not put unrelated values into stock storage/warning fields |
| `system` | Only proven stock fields with their actual meanings | `RecordVoice` remains DENY; system classification does not override policy |

L2 replay is a future gate only: exact harmless captured values, verified
outbound path and receiver, stationary owner approval, and canonical policy
checks are required. Connecting a client to cardv is not a verified outbound
relay and can steal the native M4 stream.

## 5. Passive tooling (đã có + cải tiến sprint này)

Có sẵn:

```text
discover_transport.py  # OFF vs ON, rank interface/USB/ARP/socket
libflow_protocol.py    # outer/inner decode + schema check
libflow_subscriber.py  # read-only subscribe vehicle,ped,lane
decode_payload.py      # decode 1 frame offline
cardv_status_client.py # observer :8080; ONLY with M4 disconnected (single-client stream)
```

Cải tiến sprint 1 (đã implement):

```text
tools/m4/normalize_adas.py       # inner -> AdasState dict (mirror C++ StockADASProvider)
tools/m4/test_normalize_adas.py  # synthetic test cho mapping V1
tools/m4/replay_guard.py         # check pcap/frame log trước khi replay: chỉ cho replay key vô hại
```

`replay_guard.py` enforce allowlist L2:

```text
ALLOW = {DispBrightSet, StorageStatus, DisplayMode, ClientConn}
DENY  = {vehicleWarning, vehicleMeasure, pedestrians, laneWarningRes, AdasStatus}
```

Mọi replay L2/L3 phải qua guard + stationary + owner approve.

## 6. UNKNOWN cần runtime

- URL path WS (`/`?), `source` của AdasScreenService, interface vật lý (đừng đoán `usb0`).
- Enum số của `warning_level/fcw/deviate_state/label/type`, unit của `longitude_dist/ttc/headway`.
- M4 render nvai trò gì vs cardv render (gate E trong CURRENT_ARCHITECTURE).

## 7. Tiêu chí nghiệm thu

- L0: `discover_transport.py` chỉ ra interface + peer + socket owner khi M4 ON.
- L1: `libflow_subscriber.py` + `decode_payload.py` decode 4 key stock không warning schema trên EN tốt.
- L2: replay 1 JSON vô hại qua guard, M4 không đổi trạng thái bất thường, log đầy đủ.
- L3: BLOCKED (Gate F) — không encoder, không injection cho tới khi L0/L1 proven
  bằng capture thật. `allow_semantic_injection` đã gỡ bỏ để khỏi gây hiểu lầm.
