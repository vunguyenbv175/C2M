# Báo cáo Sprint 1 — C2M Enhanced nền tảng (2026-09-11)

## WHAT WAS BUILT (đã xây gì)

EF-A01 — StockADASProvider:

```text
docs/design/STOCK_ADAS_PROVIDER.md
include/c2m/adas/adas_state.hpp
include/c2m/adas/i_adas_provider.hpp
include/c2m/adas/stock_adas_provider.hpp   # NormalizeStock() pure, test được không cần hardware
include/c2m/adas/mock_adas_provider.hpp    # scenario idle/lead/fcw/ldw/ped
tools/m4/normalize_adas.py                 # mirror Python của C++
tools/m4/test_normalize_adas.py
```

EF-A02 — M4Adapter + guard:

```text
docs/design/M4_ADAPTER_DESIGN.md
include/c2m/display/m4_adapter.hpp         # PlanMessages() L2/L3 gate
tools/m4/replay_guard.py                   # allowlist L2 vô hại
```

EF-A03 — DisplayState:

```text
docs/design/DISPLAY_STATE_API.md
include/c2m/display/display_state.hpp      # BuildFromAdas()
include/c2m/display/i_display_adapter.hpp
include/c2m/display/mock_display_adapter.hpp
```

EF-A04 — c2m-enhance core read-only:

```text
docs/design/ENHANCE_CORE_DESIGN.md
include/c2m/core/event_bus.hpp
include/c2m/core/provider_registry.hpp
include/c2m/core/c2m_enhance.hpp           # EnhanceCore::Tick()
include/c2m/diag/diagnostics.hpp
include/c2m/tpms/tpms_state.hpp            # interface trước, gateway sau
CMakeLists.txt + tests/smoke_enhance.cpp
```

EF-A05 — Web Admin V0:

```text
docs/design/WEB_ADMIN_V0_DESIGN.md
src/web/web_admin.py  # GET / /status /diagnostics, --scenario idle|lead|fcw|ldw|ped
```

EF-A06 — RoadIntelligence:

```text
docs/design/ROAD_INTELLIGENCE_DESIGN.md
include/c2m/road/road_provider.hpp         # IRoadProvider + FuseSpeedLimit
tools/road/osm_preprocess.py               # schema SQLite + sample DB + fusion smoke
```

## WHAT WAS PROVEN (đã chứng minh)

- `tools/m4/test_protocol.py`: synthetic outer/inner MessagePack — OK (sau `pip install msgpack`).
- `tools/m4/test_normalize_adas.py`: crucial-pick, fcw/pcw/ldw mapping, stale/timeout, A vs C class — OK.
- `tools/road/osm_preprocess.py`: sample SQLite 2 rows + fusion 4 nhánh camera/vietmap/osm/none — OK.
- `tools/m4/replay_guard.py`: `DispBrightSet` ALLOW-L2, `AdasStatus`/`vehicleWarning` DENY — OK.
- `src/web/web_admin.py --scenario fcw`: `/status` trả fcw active + lead 6.5m/ttc 1.1, `/diagnostics` trả mock — OK (curl kiểm chứng).
- C++ là header-only C++17, không phụ thuộc msgpack/socket; cần build Linux để chạy `smoke_enhance` (máy dev hiện tại không có g++).

## WHAT REMAINS UNKNOWN (chưa biết)

- `UNKNOWN`: WS path có phải `/`, `source` của AdasScreenService, interface vật lý M4 (cấm đoán `usb0`).
- `UNKNOWN`: unit `longitude_dist/ttc/headway`, enum `warning_level/fcw/deviate_state/label/type`.
- `UNKNOWN`: `bird_view_poly_coeff` format; TSR có enable runtime không.
- `UNKNOWN`: M4 nối trực tiếp :26012/:8080 hay qua proxy.

## STOCK COMPATIBILITY IMPACT (ảnh hưởng stock)

- Không đụng stock: toàn bộ sprint 1 là header + Python host-side + Web port 8099 riêng.
- Không chiếm 8080/26012, không gửi subscribe tới thiết bị, không replay/injection.
- `M4Adapter` mặc định `allow_semantic_injection=false`; `EnhanceCore mode=read-only`.
- Kết luận: rủi ro stock = 0 ở sprint này.

## PERFORMANCE IMPACT

- Header-only, không thread mới, không allocate vòng lặp nóng ngoài vector nhỏ.
- Web V0 + normalize Python chỉ chạy trên máy dev, không chạy trên C2M ở sprint này.
- Bản nhúng sau này phải giữ Tick ≤ 200ms, log ring 512 events, không transcode video.

## RISKS (rủi ro)

- Thiếu toolchain C++ trên máy dev → chưa biên dịch `smoke_enhance.cpp` tại chỗ.
- Nếu hiểu sai unit/enum stock, Display/Voice V1 sẽ hiển thị sai → V1 phải ghi "unit chưa xác minh + kèm raw".
- L2 replay dù vô hại vẫn cần stationary + owner approve + guard.

## NEXT HIGHEST-VALUE TASK (việc giá trị nhất tiếp theo)

1. P1: chạy `collect_baseline.sh en_good_m4_off/on` trên EN tốt → `discover_transport.py` → chốt L0 transport (không đoán).
2. P1: `libflow_subscriber.py <C2M-IP>` trên bàn test tĩnh → capture 4 key stock → xác nhận L1 decode + unit/enum.
3. P2: `FuseSpeedLimit` nối `OsmRoadProvider` SQLite thật (tỉnh mẫu) + GPS NMEA từ cardv.
4. P3: `c2m-web` bản C++ nhúng khi Web V0 ổn định, giữ nguyên JSON schema.

## Phân loại bằng chứng

```text
CONFIRMED: schema 4 key/topic stock, JSON template cardv, raw_adas writer ổn định, 6 model blob identical (kế thừa reverse trước).
HIGH-CONFIDENCE: libflow outer/subscribe shape, port 26012/8080, dual-path adas+cardv.
HYPOTHESIS: M4 nghe trực tiếp cả 2 port hoặc qua proxy.
UNKNOWN: transport vật lý, URL path, source string, unit/enum, TSR enable.
```
