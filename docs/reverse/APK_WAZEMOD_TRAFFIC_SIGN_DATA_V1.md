# Waze Mod (wazemod.io.vn) — nguồn data biển báo

APK: `wazemod.apk` (165,600,835 bytes), Waze 5.24.5.0 (versionCode 1030732),
package `com.waze`. Tải trực tiếp từ https://wazemod.io.vn/api/download/cmv5hgw2h01zu01mzicdp2av6 (2026-10-14).

## Kết luận: Waze KHÔNG có "database biển báo" riêng

Dữ liệu biển báo (chủ yếu là giới hạn tốc độ) trong Waze đến từ 3 nguồn,
tất cả đều gắn với bản đồ chứ không phải DB biển độc lập:

### 1. Map tiles vector (nguồn chính)
- Giới hạn tốc độ là **thuộc tính của road segment** trong vector tiles:
  `setSegmentSpeedLimitKmh`, `getConfigMinSegmentSpeedLimitKmh`.
- Tiles v3 tải từ URL do server config (`CONFIG_VALUE_DOWNLOAD_TILES_V3_URL`).
- Dữ liệu do cộng đồng Waze Map Editor vẽ/sửa (crowdsource), build thành tiles.
- Public status: `https://storage.googleapis.com/waze-tile-build-public/current-build/intl-status.json`

### 2. Real-time server
- `https://rt.waze.com/rtserver/distrib` — traffic, cảnh báo, hazard realtime.
- Cảnh báo giảm tốc độ: `SPEED_LIMIT_DECREASE` / `ALERT_TITLE_SPEED_LIMIT_DECREASE`.

### 3. User report (crowdsource đầu vào)
- `com.waze.gw.SpeedReportPanel$SignTile` — UI cho user báo biển tốc độ.
- Reports → server → editor duyệt → vào map tiles.

## Phần mod thêm (wazemod)
- API riêng: `com.wazemod.api.IWazeModData`, `IWazeModListener`.
- Hosts: `wazemod.io.vn`, `wazemod.chisadin.id.vn`.
- `wazemod_custom_alert_banner` — banner cảnh báo tùy biến.
- GPX export với namespace riêng (`https://wazemod.io.vn/gpx/1`).
- Mod không thay đổi nguồn data biển báo gốc (vẫn từ server Waze).

## Ý nghĩa cho dự án C2M
- Không tái sử dụng được trực tiếp: data nằm trong tiles độc quyền của Waze,
  không có API public để query biển theo tọa độ.
- Mô hình crowdsource (user report → editor → tiles) là reference tốt cho
  flywheel DB của mình.
