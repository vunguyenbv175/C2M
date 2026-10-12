# Phân tích APK UTOUR GO — API Wi-Fi chỉ đọc cho camera MINIEYE/UTOUR C2M

> **Mục tiêu:** tìm API/endpoint **chỉ đọc** để xác minh firmware B qua Wi-Fi,
> không cần cáp USB data (cổng Type-C chỉ cấp nguồn).
> Cam đang chạy stock PASS sau Candidate A, chưa flash B.
>
> **Ngày phân tích:** 2026-10-12
> **Trạng thái:** phân tích tĩnh hoàn tất, chưa test live với cam.

---

## 1. WHAT FOUND — Thông tin APK

| Trường | Giá trị | Cách xác minh |
|---|---|---|
| Package | `cc.minieye.utour` | `AndroidManifest.xml` (androguard) — CONFIRMED |
| Version | **6.1.20** (versionCode 23) | `AndroidManifest.xml` — CONFIRMED |
| Tên app | UTOUR GO | manifest — CONFIRMED |
| Main activity | `cc.minieye.c1.ui.StartActivity` | manifest — CONFIRMED |
| Nguồn file | APKPure bundle → base APK `cc.minieye.utour.apk` (split APK, 28 MB) | download 2026-10-12 — CONFIRMED |

> ⚠️ **Lưu ý:** đây là bản "latest" trên APKPure tại thời điểm phân tích, **có thể khác**
> bản đang cài trên điện thoại của bạn. Protocol với cam khả năng cao giống nhau giữa
> các bản, nhưng hãy đối chiếu version (`Cài đặt → Ứng dụng → UTOUR GO`) trước khi
> dùng kết quả cho việc xác minh firmware B.

### Kênh giao tiếp với cam (CONFIRMED)

| Kênh | Địa chỉ | Dùng cho | Evidence |
|---|---|---|---|
| REST chính | `http://192.168.42.1:8080/` | mọi API `/api/v1/...` | const-string trong hàng chục method (`DeviceBaseRepository`, `ConnRepository`, …) |
| Diagnose / FW | `http://192.168.42.1:12306/` | `/front/v1/*`, `api/v1/get/c8version`, `api/v1/c1/*` | const-string trong `DiagnoseRepository`, `SystemFwObservables`, `DiagnoseViewModel.getDownloadUrl` |
| WebSocket | `ws://192.168.42.1:8080/api/v1/device/connection/client` | trạng thái kết nối / auth | const-string trong `DeviceWebSocketManager.connect()` |
| RTSP live | `rtsp://192.168.42.1/live` | preview trực tiếp | `ImuCalibrationActivity.startPlayVideo`, `NewDeviceMainActivity$1.onStarted` |
| RTSP playback | `rtsp://192.168.42.1/tmp/SD0/` | phát lại file trên thẻ | `DeviceFileResponse.getVideoRtspUrl`, `AlbumHelper.getVideoRtspUrl` |

- **Không có UDP discovery / mDNS / SSDP** trong app (không thấy `DatagramSocket`/
  `MulticastSocket` cho discovery) — CONFIRMED (vắng mặt). Cách hoạt động: người dùng
  tự join Wi-Fi AP của cam, app gọi thẳng IP hardcode `192.168.42.1`.
- SSID cam dựng dạng `"MINIEYE-" + deviceID` (`DeviceHelper.getDeviceSsid`) — CONFIRMED.
  (Trong code không thấy prefix `"UTOUR-"`; manual ghi Wi-Fi `UTOUR-<Device ID>` /
  `MINIEYE-<Device ID>`, pass mặc định `12345678` — thông tin từ manual, không phải từ APK.)
- Stack HTTP: **OkHttp3 + Retrofit2** (Gson, RxJava2) — `RetrofitUtil.getRetrofitInstance()`.

### Cơ chế xác thực (CONFIRMED)

1. **Header `uid` trên mọi request.** `DeviceBaseRepository` gắn interceptor:
   `Request.Builder.addHeader("uid", UidHelper.getUid(context))`.
   `UidHelper.getUid()`: đọc MMKV key `'uid'`; nếu trống thì tự sinh UUID mới và lưu lại.
   → `uid` là **UUID định danh của từng bản cài app**, không phải secret của cam.
   Cam ghi nhớ uid đã authorize. WebSocket cũng gửi header `uid` tương tự.
