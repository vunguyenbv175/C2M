# EF-A06 — RoadIntelligence Interface + Host Preprocessing

## Nguyên tắc offline-first

C2M chạy được không cần phone/cloud. VietMap/VietMap LIVE chỉ là nguồn bổ sung.

```text
GPS ──┐
OSM compact DB (SQLite/R-tree, SD) ──┼──> OsmRoadProvider ──┐
camera TSR ──────────────────────────┤                       ├──> FuseSpeedLimit ──> DisplayState.speed_limit + Voice
VietMap API (online, cache) ─────────┼──> VietMapProvider ──┘
VIETMAP LIVE nav (BLE bridge V1) ────┴──> NavigationProvider ──> DisplayState.navigation
```

## Không parse PBF trên thiết bị

```text
Vietnam OSM PBF (host) -> tools/road/osm_preprocess.py -> vietnam_roads.sqlite
  bảng segments(id, min_lat,max_lat,min_lon,max_lon, maxspeed, road_class, oneway, name)
  index R-tree qua (min/max lat/lon) — file < 100MB mục tiêu V1 (chỉ quốc lộ + tỉnh lộ trước)
  -> copy vào SD -> OsmRoadProvider mmap/read-only query
```

`tools/road/osm_preprocess.py` V0 hiện: đặc tả schema + parser OSM XML nhỏ demo
+ sinh SQLite mẫu để test query/fusion trên host. PBF full VN để dành khi có
infra host (osmium + dung lượng).

## Speed-limit fusion (đã implement C++ + Python mirror)

```cpp
FuseSpeedLimit(camera, cam_conf, osm, osm_conf, vietmap, vm_conf)
```

Ưu tiên: `camera(>=0.6) > vietmap(>=0.6) > osm(>=0.4) > none`.
Output: `{limit_kmh, confidence, source, age_ms}` → `DisplayState.speed_limit_kmh`.

## VietMap / VIETMAP LIVE ranh giới

- `VietMap road/API data ≠ VIETMAP LIVE navigation protocol`. Tôn trọng license/cache,
  không scrape DB proprietary.
- V1 cho phép `VIETMAP LIVE -> BLE -> ESP32-C3 bridge -> USB/UART -> C2M`
  nếu Bluetooth native khó. `NavigationProvider` nhận arrow/distance/road_name trừu tượng,
  M4Adapter + VoiceManager render, không parse BLE raw ngoài bridge driver.

## Gate

- Offline OsmRoadProvider query < 20ms trên host, DB mẫu qua test.
- Fusion unit-test pass 4 nguồn + timeout.
- Không bundle DB lớn vào repo (chỉ script + schema + sample).
