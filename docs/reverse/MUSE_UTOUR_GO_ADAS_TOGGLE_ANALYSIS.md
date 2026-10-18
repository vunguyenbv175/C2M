# Phân tích: UTOUR GO hiển thị cảnh báo ADAS tắt sau khi mở lại trang

Ngày: 2026-10-18 (bản sửa đổi 2 — rút lại root cause v1 sau dữ liệu live mới).
Nối tiếp `MUSE_UTOUR_GO_ADAS_TOGGLE_HANDOFF_20261018.md`.
Phạm vi: **chỉ nhánh Android c2**, phân tích tĩnh APK, không gọi setter/reset/hiệu chuẩn/license trên camera.

## 0. APK đang phân tích (fingerprint)

| Trường | Giá trị |
|---|---|
| File | `~/workspace/c2m-apk/base.apk` (+ `utour-go.apk` cùng bộ) |
| Package | `cc.minieye.utour` |
| Version | 6.1.20 / versionCode 23 |
| Dex chứa code c2 ADAS | `classes.dex` |
| Obfuscation | không đáng kể |

**Giới hạn:** chưa xác nhận đây là bản đang cài trên điện thoại của chủ máy.

## 1. Rút lại kết luận v1 (RETRACTED)

Bản v1 của báo cáo này kết luận: firmware chuẩn hoá key về dạng trần (bỏ `--`),
trong khi parser app tra key `--enable_fcw` → null → false → UI toàn OFF.

**Tiền đề này SAI.** Dữ liệu live đọc lại ngày 2026-10-18 cho thấy sau giải mã base64:
19/19 dòng **vẫn có tiền tố `--`** (`--enable_fcw=true`, `--fcw_level=3`,
`--enable_hmw=true`, `--hmw_level=3`), 0 dòng key trần. Bảng key ở bàn giao §2.3
là dạng rút gọn minh hoạ, không phải raw payload.

Do đó chuỗi "firmware chuẩn hoá key trần → lookup --key thất bại" **chưa được chứng minh
và hiện bị bằng chứng live bác bỏ**. Không triển khai patch thêm alias key.

## 2. Kiểm chứng code dựng map (theo yêu cầu §1)

`AdasConverter$Companion.toAdasBean(String):AdasBean`, `classes.dex`, `method_idx=41461`,
507 instructions. Đoạn dựng map (ins 80–117), trích nguyên văn:

```
80  iterator = lines.iterator()
85  line = iterator.next()                          // v5, vd "--enable_fcw=true"
91  filled-new-array v3, [String]                   // v3 = "=" (ins 3)
97  split(line, ["="]) -> v10                       // ["--enable_fcw","true"]
99  key = v10.get(0)                                // "--enable_fcw", NGUYÊN VĂN
113 value = v5.get(1)                               // "true" (v5 = split lại dòng)
116 map.put(key, value)
117 goto loop
```

**Không có** `removePrefix`, `substring`, `replace` hay bất kỳ thao tác nào bỏ `--`
trên key trong toàn bộ 507 instructions (đã quét toàn method).
`split("=")` tự nó không bỏ `--`. Key được dùng **verbatim**.

Các lookup sau đó (ins ~118–395) đều dùng key `--`-prefixed:
`--enable_vehicle`, `--enable_ufcw`/`--ufcw_level`, `--enable_sag`/`--sag_level`,
`--enable_hmw`/`--hmw_level`, `--headway_warning_speed_thresh`,
`--enable_fcw`/`--fcw_level`, `--enable_ldw`/`--ldw_level`/`--ldw_speed_start`,
`--enable_pcw`/`--pcw_level`, `--vehicle_width`, `--left_vehicle_edge_dist`,
`--right_vehicle_edge_dist`, `--license_sn`.

**Kết luận:** với payload live (`--`-prefixed), mọi lookup đều HIT. Parser đúng.

## 3. Tái hiện offline bằng logic trích đúng từ APK (theo yêu cầu §2)