2. **Authorize lần đầu:** `POST /api/v1/device/connection/authorization` (body rỗng),
   sau đó **bấm nút cứng trên thân cam** hoặc nhập **voice verification code**
   (`POST /api/v1/device/authorization/code/generate` → cam đọc mã →
   `POST /api/v1/device/authorization/code/connect` + mã). Khớp manual C2M.
3. Kiểm tra: `GET /api/v1/device/connection/authorization` → `AuthorizationResponse{success}`.
4. **Chưa authorize → cam trả HTTP 401** → `Device401Interceptor` bắt và app hiện UI
   authorize lại. → Muốn curl thành công, dùng `uid` của app đã authorize
   (lấy từ MMKV của app trên điện thoại đã kết nối), hoặc authorize lại bằng app trước.

---

## 2. HOW VERIFIED — Phương pháp

1. Giải nén APK → 3 dex (`classes.dex`, `classes2.dex`, `classes3.dex`).
2. Dump ~137k strings từ string pool → grep URL/IP/port/path.
3. Phát hiện: **annotation Retrofit bị strip** (`annotations_off = 0`) trên các interface
   `*Api`, nên androguard không đọc được `@GET/@POST`.
4. Viết parser DEX annotation tùy chỉnh (`dex_annot.py`, đọc trực tiếp binary
   `annotations_directory_item` → `annotation_set` → `encoded_annotation`) để trích
   `@GET/@POST/@Query/@Body/@Url/@Streaming` — **mọi method+path dưới đây đều đọc
   trực tiếp từ annotation trong dex, không suy đoán.**
5. Đối chiếu chéo: base URL từ const-string trong các `*Repository`, response field
   từ class dex, luồng gọi từ caller.

**Chú giải verdict:**
- **CONFIRMED** — thấy trực tiếp trong code/string/annotation của APK.
- **HYPOTHESIS** — suy luận hợp lý từ code, chưa thấy trực tiếp.
- **UNKNOWN** — không có bằng chứng trong APK, cần test live.

---

## 3. READ-ONLY API LIST (ưu tiên cho xác minh firmware B)

Quy ước: URL đầy đủ = base + path trong annotation. **Header chung mọi request:**
`uid: <uuid-của-app-đã-authorize>`. Không có Bearer token nào khác.

### 3.1. ⭐ `GET http://192.168.42.1:12306/api/v1/get/c8version` — version firmware trực tiếp

- **EVIDENCE:** `DiagnoseApi.c8version()` / `SystemFwApi.c8version()` —
  annotation `@GET("api/v1/get/c8version")`, không param — CONFIRMED
  (đã đối chiếu độc lập bằng `dex_annot.py`).
- **Caller:** `DiagnoseRepository.c8version()` / `SystemFwObservables.c8version()`,
  base `http://192.168.42.1:12306/` — CONFIRMED.
- **Response:** `C8VersionHttpResponse{ version: String }` — CONFIRMED
  (app dùng trong `SystemFwViewModel` để so sánh version).
- **VERDICT:** CONFIRMED — **read-only** ✔
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" http://192.168.42.1:12306/api/v1/get/c8version
  ```

### 3.2. ⭐ `GET http://192.168.42.1:8080/api/v1/device/basic/info` — info thiết bị + version

- **EVIDENCE:** `DeviceApi.getDeviceBaseInfo()` — `@GET("api/v1/device/basic/info")`,
  không param — CONFIRMED.
- **Response:** `DeviceBaseInfo{ deviceID, deviceModel, needAuthorized, screenStatus,
  serverVersion, version }` — CONFIRMED. **Field `version` = version firmware cam.**
- **VERDICT:** CONFIRMED — **read-only** ✔
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" http://192.168.42.1:8080/api/v1/device/basic/info
  ```

### 3.3. `GET http://192.168.42.1:8080/api/v1/device/error/logs?timestamp={ts}&md5={md5}` — error log

