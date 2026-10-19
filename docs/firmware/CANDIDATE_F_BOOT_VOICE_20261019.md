# Candidate F — boot voice advisory (Vietnamese) — 2026-10-19

**Trạng thái:** recipe F đã được CI xác nhận đầy đủ tại run
[`39287717224`](https://github.com/vunguyenbv175/C2M/actions/runs/39287717224)
(commit `f954e0d`): toàn bộ gate xanh, gồm boot voice helper build/QEMU/host
tests 7/7, exact five-file deploy, P2/P3 allowlist và publish private vault.
Deliverable riêng tư: `deliverables/20261019-f-r39287717224` (vault commit
`371e54d`), **giữ nguyên stock token — NOT FLASH-READY**. Token cục bộ đề xuất
`20261019000001` đã được chuẩn bị bằng `reversion_sd_package.py`:
`ALLOWLIST-OK`, read-back host 4/4, chỉ đổi token 14 byte + `sysVer.txt` +
`minieye_firmware.md5`. **Chưa flash, chưa nghiệm thu phần cứng; đang chờ owner
xác nhận token và cho phép flash.**

## 1. Yêu cầu owner và quyết định bị thay thế

Owner yêu cầu bản firmware kế tiếp:

1. Khi khởi động, phát câu chào tiếng Việt **"xin chào chị Diệp"**.
2. Phát cảnh báo tiếng Việt theo trạng thái ngày/đêm của C2M:
   - tối → **"Bật đèn xe"**;
   - sáng → **"Tắt đèn khi trời sáng"**.

Bản F dùng **lịch ngày/đêm stock của C2M** (06:00:01–17:59:59) làm nguồn mặc
định. Helper đọc ISP AE (`c2m-light`) chỉ dùng **thủ công** sau khi owner xác
minh trên máy; lý do: chưa chứng minh được một tiến trình thứ hai gọi ISP an
toàn, và mở client ISP thứ hai lúc boot có thể ảnh hưởng `cardv`. Lịch stock là
theo giờ, không phải cảm biến lux; xem mục 7.

Quyết định cũ ghi trong `C2M_NEXT_UPGRADE_PLAN_20261014.md` — "không thêm lời
chào mỗi boot" — bị owner **thay thế rõ ràng** bằng yêu cầu ngày 2026-10-19.
Lịch sử quyết định cũ vẫn được giữ trong kế hoạch; bản F ghi nhận override.

## 2. Phạm vi bản F

Nền bản F là nội dung E2 đã flash (EN core + bộ tài sản C/D/D3/D4/debug, đã
đổi 17 wav hệ thống VI trong `oneed_cust.es`, SSH debug lifetime). F thêm đúng
năm tệp mới dưới `/customer/c2m`:

| Tệp | Vai trò | Mode |
|---|---|---|
| `c2m-light` | helper đọc chỉ-đọc ISP AE; **chỉ dùng thủ công** | 0755 |
| `boot_voice.sh` | hook phát chào + một nhắc đèn theo lịch stock | 0755 |
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
stock, không phải hành vi đã đo trên máy. Trong bản build này hàm đó chỉ còn
trong dynsym, không thấy call site trực tiếp; vì vậy F **không** dựa vào nó để
lấy trạng thái lúc boot.

### 3.2. Nguồn mặc định: lịch ngày/đêm stock

`SendDisplayModeToScreenv` trong `cardv` dùng cửa sổ ban ngày **06:00:01 đến
17:59:59** (06:00:00 và 18:00:00 là tối). `boot_voice.sh` tính lại đúng cửa sổ
này bằng `date +%H`, `%M`, `%S` của BusyBox:

- 06:00:01–17:59:59 → `bright` → `Light_Bright_TurnOff.wav`;
- còn lại → `dark` → `Light_Dark_TurnOn.wav`.

Đây là trạng thái ngày/đêm mà C2M stock dùng để đổi giao diện; không phải cảm
biến lux. Nó không mở thêm client ISP và không phụ thuộc thư viện vendor.

### 3.3. Helper AE thủ công (`c2m-light`)

`c2m-light` là công cụ **kiểm chứng thủ công**, không phải nguồn boot mặc định:

- preload `libmi_sys.so`, `libcam_os_wrapper.so`, `libcus3a.so` bằng
  `RTLD_GLOBAL` (vì `libmi_isp.so` không khai báo các thư viện này trong
  `DT_NEEDED`), rồi `dlopen("libmi_isp.so")`;
- `dlsym("MI_ISP_AE_QueryExposureInfo")` và gọi `(0, 0, &info)` với buffer
  0x404 byte; đọc `LVx10` tại `info + 0x230`, lấy median 5 mẫu cách 200 ms;
- chỉ in `state=dark|bright` kèm `lv`, số mẫu, ngưỡng;
- `lv` ngoài khoảng hợp lệ hoặc API lỗi → stderr và thoát `2`.

Hook chỉ gọi helper khi tồn tại `/customer/c2m/AE_LIGHT_ENABLE`, do owner tạo
**sau khi** chạy thử và xác nhận `cardv`, ghi hình, ADAS không bị ảnh hưởng.
Ngưỡng mặc định `500` (cùng ngưỡng nhánh đèn nền stock) **chưa hiệu chuẩn thực
địa**.

### 3.4. Fail-closed

Nguồn mặc định (lịch stock) không phụ thuộc API AE. Nếu `date` lỗi hoặc trạng
thái không hợp lệ, hook **không phát** câu cảnh báo đèn và ghi
`light=unknown`; câu chào vẫn phát nếu FIFO cardv sẵn sàng. Nếu helper AE được
bật nhưng lỗi/không hợp lệ, hook **quay về lịch stock**, không đoán theo giá
trị AE sai.

## 4. Phát âm thanh

`boot_voice.sh` chạy tách rời, một lần mỗi boot (guard `/tmp`):

1. chờ tối đa 15 s cho `/tmp/cardv_fifo` (do `cardv` tạo);
2. gửi `audioplay 1 dev0 /customer/c2m/Boot_Greeting.wav` vào FIFO;
3. chờ 3 s cho câu chào kết thúc;
4. nếu có `AE_LIGHT_ENABLE`: gọi `timeout 10 c2m-light --threshold 500`
   (chỉ dùng kết quả `state=dark|bright` hợp lệ); nếu không, hoặc nếu helper
   lỗi, dùng lịch stock 06:00:01–17:59:59;
5. chọn đúng một trong hai wav và phát;
6. ghi trạng thái vào `/tmp/c2m_voice_status` (chỉ trong `/tmp`, mode 0600).

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

- Lịch stock là **theo giờ**, không phải cảm biến ánh sáng. Trời âm u, gara,
  hầm hoặc hoàng hôn có thể lệch với "trời sáng" thực tế. Đây là giới hạn đã
  biết của nguồn mặc định.
- Đồng hồ hệ thống phải đúng; lịch stock dùng cùng clock với giao diện C2M.
- `MI_ISP_AE_QueryExposureInfo` từ tiến trình riêng có trả dữ liệu hợp lệ trên
  máy thật hay không; chưa xác minh. Helper preload ba thư viện vendor; việc mở
  client ISP thứ hai có thể ảnh hưởng `cardv`, nên **không bật tự động**.
- Ngưỡng `500` và đơn vị `LVx10` có đúng với ngày/đêm thực tế trên xe không.
  Owner chạy helper thủ công và xem `lv` trước khi tạo `AE_LIGHT_ENABLE`.
- Tranh chấp bộ giải mã âm thanh với ADAS lúc khởi động; chưa đo thứ tự phát.
- Thời điểm phát câu chào so với âm hiệu chuẩn/khởi động của ADAS.
- Chưa có read-back NAND hay soak; chưa flash.
- Không có điều khiển đèn xe (mục 5).

## 8. Recipe build/CI

- `fw/voice/light.c` — helper chỉ-đọc.
- `fw/voice/boot_voice.sh` — hook một lần, fail-closed.
- `fw/voice/build.sh` — build ARM32/glibc-2.30, QEMU self-test, ELF gate; link
  stock `libdl-2.30.so` với `--allow-shlib-undefined` (các ký hiệu
  `_dl_*@GLIBC_PRIVATE` do `ld-linux-armhf.so.3` stock giải quyết lúc chạy).
- `tools/fw/mutate_customer.py --bootvoice-services-dir` — cài đúng 5 tệp,
  chèn launch tách rời trước khối chờ mount SD.
- `tools/fw/test_bootvoice_gates.py` — 7 host test: exact set, round-trip
  verify, từ chối WAV/ELF/hook sai, launch order, source fail-closed, và test
  Linux dựng `light.c` native với thư viện ISP giả để kiểm offset 0x230,
  median, ngưỡng và nhánh unknown/thoát 2.
- `.github/workflows/firmware-candidateF.yml` — quy trình F đầy đủ (E2 + voice),
  giữ bảo vệ CI cũ, bổ sung pin 3 wav, build/QEMU/ELF gate cho `c2m-light`, và
  kiểm tra allowlist/thứ tự launch.

Private vault: `assets/bootvoice/` đã push lên `origin/main` (commit
`8413b0b`; WAV + MP3 + sums + README + generate.py). CI fetch đã xác nhận đúng
3 WAV và pin SHA256.

Vault `origin/main` đã có deliverable F: commit `371e54d`,
`deliverables/20261019-f-r39287717224/c2m-flash/` gồm `C2M_FLASH_A/`,
`C2M_FLASH_F/`, `EN_REPACK_GOLDEN.tar` (A), `EN_ENHANCE_IDLE.tar` (F),
`BUILD_EVIDENCE/` và `OPEN_SOURCE/`. Bốn tệp F đúng pin CI:
bin `1ca3ea4b...`, adas `0e18c91f...`, md5 `79f85f...`, sysVer `7cc079...`.

CI: run `39279662410` (commit cũ) dừng ở link vì `-Wl,--no-undefined` gặp
`_dl_*@GLIBC_PRIVATE` của stock `libdl-2.30.so`; đã sửa bằng
`-Wl,--allow-shlib-undefined`. Run sạch
[`39287717224`](https://github.com/vunguyenbv175/C2M/actions/runs/39287717224)
thành công toàn bộ: boot voice helper build + QEMU self-test `c2m-light 0.2.0`
+ 7/7 host test; ELF gate `NEEDED=['libdl.so.2','libc.so.6']`, max GLIBC 2.4;
exact five-file deploy; P2/P3 `ALLOWLIST-OK`; release layout giữ stock token;
publish vault và upload evidence. Artifact công khai `candidateF-evidence`
(id `12204861285`) chỉ chứa source/hash/báo cáo, không có firmware/audio/key
bytes.

Trạng thái host local (2026-10-19):

- `python tools/fw/test_bootvoice_gates.py` — 6/6 OK trên Windows (test
  native-linux bị skip đúng thiết kế; CI Ubuntu chạy đủ 7/7).
- `python tools/fw/test_candidate_e_gates.py` — 8/8 OK.
- `python tools/fw/test_d4_mutation.py` — 13/13 OK (1 skip).
- `python tools/fw/test_debug_mutation.py` — 13/13 OK (1 skip).
- `python fw/device_minimal/test_check_elf.py` — OK (allowlist `libdl.so.2`
  vẫn giữ trần GLIBC 2.30).
- `sh -n fw/voice/boot_voice.sh`, `sh -n fw/voice/build.sh` — OK.

## 9. Chuẩn bị token cục bộ và điều kiện xác nhận của owner

1. CI đã xong: run `39287717224` xanh toàn bộ; package F nằm trong private
   vault (`deliverables/20261019-f-r39287717224`, commit `371e54d`), vẫn giữ
   stock token.
2. Token cục bộ đã chuẩn bị bằng `tools/fw/reversion_sd_package.py` trên đúng
   bốn tệp F lấy từ vault (pin khớp CI), token đề xuất **`20261019000001`**
   (khác mọi token đã cài/đã đặt trước). Kết quả:
   - `verdict=ALLOWLIST-OK`, `readback_verified=true`,
     `host_byte_proof_only=true`, `device_tested=false`, `flash_proven=false`;
   - chỉ đổi token 14 byte trong inner image, `sysVer.txt` và
     `minieye_firmware.md5`; mọi load command/padding/footer/`adas_upgrade.sh`
     giữ nguyên;
   - output: bin `04de4ddb...`, sysVer `0fba8463...`, md5 `741a68bb...`,
     adas `0e18c91f...`; md5 sidecar mới khớp MD5 inner `174c5982...`.
   Bản chuẩn bị nằm cục bộ (không nằm trong repo công khai); chỉ dùng bản này
   để ghi thẻ, không dùng raw `C2M_FLASH_F/`.
3. **Chờ owner xác nhận token `20261019000001` và cho phép flash.** Chưa flash;
   chỉ flash sau khi owner cho phép.
4. Nghe đúng một câu chào và đúng một câu nhắc đèn; kiểm tra
   `/tmp/c2m_voice_status` (`source=theme`, `schedule=06:00:01-17:59:59`).
   Thử cả hai khung giờ (sáng/tối) bằng cách đổi giờ hệ thống trong cửa sổ test
   hoặc chờ đúng giờ; không cần che camera cho nguồn mặc định.
5. Nếu owner muốn thử AE: SSH chạy `/customer/c2m/c2m-light --threshold 500`
   trong điều kiện sáng/tối đã biết; so `lv` với thực tế. Chỉ khi helper trả
   đúng và `cardv`/ghi hình/ADAS không bị ảnh hưởng, tạo
   `/customer/c2m/AE_LIGHT_ENABLE` rồi reboot. Nếu helper gây treo, mất ghi
   hình hoặc bất thường: reboot ngay, **không tạo marker**; nếu đã tạo thì xóa
   và quay về lịch stock.
6. Xác nhận không có thay đổi âm thanh/ghi hình/ADAS ngoài dự kiến. Bất kỳ treo,
   reboot lặp, mất ghi hình hoặc cảnh báo sai → dừng, dùng rollback đã chuẩn bị.

## 10. Liên kết

- CI F: https://github.com/vunguyenbv175/C2M/actions/runs/39287717224
  (artifact `candidateF-evidence`, id `12204861285`).
- Private vault F: `deliverables/20261019-f-r39287717224` (commit `371e54d`).
- `docs/firmware/CANDIDATE_E_20261018.md` — nền E/E2.
- `docs/firmware/C2M_NEXT_UPGRADE_PLAN_20261014.md` — override ghi nhận.
- `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md` — đường phát âm thanh stock.
- `docs/firmware/FLASH_HW_CHECKLIST.md` — quy trình flash phần cứng.
