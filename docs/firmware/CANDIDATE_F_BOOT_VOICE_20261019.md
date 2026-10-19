# Candidate F — boot voice advisory (Vietnamese) — 2026-10-19

**Trạng thái:** recipe đã viết, host gates đã chạy; chưa build CI, chưa flash,
chưa nghiệm thu phần cứng. Token flash chưa cấp.

## 1. Yêu cầu owner và quyết định bị thay thế

Owner yêu cầu bản firmware kế tiếp:

1. Khi khởi động, phát câu chào tiếng Việt **"xin chào chị Diệp"**.
2. Phát cảnh báo tiếng Việt theo ánh sáng môi trường:
   - tối → **"Bật đèn xe"**;
   - sáng → **"Tắt đèn khi trời sáng"**.

Quyết định cũ ghi trong `C2M_NEXT_UPGRADE_PLAN_20261014.md` — "không thêm lời
chào mỗi boot" — bị owner **thay thế rõ ràng** bằng yêu cầu ngày 2026-10-19.
Lịch sử quyết định cũ vẫn được giữ trong kế hoạch; bản F ghi nhận override.

## 2. Phạm vi bản F

Nền bản F là nội dung E2 đã flash (EN core + bộ tài sản C/D/D3/D4/debug, đã
đổi 17 wav hệ thống VI trong `oneed_cust.es`, SSH debug lifetime). F thêm đúng
năm tệp mới dưới `/customer/c2m`:

| Tệp | Vai trò | Mode |
|---|---|---|
| `c2m-light` | đọc chỉ-đọc mức sáng từ ISP AE | 0755 |
| `boot_voice.sh` | hook phát âm thanh một lần mỗi boot | 0755 |
| `Boot_Greeting.wav` | "xin chào chị Diệp" | 0644 |
| `Light_Dark_TurnOn.wav` | "Bật đèn xe" | 0644 |
| `Light_Bright_TurnOff.wav` | "Tắt đèn khi trời sáng" | 0644 |

Không thay đổi camera/kernel/ADAS/cardv/model/calibration/license/bootloader.
Không tệp stock nào bị sửa ngoài hook `wifi/rcInsDriver.sh` đã được kiểm soát
bởi mutation allowlist; mọi tệp stock khác giữ nguyên byte.

## 3. Nhận diện sáng/tối

### 3.1. Bằng chứng tĩnh

`cardv` (stock) gọi `MI_ISP_AE_QueryExposureInfo(0, 0, &info)` và đọc trường
`LVx10` tại `info + 0x230`; nhánh `cardv_detect_FCamAEToPWM` dùng ngưỡng `500`
và ánh xạ `LVx10/10` sang mức đèn nền. Đây là bằng chứng **tĩnh** từ binary
stock, không phải hành vi đã đo trên máy.

### 3.2. Cách F đọc

`c2m-light`:

- `dlopen("libmi_isp.so")` và `dlsym("MI_ISP_AE_QueryExposureInfo")` từ thư viện
  stock trong `/lib` (liên kết `dlopen` từ `libdl-2.30.so` stock, không dùng
  libdl host);
- gọi `(0, 0, &info)` với buffer 0x404 byte, lấy median của 5 mẫu, mỗi mẫu
  cách 200 ms;
- chỉ in `state=dark|bright`, kèm `lv`, số mẫu và ngưỡng;
- `lv` ngoài khoảng hợp lệ hoặc API lỗi → in lỗi ở stderr và thoát `2`.

Ngưỡng mặc định `500` (cùng ngưỡng nhánh đèn nền stock). Ngưỡng này **chưa
được hiệu chuẩn thực địa**; xem mục 7.

### 3.3. Fail-closed

Nếu thư viện/API không khả dụng, giá trị bất thường, hook không có hook khác
để đoán: `boot_voice.sh` **không phát** câu cảnh báo đèn. Câu chào vẫn phát
nếu FIFO cardv sẵn sàng. Không có nhánh suy diễn "trời tối" từ giờ hệ thống.

## 4. Phát âm thanh

`boot_voice.sh` chạy tách rời, một lần mỗi boot (guard `/tmp`):

1. chờ tối đa 15 s cho `/tmp/cardv_fifo` (do `cardv` tạo);
2. gửi `audioplay 1 dev0 /customer/c2m/Boot_Greeting.wav` vào FIFO;
3. chờ 3 s cho câu chào kết thúc;
4. gọi `c2m-light --threshold 500`, chọn đúng một trong hai wav;
5. ghi trạng thái vào `/tmp/c2m_voice_status` (chỉ trong `/tmp`, mode 0600).

Ghi FIFO dùng `timeout 5` của BusyBox để không treo vô hạn nếu cardv chết;
khi thiếu `timeout`, dùng redirect thẳng như các script stock.

`audioplay` dùng chung bộ giải mã âm thanh stock. F phát câu chào sớm trong
luồng boot, trước khi ADAS khởi động; câu cảnh báo đèn phát sau đó. Việc tranh
chấp với cảnh báo ADAS khởi động (nếu có) **chưa được kiểm chứng thực địa**.
Không dùng F để lấn át cảnh báo an toàn; xem mục 7.

## 5. Không có điều khiển đèn xe

C2M **không có đầu ra điều khiển đèn xe đã xác minh** (không tìm thấy GPIO/CAN/
M4 nào trong phân tích tĩnh có thể bật/tắt đèn pha xe). Bản F chỉ phát **lời
nhắc bằng giọng nói**; F không đóng/mở mạch điện nào của xe. Câu "Bật đèn xe"
và "Tắt đèn khi trời sáng" là nhắc tài xế, không phải hành động điều khiển.
Muốn điều khiển đèn thật cần một giao diện phần cứng riêng và đánh giá an toàn
riêng, không thuộc phạm vi bản này.

