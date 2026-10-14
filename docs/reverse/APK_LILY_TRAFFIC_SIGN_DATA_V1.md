# Lily (com.sensornotes.xiaozhi) — nguồn data biển báo

APK: `Lily - AI Agent_3.8.1_APKPure.xapk` (178,419,837 bytes), version 3.8.1
(versionCode 38100), package `com.sensornotes.xiaozhi`, nhà phát triển
Sensor Notes Global. Tải từ CDN APKPure (data.winudf.com) 2026-10-14.

## TL;DR

Lily lấy data biển báo từ **4 nguồn**, xếp theo độ ưu tiên offline:

1. **Database biển Việt Nam tích hợp sẵn (offline)** — `assets/vnsigns/`:
   349 files, **28,551 điểm**, gồm R.420 (6,278), R.421 (6,430),
   biển tốc độ (15,343), P.125/P.130/P.131a. Format JSON gzip.
2. **OSM Overpass API (online)** — 4 server fallback, query biển/camera/
   tốc độ trong bán kính 900–1200m.
3. **Nhận diện on-device** — model TFLite `adas/vehicle_edl0.tflite` (4.5MB)
   + ML Kit OCR để đọc biển qua camera (chế độ dashcam).
4. **User report** — `SpeedReportPanel$SignTile` cho user báo biển.

## 1. Database vnsigns (offline, đáng chú ý nhất)

Vị trí: `assets/vnsigns/`, 349 files = 169 cặp `.bin` + `_pins.bin`.

### Format
- Tên file: `{floor(lat/0.5)}_{floor(lon/0.5)}` — lưới 0.5°×0.5° (~55km).
  VD: `17_209` = lat 8.5–9.0, lon 104.5–105.0 (Cà Mau/Mekong).
- Cả 2 loại đều là **gzip** chứa JSON array.

### `_pins.bin` — điểm biển báo
```json
{"y":8.85465,"g":104.81442,"t":"r420","v":0,"b":-1,"u":265}
```
- `y`/`g`: latitude/longitude.
- `t`: loại biển — `r420`, `r421`, `limit`, `p125`, `p130`, `p131a`.
- `v`: giá trị (km/h cho `limit`; 0 cho r420/r421).
- `b`: hướng biển (độ, -1 = không rõ).
- `u`: hướng áp dụng (độ 0–360).

### Thống kê toàn DB
| Loại | Số lượng | Ý nghĩa |
|------|----------|---------|
| r420 | 6,278 | R.420 bắt đầu khu đông dân cư |
| r421 | 6,430 | R.421 hết khu đông dân cư |
| limit | 15,343 | Biển tốc độ (50: 3629, 60: 3397, 80: 2838, 90: 1809, 40: 1309…) |
| p125 | 108 | P.125 |
| p130 | 121 | P.130 |
| p131a | 271 | P.131a |
| **Tổng** | **28,551** | |

### `.bin` — dữ liệu đường
JSON array các đoạn đường: `{"h":"primary","n":"Đường tỉnh 986",
"p":[[lat,lon],...]}` — polyline + tên đường tiếng Việt.

### Các DB Việt Nam khác (assets/)
- `vnhazard/` (113), `vnpark/` (109), `vnfuel/` (154), `vntoll/` (71),
  `vnrest/` (65), `vnev/` (36) — điểm POI Việt Nam.
- `traffic/` (31): `.dat` theo quốc gia + tỉnh VN
  (`cattien.dat`, `daklak.dat`, `dn.dat`, `hue.dat`, `cams.dat`…).

### Hiển thị
Layer MapLibre: `cgt-vnsigns`, `cgt-vnsigns-layer`.

## 2. OSM Overpass API (online)

4 server fallback (thử tuần tự khi lỗi, message tiếng Việt):
- `https://overpass-api.de/api/interpreter`
- `https://overpass.kumi.systems/api/interpreter`
- `https://overpass.private.coffee/api/interpreter`
- `https://maps.mail.ru/osm/tools/overpass/api/interpreter`

Queries (bán kính quanh vị trí):
- `way["maxspeed"]` (1200m), `node["highway"="speed_camera"]`,
  `node["highway"="traffic_signals"]`, `node["highway"="stop"]`,
  `node["traffic_calming"]`, `node["railway"="level_crossing"]`,
  `node["overtaking"="no"]`, `way["tunnel"="yes"]`, `way["toll"="yes"]`.
- `[out:json][timeout:12–60]`, `around:900` / `around:1200`.

## 3. ADAS on-device

- `assets/adas/vehicle_edl0.tflite` (4.5MB) — detect phương tiện.
- ML Kit OCR models — đọc chữ trên biển.
- `ui/carcam/CarCameraViewModel` — chế độ dashcam.
- `ui/traffic/TrafficCameraViewModel` — modes: nav/poi/signs/speed-limit/snap-to-road.
- `AdasOverlay`, `ADAS calibration`.
- Changelog ghi rõ: "built-in Vietnamese road signs" (biển báo Việt Nam
  tích hợp sẵn), "senyals vietnamites incorporats".

## 4. Cảnh báo bằng giọng nói

Templates TTS (tiếng Anh):
- `"Speed limit sign, {n} kilometers per hour"`
- `"The speed limit for this road is unknown."`
- `"Over the speed limit"`

## Map nền
- Tiles: `tiles.openfreemap.org` (vector OSM miễn phí).
- Cache: `mbgl-cache.db`, `mbgl-offline.db` (MapLibre).

## Ý nghĩa cho dự án C2M

1. **Database vnsigns là nguồn R.420/R.421 offline tốt nhất từng thấy** —
   12,708 điểm khu dân cư + 15,343 biển tốc độ, đã có tọa độ + hướng.
   Có thể convert sang format `signs.bin` cho c2m-warner.
2. Kiến trúc 4 lớp (offline DB → online Overpass → on-device AI → user report)
   là mẫu tham khảo tốt cho giải pháp của mình.
3. Format JSON gzip đơn giản, dễ parse, dễ tái sử dụng cho mục đích cá nhân.
