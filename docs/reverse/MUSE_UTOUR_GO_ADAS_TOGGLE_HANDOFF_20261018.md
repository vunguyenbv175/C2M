# Muse.ai — truy lỗi UTOUR GO hiển thị cảnh báo ADAS tắt sau khi lưu

Ngày bàn giao: 2026-10-18. Mục tiêu: nối tiếp lần phân tích APK UTOUR GO trước đây của Muse.ai, tìm đúng nguyên nhân và đề xuất bản sửa có bằng chứng. Đây là tài liệu chẩn đoán, **không phải kết luận đã sửa lỗi**.

## Prompt ngắn để gửi Muse.ai

> Tiếp tục từ bộ APK UTOUR GO bạn đã phân tích trước đây. Đọc `docs/reverse/MUSE_UTOUR_GO_ADAS_TOGGLE_HANDOFF_20261018.md` trong repo C2M. Truy nhánh Android c2: vì sao app hiển thị mọi cảnh báo ADAS tắt khi mở lại, dù camera đã lưu và GET `ADAS.config` vẫn trả FCW/HMW bật mức 3. Cần chỉ rõ listener/ViewModel/repository/parser, request thực tế, điều kiện trả nút về OFF; kiểm tra app có dùng `ADAS.enable` GET thiếu giá trị hay không. Đừng coi lần restart ADAS hoặc calib_state=1 là nguyên nhân: bằng chứng firmware đã phân biệt ở file bàn giao. Trả call chain, method/smali/offset và đề xuất sửa tối thiểu + test; không gọi setter, reset, hiệu chuẩn, kích hoạt license hay yêu cầu thử lại trên xe.

## 1. Triệu chứng chính xác từ chủ máy

- Camera C2M đã flash D5-VI; app trên điện thoại là **UTOUR GO Android**, chưa biết phiên bản hiện tại.
- Trong **trang ADAS của app**, bật cảnh báo → hình nhận diện phương tiện/làn trên màn M4 mất tạm thời → sau đó hiện lại.
- Mở lại trang ADAS thấy các cảnh báo hiển thị **tắt**.
- Chủ máy xác nhận lỗi xảy ra với các cảnh báo nói chung, không chỉ một nút FCW.
- Trong lần kiểm tra có giám sát, chủ máy **chỉ chọn bật hai mục**. Cấu hình camera sau lần lưu có FCW và HMW bật; các mục khác tắt. **Không được diễn giải việc các mục còn lại tắt là camera tự làm mất lựa chọn**: điều đó phù hợp với lần chọn hai mục của chủ máy.
- Chưa có ảnh/nguyên văn thông báo mà chủ máy mô tả là “lỗi ADAS”; chưa có bằng chứng về thông báo lỗi cụ thể hoặc mã lỗi từ app.
- Chưa chứng minh cảnh báo âm thanh thực tế đang hoạt động hay bị chặn. Nhận diện vẫn chạy không đủ chứng minh phần cảnh báo hoạt động.

## 2. Bằng chứng live đã thu được

Agent chỉ đọc; chủ máy đồng ý tự thao tác đúng một lần khi xe đỗ. Không mở thêm client vào stream M4/WebSocket single-client. Không agent-side setter, reset, hiệu chuẩn, sửa license hoặc chủ động restart dịch vụ.

### 2.1. Tính toàn vẹn firmware

- 17 file C2M + 10 WAV ADAS: **27/27 SHA-256 khớp manifest bản D5 phát hành**.
- Kiểm tra rộng hơn toàn bộ nhóm file ADAS và CGI: **114/114 khớp manifest** (nhóm này có bao gồm WAV, không cộng thành 141 file độc lập).
- `cardv` cũng khớp binary VI gốc.
- Như vậy chưa có bằng chứng chương trình bị sửa/hỏng trên thiết bị sau flash. Điều này **không loại trừ lỗi logic hoặc tương thích** trong firmware/app.

### 2.2. Một lần lưu cấu hình và thay PID

