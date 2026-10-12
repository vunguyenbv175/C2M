# UTOUR GO APK — Modding Guide cho Coding Agent

> **Mục đích:** tài liệu kỹ thuật để coding agent mod APK `cc.minieye.utour`
> (điều khiển cam MINIEYE/UTOUR C2M qua Wi-Fi). Viết từ kết quả phân tích tĩnh,
> mọi class/method/path đều đã verify trong dex.
>
> **Báo cáo phân tích API đầy đủ:** [`APK_UTOUR_GO_WIFI_API_V1.md`](./APK_UTOUR_GO_WIFI_API_V1.md)
> (endpoint read-only, dangerous list, auth, cross-check live).
> Doc này chỉ tập trung vào **những gì cần để mod**.

---

## 1. Fingerprint APK (đã verify)

| Trường | Giá trị |
|---|---|
| Package | `cc.minieye.utour` |
| Version | 6.1.20 (versionCode 23) |
| App name | UTOUR GO |
| Ngôn ngữ | Kotlin + Java (có `kotlin.jvm.internal.Intrinsics` check khắp nơi) |
| Native lib (`.so`) | **KHÔNG CÓ** — pure Dalvik, mod không lo JNI |
| Dex | `classes.dex` (8.9 MB), `classes2.dex` (9.3 MB), `classes3.dex` (1.1 MB) |
| Obfuscation | **Hầu như không** — tên class/method/interface đọc được nguyên văn |
| HTTP stack | OkHttp3 + Retrofit2 + RxJava2 |
| Converter | c2 dùng `SimpleXmlConverterFactory` (XML!); c1 dùng Gson (JSON) |
| Chữ ký file phân tích | `META-INF/BNDLTOOL.RSA` — **test key của bundletool** (do APKPure resign split APK), **không phải** key production của MINIEYE |

**Hệ quả cho modding:**
- Mọi bản mod đều phải **ký lại bằng key riêng** → **bắt buộc gỡ bản gốc trước khi cài**
  (Android từ chối cài đè khi chữ ký khác).
- **Giữ nguyên package name** `cc.minieye.utour` — đổi sẽ vỡ đường dẫn MMKV, FileProvider, deep link.
- Nên **tăng `versionCode`** (23 → 24+) để phân biệt bản mod với bản gốc.
- Play Store update sẽ ghi đè mất mod — tắt auto-update cho app này.

## 2. Toolchain

```bash
# 1. Bung (cần Java + apktool trên máy mod)
apktool d base.apk -o utour-mod

# 2. Sửa smali trong utour-mod/smali[_classes2,_classes3]/...
#    hoặc res/values/strings.xml, AndroidManifest.xml

# 3. Đóng gói + ký
apktool b utour-mod -o utour-mod.apk
apksigner sign --ks mykey.jks --out utour-mod-signed.apk utour-mod.apk
adb install -r utour-mod-signed.apk   # gỡ bản gốc trước nếu trùng package
```

**Tool phân tích tái dùng** (trong `~/workspace/c2m-apk/analysis/`):
- `dex_annot.py` — trích Retrofit annotations (`@GET/@POST/@Query/@QueryMap/@Body/@Part/@Url/@Streaming`)
  trực tiếp từ binary dex. Dùng để đối chiếu sau khi mod (verify annotation còn nguyên).
- **Lưu ý:** annotation Retrofit của nhánh **c1 đã bị strip** trong bản gốc
  (`annotations_off = 0`); nhánh **c2 còn nguyên**. Khi mod thêm method Retrofit vào
  interface c2, annotation sẽ được giữ (apktool rebuild không strip).

## 3. Bản đồ code theo mục tiêu mod

### 3.1. Đổi base URL / IP cam (mod phổ biến nhất)

| Nhánh | Class | Dex | Điểm sửa (smali) |
|---|---|---|---|
| c2 | `cc.minieye.c2.net.C2Api$Companion` → `createC2Api()` | classes.dex | `const-string v1, "http://192.168.1.1"` → IP mới |
| c2 | `cc.minieye.c2.net.ApiWrapper$Companion` → `createC2Api()` | classes.dex | tương tự |
| c2 | `cc.minieye.c2.business.setting.SettingApi$Companion` → `api()` | classes.dex | tương tự |
| c2 | `cc.minieye.c2.business.version.DeviceVersionApi$Companion` → `api()` | classes.dex | tương tự (kênh OTA) |
| c1 | `cc.minieye.c1.deviceNew.DeviceBaseRepository` → `getDeviceHttpClient()` | classes.dex | `const-string "http://192.168.42.1:8080/"` |
| c1 | `cc.minieye.c1.deviceNew.diagnose.DiagnoseRepository` | classes.dex | `const-string "http://192.168.42.1:12306/"` |

