# Phân tích: UTOUR GO hiển thị cảnh báo ADAS tắt sau khi mở lại trang

Ngày: 2026-10-18. Nối tiếp `MUSE_UTOUR_GO_ADAS_TOGGLE_HANDOFF_20261018.md`.
Phạm vi: **chỉ nhánh Android c2**, phân tích tĩnh APK, không gọi setter/reset/hiệu chuẩn/license trên camera.

## 0. APK đang phân tích (fingerprint)

| Trường | Giá trị |
|---|---|
| File | `~/workspace/c2m-apk/base.apk` (+ `utour-go.apk` cùng bộ) |
| Package | `cc.minieye.utour` |
| Version | 6.1.20 / versionCode 23 |
| Dex chứa code c2 ADAS | `classes.dex` |
| Obfuscation | không đáng kể |

**Giới hạn:** chưa xác nhận đây là bản đang cài trên điện thoại của chủ máy (bàn giao ghi "chưa biết phiên bản hiện tại").
Mọi class/method dưới đây đã verify trực tiếp trong dex.

## 1. Kết luận: ROOT CAUSE (CONFIRMED)

**Lỗi bất đối xứng định dạng key giữa đường ghi và đường đọc của app, trong khi firmware chuẩn hoá về key trần.**

- **Đường ghi (save):** app serialize config với key có prefix `--`
  (`AdasFlag.toString()` → `--enable_fcw=true\n--fcw_level=3\n…`) → base64 → `action=set&property=ADAS.config`.
- **Firmware lưu/trả về key trần** (không `--`): bằng chứng live từ bàn giao —
  `adas_de.flag` giải mã và `GET ADAS.config` qua HTTP đều là `enable_fcw=true`, `fcw_level=3`.
- **Đường đọc (mở lại trang):** parser `toAdasBean` dựng map từ key trần,
  nhưng tra cứu bằng key `--enable_fcw` → `map.get()` trả **null** →
  `Boolean.parseBoolean(null)` = **false** cho mọi `enable_*` →
  `bean.<warning> = enable ? level : 0` = **0** →
  UI `adasFormatString(0)` → `R.string.close` → hiển thị **"tắt"** cho tất cả.

Camera **không hề mất cấu hình** (FCW/HMW vẫn true/3 trong file và API).
Lỗi hoàn toàn nằm ở parser readback phía app.

## 2. Call chain đầy đủ

### 2.1. Mở lại trang (reopen → readback → parser → UI OFF)

```
AdasSettingActivity.parseIntent()
  → AdasSettingActivity.getAdasSettings()
    → AdasSettingViewModel.getAdasSettings()
      → AdasSettingRepository.getSettings()
        → AdasSettingRepository.get("*")
          map = {action="get", property="ADAS.config", VersionPrototal="1.0.1"}
          → SettingApi.config(map)
            → GET http://192.168.1.1/cgi-bin/Config.cgi?action=get&property=ADAS.config&VersionPrototal=1.0.1
            → HTTP 200, body = "0\nOK\nADAS.config=<base64>"
        → AdasSettingRepository.parseResponse(response)
            body.split("\n") → List ["0","OK","ADAS.config=<base64>"]   // Response.success(code, list)
      → AdasSettingViewModel$getAdasSettings$1.invokeSuspend
        → bodyToAdasBean(list): tìm dòng contains "ADAS.config="
        → AdasConverter$Companion.toAdasBean(line)
            split("ADAS.config=")[1]                    // base64
            .replace('$', '=')                          // fix padding
            Base64Util.decode → UTF-8 → trim → split("\n")
            split("=") → map.put("enable_fcw","true")   // KEY TRẦN
            ...
            map.get("--enable_fcw")  → null  → parseBoolean → false   // ← BUG
            map.get("--fcw_level")   → null  → default "1" → 1
            bean.fcw = false ? 1 : 0  → 0
            (tương tự hmw/ldw/pcw/sag/ufcw → 0)
        → getAdasSettingsLiveData.setValue(bean)        // bean toàn 0
    → observer (viewModelInit) → parseGetAdasSettingsLiveData(bean)
        fcwShowText.setText(adasFormatString(0)) → R.string.close → "tắt"
        (hmw/ldw/pcw/sag/ufcw tương tự; switchTsr.setChecked(bean.tsrEnable=false))
```