Script: logic sao chép 1:1 từ smali (`split("ADAS.config=")[1]` → `replace('$','=')` →
`Base64.decode(DEFAULT)` → UTF-8 → `trim()` → `split("\n")` → `split("=")` → map verbatim →
lookup `--`-key → `parseBoolean` → `bean.x = enable_x ? level : 0`).

Fixture: response `0\nOK\nADAS.config=<base64>`, decoded 19 dòng
(`--enable_fcw=true`, `--fcw_level=3`, `--enable_hmw=true`, `--hmw_level=3`,
các mục khác false/0, thiếu 5 key TSR như live), cộng bản đối chứng key trần.

| Fixture | Map keys | Bean | UI hiển thị |
|---|---|---|---|
| PREFIXED (`--`, đúng format live) | 19 key `--…` | fcw=3, hmw=3, còn lại 0 | FCW=high, HMW=high, còn lại close — **ĐÚNG** |
| BARE (không `--`) | 19 key trần | toàn 0 | toàn close — SAI (đúng như dự đoán lý thuyết) |

**Kết quả:** fixture prefixed parse **đúng**. Parser của APK 6.1.20/23 không phải nguyên nhân
với payload live hiện tại. (Chi tiết log map/bean đã in đầy đủ khi chạy.)

## 4. Truy tiếp các nhánh còn lại (theo yêu cầu §3) — không nhánh nào trong APK này cho ra "tất cả OFF"

Đã kiểm tra toàn bộ đường `getSettings → bodyToAdasBean → LiveData → observer → UI`:

| Nhánh | Kết quả trong APK 6.1.20/23 |
|---|---|
| Parse thành công (`isSuccessful`, response live) | Bean đúng (mục 3) → UI đúng. Không phải bug. |
| `!isSuccessful` → `defaultAdasBean()` → `setValue` | Bean default → hiển thị **medium** (hoặc super_high nếu model=C2L), **không phải off**. Loại trừ. |
| Exception trong fetch/parse → catch → `defaultAdasBean()` → `setValue` | Như trên: medium/super_high, không phải off. Loại trừ. (Lưu ý: bản v1 viết sai "LiveData không được update" — catch có gọi `setValue(default)`.) |
| `getAdasSettings()` không chạy / observer không fire | Layout `c2_activity_adas_setting.xml`: các `*ShowText` default text **rỗng** (không phải "tắt"); `switchTsr` default unchecked. Không khớp triệu chứng "hiển thị tắt". |
| Ghi đè sau đó (writer khác vào LiveData) | Quét toàn bộ `c2/business/adas`: chỉ `getAdasSettings$1` ghi `getAdasSettingsLiveData`. Không có. |
| Auto-save khi đóng/mở trang | `onBackPressed` không gọi submit/setAdas. Không có. |
| Đọc calibration/AdasStatus rồi mờ switch | `parseGetAdasSettingsLiveData` không đọc các trạng thái này. Không có. |

**Kết luận hẹp:** với payload live hiện tại, **APK 6.1.20/23 không có đường nào sinh ra "tất cả cảnh báo hiển thị tắt".**

## 5. Đối chiếu mâu thuẫn defaultAdasBean (theo yêu cầu §4)

Bản v1 viết: `defaultAdasBean(2,2,2,2,2,2,…)` "cũng hiển thị tắt", đồng thời mô tả
`adasFormatString(2)` = medium — mâu thuẫn. Kiểm tra `AdasBean.<init>` (iput order):

```
param → field: p0→pcw, p1→ldw, p2→hmw, p3→sag, p4→fcw, p5→ufcw,
               p6→devicePosition, p7→carSize, p8→type, p9→tsrEnable
```

(`ldwActiveSpeed`/`hmwActiveSpeed` khởi tạo 0 trong ctor, set sau qua setter.)

