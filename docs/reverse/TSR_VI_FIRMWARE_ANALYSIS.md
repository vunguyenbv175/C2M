# TSR trong firmware tiếng Việt (VI) — Phân tích

Ngày: 2026-10-14.
Firmware: `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar` (sysVer 20230920185743),
tải từ Google Drive do user cung cấp, **SHA-256 khớp**
`f28cad04…b081b8d3cfa`. Binary `adas` trích xuất bằng tool UBIFS của repo,
**SHA-256 khớp** `997b71c2…95527d1`.

## Kết luận nhanh

1. **TSR trên bản VI giống hệt bản EN** — cùng pipeline, cùng 8 flags,
   cùng mặc định `--enable_tsr=false`. Không có cải tiến hay cắt giảm TSR.
2. Bản VI khác EN ở: build commit, model nhúng (`--m0` checksums khác),
   và 2 file âm thanh LDW/PCW (nhỏ hơn, khác hash — có thể là tiếng Việt).
3. ADAS không chạy trên bản VI (user report) — **không phải do TSR**
   (code TSR y hệt); nghi phạm chính là model nhúng khác (HYPOTHESIS).

## 1. TSR trên VI (CONFIRMED static)

| Hạng mục | VI | EN | So sánh |
|---|---|---|---|
| `TsrProcess` / `ReadTsr` / `TsrMsg` / `TsrRes` | có | có | giống hệt |
| `tsr::SpeedLimitReporter` + `ReportWarningState/Level` | có | có | giống hệt |
| `tsr::HeightWarningState` | có (14 refs) | có | giống hệt |
| Số lượng strings chứa "tsr" | 115 | 115 | **diff rỗng** |
| 8 flags + mô tả tiếng Anh | đủ | đủ | giống hệt |
| `--enable_tsr` mặc định | `false` | `false` | giống hệt |
| Ngưỡng số (`*_max_thresh=200.0`, còn lại 0) | giống | giống | giống hệt |
| Debug fields `TsrDetect` (speed/height/weight) | đủ | đủ | giống hệt |
| `TSR_HL` / `TSR_HL_W` / `TSR_WL` | có | có | giống hệt |
| `audios.txt` (9 ID, không có ID riêng cho TSR) | giống | giống | giống hệt |

## 2. Điểm khác biệt VI vs EN (ngoài TSR)

- **Build commit:** VI `e5343105…`, EN `00780a57…` — build khác nhau.
- **Model nhúng:** `--m0` = 6 SHA-256 hashes (fingerprint của 6 model Caffe
  d0/v_a/v_t/p_r/road/tl trong `params/model.txt`) — khác hoàn toàn giữa 2 bản.
  NHƯNG `model.img` (blob mã hóa 507040 bytes, entropy 7.96) thì
  **giống hệt nhau** (SHA-256 khớp) → weights thực tế giống nhau; `--m0`
  chỉ là fingerprint lúc build, không hash blob đã ship.
- **Âm thanh:** `FCW.wav` giống hệt nhau; `LDW.wav` (75820 vs 95660 bytes)
  và `PCW.wav` (73738 vs 119852 bytes) **khác** — bản VI nhỏ hơn đáng kể,
  có thể là giọng tiếng Việt (chưa nghe kiểm chứng — user có thể mở nghe).
  `audios.txt` giữ nguyên duration của bản EN (có thể stale).
- **`run.sh`:** giống hệt nhau.
- Binary `adas`: không thấy chuỗi tiếng Việt (logic tiếng Anh).

## 3. Vì sao ADAS không chạy trên bản VI?

TSR đã loại trừ (code y hệt). `--m0` khác nhau nhưng `model.img` giống hệt
→ model weights không phải thủ phạm. Các giả thuyết còn lại:

1. Khác biệt trong chính binary `adas` bản VI (build khác, commit khác) —
   có thể lỗi init ở module khác (calib, license, platform).
2. Khác biệt config/license ngoài `adas` (chưa khảo sát).
3. Lỗi ở tầng cardv/integration của bản VI (chưa khảo sát).

Kiểm chứng đề xuất: lấy log khởi động ADAS trên bản VI (nếu có);
so sánh hành vi init giữa 2 binary.

## 4. Ý nghĩa cho dự án TSR

- Mọi kết luận về TSR trong `TSR_STOCK_FEATURES_V1.md` (từ bản EN) **áp dụng
  nguyên cho bản VI**.
- Candidate C bật TSR bằng hook trên nền EN — không cần quan tâm bản VI.
- Nếu muốn giọng cảnh báo tiếng Việt: bản VI có LDW/PCW khác bản EN —
  đáng mở nghe thử trước khi TTS lại.
