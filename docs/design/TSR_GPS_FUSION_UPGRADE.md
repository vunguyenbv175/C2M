# Nâng cấp TSR + kết hợp GPS — Phân tích khả thi

Ngày: 2026-10-14.

## 1. Hiện trạng (đã xác minh)

**Stock TSR (firmware gốc):**
- Pipeline thật: `TsrProcess` → `ReadTsr` → `SpeedLimitReporter` /
  `HeightWarningState` → `TsrWarning` → CAN + bus nội bộ. CONFIRMED (static).
- Phát hiện 3 loại giới hạn: tốc độ, chiều cao, tải trọng.
- Vendor tắt mặc định (`--enable_tsr=false`); Candidate C đã bật bằng hook
  (flash 2026-10-14); runtime UNVERIFIED.
- 8 flags điều chỉnh (trích từ ELF, xem bảng dưới).

**GPS:**
- Cam C2M có GPS (user xác nhận); app đọc GPS điện thoại (CONFIRMED từ APK).
- Prototype `~/workspace/c2m-gps/`: SQLite SignDB + Warner engine, demo PASS.
- Chưa có API Wi-Fi nào đọc được trạng thái TSR live từ cam (đã quét APK:
  chỉ có endpoint hiệu chuẩn camera ADAS, không có endpoint warning/event).

## 2. Giá trị mặc định của 8 flags TSR (trích từ binary gốc)

| Flag | Mặc định | Đơn vị | Ý nghĩa |
|---|---|---|---|
| `enable_tsr` | `false` | bool | Bật/tắt TSR |
| `tsrw_interval` | `0.0` | giây | Chu kỳ lặp cảnh báo |
| `tsrw_sli_over_min_ratio` | `0.0` | % | Ngưỡng quá tốc độ tối thiểu (%) |
| `tsrw_sli_over_min_thresh` | `0.0` | km/h | Ngưỡng quá tốc độ tối thiểu (km/h) |
| `tsrw_sli_speed_min_thresh` | `0.0` | km/h | Tốc độ biển tối thiểu để TSR hoạt động |
| `tsrw_sli_speed_max_thresh` | `200.0` | km/h | Tốc độ biển tối đa để TSR hoạt động |
| `tsrw_sli_host_speed_min_thresh` | `0.0` | km/h | Tốc độ xe tối thiểu để cảnh báo |
| `tsrw_sli_host_speed_max_thresh` | `200.0` | km/h | Tốc độ xe tối đa để cảnh báo |

Nhận xét: với mặc định, cảnh báo kích hoạt với **mọi** mức vượt tốc độ
(>0% và >0 km/h) — rất nhạy, có thể là lý do vendor tắt (HYPOTHESIS).
Các giá trị trên là fallback trong binary; `adas.flag` của nhà máy có thể
đã ghi đè — cần đọc flag thực tế trên thiết bị trước khi tune.

## 3. Các hướng nâng cấp

### H1 — Tune 8 flags TSR qua config (không đụng binary)
- **Cách làm:** mở rộng hook của Candidate C: sau khi decode `adas.flag`,
  ghi thêm các flag `tsrw_*` với giá trị mong muốn (cùng cơ chế base64/md5
  như stock `run.sh`), rồi mới cho `adas_service.sh` chạy.
- **Ví dụ khởi điểm (HYPOTHESIS, cần lái thử):**
  `tsrw_sli_over_min_thresh=5`, `tsrw_sli_over_min_ratio=10`,
  `tsrw_interval=5`, `tsrw_sli_host_speed_min_thresh=20`
  (tránh cảnh báo khi bò trong phố).
- **Ưu:** không sửa binary, đảo ngược được (với điều kiện backup config —
  hook hiện tại CHƯA backup, phải bổ sung trước).
- **Nhược:** tune mù nếu chưa có runtime; config sống sót qua flash nên
  rollback firmware ≠ rollback config.

### H2 — GPS Warner chạy trong app điện thoại
- **Cách làm:** port `~/workspace/c2m-gps/` (Python) sang Kotlin trong app:
  SQLite + spatial query + luật Warner đã kiểm chứng (lookahead theo tốc độ,
  lọc bearing ±30°, lọc hướng biển, cooldown).