Nhánh lỗi dự phòng: nếu `isSuccessful()==false` hoặc exception,
`defaultAdasBean()` được dùng (C2M → `AdasBean(2,2,2,2,2,2,0,"Small","same",false)`),
cũng hiển thị tắt — nhưng đây **không** phải đường đã kích hoạt trong case này
(response 200 OK, parse "thành công" ra toàn false).

### 2.2. Lưu cấu hình (save — hoạt động đúng)

```
AdasSettingActivity (listener) → AdasSettingViewModel.submit(adasBean)
  → AdasConverter$Companion.toBase64String(adasBean)
      → AdasFlag.toString()   // key "--enable_fcw=" … (xem §3)
      → base64
  → AdasSettingRepository.setAdas(b64)
      map = {action="set", property="ADAS.config", value=b64, VersionPrototal="1.0.1"}
      → SettingApi.config(map) → GET action=set…
```

Restart ADAS sau save là **thiết kế firmware** (`Config.cgi` → `adas_config_update` → `config_changed`
→ adas thoát → `mutualism` thoát → `adas_guard.sh` chạy lại `run.sh`), không phải app gọi reboot,
không phải bằng chứng crash/license lỗi (đã truy ở bàn giao §3.1).

## 3. Bằng chứng method/smali (classes.dex)

| # | Vị trí | Bằng chứng |
|---|---|---|
| 1 | `AdasConverter$Companion.toAdasBean(String):AdasBean` | ins đầu: `split("ADAS.config=")` → `get(1)`; `replace('$'→'=')`; `Base64Util.decode`; `trim`; `split("\n")`; vòng lặp `split("=")` → `map.put(key,value)` với key trần (ins ~85–116) |
| 2 | cùng method, ins ~118–~395 | mọi lookup dùng prefix `--`: `map.get("--enable_vehicle")`, `"--enable_fcw"`, `"--fcw_level"`, `"--enable_hmw"`, `"--hmw_level"`, `"--enable_ldw"`, `"--ldw_level"`, `"--enable_pcw"`, `"--pcw_level"`, `"--enable_sag"`, `"--sag_level"`, `"--enable_ufcw"`, `"--ufcw_level"`, `"--headway_warning_speed_thresh"`, `"--vehicle_width"`, `"--left_vehicle_edge_dist"`, `"--right_vehicle_edge_dist"`, `"--license_sn"` |
| 3 | cùng method, ins ~397–448 | `bean.x = flag.enable_x ? flag.x_level : 0` cho pcw/ldw/hmw/sag/fcw/ufcw (ldw có thêm gate `isC2M`) |
| 4 | `AdasFlag.toString()` | const-string `"\n--enable_fcw="`, `"\n--fcw_level="`, `"\n--enable_hmw="`… — đường ghi dùng key `--` |
| 5 | `AdasSettingRepository.get()` | const-string `property="ADAS.config"`, `action="get"`, `VersionPrototal="1.0.1"` → `SettingApi.config` |
| 6 | `AdasSettingRepository.parseResponse` | `body().string()` → `split("\n")` → `Response.success(code, list)` |
| 7 | `AdasSettingViewModel.bodyToAdasBean` | tìm dòng `contains("ADAS.config=")` → `toAdasBean(dòng)`; log tag `AdasSettingViewModel` |
| 8 | `AdasSettingActivity.parseGetAdasSettingsLiveData` | `getFcw()→adasFormatString()→fcwShowText`, tương tự hmw/ldw/pcw/sag/ufcw; `switchTsr.setChecked(getTsrEnable())` |
| 9 | `AdasSettingActivity.adasFormatString(int)` | `0 → R.string.close`; 1→low, 2→medium, 3→high, 4→super_high |
| 10 | `AdasConverter.<clinit>` | `isC2M = deviceModel.equals("C2M")` — true trên máy này |
| 11 | `AdasConverter$Companion.defaultAdasFlag()` | nhánh `isC2M=true` trả `AdasFlag` toàn 0/false (chỉ dùng khi fallback, không phải đường chính của bug này) |

## 4. Trả lời các câu hỏi ưu tiên của bàn giao

