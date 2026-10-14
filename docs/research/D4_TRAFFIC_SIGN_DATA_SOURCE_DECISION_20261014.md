# D4 — Nguồn dữ liệu biển báo & giới hạn tốc độ cho C2M

**Ngày:** 2026-10-14  
**Trạng thái:** RESEARCH / D4 ONLY — chưa triển khai hoặc test API thật trên thiết bị  
**Nhánh:** \`research/d4-traffic-sign-providers-20261014\` tạo từ \`main\`.  
**Ranh giới:** D3 đang được coding agent triển khai độc lập. **Không chỉnh code, nhánh, scope, gate hay firmware D3 trong nghiên cứu này.** Các tài liệu nghiên cứu Lily/VietMap nằm ở nhánh D3 trước đây là nguồn tham khảo, không phải yêu cầu ghép vào D3.

## 0. Kết luận đã sửa: Consumer VietMap API KHÔNG chứng minh có dữ liệu biển báo

Hai Consumer trên VietMap Console:
- **Consumer API (thường \`default\`):** Search, Routing, Matching, Reverse… **chỉ các endpoint đã được bật**.
- **Consumer Tilemap:** hiển thị nền bản đồ, không dùng cho Search/Route.

**Không cái nào tự động cấp quyền Driving Alert.**

| Dịch vụ VietMap | Dữ liệu có bằng chứng công khai | Có dùng ngay cho tra cứu biển báo C2M? |
|---|---|---|
| Search/Autocomplete | Địa điểm/địa chỉ | **Không** |
| Route v4 | Hình học tuyến, khoảng cách, turn-by-turn instructions | **Không có schema biển báo được xác minh** |
| Match/Match Tolls | Ghép GPS track vào đường, tính phí đường (tùy endpoint) | **Không** |
| Reverse geocoding | Địa chỉ/tên đường | **Không** |
| Traffic layer | PNG/vector biểu diễn tình trạng giao thông | **Không**; khác biển báo |
| **Driving Alert / Speed Alert** | **SDK** VietMap công khai mô tả tốc độ, biển/camera, tải dữ liệu từng vùng | **Tiềm năng, nhưng Trial OFF; phải có entitlement + contract riêng** |
| Tilemap consumer | Bản đồ nền | **Không** |

**Lưu ý mâu thuẫn trong tài liệu chính thức:**
Trang Traffic API marketing/FAQ nói Routing API có biển báo và giới hạn tốc độ theo đường, nhưng các trang schema Route v4 được đối chiếu trước đó **không công bố** \`traffic_signs\`, \`maxspeed\`, \`speed_limit\` hoặc endpoint biển báo chuyên dụng. \`paths[].instructions[].sign\` **là mã chỉ dẫn rẽ** (ví dụ rẽ phải/trái) **không phải biển báo giao thông thực địa**. Không suy diễn từ lời marketing thành field thật. Chỉ đổi kết luận nếu request **được cấp quyền** trả dữ liệu có typed schema và unit/direction rõ.

Tài liệu:
- https://maps.vietmap.vn/docs/map-api/route-version/route-v4/
- https://maps.vietmap.vn/docs/map-api/traffic/
- https://maps.vietmap.vn/docs/map-api/console/usage-limitation/
- https://maps.vietmap.vn/docs/map-api/console/manage-api-key/
- https://maps.vietmap.vn/docs/vi/map-api/overview/

SDK VietMap công khai:
- https://github.com/vietmap-company/vietmap-react-native-navigation: \`configureAlertAPI(apiKey, apiKeyId)\`, \`startSpeedAlert()\`, chế độ free-drive trên mobile.
- https://github.com/vietmap-company/vietmap_speed_alert_ios: \`ZoneNetworkManagerV2\` tải dữ liệu theo vùng, \`processGps\` phát event biển hiện tại / biển sắp tới / camera / voice; tài liệu nêu **enterprise only**, không phải API được Consumer \`default\` mở sẵn. SDK ở nhánh main cũng ghi engine chỉ hỗ trợ một số loại xe tải/buýt tại thời điểm tài liệu; **chưa xác minh hỗ trợ xe con**. Địa chỉ ví dụ \`dev.fastmap.vn/drivingalert\` chỉ là SDK dev base URL, **không phải endpoint HTTP được phép đoán hay gọi thử**.

**Kết luận VietMap cho D4:** ưu tiên **LOW / OPTIONAL** cho chức năng biển báo. Chỉ dành vài phút lấy bằng chứng qua schema, một smoke call Route nếu có key riêng cục bộ và được phép, và hỏi VietMap Driving Alert về quyền truy cập. Nếu response Route không có trường biển báo, đóng nhánh khảo sát Consumer API, không phí thêm lượt gọi Route/Match để “săn” biển báo. Không yêu cầu người dùng gửi key cho assistant.

## 1. Nguồn D4 đáng ưu tiên hơn (không phụ thuộc VietMap)

| Nguồn | Giá trị cho D4 | Giới hạn / việc cần làm |
|---|---|---|
| **Native C2M camera TSR** | Biển thực tế vừa đi qua/nhìn thấy, nếu firmware vendor có emit event | Cần capture payload thật và xác định enum/unit; dữ liệu camera có thể sai |
| **OSM/Overpass \`way[maxspeed]\`** | Giới hạn tốc độ gắn với đường, có geometry và direction tags | Không phải biển vật lý; cần snap chính xác đoạn/chiều đường, freshness, rate limit |
| **Bộ dữ liệu biển offline đã phân tích từ Lily APK** | 28.551 điểm, gồm 15.343 biển \`limit\`, 12.708 R420/R421 | Quyền tái phân phối chưa rõ; tất cả điểm \`P.127\` trong DB đã chuyển hiện thiếu hướng áp dụng; không bật cảnh báo tốc độ bằng cách bỏ kiểm tra hướng |
| **Road polyline offline Lily \`vnsigns/*.bin\`** | Tên/geometry đường, đáng thử để ghép vị trí biển + chiều | Cần xác minh format, bản quyền, map-matching với đường song hành/nút giao |
| **OSM extracts offline (Geofabrik/planet extracts)** | Dữ liệu đường cập nhật theo vùng, cache offline, định kỳ build host | ODbL/attribution; sparse maxspeed ở VN; tự kiểm tra coverage |
| **Mapillary traffic-sign features** | Object biển báo từ ảnh đường phố, khác OSM way maxspeed | API token, dữ liệu có thể thưa/không mới; xác minh license, diện phủ VN trước |
| **VietMap Driving Alert** | Nguồn thương mại chuyên biệt, rất đáng giá nếu cấp quyền hợp lệ | Không mặc định free; public key \`default\` không đủ |

**Không đồng nhất**: biển vật lý (\`P127\`) với hạn chế tốc độ trên \`way\`; R420 khu dân cư với giá trị km/h mặc định; camera phạt nguội với giới hạn tốc độ. Giữ nguồn + roadId + hướng + thời gian + loại xe + độ tin cậy trên mọi event.

## 2. Mục tiêu sản phẩm D4

**D4 chỉ cần chứng minh** một tuyến thử nghiệm trả ra đúng giới hạn tốc độ/hướng bằng dữ liệu offline hoặc OSM cache **và** có bảng evidence so với biển thực địa. Không cần tích hợp ngay VietMap, không cần viết UI lớn, không động đến luồng flash D3.

Đường dữ liệu dự kiến:

\`\`\`text
C2M GPS + heading ──> map matching đoạn/chiều đường ──┐
Camera TSR live ──────────────────────────────────────┤
Offline roads/signs (licensed) ────────────────────────┼─> fusion/source/confidence ─> advisory event
Cached OSM Overpass / future Mapillary ────────────────┤
[Authorized VietMap Driving Alert only if available] ─┘
\`\`\`

**Thứ tự thực thi:**
1. Host: tạo bộ mẫu synthetic + một vùng đường nhỏ, có \`maxspeed\`, \`maxspeed:forward/backward\`, \`maxspeed:conditional\`, và biển point; kiểm tra map matching đúng chiều.
2. Host: đo coverage thực tế một số đoạn đường ở Việt Nam bằng OSM/Overpass có cache, truy vấn có kiểm soát; đếm đường có/không có speed limit. Không gọi Overpass theo mỗi fix GPS.
3. Host: kiểm tra riêng road polylines Lily (nếu bản XAPK/binary đã có quyền đọc) và độ đáng tin của field \`u\`; không tự bù hướng chỉ từ đường gần nhất nếu giao lộ/đường song hành mơ hồ.
4. Optional: thử Mapillary traffic-sign API qua token hợp lệ, có thể bỏ nếu thiếu coverage/terms.
5. Conditional: Consumer VietMap API smoke **tối đa 1 Route v4** để tìm field mới so với schema (chỉ nếu có API key chủ sở hữu trong secret store). Nếu không có sign/limit có type cụ thể, kết luận \`NO_SIGN_API_IN_DEFAULT_CONSUMER\`, đóng test VietMap Trial. **Driving Alert chỉ test nếu thực sự được bật + có hợp đồng endpoint công khai/chính thức cho tài khoản.**
6. Ghi docs và kế hoạch adapter \`RoadSignProvider\`; code D4 chỉ khi D3 đã ổn và không gây xung đột.

## 3. Runbook cho coding agent D4

**Preflight**
- Đọc trạng thái D3 hiện tại bằng GitHub/working tree trước khi sửa mã; **không cherry-pick hoặc merge nhánh D4 vào D3**.
- Cắm toàn bộ nghiên cứu vào **nhánh D4 riêng** từ \`main\`, không commit dữ liệu proprietary, XAPK, API keys, biển/tọa độ cá nhân.
- Nếu Agent muốn test VietMap: kiểm tra quota quyền tài khoản ở Console. API key Consumer \`default\` được cung cấp qua environment/secret store của **chủ tài khoản**, không commit, không paste chat. Tilemap key không dùng gọi API. Không giả lập/giải ngược endpoint nội bộ không được VietMap cấp quyền.
- Không test trực tiếp camera, không thay firmware D3 và không mở GPS UART đang dùng bởi \`cardv\`.

**Acceptance / evidence**
- \`vietmap_default_consumer\`: \`DOCS_ONLY_NO_SIGN_SCHEMA\` | \`SMOKE_NO_SIGN_FIELD\` | \`SMOKE_TYPED_SIGN_FIELD\` (kèm payload redacted and field schema) | \`NO_KEY\`; \`Driving Alert\`: \`OFF\` | \`ON_NO_DOC\` | \`ENTITLED_TESTED\`; tuyệt đối không báo PASS nếu không gọi API.
- \`osm_coverage\`: số đoạn đường có \`maxspeed\`/tổng đoạn trong vùng thử, ngày tải và các giới hạn đường/chiều; không chỉ trình bày tổng số point.
- \`lily_offline\`: source/license, record counts, unknown headings và số point có thể map-match chính xác; **không báo 15.343 giới hạn tốc độ đã deploy chỉ vì DB chứa 15.343 record**.
- \`mapillary\`: token/coverage/billing/right-to-cache nếu test.
- \`d4_decision\`: nên tiếp tục nguồn nào, chi phí, code thay đổi gì sau khi D3 hoàn tất; PASS/NO-GO cho từng provider; nêu rõ host-only vs on-device.

**Giới hạn thử nghiệm:** VietMap ≤1 Route call (nếu có key), Overpass tối đa vài truy vấn nhỏ có cache cho khu vực định trước, Mapillary chỉ thử theo token/terms. Không scrape hàng loạt, không lưu service key trong firmware/app phát hành.

## 4. Prompt ngắn giao manager agent

> Đây là nghiên cứu cho **D4**, không phải D3. D3 đang được coding agent triển khai; giữ nguyên branch, code và gates D3. Đọc tài liệu D4 này, ưu tiên kiểm chứng OSM maxspeed + road direction và các nguồn biển báo offline/Mapillary. VietMap Consumer \`default\` hiện chỉ có API route/search/match được xác minh; **không có public sign schema**. Nếu có key qua môi trường bảo mật, tối đa một Route v4 smoke để xác nhận, nếu thiếu sign/limit thì dừng khảo sát Consumer API. Không dùng Tilemap key, không đoán endpoint Driving Alert; chỉ theo khi VietMap cấp quyền/tài liệu. Viết evidence report và phương án tích hợp sau D3, không merge/flash hay chặn D3; tự quyết trong scope D4. Khi review code, dùng Codex Combo Review-Normal/Review-Hard qua 9router, **không dùng AO native Review**.

## 5. Reference từ các nghiên cứu trước (chỉ đọc, không nhập sang D3)

- https://github.com/vunguyenbv175/C2M/blob/feature/d3-tsr-events-20261014/docs/research/VIETMAP_FREE_API_C2M_D3_20261014.md
- https://github.com/vunguyenbv175/C2M/blob/feature/d3-tsr-events-20261014/docs/research/LILY_API_DEEP_DIVE_D3_20261014.md
- https://github.com/vunguyenbv175/C2M/blob/feature/d3-tsr-events-20261014/docs/runbooks/VIETMAP_CONSUMER_API_AGENT_TEST_D3.md — tài liệu cũ viết nhầm scope D3; **D4 thay thế, KHÔNG giao cho agent D3**.
- https://wiki.openstreetmap.org/wiki/Key:maxspeed
- https://wiki.openstreetmap.org/wiki/Overpass_API
- https://www.openstreetmap.org/copyright
