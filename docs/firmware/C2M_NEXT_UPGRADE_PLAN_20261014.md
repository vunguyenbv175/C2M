# Kế hoạch nâng cấp C2M sau bản C — 2026-10-14

**Trạng thái:** kế hoạch đề xuất, chưa triển khai firmware D, chưa yêu cầu flash.
**Quyết định đã chốt:** giữ âm thanh/kích hoạt ADAS theo hãng; không thêm lời
chào mỗi boot, không ép hiệu chuẩn lại chỉ để nghe câu chào.

## 1. Kết luận phân tích

Bản C chứng minh đường nâng cấp hẹp trên nền EN là khả thi: đã build qua
pipeline, ghi thẻ đúng hash, người dùng báo flash thành công và nghe cảnh báo
Việt. Chưa đủ bằng chứng để gọi toàn bộ bản C là đã nghiệm thu, đặc biệt TSR.

Hướng tiếp theo nên là:

> **Nghiệm thu C → hoàn thiện chẩn đoán và phục hồi cấu hình → chứng minh TSR
> đầu-cuối → nâng cấp chức năng qua giao diện đã xác minh.**

Không thay ADAS/model/kernel/cardv đồng loạt. Ghi hình và cảnh báo gốc có
quyền ưu tiên cao hơn mọi tính năng mới. Khả năng có trong binary không đồng
nghĩa đã chạy trên máy; cờ bật không đồng nghĩa có kết quả trên màn hình.

## 2. Mốc nền và mức bằng chứng

| Hạng mục | Bằng chứng hiện có | Phần chưa biết |
|---|---|---|
| Firmware C | Pipeline `38505113273` xanh; gói cuối VALID 33 kiểm tra; thẻ read-back 4/4; chủ máy báo flash thành công | Nghiệm thu nhiều boot, ghi hình dài hạn trên đúng C |
| Cảnh báo Việt | Chủ máy nghe tiếng Việt, chọn nhóm LDW/PCW/FCW | Chưa xác nhận riêng từng slot/câu, thời lượng, ưu tiên và chồng âm |
| Câu chào | `audios.txt`: `calib_success` → `adas_activated.wav`; không nghe lúc boot thường | Chưa bắt sự kiện calib ở runtime; không cần thử lại theo lựa chọn chủ máy |
| Daemon chẩn đoán | Binary `0.2.0-sdlog1` không đổi; B mount-wait đã có START/HB thực tế | Chưa đọc bộ log C; START/HB chỉ chứng minh daemon sống |
| TSR | Binary stock có đường TSR; hook C có patch cờ | Giá trị hiệu lực, detector/model, lớp biển hỗ trợ, kết quả nhận diện, app/M4 |
| Đèn giao thông | Có slot `tlr_green_on`; C thêm WAV Việt 1128 ms | Điều kiện kích hoạt và đường phát sự kiện; không suy ra từ TSR biển tốc độ |
| Phục hồi | Giữ firmware A/B đã đóng băng | Flash A không bảo đảm hoàn nguyên cờ TSR đã ghi trong config |

**Bản C hiện trên máy theo lịch sử flash:** token `20261014000002`, SHA256
SD payload `SigmastarUpgradeSD_SSC8838G.bin` là
`ce8969f849629a90081c80ec67792a34d7e828a41512ca35db0e8a9edd0be3b9`.
Đây là hash của gói đã ghi/read-back trên thẻ và được báo đã flash, không
phải kết quả đọc lại NAND hiện thời.

Giữ C làm mốc so sánh mới nhưng chỉ ghi mức **flash thành công + audio Việt
một phần**; không nâng kết luận thành TSR PASS hay full ADAS PASS.

## 3. Các vấn đề phải giải quyết trước tính năng mới

### 3.1. Cấu hình TSR tồn tại qua flash: rollback firmware khác rollback config

`tools/fw/mutate_customer.py:TSR_PATCH_LINES` hiện decode `adas.flag`, tìm
chuỗi `--enable_tsr=false`, rồi ghi cả `adas_de.flag` và `adas.flag` tại
`/customer/minieye/config`. Stock updater bảo toàn thư mục cấu hình này.

Hệ quả:
- Flash A/B bỏ hook không nhất thiết trả TSR về trạng thái trước C.
- C chưa lưu bản gốc trước khi patch; snapshot lấy bây giờ là **sau C**, không
  được gọi là cấu hình trước C.