Vậy `defaultAdasBean` bản non-C2L = pcw/ldw/hmw/sag/fcw/ufcw = **2** → UI hiện
**"medium"** cho cả 6, không phải "tắt". Bản v1 sai ở điểm này; đã đính chính.
(Không suy mapping từ vị trí tham số nữa — đã đọc trực tiếp ctor.)

## 6. Bảng CONFIRMED / HYPOTHESIS / UNKNOWN (cập nhật)

| # | Nội dung | Trạng thái |
|---|---|---|
| C1 | Parser `toAdasBean` parse **đúng** payload live (`--`-prefixed) — chứng minh bằng repro offline | CONFIRMED (rút lại C1 của v1) |
| C2 | Code dựng map không strip `--`; key dùng verbatim (ins 80–117, method_idx 41461) | CONFIRMED |
| C3 | Camera lưu đúng FCW/HMW=true/3; API `ADAS.config` trả đúng 19 dòng `--`-key | CONFIRMED (live 2026-10-18) |
| C4 | App 6.1.20/23 không gọi `ADAS.enable` GET (string không tồn tại trong 3 dex) | CONFIRMED |
| C5 | Restart sau save là cơ chế chủ đích của firmware | CONFIRMED (giữ từ v1) |
| C6 | `calib_state=1` không gây all-OFF (UI không đọc state này) | CONFIRMED (giữ từ v1) |
| C7 | `defaultAdasBean` cho ra medium/super_high, không phải off (mapping ctor đã verify) | CONFIRMED (đính chính v1) |
| C8 | Đóng trang không auto-save (`onBackPressed` không gọi submit) | CONFIRMED |
| C9 | Mỗi lần save app ghi đè toàn blob và làm mất 5 key TSR (`AdasFlag.toString()` không emit) | CONFIRMED (giữ từ v1, vấn đề riêng) |
| H1 | **Điện thoại đang chạy bản UTOUR GO khác 6.1.20/23** — bản đó parse sai payload `--` (ví dụ lookup key trần, hoặc logic khác) → all lookup miss → all OFF. Khớp triệu chứng chính xác. | HYPOTHESIS — giả thuyết hàng đầu hiện tại |
| H2 | Response mà app trên điện thoại nhận được khác với OpenCode đọc (thời điểm/kênh khác) | HYPOTHESIS — yếu hơn H1 |
| U1 | Version APK thực tế trên điện thoại | UNKNOWN — artifact nhỏ nhất còn thiếu (xem §8) |
| U2 | Số dòng smali tuyệt đối sau apktool (offset trong báo cáo là index instruction tương đối) | UNKNOWN |

**Điều kiện phản chứng H1:** lấy được APK trên điện thoại, trích `toAdasBean` tương ứng —
nếu parser giống hệt 6.1.20/23 thì H1 sai, phải truy tiếp phía response/runtime.

## 7. Đề xuất patch

**Không đề xuất patch** cho đến khi tái hiện được lỗi (đúng yêu cầu).
Parser của 6.1.20/23 đã đúng với firmware hiện tại; patch alias key không có cơ sở.

## 8. Artifact nhỏ nhất còn thiếu

1. **Version UTOUR GO trên điện thoại** (Settings → Apps → UTOUR GO). Nếu khác 6.1.20/23 → lấy APK
   (APK extractor hoặc `adb pull`) để so sánh trực tiếp hàm `toAdasBean`/`AdasConverter`.
2. Nếu cùng 6.1.20/23: logcat khi mở trang ADAS —
   `adb logcat -s AdasConverter:I AdasSettingViewModel:I AdasSettingActivity:E`
   (xem các dòng `toAdasBean: decodeString:`, `toAdasBean: map =>`, `configBean:`,
   `getAdasSettings:` để biết app thực sự nhận/parse ra gì). Không cần thao tác xe.

---
*Phân tích tĩnh bằng androguard trên `classes.dex` của UTOUR GO 6.1.20/23;
repro offline chạy logic 1:1 từ smali; response live do OpenCode đọc ngày 2026-10-18.
Không thực hiện bất kỳ lệnh ghi nào lên camera.*