Disassembly đã verify của `C2Api$Companion.createC2Api()` (smali tương đương):
```smali
new-instance v0, Lretrofit2/Retrofit$Builder;
invoke-direct {v0}, Lretrofit2/Retrofit$Builder;-><init>()V
const-string v1, "http://192.168.1.1"          # <-- SỬA DÒNG NÀY
invoke-virtual {v0, v1}, Lretrofit2/Retrofit$Builder;->baseUrl(Ljava/lang/String;)Lretrofit2/Retrofit$Builder;
...
invoke-static {}, Lretrofit2/converter/simplexml/SimpleXmlConverterFactory;->create()...
invoke-virtual {v0}, Lretrofit2/Retrofit;->create(Ljava/lang/Class;)Ljava/lang/Object;
```
→ Chỉ cần đổi 1 `const-string` là toàn bộ API c2 trỏ sang IP mới. Không cần đụng annotation.

### 3.2. Thêm endpoint CGI mới (nhánh c2)

Pattern chuẩn của app — làm theo là ăn ngay:

1. **Thêm method vào interface** `cc.minieye.c2.net.C2Api` (smali):
   ```smali
   # ví dụ: đọc property mới
   .method public abstract myNewProp(Ljava/util/Map;)Lio/reactivex/Observable;
       .annotation runtime Lretrofit2/http/GET;
           value = "cgi-bin/Config.cgi"
       .end annotation
       .annotation runtime Lretrofit2/http/QueryMap;
       .end annotation
   .end method
   ```
   Hoặc dùng style có sẵn: `getVersion(@Query("action") String, @Query("property") String)`
   như `C2Api.getVersion` — đã verify annotation.
2. **Gọi từ Repository**: theo pattern `BaseRepository.get()` —
   dựng `Map{action="get", property="Camera.menu.X", VersionPrototal="1.0.1"}`
   rồi gọi `c2Api.config(map)`. **Nhớ `VersionPrototal=1.0.1`** (param bắt buộc, giữ nguyên typo).
3. **Response**: plain text split `\n` (`BaseRepository.parseResponse()`); file-list thì XML
   (`FileRepository.parse()`, converter SimpleXML).

Danh sách `property=` đã biết: xem §1.5 phần c2 trong
[`APK_UTOUR_GO_WIFI_API_V1.md`](./APK_UTOUR_GO_WIFI_API_V1.md) (bảng `action=get` đầy đủ).

### 3.3. Thêm màn hình / nút mới

- Manifest có **83 activities, 9 services, 0 receivers, 4 providers** (đã liệt kê bằng androguard).
- Entry theo nhánh:
  - c2 (UTOUR-M6): `cc.minieye.c2.C2MainActivity` — màn hình chính; `cc.minieye.c2.business.diagnose.DiagnoseActivity`,
    `cc.minieye.c2.business.file.AllFileActivity`, `cc.minieye.c2.business.setting.SettingActivity`,
    `cc.minieye.c2.business.storage.StorageManageActivity`, `cc.minieye.c2.business.version.TestVersionActivity`.
  - c1: `cc.minieye.c1.deviceNew.main.NewDeviceMainActivity`, `cc.minieye.c1.deviceNew.diagnose.DeviceDiagnoseActivity`.
- Thêm Activity mới: tạo class + khai báo trong `AndroidManifest.xml` (apktool rebuild tự xử resource).
- Logic gọi cam đặt ở **Repository** (`cc.minieye.c2.business.<domain>.*Repository`), UI gọi qua
  **ViewModel** (`cc.minieye.c2.viewmodel.*`, `business.*.*ViewModel`) — theo đúng kiến trúc MVVM có sẵn.

### 3.4. OTA / upload firmware (đọc kỹ trước khi mod)

| Nhánh | Upload endpoint | Code |
|---|---|---|
| c2 | `POST http://192.168.1.1/action/upload` (multipart: `@Part(name)` + `@Part` file) | `DeviceVersionApi.upload()`, `C2UploadPkgService.uploadPkg2Device()` / `otaUpdate()` |
| c1 | `POST http://192.168.42.1:8080/api/v1/device/upgrade/package` (multipart) | `DevicesRemoteRepository.upgradePackage()`, `UploadDevicePkgService` |

