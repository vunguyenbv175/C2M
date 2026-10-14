# TSR trong firmware gốc C2M — Báo cáo tính năng chi tiết

Ngày: 2026-10-14 (bổ sung bằng chứng gốc từ binary thật).
Firmware: `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar` (sysVer 20230803193750) —
tải từ vault repo, **SHA-256 khớp** `3a703522…b4904cd4`; binary `adas`
trích xuất bằng tool UBIFS của repo, **SHA-256 khớp**
`0dcc6982…94043`, BuildID `5acaac94…281d`.

Quy ước nhãn:
- **CONFIRMED (static)**: có bằng chứng trong binary/strings/config của firmware gốc.
- **UNVERIFIED**: chưa có bằng chứng runtime trên thiết bị thật.
- **HYPOTHESIS**: suy luận hợp lý, cần kiểm chứng.

## Kết luận nhanh

1. Firmware gốc **có sẵn pipeline TSR thật** (không phải strings chết).
2. TSR phát hiện **3 loại giới hạn**: tốc độ (speed), chiều cao (height),
   tải trọng (weight) — CONFIRMED qua debug fields.
3. Mặc định vendor: `--enable_tsr=false` **(TẮT)** — CONFIRMED.
   Lý do vendor tắt: không rõ.
4. Candidate C (flash 2026-10-14) đã bật flag bằng hook — hiệu quả runtime
   của TSR **vẫn UNVERIFIED**.

## 1. Pipeline TSR trong firmware

```
camera (ringbuf_vehicle, vehicle_run_freq=10)
        │
        ▼
vehicle::VehicleAlgo::TsrProcess()      ← xử lý nhận diện biển báo
        │
        ▼
VehicleRun::ReadTsr()                  ← đọc kết quả TSR mỗi vòng lặp
        │
        ├──► vehicle::TsrMsg / vehicle::TsrRes / TsrTraceRes
        │
        ├──► tsr::SpeedLimitReporter::Update(int, long long, float)
        │         ├──► ReportWarningState()   (trạng thái cảnh báo)
        │         └──► ReportWarningLevel()   (mức cảnh báo)
        ├──► tsr::HeightWarningState          (cảnh báo giới hạn chiều cao)
        │
        ├──► product::Distribution::SetTsrResult(...)   (phân phối kết quả)
        │
        ├──► CollectService::Send<TsrWarning>           (bus sự kiện nội bộ)
        │    Send<vector<TsrTraceRes>>
        │
        └──► CANWarningSender::SetEnableTSR(bool)       (đầu ra CAN bus)
             CANWarningSender::SetTSRWarningLevel(int)
```

Source file (từ build path trong binary):
`src/product/speed_limit_reporter.cpp`,
`src/product/height_warning_state.cpp`,
`src/product/distribution.cpp`.

## 2. Bộ tham số TSR (gflags trong binary gốc)

| Flag | Mô tả trong binary | Ý nghĩa |
|---|---|---|
| `enable_tsr` | — | Bật/tắt TSR (mặc định `false`) |
| `tsrw_interval` | "TSR warning interval, second" | Chu kỳ lặp cảnh báo (giây) |
| `tsrw_sli_over_min_ratio` | "TSR SLI work over speed min ratio, %" | Ngưỡng quá tốc độ tối thiểu (% vượt biển) |
| `tsrw_sli_over_min_thresh` | "TSR SLI work over speed min thresh, km/h" | Ngưỡng quá tốc độ tối thiểu (km/h) |
| `tsrw_sli_speed_min_thresh` | "TSR SLI work speed min thresh, km/h" | Tốc độ biển tối thiểu để TSR hoạt động |
| `tsrw_sli_speed_max_thresh` | "TSR SLI work speed max thresh, km/h" | Tốc độ biển tối đa để TSR hoạt động |
| `tsrw_sli_host_speed_min_thresh` | "TSR SLI work host speed min thresh, km/h" | Tốc độ xe tối thiểu để cảnh báo |
| `tsrw_sli_host_speed_max_thresh` | "TSR SLI work host speed max thresh, km/h" | Tốc độ xe tối đa để cảnh báo |