Theo mẫu quan sát cách nhau khoảng 2–5 giây; thời gian dưới đây là **UTC của laptop**, không dùng đồng hồ camera để suy thời điểm:

| Thời điểm | Quan sát |
|---|---|
| 01:09:41 | ADAS PID 2080; lane 2079/2082; mutualism 2073–2076 |
| 01:10:21 | `adas.flag` đổi hash; bản giải mã và PID cũ chưa đổi |
| 01:10:36 | Không còn quan sát được ADAS/lane/mutualism trong mẫu |
| 01:10:38 | Mutualism mới xuất hiện; `adas_de.flag` đã đổi hash |
| 01:10:47 | ADAS PID 4061; lane 4060/4062 |
| 01:12:39 | Các PID mới vẫn tồn tại, hash cấu hình mới giữ nguyên |

- Đợt quan sát hoàn tất **63/63 lệnh SSH thành công**. Mẫu đang ghi dở trong lúc đọc log không phải bằng chứng mất kết nối hay crash.
- Hai file hiệu chuẩn không đổi hash qua thao tác; trạng thái số của cả bản mã hóa và bản giải mã đều là `install_calib_state=1`.
- Sau restart, một tiến trình ADAS và các dịch vụ C2M hiện diện; cả ba liên kết M4 8080/24012/26012 được thiết lập lại.

### 2.3. Cấu hình sau lần chọn hai mục

Chỉ các cờ chức năng chung được liệt kê; không có license/SN, geometry hiệu chuẩn hoặc cấu hình riêng đầy đủ.

| Nhóm | Giá trị sau lưu |
|---|---|
| `enable_vehicle` | `true` |
| `enable_fcw`, `fcw_level` | `true`, `3` |
| `enable_hmw`, `hmw_level` | `true`, `3` |
| `enable_ufcw`, `ufcw_level` | `false`, `0` |
| `enable_sag`, `sag_level` | `false`, `0` |
| `enable_ldw`, `ldw_level` | `false`, `0` |
| `enable_pcw`, `pcw_level` | `false`, `0` |
| `headway_warning_speed_thresh` | `30` |

- Nội dung giải mã từ `adas.flag` khớp `adas_de.flag` sau restart.
- Năm khóa TSR trước đó có trong cấu hình không còn sau lần ghi toàn bộ: `enable_tsr`, `tsrw_interval`, `tsrw_sli_over_min_ratio`, `tsrw_sli_over_min_thresh`, `tsrw_sli_host_speed_min_thresh`.
- Đây là thay đổi persistence riêng cần ghi nhận, **không đủ để quy nguyên nhân lỗi tất cả công tắc OFF cho TSR**.
- Hook TSR chỉ chạy lúc boot; trạng thái `ALREADY_APPLIED` còn lại từ boot không xác nhận cấu hình mới sau app save. Không chạy hook để “sửa thử”.

### 2.4. Đọc qua HTTP của chính camera, không chỉ qua SSH

GET đã được phân tích tĩnh trước khi gọi; file nguồn đã tồn tại.

```text
GET /cgi-bin/Config.cgi?action=get&property=ADAS.config&VersionPrototal=1.0.1
HTTP 200
0
OK
ADAS.config=<base64>
```

- Giá trị base64 dài 496 byte, strict-valid, giải mã 372 byte/19 dòng cờ hợp lệ.
- Hash dữ liệu giải mã qua HTTP khớp file `adas_de.flag` đang dùng.
- FCW/HMW qua API cũng là **true / 3**.
- File nguồn dài 640 byte: prefix base64 496 byte, sau đó NUL và vùng đệm. **Không thấy prefix bị cắt cụt ở lần này**; không được suy “fixed 640 byte chắc chắn gây truncation” chỉ từ kích thước file.
- Không có CR/NUL trong dữ liệu giải mã; có LF cuối. Response có ba dòng: `0`, `OK`, `ADAS.config=...`.