- **EVIDENCE:** `DeviceService.getLogsFromDevice` / `DeviceLogApi.getLogsFromDevice` —
  `@GET("api/v1/device/error/logs")`, `@Query("timestamp")`, `@Query("md5")` — CONFIRMED.
- **Ngữ nghĩa param** (từ `DevicesRepository.postDeviceLogsToWeb`): app lấy `timestamp` +
  `content_md5` của bản log mới nhất trên cloud rồi hỏi cam log mới hơn — CONFIRMED (luồng).
- **HYPOTHESIS:** gọi `timestamp=0&md5=` (rỗng) trả toàn bộ error log — hợp lý, chưa test.
- **Response:** list `DeviceLogFromDevice{ content, content_md5, level, tag, ticket,
  timestamp }` — CONFIRMED.
- **VERDICT:** CONFIRMED endpoint — **read-only** ✔ (param `timestamp=0`: HYPOTHESIS)
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" \
    "http://192.168.42.1:8080/api/v1/device/error/logs?timestamp=0&md5="
  ```

### 3.4. `GET http://192.168.42.1:8080/api/v1/device/upgrade/logs` — lịch sử flash

- **EVIDENCE:** `DeviceService.deviceUpgradeLogs()` / `DeviceLogApi.getDeviceUpgradeLogsFromDevice()` —
  `@GET("/api/v1/device/upgrade/logs")`, không param — CONFIRMED.
- **VERDICT:** CONFIRMED — **read-only** ✔ (biết cam đã từng flash build nào)
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" http://192.168.42.1:8080/api/v1/device/upgrade/logs
  ```

### 3.5. `GET http://192.168.42.1:8080/api/v1/albums/medias/lists` — liệt kê + tải file thẻ

- **EVIDENCE:** `DeviceService.files(...)` / `AlbumApi.getAlbumFile(...)` —
  `@GET("/api/v1/albums/medias/lists")`, 5 `@Query`: `album, mediaType, orderBy, order,
  timeSince` — CONFIRMED.
- **Response:** `DeviceFileResponse` / `AlbumMedia{ mediaID, mediaType, imageURL,
  video{videoURL}, thumbnailURL, size, createTime, … }` — CONFIRMED.
- **Tải file:** URL đầy đủ = `http://192.168.42.1:8080` + `video.videoURL`
  (hoặc `imageURL`) — `DeviceFileResponse.getVideoHttpUrl()`, `AlbumHelper.getFileHttpUrl()` —
  CONFIRMED. → **Tải file từ thẻ nhớ qua Wi-Fi, không cần USB.**
- **VERDICT:** CONFIRMED — **read-only** ✔
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" \
    "http://192.168.42.1:8080/api/v1/albums/medias/lists?album=&mediaType=&orderBy=&order=&timeSince=" \
    | python3 -m json.tool | head -60
  # rồi: curl -H "uid: <APP_UUID>" "http://192.168.42.1:8080<videoURL>" -o clip.mp4
  ```

### 3.6. `GET http://192.168.42.1:12306/front/v1/diagnosedownload` — file diagnose

- **EVIDENCE:** `DiagnoseApi.downloadFileToTestSpeed()` —
  `@GET("front/v1/diagnosedownload")` + `@Streaming` — CONFIRMED.
  `DiagnoseViewModel.getDownloadUrl()` trả literal
  `"http://192.168.42.1:12306/front/v1/diagnosedownload"`, app tải bằng OkHttp trực tiếp
  (`ResponseBody.byteStream()` → lưu file) — CONFIRMED.
- **Nội dung file trả về: UNKNOWN** (tên gợi ý liên quan test tốc độ download).
- **VERDICT:** CONFIRMED endpoint — **read-only** ✔
- **Tái hiện:**
  ```bash
  curl -s -H "uid: <APP_UUID>" http://192.168.42.1:12306/front/v1/diagnosedownload -o diagnose.bin
  file diagnose.bin
  ```

### 3.7. Các endpoint chỉ đọc khác (CONFIRMED)