## 6. Tài sản âm thanh (private vault)

PCM16, mono, 24 kHz, làm bằng Edge TTS `vi-VN-HoaiMyNeural`. Bytes nằm trong
private vault `assets/bootvoice/`; chỉ SHA256 được công bố:

| Tệp | Thời lượng | SHA256 |
|---|---:|---|
| `Boot_Greeting.wav` | ~1.99 s | `c26fcfa8384247cd8030d35b59104b494c8ef9d3741e4f4fbb5544b2f7b1d47d` |
| `Light_Dark_TurnOn.wav` | ~2.81 s | `a20cf9be0f368d6144bb3c4e858c278751482dc7104f42cd422055f3290fe890` |
| `Light_Bright_TurnOff.wav` | ~2.83 s | `59eac76edc1699b07b01887fefd97ae0eef286c0308180977a7b84c8187ea223` |

CI gate kiểm RIFF/WAVE, PCM16, mono, 24 kHz cho từng tệp trước khi cài.

## 7. Chưa được xác minh (phải ghi rõ)

- `MI_ISP_AE_QueryExposureInfo` từ tiến trình riêng có trả dữ liệu hợp lệ trên
  máy thật hay không; nếu không, không có câu cảnh báo đèn.
- Ngưỡng `500` và đơn vị `LVx10` có đúng với ngày/đêm thực tế trên xe không.
  Owner xem `/tmp/c2m_voice_status` sau các lần boot tối/sáng để đối chiếu.
- Tranh chấp bộ giải mã âm thanh với ADAS lúc khởi động; chưa đo thứ tự phát.
- Thời điểm phát câu chào so với âm hiệu chuẩn/khởi động của ADAS.
- Chưa có read-back NAND hay soak; chưa flash.
- Không có điều khiển đèn xe (mục 5).

## 8. Recipe build/CI

- `fw/voice/light.c` — helper chỉ-đọc.
- `fw/voice/boot_voice.sh` — hook một lần, fail-closed.
- `fw/voice/build.sh` — build ARM32/glibc-2.30, QEMU self-test, ELF gate.
- `tools/fw/mutate_customer.py --bootvoice-services-dir` — cài đúng 5 tệp,
  chèn launch tách rời trước khối chờ mount SD.
- `tools/fw/test_bootvoice_gates.py` — 7 host test: exact set, round-trip
  verify, từ chối WAV/ELF/hook sai, launch order, source fail-closed, và test
  Linux dựng `light.c` native với thư viện ISP giả để kiểm offset 0x230,
  median, ngưỡng và nhánh unknown/thoát 2.
- `.github/workflows/firmware-candidateF.yml` — quy trình F đầy đủ (E2 + voice),
  giữ bảo vệ CI cũ, bổ sung pin 3 wav, build/QEMU/ELF gate cho `c2m-light`, và
  kiểm tra allowlist/thứ tự launch.

Private vault: `assets/bootvoice/` đã tạo commit cục bộ (WAV + MP3 + sums +
README + generate.py). **Chưa push lên `origin/main`** trong phiên này (không có
quyền đẩy); phải push trước khi dispatch CI, nếu không bước fetch sẽ fail closed.

Trạng thái host local (2026-10-19):

- `python tools/fw/test_bootvoice_gates.py` — 6/6 OK trên Windows (test
  native-linux bị skip đúng thiết kế; CI Ubuntu chạy đủ 7/7).
- `python tools/fw/test_candidate_e_gates.py` — 8/8 OK.
- `python tools/fw/test_d4_mutation.py` — 13/13 OK (1 skip).
- `python tools/fw/test_debug_mutation.py` — 13/13 OK (1 skip).
- `python fw/device_minimal/test_check_elf.py` — OK (allowlist `libdl.so.2`
  vẫn giữ trần GLIBC 2.30).
- `sh -n fw/voice/boot_voice.sh`, `sh -n fw/voice/build.sh` — OK.

## 9. Điều kiện xác nhận của owner (chưa thực hiện)

1. Dispatch workflow `firmware-candidateF.yml`, kiểm tra mọi gate xanh; nạp
   package vào private vault.
2. Chuẩn bị token cục bộ bằng `tools/fw/reversion_sd_package.py` (fail-closed,
   token mới khác mọi token đã cài), deep validation, ghi thẻ + read-back 4/4.
3. Chỉ flash sau khi owner cho phép; kiểm tra: câu chào khi boot; tiếng Việt
   hệ thống; ADAS/FCW/HMW/ghi hình như trước.
4. Thử tối/sáng: che camera (tối) và để nơi sáng; nghe đúng một câu nhắc; ghi
   lại `/tmp/c2m_voice_status` để hiệu chuẩn ngưỡng.
5. Xác nhận không có thay đổi âm thanh/ghi hình/ADAS ngoài dự kiến. Bất kỳ treo,
   reboot lặp, mất ghi hình hoặc cảnh báo sai → dừng, dùng rollback đã chuẩn bị.

## 10. Liên kết

- `docs/firmware/CANDIDATE_E_20261018.md` — nền E/E2.
- `docs/firmware/C2M_NEXT_UPGRADE_PLAN_20261014.md` — override ghi nhận.
- `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md` — đường phát âm thanh stock.
- `docs/firmware/FLASH_HW_CHECKLIST.md` — quy trình flash phần cứng.