- Nếu thiếu dòng literal, decode lỗi, có dòng lặp/comment hoặc ghi lỗi, hook
  hiện chưa có báo cáo đủ rõ. Hai file ghi tuần tự không phải một giao dịch
  nguyên tử; cần thiết kế phát hiện/phục hồi ghi dở.
- Cần tìm backup trước C nếu còn. Nếu không có, chỉ thiết kế thao tác tắt cờ
  TSR đã xác minh, không hứa khôi phục nguyên trạng toàn bộ cấu hình.

**Yêu cầu bản sau:** đọc/parse có giới hạn; kiểm tra decode thành công; chỉ
cho phép sửa đúng một khóa đã xác minh; backup riêng tư trước thay đổi;
kiểm chứng byte ngoài khóa không đổi; lưu trạng thái giao dịch và xác nhận
sau ghi. Khóa vắng/lặp/mâu thuẫn phải báo trạng thái, không tự đoán hay chèn.

Ưu tiên nghiên cứu override tạm thời nếu đường nạp flag hỗ trợ và đã được
kiểm chứng. Nếu phải ghi persistent, cần chủ máy chấp thuận riêng cho thao
tác đó; không đưa reset calib/license vào recovery. Recovery cũng phải dùng
token flash hợp lệ, khác token đang cài; giữ nguyên các gói A/B đóng băng.

### 3.2. Thời lượng WAV Việt cần được nghiệm thu, không chỉnh theo suy đoán

Đã đo bằng `wave` từ file giải nén gói C cuối:

| Slot | WAV thực, ms (làm tròn) | `audios.txt`, ms |
|---|---:|---:|
| LDW | 1579 | 1003 |
| PCW | 1535 | 1211 |
| SAG / stop_and_go | 1920 | 1112 |
| VB | 1579 | 1152 |
| calib_success | 2261 | 2047 |
| fail | 3925 | 3562 |
| tlr_green_on | 1128 | 1260 |

VI hãng cũng dùng list này dù độ dài file khác. Đây là **rủi ro cần đo**, chưa
phải bằng chứng bị cắt tiếng. Quan sát câu có đủ, thời gian phản hồi và việc
cảnh báo ưu tiên cao ngắt/chờ cảnh báo thấp. Không kéo dài duration toàn bộ
vì có thể làm cảnh báo an toàn bị trì hoãn. FCW/HMW không đổi trong C.

Chỉ sửa slot có lỗi đã tái hiện: chọn WAV ngắn hơn hoặc sửa duration theo
cơ chế player đã xác minh. Khi sửa list, cập nhật md5 tương ứng; giữ priority
và loop. Không thay toàn bộ audio bằng TTS ở bước này.

### 3.3. Pipeline cần khóa đầu vào và chặn đúng phạm vi thay đổi

Workflow C kiểm SHA của WAV bằng checksum file lấy cùng nhánh vault `main`;
đây là kiểm nhất quán, chưa khóa độc lập một phiên bản asset bất biến.

Việc host cần làm trước bản mới:
- Pin commit vault và hash/list asset kỳ vọng trong cấu hình build; thay
  WAV và checksum cùng lúc không được âm thầm đổi bản build.
- Cứng hóa parser RIFF: duyệt chunk, kiểm tra PCM fmt/data, kích thước và
  số frame, file truncated/không hợp lệ; không chỉ đọc offset header cố định.
- Verifier kiểm cả type/mode/uid/gid cho hook và file thay thế/được thêm,
  ngoài size/hash; ngoại lệ mtime cho file đã sửa phải rõ ràng. Với thư mục,
  size/mtime chỉ là thông tin; danh sách con vẫn phải nằm trong allowlist.
- Allowlist phải là hợp đồng của variant, không chỉ tin mọi path do mutation
  manifest tự khai. Chặn path traversal, symlink và đường ngoài vùng cho phép.
- Test các lỗi cấu hình TSR: absent key/file, true sẵn, invalid base64,
  duplicate key, comment, permission/write failure và gián đoạn giữa hai file.
- Duy trì no-op rebuild, mutated rebuild, ELF/ABI, QEMU, deep validation,
  re-extraction đúng file từ gói cuối và read-back thẻ. QEMU không kiểm được
  camera/IPU/ADAS/M4 thực tế.

## 4. Lộ trình theo cổng nghiệm thu

### P0 — Chốt nghiệm thu C, chưa cần flash mới

**Việc agent:** viết bảng test/công cụ đọc `C2M_DIAG` trên máy tính; phân loại
START/HB, boot mới, log thiếu, reset khả nghi. Đối chiếu video/audio ghi lại.
Không suy từ mất HB ra ADAS crash: thẻ/mount/log-cap cũng có thể gây mất log.

