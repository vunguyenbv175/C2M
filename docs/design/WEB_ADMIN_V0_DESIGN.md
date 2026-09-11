# EF-A05 — Web Admin V0 (read-only)

**Nguyên tắc:** stock app giữ nguyên. `c2m-web` là tiến trình riêng, crash không
ảnh hưởng ghi hình. V0 chỉ GET, không settings-write, không update.

## Endpoints V0

```text
GET /status       EnhanceCore.Last() + registry snapshot (mock scenario)
GET /diagnostics  DiagSnapshot tĩnh + version road-DB + uptime
GET /             trang HTML nhẹ, auto-refresh /status (không JS framework)
```

## Chạy trên máy dev (không cần hardware)

```sh
python3 src/web/web_admin.py --scenario lead --port 8099
# mở http://127.0.0.1:8099/  /status  /diagnostics
```

`scenario`: `idle|lead|fcw|ldw|ped` (từ MockADASProvider).

## Lên thiết bị thật (sau này)

- Thay `MockADASProvider` bằng `StockADASProvider` nối libflow :26012.
- Bind `127.0.0.1` hoặc AP-interface, không chiếm port stock (8080/26012).
- Server C++ nhúng (civetweb/mongoose-style, single-thread) thay Python; giữ
  nguyên JSON schema V0 để PWA không phải sửa.
- `/live` overlay và `/update` để dành V1 sau khi gate tương thích stock pass.
