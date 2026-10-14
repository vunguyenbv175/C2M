# c2m-warner — on-device offline traffic-sign Warner

Daemon chạy **trên cam C2M**, không cần điện thoại, không cần mạng.
Đọc NMEA GPS → so với database biển offline → ghi alert.

## Kiến trúc

```
main.c    daemon loop: mở serial GPS, đọc từng dòng NMEA
nmea.c    parse $xRMC (GP/GN/BD) + verify checksum -> lat/lon/tốc độ/hướng
warner.c  engine cảnh báo (port từ prototype Python ~/workspace/c2m-gps/):
          lookahead = tốc độ × 8s (kẹp 150–600m), lọc bearing ±30°,
          lọc hướng biển ±45°, cooldown 120s/biển
db.c      nạp signs.bin (binary gọn, LE, xem tools/build_signs_bin.py)
```

## Build

```sh
# host (test logic)
cmake -B build-host && cmake --build build-host
./build-host/test_warner          # unit test
ctest --test-dir build-host

# device (ARM — đã build OK, ELF-GATE pass)
cmake -B build-arm -DCMAKE_TOOLCHAIN_FILE=../device_minimal/toolchain-armhf-dyn.cmake
cmake --build build-arm
# xóa NEEDED ld-linux thừa do libm của toolchain Ubuntu tự thêm vào
# (libm-2.30.so gốc trên cam không có entry này; entry trỏ đúng loader đã gate)
patchelf --remove-needed ld-linux-armhf.so.3 build-arm/c2m-warner
python3 ../device_minimal/check_elf.py --allow-dynamic build-arm/c2m-warner
# => ELF-GATE: OK (12.6 KB, glibc max 2.4, no NEON, hard-float)
```

## Database biển

```sh
python3 tools/build_signs_bin.py --demo /tmp/signs.bin
python3 tools/build_signs_bin.py --sqlite signs.db /tmp/signs.bin
```

Triển khai trên cam: copy `signs.bin` vào `/customer/c2m-warner/signs.bin`
(hoặc thẻ SD). Format: magic `C2MSDB01`, u32 count, records 100 bytes
(double lat, double lon, float heading, char type[16], char label[64]).

## GPS input

Mặc định `/dev/ttyS1` @ 9600 8N1 (cardv đọc NMEA từ đây — CONFIRMED từ
`getlog.sh` + strings của cardv). **Rủi ro:** cardv giữ port → daemon đọc
tranh có thể làm mất câu NMEA của cardv. Các phương án, theo thứ tự ưu tiên
khi bring-up trên thiết bị thật:

1. Thử `/dev/ttyS2` trước (getlog.sh đọc cả 2 port; có thể 1 port còn trống).
2. Kiểm tra cardv có giữ ttyS1 persistently không (`lsof`/`fuser` trên cam).
3. Nếu xung đột: đọc với tần suất thấp hoặc chuyển sang tap khác.

## Alert output

v1: ghi `/tmp/c2m_warner.log` + stdout (`ALERT <label> (<type>) <dist>m`).
Điểm móc âm thanh/hiển thị đánh dấu `HOOK` trong main.c — cần verify
runtime format lệnh `play_wav_cmd` qua `/tmp/cardv_fifo` trước khi bật.

## Lưu ý kỹ thuật

- Đồng hồ dùng giờ GPS từ câu RMC (không gọi clock_gettime/gettimeofday:
  toolchain redirect sang `__*_time64@GLIBC_2.34`, không tồn tại trên
  loader 2.30 của cam).
- `warner_angle_diff` không dùng `fmod` (bind `fmod@GLIBC_2.38`).
- Mọi symbol glibc còn lại đều ≤ 2.4 — đã qua gate `check_elf.py`.

## Liên quan

- Stock `edog` engine trong cardv (phát hiện 2026-10-14): xem
  `docs/design/TSR_GPS_FUSION_UPGRADE.md` §7 — nếu crack được format DB
  `/edogs` thì không cần daemon riêng.
- Stock TSR (adas): `docs/reverse/TSR_STOCK_FEATURES_V1.md`.