- **Nguồn GPS:** GPS điện thoại (app đã có quyền và code đọc).
- **Nguồn DB biển:** Mapillary API (cần token của Vũ) → build offline DB
  theo tuyến đường hay đi; bổ sung dần bằng crowdsource (mục H3).
- **Ưu:** không đụng firmware, triển khai độc lập, chạy offline.
- **Nhược:** phụ thuộc độ phủ DB; GPS phone sai số ±3–5m.

### H3 — Fusion hai chiều TSR × GPS (đích đến)
Ba vòng kết hợp, triển khai dần:

1. **GPS dự báo → TSR xác minh (giảm false positive của GPS-DB):**
   GPS báo "sắp tới biển 60" → khi TSR cũng detect biển 60 trong frame
   → cảnh báo độ tin cậy cao. Cần kênh đọc TSR runtime (xem §5).

2. **TSR detect → GPS đối chiếu (giảm false positive của TSR):**
   TSR báo biển 80 nhưng DB + map cho biết đoạn đường này chỉ có biển 60
   → đánh dấu nghi ngờ, không cảnh báo vội.

3. **Crowdsource flywheel (xây DB từ chính xe):**
   Mỗi lần TSR detect chắc chắn (kèm GPS) → ghi vào DB local → DB càng đi
   càng đầy, càng chính xác; DB tốt lại giúp vòng 1+2. Đây là cách Vietmap
   xây dữ liệu, nhưng mình làm ở quy mô cá nhân.

### H4 — Daemon fusion on-device (dài hạn)
- Repo đã có `fw/device_minimal/c2m_idle.c` (daemon tự build chạy trên cam).
- Fusion on-device cần daemon đọc được (a) GPS của cam, (b) kết quả TSR
  runtime — cả hai kênh hiện chưa có tài liệu. Cần RE thêm trước khi
  cam kết hướng này.

## 4. Ma trận quyết định

| Hướng | Effort | Rủi ro | Phụ thuộc | Giá trị |
|---|---|---|---|---|
| H0: lái thử verify TSR stock (Candidate C) | Thấp | Thấp | Không | Bắt buộc trước mọi tune |
| H1: tune flags qua config | Thấp | Trung bình | H0 | Cao nếu TSR chạy tốt |
| H2: GPS Warner trong app | Trung bình | Thấp | Token Mapillary + DB | Cao, độc lập firmware |
| H3.3: crowdsource DB | Trung bình | Thấp | H1 hoặc H2 | Cao, hiệu ứng flywheel |
| H3.1/3.2: fusion 2 chiều | Cao | Trung bình | Kênh đọc TSR runtime | Rất cao |
| H4: daemon on-device | Cao | Cao | RE kênh TSR/GPS trên cam | Dài hạn |

## 5. Điều kiện tiên quyết & rủi ro

1. **Lái thử H0 trước:** đừng tune khi chưa biết TSR stock detect được gì.
   Checklist đã có trong `docs/reverse/TSR_STOCK_FEATURES_V1.md`.
2. **Backup config:** bổ sung backup `adas.flag`/`adas_de.flag` vào hook
   trước khi tune thêm flag (hiện tại hook C chưa backup).
3. **Kênh đọc TSR runtime:** chưa có. Các ứng viên: debug log
   (`TsrDetect` fields, qua `getlog.sh`/thẻ diag), ScreenService, CAN
   (không với tới từ app). Cần RE/survey trước H3.1/H3.2.
4. **DB biển VN:** điểm nghẽn của H2. Mapillary coverage ở VN chưa đo;
   OSM thưa. Crowdsource (H3.3) là lối ra bền vững.
5. **Đừng tune quá tay:** ngưỡng mặc định 0/0 rất nhạy; tăng dần từ
   (5 km/h, 10%, interval 5s) và đo false-positive trên đường thật.

## 7. PHÁT HIỆN MỚI (2026-10-14): stock `edog` engine trong cardv

**Đính chính:** `/edogs` chỉ xuất hiện trong chuỗi diagnostic
`Unsupport gps/edogs module!!`, KHÔNG chứng minh đó là file database.
Static default/config CGI có `Camera.Menu.Edog=ON`, `setEdog()` ghi nvconf
và FIFO `edog 1`/`edog 0`; vì vậy không đúng khi nói không có switch/menu.
Default ON vẫn không chứng minh module/data/runtime tồn tại. `edog_audio`
pack chưa có trong ảnh, còn âm hệ thống bình thường có, không chỉ `.gitkeep`.
Giữ các đoạn dưới như ghi chép ban đầu, không dùng `/edogs` làm đường deploy.