**Việc cần chủ máy cung cấp:**
1. Thẻ ghi hình sau một phiên trên 6 phút để lấy START + ít nhất một HB.
2. Ba lần bật máy độc lập và một phiên chạy thông thường 30–60 phút.
3. Xác nhận app/live view/ghi hình; kiểm clip có phát được, gap bất thường,
   hỏng file hoặc reboot. Ghi thời gian xuất hiện và hoàn cảnh nếu có lỗi.
4. TSR ghi riêng: biển thực tế, thời điểm, màn hình/app hiện gì; đèn giao
   thông có phát “Đèn xanh” không. Không nghe cũng là kết quả cần ghi.

**PASS nền:** không thấy regression mới trong các tình huống đã thử, clip
liên tục theo hành vi stock, audio Việt nghe rõ. Soak 24 giờ ghi hình có
nguồn ổn định là cổng sau đó trước khi gọi bản ổn định; không có UART/shell
thì vẫn ghi rõ giới hạn bằng chứng.

**STOP:** treo, reboot lặp, mất/gián đoạn ghi hình mới, ADAS im bất thường,
hoặc cảnh báo sai gây phân tâm. Dừng phát triển tính năng và xử lý recovery.
Không tạo tình huống nguy hiểm để ép FCW/PCW/LDW; dùng hành khách/recording
quan sát, không thao tác app khi đang lái.

### P1 — Công cụ host + thiết kế phục hồi cấu hình

Không phụ thuộc xe đang kết nối:
- Công cụ đề xuất `tools/diag/parse_c2m_diag.py` và
  `tools/diag/audio_contract_report.py` (chưa tồn tại tại lúc viết kế hoạch).
- Báo cáo acceptance C với trạng thái `PASS / FAIL / UNVERIFIED / BLOCKED`
  từng hạng mục, tránh một nhãn xanh che nhiều phần chưa test.
- Các cải tiến pipeline ở mục 3.3, test negative trước khi build.
- Recovery spec: phân biệt hoàn nguyên firmware với tắt/hoàn nguyên cờ TSR;
  tìm backup trước C, xác minh backup hiện tại và cơ chế restore.

**Cổng:** test host pass; sai asset, sai phạm vi, cấu hình bất thường đều bị
chặn; recovery chưa được xác minh thì không công bố “rollback an toàn”.

### P2 — Candidate D1: chẩn đoán nhẹ, không thêm tính năng ADAS

**Mục tiêu:** quan sát được máy đang làm gì mà không cần shell trong các
phiên dùng bình thường. Đây là candidate firmware kế tiếp được khuyến nghị.

Phạm vi đề xuất:
- Giữ wav/list C và binary stock ADAS/cardv/model/kernel/rootfs/bootloader.
- Nâng daemon chỉ đọc dữ liệu đã cho phép: uptime, MemAvailable, tải CPU,
  trạng thái mount, dung lượng SD và sự tồn tại của process theo tên đã
  xác minh (`cardv`, ADAS/supervisor). Không đọc frame/raw_adas hay `/dev`.
- Có thể báo trạng thái riêng khóa TSR sau khi parser và đường đọc đã được
  kiểm chứng; không dump toàn bộ flag/cmdline/license/serial hay config.
- Log tăng dần có giới hạn, ring/cap, rate limit; thẻ vắng/đầy/lỗi phải bỏ
  chẩn đoán mà không làm thay đổi stock. Không watchdog tự reboot/kill ADAS.
- Chỉ ghi thư mục chẩn đoán SD và marker tạm được duyệt. **D1 không có quyền
  sửa persistent config**; hook TSR hiện hữu của C là vấn đề riêng phải được
  review, không ngầm mở rộng trong daemon.
- Bắt đầu chỉ có telemetry process/mount/memory; không thêm socket/web/API
  nếu chưa có yêu cầu cần thiết.

**Ngân sách mục tiêu, chưa đo trên cam:** mẫu mỗi 60 s, heartbeat 5 phút;
CPU trung bình ≤1%, RSS ≤2 MiB, tổng log ≤1 MiB. Điều chỉnh theo khả năng
đo thực tế, ghi rõ khi không đo được. I/O best-effort không tự chứng minh
không block: cần thử thẻ chậm/đầy trên host và đối chiếu ghi hình thực tế.