1. **Map công tắc:** FCW→`R.id.fcwShowText`/`getFcw()`; HMW→`hmwShowText`/`getHmw()`;
   LDW→`ldwShowText`; PCW→`pcwShowText`; SAG→`sagShowText`; UFCW→`ufcwShowText`;
   TSR→`R.id.switchTsr`/`getTsrEnable()`. Không có master switch nào trong UI render bean.
2. **Câu lệnh đặt OFF:** `toAdasBean` ins ~433–440 (`enable_fcw=false → v13=0`) và các khối tương tự;
   điểm hiển thị cuối là `adasFormatString(0) → R.string.close`.
3. **Request thật duy nhất trong chain đọc:** `GET cgi-bin/Config.cgi?action=get&property=ADAS.config&VersionPrototal=1.0.1`
   qua `SettingApi.config(@QueryMap)`. Không có request c1, không có fallback URL.
4. **`ADAS.enable` GET: APP KHÔNG HỀ GỌI.** String `ADAS.enable` không tồn tại trong cả 3 dex
   (chỉ có `ADAS.config`, `ADAS.Adjust`/`ADAS.adjust`). Câu hỏi "GET thiếu giá trị" là moot —
   app không đọc master enable từ camera.
5. **Parser với response thực `0/OK/ADAS.config=<base64>`:**
   - Lấy đúng dòng `ADAS.config=` (qua `contains`, không nhầm dòng `0`). ✔
   - Base64 không padding chuẩn được chấp nhận (có `replace('$','=')`). ✔
   - Split `--key=value`, trailing LF (`trim()`), `true/false`, level `0/3` đều xử lý đúng **nếu key khớp**. ✘ Key không khớp (`--` vs trần) → toàn bộ sai.
   - Thiếu TSR keys: lookup null → `tsrEnable=false`, level→default — không crash, không phải nguyên nhân all-OFF.
   - Không có try/catch trong `toAdasBean`; exception (vd response thiếu dòng `ADAS.config=`) nổi lên
     `invokeSuspend` → log `getAdasSettings err`, LiveData giữ giá trị cũ.
6. **Save:** app gửi **toàn bộ blob** mỗi lần (`action=set`, `value=<base64 của AdasFlag.toString()>`).
   Vì `toString()` không emit các key `enable_tsr`/`tsrw_interval`…, mỗi lần save của app **xóa 5 key TSR**
   khỏi file camera — đúng như bàn giao §2.3 quan sát. Đây là vấn đề persistence riêng,
   **không phải nguyên nhân all-OFF** (FCW/HMW vẫn được ghi đúng).
7. **Trạng thái chung:** `parseGetAdasSettingsLiveData` không đọc calibration/activation/AdasStatus —
   không có logic làm mờ/disable switch theo `install_calib_state`. `calib_state=1` không liên quan đến bug này.

## 5. Bảng CONFIRMED / HYPOTHESIS / UNKNOWN

| # | Nội dung | Trạng thái |
|---|---|---|
| C1 | Parser readback tra key `--x` trong khi map chứa key `x` → mọi `enable_*`=false → UI toàn OFF | CONFIRMED (smali + response live) |
| C2 | Camera lưu đúng FCW/HMW=true/3; API `ADAS.config` trả đúng | CONFIRMED (bàn giao §2.3–2.4) |
| C3 | App không gọi `ADAS.enable` GET | CONFIRMED (string pool 3 dex) |
| C4 | Restart sau save là thiết kế firmware, không phải crash | CONFIRMED (trace bàn giao §3.1) |
| C5 | `calib_state=1` không gây all-OFF (UI không đọc state này) | CONFIRMED (render path) |
| C6 | Mỗi lần save app xóa 5 key TSR khỏi blob camera | CONFIRMED (`AdasFlag.toString()` không emit chúng + quan sát §2.3) |
| H1 | Firmware cũ/stock từng trả key `--` (lý do app viết parser này); bản D5-VI chuẩn hoá về key trần | HYPOTHESIS — cần sample response của firmware gốc để xác minh |
| H2 | Base64 `$`-padding là di sản firmware cũ; bản hiện tại trả `=` chuẩn (parser chịu cả hai) | HYPOTHESIS nhẹ |
| U1 | APK trên điện thoại có đúng 6.1.20/23 không | UNKNOWN |
| U2 | Số dòng smali tuyệt đối sau apktool (offset trong báo cáo là index instruction tương đối trong method) | UNKNOWN — dùng class/method + const-string để định vị lại |

