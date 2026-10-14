# So sánh firmware VI vs EN — Bản Việt khác gì? Có báo biển khu dân cư không?

Ngày: 2026-10-14.
EN: `V2023.08.03.1` (SHA-256 `3a703522…`, từ vault).
VI: `V2023.09.20.1` (SHA-256 `f28cad04…`, từ Google Drive do user cung cấp).
Cả hai đều đã verify hash và trích xuất đầy đủ (customer UBIFS + rootfs).

## Đính chính evidence (2026-10-14)

- Không tìm thấy tên lớp R.420/R.421 là bằng chứng âm tính tĩnh, không đủ
  chứng minh tuyệt đối detector không hỗ trợ hoặc kết luận quảng cáo sai.
  Khả năng nhận diện những biển này vẫn cần runtime/model class evidence.
- `--m0` KHÔNG là hashes/fingerprint model: đây là directory AES offset/size.
  Sáu embedded blobs byte-identical EN/VI theo
  `docs/reverse/ADAS_PACKAGE_LOADER_V1.md`; “model nhúng khác” bên dưới bị rút.
- “Diff rỗng” chỉ surface strings được so, không toàn bộ customer tree/code.
  Repo đã chứng minh khác biệt binary/metadata/cardv/system audio.
- Có 7 ADAS WAV đổi, FCW/HMW không đổi. C đã dùng donor Việt; không cần
  thay model/VI binary để Việt hóa âm. oneed_cust cũng có asset khác thực sự.
- R.420 không tự đồng nghĩa “60 km/h cho mọi xe”; cần loại xe/đường/quy định.
  Dữ liệu GPS mới có 12,708 điểm R.420/R.421 có hướng, nhưng heading semantics,
  cùng tuyến và input/output chưa kiểm chứng. Xem
  `docs/firmware/CANDIDATE_D_TSR_FAST_TRACK.md` trước mọi deploy.

## Kết luận nhanh (ghi chép ban đầu; xem đính chính trên)

1. **Bản VI KHÔNG có thêm tính năng báo biển khu dân cư (R.420/R.421).**
   Không có chuỗi "khu dân cư"/"R.420"/"residential" nào trong `adas`,
   `cardv`, cây customer hay APK. TSR trên VI giống hệt EN: chỉ phát hiện
   biển giới hạn **tốc độ / chiều cao / tải trọng**.
2. Điểm khác biệt thực sự của bản VI: **âm thanh cảnh báo tiếng Việt**
   (6/8 file wav khác bản EN) + build mới hơn (model nhúng khác).
3. Khả năng cao quảng cáo đã thổi phồng: "báo bằng tiếng Việt" bị diễn giải
   thành "báo thêm biển khu dân cư".

## 1. Bảng so sánh chi tiết

| Thành phần | EN (2023-08-03) | VI (2023-09-20) | Kết luận |
|---|---|---|---|
| `adas` binary | commit `00780a57` | commit `e5343105` | build khác |
| TSR pipeline | đầy đủ | đầy đủ, **diff rỗng** | giống hệt |
| 8 flags TSR | `--enable_tsr=false` | `--enable_tsr=false` | giống hệt |
| Model nhúng (`--m0`) | 6 hashes A | 6 hashes B (khác hoàn toàn) | fingerprint lúc build khác |
| `model.img` (507040 B, mã hóa) | SHA-256 `07ba919b…` | **SHA-256 `07ba919b…` (giống hệt)** | weights thực tế giống nhau |
| `run.sh` | — | — | giống hệt |
| Cây file customer | 227 entries | 227 entries, diff rỗng | giống hệt |
| `cardv` binary | hash `344b4a3f…` | hash `56db44d9…` | build khác, strings diff nhỏ (chủ yếu NMEA/GPS) |
| `audios.txt` | 9 ID | 9 ID | giống hệt |
| FCW.wav, HMW.wav | — | — | **giống hệt** (hash khớp) |
| LDW/PCW/SAG/VB/adas_activated/adas_fail/updating.wav | — | — | **khác** (VI nhỏ hơn) |
| oneed_cust | 0x364000 | 0x326000, cùng 45 files | tương đương |
| rootfs | 560 entries | 560 entries | tương đương |

## 2. Về claim "bản Việt báo biển khu dân cư"

Đã tìm kiếm toàn diện, **không thấy**:

- ❌ Không có `R.420` / `R.421` / `R420` trong `adas` (EN lẫn VI).
- ❌ Không có "khu dân cư" / "đông dân cư" / "residential" trong `adas`,
  `cardv`, cây customer, oneed_cust (cả 2 bản).
- ❌ Không có trong APK UTOUR GO v6.1.20.
- ❌ TSR chỉ có 3 đầu ra: `speed_limit`, `height_limit`, `weight_limit`
  — không có class "zone" hay "residential area".

**Phán quyết:** với firmware VI `V2023.09.20.1` này, claim quảng cáo là
**không đúng** (hoặc nói về sản phẩm/phiên bản khác). Những gì bản VI hơn
bản EN thực sự chỉ là **giọng cảnh báo tiếng Việt** (6/8 wav khác) — có thể
chính điều này đã bị quảng cáo thổi thành "báo biển khu dân cư".

Lưu ý: R.420/R.421 là biển báo hiệu lệnh về khu đông dân cư (liên quan giới
hạn tốc độ 60 trong đô thị). Nếu muốn tính năng này thật, phải tự build:
hoặc train thêm class cho model TSR, hoặc (thực tế hơn) dùng GPS Warner
(`fw/warner/`) với DB chứa vị trí các biển R.420/R.421.

## 3. Vì sao ADAS không chạy trên bản VI (nhắc lại)

TSR đã loại trừ (code y hệt). `--m0` khác nhưng `model.img` giống hệt
→ model weights không phải thủ phạm (đính chính giả thuyết cũ).
Nghi phạm còn lại: chính binary `adas` bản VI, config/license, hoặc tầng
cardv/integration — xem `TSR_VI_FIRMWARE_ANALYSIS.md`.