**Cổng:** test host fault injection + ABI/ELF/QEMU + deep image pass; flash
được chủ máy xác nhận riêng; 3 cold boots, phiên 30–60 phút, clip nguyên vẹn,
log đúng schema và không có dữ liệu nhạy cảm. Hỏng telemetry phải chỉ mất
telemetry, không kéo theo ghi hình/ADAS.

### P3 — Candidate D2 / nhánh TSR: kiểm chứng đầu-cuối và điều khiển có phục hồi

Không gộp với D1 để tách nguyên nhân lỗi. Trước tiên thu bằng chứng trên C,
sau đó chỉ build nếu thật sự cần thêm quan sát/guard/enable-disable.

Tách hai tính năng, không coi chúng là một:
- **Biển báo/tốc độ:** ảnh đầu vào → detector/class → kết quả giới hạn tốc độ
  → kênh xuất → app/M4. Cần xác minh từng đoạn, không bịa trường packet/port.
- **Đèn giao thông:** detector/event `tlr_green_on` → player → WAV. Cần xác
  minh flag/gate riêng nếu có; việc TSR true không chứng minh gate này mở.

Quy trình:
1. Xác minh giá trị hiệu lực và loại flag thực tế; thiếu key không kết luận
   true. Không in dữ liệu cấu hình nhạy cảm ra artifact public.
2. Đọc static/reverse đường TSR và ScreenService; nếu có giao diện được phép,
   bắt dữ liệu thụ động để tìm sự kiện. Chưa cho phép truy cập thì ghi BLOCKED.
3. Lập bảng 10–20 lượt quan sát ban ngày, tuyến cố định: biển/lớp đã xác minh,
   đúng/sai/bỏ sót, độ trễ, màn hình có cập nhật không. Tách đêm/mưa thành đợt
   sau. Quy mô này chỉ là smoke test, không chứng nhận độ tin cậy an toàn.
4. Nếu có recognition nhưng không hiển thị: sửa đúng lớp adapter/display
   sau khi biết contract; không đổi model nhằm chữa lỗi output.
5. Nếu không có recognition: kiểm input/gate/model/log trước; chỉ thử model
   khác sau khi có toolchain và bằng chứng tương thích.
6. Triển khai enable/disable có guard + backup/recovery (mục 3.1) nếu owner
   duyệt; test trạng thái true/false qua reboot và restore riêng phần config.

**Cổng TSR ban đầu:** ít nhất một lớp biển thực sự nhận diện và xuất đúng
đầu-cuối qua nhiều lượt; báo riêng false positive/miss. Từng lớp chưa thử
vẫn UNVERIFIED. Traffic-light PASS phải có sự kiện và âm thực tế riêng.
Nếu không có quyền shell/capture, không suy luận lấp khoảng trống; ưu tiên
màn hình/video/log được phép và giữ mức PARTIAL.

## 5. Các nâng cấp sản phẩm sau nền ổn định

Phần này được quyết định theo dữ liệu P0–P3, không phải cam kết tất cả cùng
chạy được trên C2M. Chỉ làm một nhánh can thiệp tại một thời điểm.

| Ưu tiên | Tính năng | Điều kiện vào | Giới hạn/rủi ro |
|---|---|---|---|
| Cao | TSR có trạng thái rõ và cách tắt an toàn | P3 chứng minh detector/output, recovery được kiểm | Không quảng cáo nhận mọi biển Việt Nam |
| Vừa | Việt hóa thêm âm hệ thống | Có nhu cầu thực tế, map sự kiện player và integrity `oneed_cust` | Mở rộng allowlist partition riêng; không lấy toàn bộ VI firmware |
| Vừa | Màn hình trạng thái/quan sát ADAS | Contract app/M4 thu thụ động và decoder đã biết | Bắt đầu read-only; chưa bật transmit/proxy |
| Sau | Cảnh báo tốc độ theo dữ liệu bản đồ | GPS/heading và dữ liệu hợp pháp, schema đã xác minh | Không suy từ string “VietMap”; cảnh báo có timeout và chỉ rõ nguồn |
| Sau | TPMS/BLE | Có thiết bị/sensor thực, transport và protocol đã bắt | Chưa mặc định cam có BLE hoặc dùng được USB dongle |
| Xa | AI tùy chỉnh/biển Việt Nam | Toolchain IPU đúng model format, frame contract, RAM/CPU đo thực tế | Không deploy ONNX/TFLite trực tiếp theo phỏng đoán; stock recorder luôn ưu tiên |