| # | Method | URL | Ghi chú |
|---|---|---|---|
| 7 | `GET` | `http://192.168.42.1:8080/api/v1/device/info?timestamp={ts}&timezone={tz}` | `DeviceApi.getCurrentDevice`; app truyền `System.currentTimeMillis()` + timezone offset — dùng để check "đã kết nối cam" |
| 8 | `GET` | `http://192.168.42.1:8080/api/v1/device/storage/info` | `DeviceService.getStorage()` — dung lượng thẻ |
| 9 | `GET` | `http://192.168.42.1:8080/api/v1/device/settings/` | `DeviceService.getDeviceSettings()` — chỉ đọc (bản POST cùng path là write) |
| 10 | `GET` | `http://192.168.42.1:8080/api/v1/device/connection/authorization` | `DeviceService.getAuthorizationStatus()` — kiểm tra uid đã authorize chưa |
| 11 | `GET` | `http://192.168.42.1:8080/api/v1/albums/info?album=` | `AlbumApi.getAlbumInfo()` |
| 12 | `GET` | `http://192.168.42.1:12306/api/v1/c1/getdiagnoselist` | `DiagnoseApi.getDiagnoseList()` → `DiagnoseListResponse{count}` + list `DiagnoseItem` (mỗi item chứa URL động cho `diagnose(@Url)`) |
| 13 | `GET` | `http://192.168.42.1:12306/api/v1/c1/getrestorestate` | `SystemFwApi.getRestoreState()` |
| 14 | `GET` | `http://192.168.42.1:8080/api/v1/adas/camera/still/duration` | read-only |
| 15 | `GET` | `http://192.168.42.1:8080/api/v1/adas/settings` | read-only |
| 16 | `GET` (động) | `@Url` + `@Streaming`: `downloadPhoto(url)`, `diagnose(url)`, `diagnose1(url)` | URL do app truyền vào |

### 3.8. Legacy path `http://192.168.1.1` (code `cc.minieye.c2.*`)

- `GET http://192.168.1.1/getlog.tar.gz` (header `Connection: close`) —
  `c2/business/diagnose/DiagnoseRepository.downloadLog()` — CONFIRMED (string + caller).
- `GET http://192.168.1.1/thumb<path>` / `http://192.168.1.1<path>` —
  `c2/business/file/File.imageUrl()` — CONFIRMED (string + caller).
- **VERDICT:** CONFIRMED tồn tại trong APK — **UNKNOWN** có hoạt động với C2M hiện tại
  không (IP `.1.1` khác `.42.1`; có thể dành cho dòng cam cũ).

### 3.9. `/cgi-bin/Config.cgi` (legacy CGI)

- Strings CONFIRMED trong pool:
  `/cgi-bin/Config.cgi?action=get&property=Camera.Menu.SDInfo`,
  `/cgi-bin/Config.cgi?action=get&property=Camera.menu.UUID`,
  `/cgi-bin/Config.cgi?action=set&property=SD0&value=format`.
- **Không tìm thấy method nào** trong cả 3 dex dùng const-string chứa các path này
  (đã quét toàn bộ bytecode).
- **VERDICT:** CONFIRMED string — **UNKNOWN** cách dùng (có thể dead code hoặc gọi từ native).

---

## 4. DANGEROUS API LIST — chỉ liệt kê, KHÔNG gọi, KHÔNG thử

