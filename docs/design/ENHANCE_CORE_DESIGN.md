# EF-A04 — c2m-enhance Core (read-only V0)

**Mục tiêu:** daemon tăng cường đầu tiên, chỉ đọc, không điều khiển stock.

```text
Mock/StockADASProvider -> EnhanceCore.Tick() -> DisplayState -> Mock/M4Adapter
                                              -> ProviderRegistry (health)
                                              -> EventBus (warning/system events)
                                              -> /status + /diagnostics (Web V0)
```

## Thiết kế

- `include/c2m/core/event_bus.hpp`: bus sync nhỏ, giữ 512 event gần nhất.
- `include/c2m/core/provider_registry.hpp`: map tên provider -> ServiceHealth.
- `include/c2m/core/c2m_enhance.hpp`: `EnhanceCore::Tick(now_ms, ego_speed)`:
  1. `adas_->Poll()` (non-blocking, stale nếu timeout 500ms)
  2. `BuildFromAdas()` thành DisplayState
  3. `disp_->Render()` (mock hoặc M4 dry-run)
  4. Cập nhật registry + publish event warning nếu fcw/pcw/ldw.
- `mode="read-only"` là gate cứng V0: không có code path nào gọi stock recorder/config.

## Tương lai (không làm sprint này)

- Watchdog restart enhancement-daemon (không restart stock).
- `c2m-diagnostics` tách riêng khi cần SoC-temp/SD-health từ driver thật.
- Updater an toàn (version/SHA-256/signature/rollback) — EF P11.