- Check-update cloud (c2): `POST api/mpk-release/check-update` (`ServerVersionApi.getDeviceUpdateFromWeb`),
  `GET api/device/c2/get-latest-version`, `GET api/device/c2/get-sn?uuid=` — base URL cloud lấy runtime.
- Định dạng package app từng cache: `.mpk`, `.mpkg.tar`, `.enc` (có thể mã hóa) — vd `u453_C2LMain.mpk`.
- **Mod an toàn:** thêm UI "chọn file local → upload" bỏ qua bước check cloud (vì hãng đã ngừng update,
  cloud không còn trả về gì). **Không tự động flash** — để user bấm xác nhận.

### 3.5. Auth (để biết có cần bypass gì không)

- **Nhánh c2: KHÔNG CÓ auth** — Retrofit builder trơn, không interceptor, không header.
  Mod không cần đụng gì.
- **Nhánh c1:** mọi request gắn header `uid` (`DeviceBaseRepository` interceptor,
  `UidHelper.getUid()` — UUID tự sinh lưu MMKV key `'uid'`); cam trả 401 nếu chưa authorize.
  Muốn mod c1 bỏ qua auth: sửa interceptor hoặc hardcode `uid` đã authorize.

### 3.6. RTSP (nếu mod liên quan video)

| Nhánh | URL | Code |
|---|---|---|
| c2 trước | `rtsp://192.168.1.1/liveRTSP/av4` | `C2MainActivity.playRealtimeMedia` |
| c2 sau | `rtsp://192.168.1.1/liveRTSP/av5` | `C2MainActivity.playRealtimeMedia` |
| c1 live | `rtsp://192.168.42.1/live` | `NewDeviceMainActivity$1.onStarted` |
| c1 playback | `rtsp://192.168.42.1/tmp/SD0/` | `AlbumHelper.getVideoRtspUrl` |

## 4. Những điểm dễ vỡ khi mod (checklist)

- [ ] **Backup APK gốc** trước khi mod (giữ file `base.apk`).
- [ ] Sau rebuild, chạy `dex_annot.py` đối chiếu annotation Retrofit còn nguyên
      (nhất là khi thêm method mới vào interface c2).
- [ ] Đổi `versionCode` 23 → 24+ trong `apktool.yml`/`AndroidManifest.xml` để phân biệt bản mod.
- [ ] Không đổi `package` / `applicationId`.
- [ ] Mọi `const-string` URL trong smali: search toàn bộ `smali*/` cho `192.168.1.1`
      (c2) / `192.168.42.1` (c1) để không sót base URL (có 4+ chỗ dựng client ở c2).
- [ ] Test trên máy phụ trước nếu có; với cam thật: bắt đầu bằng các endpoint **read-only**
      (`Camera.menu.FWVersion`, `getlog.tar.gz`) để xác nhận app mod giao tiếp được.
- [ ] **Không mod/tắt** các guard ở `C2UploadPkgService` nếu chưa hiểu rõ — flash sai = brick cam.

## 5. Ví dụ: thêm nút "Verify firmware B" (1 chạm)

Mục tiêu: bấm 1 nút → đọc version, tải log, liệt kê file thẻ → hiện kết quả.

1. Thêm method vào `C2Api` (smali) — hoặc tái dùng `config(@QueryMap)` có sẵn (khuyến nghị:
   **không cần thêm method**, chỉ gọi `config()` với map mới).
2. Trong `SettingRepository` (hoặc Repository mới), viết 3 hàm theo pattern `getFWVersion()`:
   - `getFWVersion()`: map `{action=get, property=Camera.menu.FWVersion, VersionPrototal=1.0.1}`
   - `getSDInfo()`: map `{action=get, property=Camera.Menu.SDInfo, VersionPrototal=1.0.1}`
   - log: gọi `DiagnoseRepository.downloadLog()` có sẵn (`http://192.168.1.1/getlog.tar.gz`)
3. Thêm Activity mới (khai báo manifest) với 1 nút + TextView hiện kết quả;
   gọi 3 hàm trên qua RxJava `Observable.zip`.
4. Không cần auth, không cần đổi base URL nếu giữ `192.168.1.1`.

Toàn bộ class/method/pattern trên đã verify trong dex — agent chỉ việc làm theo,
không cần phân tích lại.

---

*Doc này là bản đồ modding; bản đồ API đầy đủ (endpoint, param, response, dangerous list,
cross-check live với UTOUR-M6) ở [`APK_UTOUR_GO_WIFI_API_V1.md`](./APK_UTOUR_GO_WIFI_API_V1.md).
Phân tích tĩnh bằng androguard + `dex_annot.py`; không gọi mạng tới cam.*