| # | Method | URL đầy đủ | Tác động | Evidence |
|---|---|---|---|---|
| 1 | `POST` | `http://192.168.42.1:8080/api/v1/device/storage/format` | **Format thẻ nhớ** (`StorageApi.formatSdcard`, `DeviceService.initSdcard`) | annotation CONFIRMED |
| 2 | `POST` | `http://192.168.42.1:8080/api/v1/device/storage/clear` | Xóa storage (body `ClearCacheCommand`) | annotation CONFIRMED |
| 3 | `POST` | `http://192.168.42.1:8080/api/v1/albums/medias/deletes` | **Xóa file** trên thẻ (body `DeleteFileReq`) | annotation CONFIRMED |
| 4 | `POST` | `http://192.168.42.1:8080/api/v1/device/restart` | **Reboot cam** | annotation CONFIRMED |
| 5 | `POST` (@Multipart) | `http://192.168.42.1:8080/api/v1/device/upgrade/package` | **OTA / upload firmware** (`UploadDevicePkgService`) | annotation CONFIRMED |
| 6 | `POST` | `http://192.168.42.1:12306/api/v1/c1/restore` | Restore device (`SystemFwApi.restoreDevice`) | annotation CONFIRMED |
| 7 | `POST` | `http://192.168.42.1:12306/api/v1/c1/checkflash` | Check flash (ghi) | annotation CONFIRMED |
| 8 | `POST` | `http://192.168.42.1:12306/front/v1/uploadfile` | Upload file lên cam (`SystemFwApi.uploadFile`) | annotation CONFIRMED |
| 9 | `POST` | `http://192.168.42.1:12306/front/v1/diagnoseupload` | Upload diagnose | annotation CONFIRMED |
| 10 | `POST` | `http://192.168.42.1:8080/api/v1/device/settings/` | Ghi settings (JSON, `Content-Type: application/json`) | annotation CONFIRMED |
| 11 | `POST` | `http://192.168.42.1:8080/api/v1/adas/settings` | Ghi ADAS settings | annotation CONFIRMED |
| 12 | `POST` | `http://192.168.42.1:8080/api/v1/adas/camera/adjust?status=&pitch=&yaw=&roll=` | Calibration camera | annotation CONFIRMED |
| 13 | `POST` | `http://192.168.42.1:8080/api/v1/device/factory/settings` | Factory reset | annotation CONFIRMED |
| 14 | `POST` | `http://192.168.42.1:8080/api/v1/albums/videos/record`, `…/albums/photos/take` | Bắt đầu quay / chụp (đổi trạng thái cam) | annotation CONFIRMED |
| 15 | `POST` | `http://192.168.42.1:8080/api/v1/device/connection/authorization`, `/authorization/code/*`, `/authorization/history/clear` | Đổi trạng thái authorize | annotation CONFIRMED |
| 16 | `GET/POST?` | `/cgi-bin/Config.cgi?action=set&property=SD0&value=format` (host UNKNOWN) | Format (legacy) | string CONFIRMED, usage UNKNOWN |

---

## 5. WHAT REMAINS UNKNOWN

1. **`/tmp/c2m_idle.marker` và danh sách process:** không có endpoint nào trong APK đọc
   file tùy ý trên cam hay liệt kê process. API file duy nhất là `/api/v1/albums/*`
   (thẻ nhớ) và `diagnosedownload`. → **Không có "shell đọc file" trong app chính thức.**
2. **Nội dung `front/v1/diagnosedownload` trả về** — biết là file stream, chưa biết là gì.
3. **`diagnose(@Url)`** — URL động lấy từ `getdiagnoselist`; chưa biết danh sách đầy đủ.
4. **Endpoint nào (nếu có) cho phép anonymous** không cần `uid` authorize.
5. **`/cgi-bin/Config.cgi`** — string tồn tại nhưng không có caller trong dex → có thể dead code.
6. **`192.168.1.1` vs `192.168.42.1`** — hai code path (`c1` mới dùng `.42.1`, `c2` legacy
   dùng `.1.1`). C2M hiện tại dùng path nào cho log — cần test live.
7. **Response JSON chi tiết** — tên field JSON vs Java field có thể khác do Gson
   `@SerializedName`.

---

## 6. NEXT STEPS — quy trình xác minh firmware B qua Wi-Fi (đề xuất)

> Điều kiện: điện thoại join Wi-Fi AP của cam (`MINIEYE-<deviceID>`, pass mặc định
> `12345678` theo manual). Header `uid`: lấy UUID app đã authorize (MMKV của app
> trên điện thoại đã kết nối), hoặc thử UUID bất kỳ — nếu cam trả **401** thì authorize
> lại bằng app trước. **Chỉ chạy các lệnh GET dưới đây; không chạy bất kỳ POST nào
> trong §4.**