Giá trị mặc định số của các flag trên không nằm ở vùng plaintext
(chỉ có `--enable_tsr=false` ở đó) — cần parse gflags struct hoặc đo runtime.

## 3. Tính năng chi tiết

### F1 — Nhận diện biển giới hạn tốc độ (SLI)
- **CONFIRMED (static).** `tsr::SpeedLimitReporter` + `TsrProcess`/`ReadTsr`.
- Debug fields: `speed_warning`, `speed_warning_state`, `speed_warning_level`,
  `speed_limit = `, `tsr_warning_filtered`.
- Model CNN: 6 model nhúng (`d0`, `v_a`, `v_t`, `p_r`, `road`, `tl` theo
  `params/model.txt`); blob nào phục vụ TSR chưa pinpoint (HYPOTHESIS).
- Biển tốc độ VN nào trigger được (40/50/60/80…): UNVERIFIED.

### F2 — Cảnh báo quá tốc độ
- **CONFIRMED (static).** `ReportWarningState()`/`ReportWarningLevel()` +
  bộ ngưỡng `tsrw_sli_*` ở trên + `SetTSRWarningLevel` ra CAN.
- Phía app (APK v6.1.20, nhánh c2) có entity cấu hình tương ứng:
  `tsrEnable`, `enable_tsr_sli_warning`, `tsrw_sli_over_min_thresh`,
  `tsrw_sli_over_min_ratio`, `tsrw_sli_host_speed_min_thresh`,
  `tsrw_sli_host_speed_warning_thresh`, biến thể `tsrt_*`
  (ý nghĩa hậu tố `t` chưa rõ). Kênh truyền từ app xuống firmware:
  không thấy property `Camera.Menu.TSR*` nào — UNVERIFIED.

### F3 — Cảnh báo giới hạn CHIỀU CAO (phát hiện mới từ binary gốc)
- **CONFIRMED (static).** `tsr::HeightWarningState` singleton +
  `height_warning_state.cpp`; debug fields `height_warning_state`,
  `height_warning`, `height_limit = `.
- Flag liên quan: `host_vehicle_height`, `camera_height`
  (mặc định `--camera_height=1.3`), `--max_valid_camera_height=4.0`,
  `--min_valid_camera_height=0.5`.
- Trạng thái debug: `TSR_HL`, `TSR_HL_W` (HYPOTHESIS: Height Limit /
  Height Limit Warning), `TSR_WL` (HYPOTHESIS: Weight Limit).
- Đây là tính năng chưa từng được nhắc trong tài liệu repo trước đây.

### F4 — Giới hạn TẢI TRỌNG
- **CONFIRMED một phần.** Debug field `weight_limit = ` tồn tại trong
  `TsrDetect`, nhưng không thấy `WeightWarningState` tương ứng — có thể chỉ
  detect giá trị, chưa có máy trạng thái cảnh báo. UNVERIFIED runtime.

### F5 — Hiển thị lên màn hình / CAN bus
- **CONFIRMED (static)** đầu ra CAN: `CANWarningSender::SetEnableTSR`,
  `SetTSRWarningLevel`, `SetCurrentSpeed`, `Send`.
- Hiển thị biển lên màn hình M4: HYPOTHESIS (`--enable_screen_service=true`
  + `ScreenService`; `M4_ADAPTER_DESIGN.md` đã thiết kế field
  `speed_limit_kmh` "nếu runtime chứng minh").

### F6 — Âm thanh cảnh báo
- ADAS **không tự phát âm thanh**: binary `adas` không có wav/alsa/fifo,
  chỉ có `--audio_list_file=audios.txt`; phát âm thanh do `cardv` thực hiện
  (CONFIRMED static — xem `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md`).