GET khác đã phân tích tĩnh và xác minh live:

```text
GET /cgi-bin/Config.cgi?action=get&property=ADAS.enable&VersionPrototal=1.0.1
HTTP 200
0
OK
```

**Không có dòng `ADAS.enable=<value>`.** `0` là mã thành công chung của CGI, **không phải bằng chứng trạng thái OFF**.

Chưa biết app có gọi getter thiếu giá trị này hay không; chưa biết parser mặc định OFF hay không. Đây là câu hỏi cần APK trả lời, chưa phải nguyên nhân đã chứng minh.

## 3. Những đường firmware đã truy được

Các địa chỉ dưới đây từ static trace của firmware VI gốc, binary cài trên máy khớp bản đã phân tích. Đây là mốc để cross-check, không yêu cầu Muse tin suy đoán thay cho mã APK.

### 3.1. Restart sau config save là thiết kế có chủ đích

1. `Config.cgi::ExeCgiCmd` tại `0x11b20` xử lý `ADAS.config`:
   - SET thay toàn bộ blob, đổi `$` thành `=`, ghi fixed 640 byte, fsync/close.
   - Gửi `adas_config_update` vào FIFO của cardv.
2. `cardv::minieye_adas_config_update()` tại `0x72b8c` gửi thông báo `changed` trên `MINIEYE.Config.v2`.
3. Trong `adas`, `sdk::VehicleInfoRecv::recv` tại `0x7e308`, Config.v2 đi tới store cờ `config_changed` tại `0x7e8fc`.
4. CameraLoop/LaneRun/LicenseService thấy cờ và kết thúc; `RunAlgorithm` giải phóng tài nguyên, `main` trả về 0.
5. `mutualism` chờ **bất kỳ** child kết thúc rồi thoát; parent-death handlers dừng các process group còn lại.
6. `adas_guard.sh` kiểm tra mỗi 3 giây, chạy lại `run.sh`; script giải mã cấu hình mới và tạo chuỗi ADAS/lane mới.

**Do đó mất hình và thay PID khi lưu setting không tự chứng minh crash, license lỗi hoặc rollback.** Restart không khôi phục các cờ FCW/HMW cũ; hiện hai cờ vẫn bật.

### 3.2. Master enable và trạng thái màn hình là các đường khác nhau

- `ADAS.enable` GET trong CGI: xuất success rồi kết thúc, thiếu phần trả value.
- SET chỉ gửi `adas_enable <value>` tới FIFO.
- Global `cardv::adas_enable` tại `0x13e24c` khởi tạo `1`; tìm thấy handler ghi tại `0x5f390`, chưa tìm thấy executable reader trong cardv đã quét. Không suy ra nó thực sự chặn warning/frame.
- `SendADASInfoToScreen` tại `0x9a20c` dùng **process presence**, không đọc global trên. Nó debounce tới lần quan sát thành công thứ năm từ counter 0 mới báo present.
- `SetADASStatus`/`WSSetADASStatus` tạo message dạng:

```json
{"type":3000,"uuid":"AdasStatus","status":true}
```

- Restart có thể tạo một khoảng `AdasStatus=false` rồi phục hồi. **Chưa chứng minh UTOUR GO nhận message này hoặc dùng nó để reset switch**; đừng nhầm đường M4 với đường app.

### 3.3. Không có căn cứ ép hiệu chuẩn state 1 thành 2