Không thêm lời chào mỗi boot. Không mở telnet/SSH đoán mật khẩu, không biến
cam thành máy chủ quản trị mới chỉ để có giao diện đẹp. EN/VI binary bisect
là nhánh nghiên cứu nguyên nhân regression riêng, không là nâng cấp mặc định
cho máy đang có ADAS hoạt động.

## 6. Hợp đồng thực thi và quản lý bản build

- Mỗi candidate tái dựng từ EN golden + bộ thay đổi đã pin, không chồng patch
  không kiểm soát lên binary đã flash. So sánh cả với golden lẫn mốc C.
- Giữ ABI ARMv7-A hard-float, VFPv3-D16, glibc ≤2.30; không tự bật NEON chỉ
  vì ARMv7. Mỗi symbol/dependency mới phải qua ELF gate và stock-rootfs QEMU.
- Không thay camera/calibration/license; không đọc/ghi thiết bị vật lý hoặc
  gửi lệnh IPC chưa được chấp thuận. Probing cam tiếp tục read-only.
- Firmware/audio/model/config riêng tư nằm vault; public chỉ code, contract,
  hash, báo cáo đã loại dữ liệu nhạy cảm. Không đưa config gốc vào diag public.
- Token mới cấp khi build, phải khác stock và token đang cài; xác minh trạng
  thái máy trước flash, không tái sử dụng token recovery đã hết hiệu lực.
- Thẻ: xác minh physical disk/partition/label **trước mọi ghi/xóa/chkdsk**,
  archive log cũ, không format nếu không cần, stage+flush+4/4 read-back,
  tháo thẻ an toàn. Dirty/unhealthy phải dừng để đánh giá, không bỏ qua guard.
- Fail ở bất kỳ cổng nào: chưa dispatch/flash bước kế tiếp. Có phương án
  phục hồi đã review không có nghĩa được tự ghi config vào máy.

## 7. Thứ tự công việc gần nhất

1. Viết parser log + mẫu acceptance C trên host; lấy thẻ ghi hình khi chủ máy
   tiện, không cần nạp bản mới chỉ để tiếp tục test audio/TSR.
2. Khóa asset/variant, bổ sung verifier/parser/test lỗi; chuẩn bị recovery spec.
3. Thiết kế và test D1 chẩn đoán nhẹ; chỉ tạo gói flash sau khi cổng nền và
   recovery review đủ, rồi xin chủ máy xác nhận thao tác flash.
4. TSR: thu bằng chứng trên C song song với việc host; quyết định cần D2 hay
   sửa display/flags sau kết quả, không bật thêm cờ vô tội vạ.
5. Chọn một nhánh sản phẩm trong mục 5 khi ghi hình/audio/nền đã ổn định.

**Ước lượng công sức, không phải lịch cam kết:** P1 khoảng 1–2 phiên làm việc;
D1 khoảng 2–4 phiên gồm host tests/build/review; TSR phụ thuộc quyền capture,
đường chạy và thiết bị màn hình nên chưa chốt thời hạn. Soak/road test là
thời gian nghiệm thu riêng. Không đặt ngày hoàn tất AI/TPMS khi interface và
SDK còn chưa được chứng minh.

## 8. Hồ sơ tham chiếu và xác minh khi lập kế hoạch

- `docs/firmware/CANDIDATE_C_VIAUDIO_TSR.md`: định danh gói C và kết quả owner.
- `docs/firmware/C2M_AUDIO_TSR_MECHANISM.md`: audio mapping, flag persistence.
- `tools/fw/mutate_customer.py`, `tools/fw/verify_b_manifest.py`,
  `.github/workflows/firmware-candidateC.yml`: phạm vi mutation/gates hiện tại.
- `fw/device_minimal/c2m_idle.c`, `docs/firmware/TARGET_ABI.md`: nền daemon/ABI.
- `docs/firmware_en_vi/10_CODING_AGENT_WORKPLAN.md` và
  `09_REGRESSION_BISECT_PLAN.md`: không thay hệ thống khi interface chưa biết.

Đã chạy lại trên host lúc lập kế hoạch: `tests/test_candidate_b.py`,
`fw/device_minimal/test_check_elf.py`, `test_sdlog.py`, `test_startup_abi.py`
đều PASS. Đã đo frame/duration/hash 8 WAV của gói C cuối. Những kiểm tra này
không thay thế kiểm chứng phần cứng; phiên lập kế hoạch không ghi vào cam,
thẻ hoặc flash firmware mới.