- `audios.txt` (trích từ ảnh gốc): 9 ID
  `fcw/hwm/vb/stop_and_go/ldw/pcw/fail/calib_success/tlr_green_on` —
  **không có ID riêng cho TSR** → âm thanh cảnh báo TSR dùng chung kênh nào
  còn UNVERIFIED.

### F7 — Đèn giao thông (liên quan)
- Code có thật: `TlrDetect`, `TlrCnnCls`, `tlr::GreenWarning`,
  `tsr::GreenWarningState`, `SetTlrResult` — CONFIRMED (static).
- `tlr_green_on.wav` **thiếu** trong ảnh gốc (Candidate C đã thêm bản TTS
  "Đèn xanh"). Coi như năng lực codebase, không phải tính năng đã bật.

## 4. Cơ chế bật/tắt (xác minh từ ảnh gốc)

`run.sh` (trích nguyên văn từ firmware):

```sh
config_dir=/customer/minieye/config
# decode base64 adas.flag -> adas_de.flag (re-decode khi md5 lệch)
# ...
# exit 1 nếu thiếu config
```

- `minieye/config/` trong ảnh chỉ có `.gitkeep`: `adas.flag` do nhà máy
  provision trên thiết bị, **sống sót qua flash** (updater backup
  `/customer/minieye/config`).
- Candidate C (2026-10-14): hook chạy trước `adas_service.sh`, decode flag,
  flip `--enable_tsr=false` → `true`, ghi lại cả 2 file cho khớp md5.
- **Cảnh báo:** flash A/B (không hook) KHÔNG đảm bảo TSR tắt trở lại vì
  config được giữ lại. Rollback firmware và rollback config là 2 việc riêng.

## 5. Trạng thái kiểm chứng runtime (tới 2026-10-14)

| Hạng mục | Trạng thái |
|---|---|
| ADAS nói chung trên EN gốc | Chạy (user report) |
| ADAS trên VI gốc | Không chạy (user report) |
| Candidate C: cảnh báo tiếng Việt (LDW/PCW/FCW) | Nghe thấy bằng tai — OK |
| Candidate C: TSR nhận diện / hiển thị / cảnh báo | **UNVERIFIED** |
| Biển tốc độ VN nào trigger được | UNVERIFIED |
| Cảnh báo chiều cao / tải trọng | UNVERIFIED |

Checklist lái thử TSR:
1. Lái qua các biển giới hạn tốc độ (40/50/60/80), ghi hit/miss/false-positive
   từng biển.
2. Quan sát app UTOUR GO + màn hình M4: có hiện biển tốc độ không.
3. Nghe: có âm báo khi quá tốc độ không; khoảng lặp có đúng `tsrw_interval` không.
4. Biển hạn chế chiều cao (cầu vượt, hầm): có cảnh báo không.
5. Nếu ADAS lỗi sau khi bật TSR: báo cáo, rollback, DỪNG (theo runbook C).

## 6. Tài liệu liên quan trong repo

- `docs/firmware_en_vi/03_ADAS_ENGINE_TSR_AND_REGRESSION.md` — regression
  EN/VI, 6 model nhúng, `--enable_tsr=false`.
- `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md` — cơ chế audio + flag TSR,
  candidate C, TSR rollback uncertainty.
- `docs/firmware/CANDIDATE_C_VIAUDIO_TSR.md` — build record candidate C.
- `docs/design/STOCK_ADAS_PROVIDER.md` — `detected_speed_limit` để trống,
  chờ runtime chứng minh.
- `docs/design/M4_ADAPTER_DESIGN.md` — thiết kế hiển thị `speed_limit_kmh`.
- `docs/master/AGENT_KICKOFF.md` — nguyên tắc: KHÔNG claim TSR được bật khi
  chưa có bằng chứng runtime.