- `adas_checkcalib.sh` chấp nhận `1` hoặc `2`; không chạy script đó để đo vì nó có thể giải mã/ghi lại file.
- Nhánh startup thực tế trong ADAS tại `0x68fc8` chấp nhận **state > 0**.
- `EnvParam::SetCSwitch` tại `0x7aab4` ánh xạ `enable_fcw`/`enable_hmw` sang các khóa warning tương ứng, không có so sánh install state 1/2 trong hàm đã truy.
- `SetWarningLevel` chấp nhận khoảng 1–4; mức 3 không bị loại ở nhánh đó.
- FCW/HMW có các điều kiện tốc độ, target, TTC/headway và suppress riêng; việc chưa phát warning khi đứng yên không nói được switch đã tắt.
- Nhánh `ShareCalibParam` kiểm tra chuyển 1 → 2 để phát `calib_success`, không phải bằng chứng state 1 vô hiệu hóa warning.
- Screen status có kiểm tra riêng `install_calib_state=2`; không suy điều kiện đó sang toàn bộ warnings hoặc app.
- Activation/license runtime vẫn chưa chứng minh đầy đủ; không được chỉnh/bỏ qua license hay in dữ liệu license.

## 4. APK cần nối tiếp từ lần Muse phân tích trước

Tài liệu lưu trong repo:
- [APK_UTOUR_GO_WIFI_API_V1.md](APK_UTOUR_GO_WIFI_API_V1.md) — **đọc phần bổ sung nhánh c2**, không áp API c1 sang C2M.
- [APK_UTOUR_GO_MODDING_GUIDE_V1.md](APK_UTOUR_GO_MODDING_GUIDE_V1.md).

Lần phân tích trước ghi APK package `cc.minieye.utour`, version **6.1.20 / versionCode 23**, dex `classes.dex`, `classes2.dex`, `classes3.dex`, ít obfuscation. **Chưa xác nhận đây là bản đang cài trên điện thoại hiện nay.** Ghi rõ fingerprint/version APK Muse thực sự phân tích; nếu khác bản chủ máy thì đánh dấu giới hạn.

Workspace lịch sử được ghi là `~/workspace/c2m-apk/analysis/`, có `FINDINGS.md`, `dex_annot.py`, `disas.py`. Máy đang chạy OpenCode hiện không có APK/decompile tương ứng; Muse hãy dùng bộ đã có từ lần trước nếu còn, không cần làm lại toàn bộ phân tích API.

Mốc class/method đã biết:

```text
cc.minieye.c2.net.C2Api
cc.minieye.c2.net.ApiWrapper
cc.minieye.c2.business.setting.SettingActivity
cc.minieye.c2.business.<domain>.*Repository
cc.minieye.c2.viewmodel.* / business.*.*ViewModel
AdasSettingRepository.setAdas()
AdasSettingRepository.enterSetting()/exitSetting()
BaseRepository.get()/set()/parseResponse()
```

Nhánh c2 dùng HTTP port 80, `/cgi-bin/Config.cgi`, QueryMap với `VersionPrototal=1.0.1` (giữ nguyên typo). C1 REST port 8080 **không phải nhánh đã xác nhận trên camera này**.

`CollisionSensing` là property settings riêng; chủ máy đã xác nhận thao tác trên **trang ADAS**, không phải cảm biến G/khóa video. Vẫn cần mã APK xác định đúng label ↔ field, không chỉ dịch tên tiếng Việt.

## 5. Nhiệm vụ phân tích APK ưu tiên

1. **Map đúng công tắc**: label/resource ID → listener → ViewModel → model field → serialized flag. Phân biệt FCW, UFCW, HMW và master switch.
2. **Truy lần mở lại trang**: onCreate/onResume/load/refresh → mọi request → parser → model → setChecked/binding. Chỉ ra câu lệnh nào có thể đặt tất cả OFF.
3. **Liệt kê request thật trong call chain**, không chỉ string pool: action/property/value, thứ tự, nơi chọn c1/c2, điều kiện thành công/thất bại.
4. **Kiểm tra `ADAS.enable`**: app có gọi GET không? Nếu trả chỉ `0\nOK\n`, code xử lý missing field thế nào? Có default false, exception fallback hoặc reset toàn model không?
5. **Kiểm tra parser `ADAS.config`** với response đã biết:
   - Có lấy đúng dòng `ADAS.config=` không, thay vì nhầm dòng mã `0`?
   - Base64 unwrapped/no-padding như mẫu có được chấp nhận?
   - Cách split `--key=value`, trailing LF, Boolean true/false, level 0/3.
   - Thiếu TSR keys có làm parser bỏ cả model/default OFF không? Chỉ kết luận khi có nhánh mã tương ứng.
   - Có field bắt buộc khác, default object hoặc catch exception trả model rỗng?