Phân tích binary `cardv` (rootfs gốc) phát hiện một **hệ thống cảnh báo tốc
độ bằng GPS đã có sẵn trong firmware** — "edog" (electronic dog, 电子狗):

- Engine đầy đủ: `GpsTask` đọc NMEA (`/dev/ttyS1`, `/dev/ttyS2`),
  `nmea_parse_gps_bd_gn`, các hàm detect `edog_twdz_det` / `edog_zcwy_det` /
  `edog_suanda_det` / `edog_suandu_getalltype`, `parse_edog_data`,
  `ef_start_task_readedog`.
- Âm thanh: `edog_playsound*`, `zz_edog_playsoundspeedlimith`,
  `edog_alarmwitoutsound`; file wav tại `/oneed_cust/audio/edog_audio/`
  (`10.wav`…`500.wav` = các mốc tốc độ, `TA*.wav`).
- Database: đọc từ `/edogs` (định dạng chưa rõ — cần RE thêm).

**Nhưng:** audio pack và database **không có** trong ảnh stock
(oneed_cust chỉ có `.gitkeep` ở `/audio`), không thấy menu bật edog trong
CGI/APK. Tương tự TSR: code có, data/config thiếu hoặc tắt.

→ **Nếu crack được format `/edogs` + tìm được công tắc bật**, ta có ngay
cảnh báo GPS chuẩn vendor mà không cần viết code mới. Đây là hướng điều tra
giá trị cao nhất hiện tại (xếp trên cả daemon tự viết).

## 8. Daemon on-device `c2m-warner` (replay-only prototype; NOT on-device)

Theo chỉ đạo "không dùng app điện thoại, chạy offline trên C2M trước":
đã port Warner engine sang C tại `fw/warner/`:

- `main.c` / `nmea.c` / `warner.c` / `db.c` — đọc NMEA RMC (có verify
  checksum), engine cảnh báo (luật đã kiểm chứng từ prototype Python),
  DB binary gọn `signs.bin` (tool `tools/build_signs_bin.py`).
- Unit test + e2e trên host: **PASS** (cảnh báo đúng 2/5 biển demo).
- Cross-build ARM: CMakeLists sẵn, dùng
  `fw/device_minimal/toolchain-armhf-dyn.cmake`; cần cài
  `gcc-arm-linux-gnueabihf` trên máy build (VM hiện chưa có).

Review cập nhật: entrypoint đã được giới hạn HOST/REPLAY để chặn busy-loop
và đọc tranh UART; việc deploy chưa được phép.
1. **GPS input:** cần nguồn fan-out thụ động đã chứng minh, không mở ttyS1/S2
   cùng `cardv`; đọc chậm vẫn tiêu thụ bytes, kiểm ownership không tạo tap.
2. **Alert output:** grammar và arbitration âm thanh/hiển thị phải được xác
   minh; log/stdout không phải nâng cấp cảnh báo người dùng.
3. **Triển khai:** chỉ sau input/output, DB, ABI/QEMU và manifest gates. Không
   cài launcher tự chạy bản replay, không flash chỉ để thấy thêm log.

## 9. Roadmap cập nhật (on-device first, không app điện thoại)

- **Phase 0 (ngay):** lái thử Candidate C theo checklist TSR.
- **Phase 1:** điều tra `edog` — format `/edogs`, công tắc bật, audio pack
  (có thể tự TTS). Nếu mở được → xong, khỏi viết daemon.
- **Phase 2 (song song):** cross-build `c2m-warner`, nhưng chỉ bring-up bằng
  replay trước. `signs_vn.bin` (28,551 điểm, ~2.86 MB, nguồn Lily APK) là
  private owner-provided input, không commit/redistribute; chưa đủ để gọi là
  DB đã triển khai. Không mở ttyS1/S2 trên firmware và không móc audio/M4 khi
  chưa có passive/runtime contract.
- **Phase 3:** fusion TSR × GPS trên cam (khi có kênh đọc TSR runtime).
- **Phase 4:** crowdsource DB từ chính xe (ghi nhận TSR detect + GPS).