```bash
UID="<APP_UUID>"   # UUID app đã authorize với cam

# 0) Kiểm tra kết nối + auth
curl -s -H "uid: $UID" \
  "http://192.168.42.1:8080/api/v1/device/info?timestamp=$(date +%s)000&timezone=7" \
  | head -c 600; echo

# 1) ⭐ VERSION FIRMWARE — so sánh với build B mong đợi
curl -s -H "uid: $UID" http://192.168.42.1:12306/api/v1/get/c8version; echo
curl -s -H "uid: $UID>" http://192.168.42.1:8080/api/v1/device/basic/info \
  | python3 -m json.tool

# 2) Error log của cam (thử timestamp=0 để lấy toàn bộ)
curl -s -H "uid: $UID" \
  "http://192.168.42.1:8080/api/v1/device/error/logs?timestamp=0&md5=" \
  | head -c 2000; echo

# 3) Lịch sử các lần flash trước
curl -s -H "uid: $UID>" http://192.168.42.1:8080/api/v1/device/upgrade/logs \
  | head -c 2000; echo

# 4) Liệt kê file thẻ + tải 1 file (xác minh thẻ còn nguyên)
curl -s -H "uid: $UID" \
  "http://192.168.42.1:8080/api/v1/albums/medias/lists?album=&mediaType=&orderBy=&order=&timeSince=" \
  | python3 -m json.tool | head -60
# rồi: curl -H "uid: $UID" "http://192.168.42.1:8080<videoURL_từ_response>" -o clip.mp4

# 5) File diagnose kênh 12306
curl -s -H "uid: $UID" http://192.168.42.1:12306/front/v1/diagnosedownload -o diagnose.bin
file diagnose.bin

# 6) Danh sách diagnose items (URL động)
curl -s -H "uid: $UID" http://192.168.42.1:12306/api/v1/c1/getdiagnoselist

# 7) Storage / auth status
curl -s -H "uid: $UID" http://192.168.42.1:8080/api/v1/device/storage/info; echo
curl -s -H "uid: $UID" http://192.168.42.1:8080/api/v1/device/connection/authorization; echo
```

Python tương đương (lấy version):

```python
import requests
UID = "<APP_UUID>"   # UUID app đã authorize với cam
h = {"uid": UID}
print(requests.get("http://192.168.42.1:12306/api/v1/get/c8version",
                    headers=h, timeout=10).json())
print(requests.get("http://192.168.42.1:8080/api/v1/device/basic/info",
                    headers=h, timeout=10).json())
```

**Thứ tự ưu tiên khi xác minh firmware B:**
1. `GET :12306/api/v1/get/c8version` → so `version` với build B mong đợi.
2. `GET :8080/api/v1/device/basic/info` → đối chiếu field `version`.
3. `GET :8080/api/v1/device/upgrade/logs` → xem log có ghi nhận lần flash B không.
4. `GET :8080/api/v1/device/error/logs?timestamp=0&md5=` → kiểm tra lỗi sau flash.

---

## 7. Kết luận

- ✅ **Có ít nhất 2 endpoint đọc version firmware qua Wi-Fi:**
  `GET :12306/api/v1/get/c8version` và `GET :8080/api/v1/device/basic/info`
  (field `version`) — CONFIRMED từ annotation trong dex.
- ✅ **Có endpoint đọc log:** `:8080/api/v1/device/error/logs`,
  `:8080/api/v1/device/upgrade/logs` — CONFIRMED.
- ✅ **Có endpoint liệt kê + tải file từ thẻ:** `:8080/api/v1/albums/medias/lists` — CONFIRMED.
- ❌ **Không có** endpoint đọc file tùy ý (`/tmp/c2m_idle.marker`) hay danh sách
  process trong app chính thức.
- ⚠️ Rào cản duy nhất: cần header `uid` đã được cam authorize (401 nếu chưa) —
  lấy từ app đã kết nối, hoặc authorize lại bằng app.

---

*Phân tích tĩnh bằng androguard + parser DEX annotation tự viết (`dex_annot.py`).
Không gọi bất kỳ API nào tới cam, không thực thi code mạng.
Không phát hiện key/credential/serial thật nào cần che giấu.
File làm việc: `~/workspace/c2m-apk/analysis/` (FINDINGS.md, dex_annot.py, disas.py).*