**Điều kiện phản chứng:** nếu logcat `AdasConverter` cho thấy `toAdasBean: map =>` chứa key **có** `--`
mà UI vẫn OFF → C1 sai. Nếu map chứa key trần → C1 đứng vững.

## 6. Đề xuất sửa tối thiểu (chưa deploy, không đụng camera)

**Vị trí:** `AdasConverter$Companion.toAdasBean`, vòng lặp dựng map (ins ~85–116).

**Sửa:** khi `map.put(key, value)`, lưu thêm biến thể `--`-prefixed:

```kotlin
// pseudo (tương đương smali cần chèn sau split("=")):
val k = key
map[k] = value
if (!k.startsWith("--")) map["--$k"] = value else map[k.removePrefix("--")] = value
```

Chỉ chạm **một điểm** (put-loop), không sửa ~20 lookup, không sửa đường ghi,
chịu được cả firmware trả key trần (hiện tại) lẫn key `--` (nếu H1 đúng với bản cũ).
Không "bật cứng" cảnh báo, không giả trạng thái thành công — giá trị hiển thị vẫn là giá trị camera trả về.

**Không làm:** bypass license, ép `calib_state=2`, reset config, gọi setter trên camera,
sửa `defaultAdasFlag()` (đường fallback không phải nguyên nhân).

**Ghi chú thêm (không bắt buộc cho bug này):** nếu muốn giữ TSR keys qua các lần save,
`AdasFlag.toString()` cần emit lại `enable_tsr`/`tsrw_interval`/… hoặc chuyển save sang merge
thay vì replace toàn blob — để riêng, không gộp vào fix tối thiểu.

## 7. Test offline bằng fixture (không cần thiết bị)

Dựng harness JVM/Kotlin sao chép đúng logic `toAdasBean` (hoặc unit test gọi trực tiếp method
trong APK đã patch), chạy các fixture đã làm sạch:

| Fixture | Input | Kỳ vọng sau fix |
|---|---|---|
| F1 (case thật) | `0\nOK\nADAS.config=<base64(key trần: enable_fcw=true,fcw_level=3,enable_hmw=true,hmw_level=3, còn lại false/0)>` | bean fcw=3, hmw=3; các mục user tắt =0; UI hiện đúng 2 mục bật |
| F2 (định dạng cũ) | như F1 nhưng key `--`-prefixed | cùng kỳ vọng F1 (robustness) |
| F3 (thiếu dòng config) | `0\nOK\n` | không crash; LiveData giữ giá trị cũ; log `getAdasSettings err` (hành vi hiện tại giữ nguyên) |
| F4 (thiếu TSR keys) | F1 bỏ 5 key TSR | parse OK, tsrEnable=false, các warning khác đúng |
| F5 (`$` padding) | base64 dùng `$` thay `=` cuối | parse OK như F1 |
| F6 (level 0/3, true/false) | biên: `enable_fcw=false,fcw_level=3` | bean fcw=0 (enable gate đúng) |

**Tiêu chí pass vòng 1:** F1 chuyển từ FAIL (bean toàn 0) → PASS; F2–F6 không regression.
Nếu vẫn thiếu bằng chứng sau vòng này, artifact cần thêm duy nhất là logcat dòng
`AdasConverter: toAdasBean: map =>` và `configBean:` khi mở trang ADAS trên máy thật
(lấy bằng `adb logcat -s AdasConverter:I AdasSettingViewModel:I`, không cần thao tác xe).

## 8. Chuỗi nhân quả tóm tắt (để đối chiếu nhanh)

```
app GHI "--enable_fcw=true" ──► firmware LƯU "enable_fcw=true" ──► firmware TRẢ "enable_fcw=true"
         (AdasFlag.toString)            (chuẩn hoá, bỏ "--")              (GET ADAS.config)

app ĐỌC: map{"enable_fcw":"true"}  +  lookup("--enable_fcw") → null → false → bean.fcw=0 → UI "tắt"
```

---
*Phân tích tĩnh bằng androguard trên `classes.dex` của UTOUR GO 6.1.20/23; response live lấy từ
`MUSE_UTOUR_GO_ADAS_TOGGLE_HANDOFF_20261018.md`. Không thực hiện bất kỳ lệnh ghi nào lên camera.*