6. **Truy thao tác save**: app gửi toàn bộ config thế nào, có master `ADAS.enable`, request `Setting enter/exit`, timeout/retry hoặc event async sau restart làm ghi đè UI/model không?
7. **Kiểm tra trạng thái chung**: app có đọc calibration/activation/process status, AdasStatus hoặc error code rồi làm mờ/tắt switch không? Đừng mặc định message M4 cũng đi tới app.
8. Tách rõ **saved switch** với **warning event active lúc lái xe**. Warning event false khi đỗ không được dùng để biểu diễn cấu hình disabled nếu đó không phải thiết kế app có bằng chứng.

## 6. Đầu ra cần Muse trả

Trả một file Markdown (gợi ý `MUSE_UTOUR_GO_ADAS_TOGGLE_ANALYSIS.md`) gồm:

1. APK fingerprint/version và nguồn artifact đang phân tích.
2. Call chain cho **save**, **reopen/readback**, **OFF/error path**, có class/method + smali/dex offset hoặc trích mã đủ kiểm tra.
3. Bảng **CONFIRMED / HYPOTHESIS / UNKNOWN**, đặc biệt đối với missing `ADAS.enable` và calib_state 1.
4. Kết luận hẹp: lỗi app parsing/state reconciliation, firmware response contract, hay chưa đủ bằng chứng; nêu điều kiện phản chứng.
5. Bản sửa tối thiểu **đề xuất**, chưa deploy: sửa ở method/field nào, vì sao đúng, không “bật cứng” tất cả cảnh báo hoặc giả trạng thái thành công.
6. Test offline bằng fixture đã làm sạch: response `0/OK/ADAS.config=<base64>`, missing enable field, true/false và level 0/3, model thiếu TSR keys, transient process unavailable rồi recover. Không cần thiết bị cho vòng đầu.
7. Nếu vẫn thiếu bằng chứng: chỉ yêu cầu artifact/trace nhỏ nhất thực sự cần, kèm cách lấy an toàn, không yêu cầu reset/flash lại để thử mò.

## 7. Ranh giới an toàn và tránh kết luận sai

- Phân tích tĩnh/offline là mặc định; không gọi API set hoặc command restart từ kết quả bàn giao.
- Không reset, không ép calib_state=2, không bypass license, không fake speed/warning, không tạo warning-slot injection.
- Không mở client WebSocket mới khi M4 đang dùng stream single-client.
- Không đòi ADB M4: màn này không có cảm ứng và chưa có ủy quyền cho lần thử mới.
- Không upload firmware/audio/database riêng, raw config/calib/license, private key, challenge hoặc log nhạy cảm lên public service/repo. Chỉ cần APK hợp pháp và fixture đã làm sạch; fingerprint artifact được dùng để đối chiếu.
- Các GET `ADAS.config`, `ADAS.Adjust`, `adasVersion` dùng fopen `a+` trong CGI: có thể tạo file nếu thiếu. Không quảng bá chúng là read-only vô điều kiện; các lần đọc live ở đây đã xác nhận source tồn tại trước, không gửi notification/setter.
- Không kết luận cấu hình bị mất sau flash chỉ vì hiện không có `.bak` hoặc log restore; nguồn gốc restore/provisioning chưa chốt.
- Không hồi sinh giả thuyết “VI ADAS regression” cũ đã bị supersede do setting-confounded. Lỗi hiện tại phải có chứng cứ riêng.
- **Không xem việc file/API báo bật là bằng chứng warning thực tế đã được phát.** Cũng không xem UI OFF là bằng chứng file bị rollback: lần này source/decoded/API giữ hai mục ON.
