# Báo cáo đáp ứng Owner Review V2 — Gates A–F (2026-09-11)

Trả lời `docs/reviews/2026-09-11_SPRINT1_OWNER_REVIEW_V2.md`. Mọi claim dưới đây
đều chạy lại được bằng lệnh trong repo.

## WHAT WAS BUILT

Gate A — firmware-grounded contract:

```text
docs/reverse/STOCK_ADAS_SCHEMA_V2.md
docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json   (52 fields: 13 CONFIRMED / 11 HIGH-CONF / 24 RAW-ONLY / 4 UNKNOWN)
docs/reverse/EVIDENCE_CARDV_CONTRACT.json      (token search trong cardv ELF gốc)
docs/reverse/EVIDENCE_CARDV_SYMDIFF.json       (readelf dynsym EN/VI)
tools/fw/stock_adas_schema_evidence.py         (search upgrade image)
tools/fw/stock_adas_schema_v2.py               (generator bảng field, tự đo lại)
tools/fw/cardv_contract_evidence.py
tools/fw/cardv_symdiff.py
tools/fw/adas_plainblock_evidence.py
tools/fw/ubifs_ls.py / ubifs_extract_plain.py / extract_rootfs_cpio.py / rootfs_cpio_grep.py
```

Gate B — foundation safety (F1/F2/F4/F5/F11/F12):

```text
include/c2m/adas/adas_state.hpp          (AdasRaw, Evidence, ProcessPresence, LeadInfo)
include/c2m/adas/stock_adas_provider.hpp (sole drivers, honest health, no fallback)
include/c2m/display/m4_policy.hpp        (canonical policy, default-deny)
include/c2m/display/m4_adapter.hpp       (Plan vs RenderEx(capability), TransmitStatus)
include/c2m/core/c2m_enhance.hpp         (core không bao giờ transmit)
tools/m4/m4_policy.json + test_m4_policy.py   (parity C++/Python)
tools/m4/normalize_adas.py + test (negative cases)
```

Gate C — build reality: `.github/workflows/ci.yml`, `tools/ci/local_ci.py`,
WinLibs GCC 16.1.0 local proof (2 index bug do CI bắt được đã sửa).

Gate D — daemon thật: `src/enhance/main.cpp` (`c2m-enhance --scenario --ticks
--period-ms`, SIGINT/SIGTERM, JSON/tick), target CMake + ctest.

Gate E — real-data path: `tools/m4/make_fixture.py` (frame stock-compatible) +
`test_real_data_path.py` (decode→normalize→DisplayState). Fixture thay bằng
pcap thật khi có hardware mà không đổi consumer.

Gate F — M4 passive: L3 BLOCKED, `GPSSpeed` gỡ khỏi L2, `replay_guard` đồng bộ
policy JSON.

Road (F10): `tools/road/fixtures/tiny_map.osm` parse thật → SQLite R*Tree →
query heading-aware → fusion test.

Web (F8): gắn nhãn HOST PROTOTYPE trong HTML + `/status.transport=mock`.

## WHAT WAS PROVEN

- SHA-256 TAR gốc khớp README; partition carve (rootfs gzip-cpio 560 entries,
  customer UBIFS 227 files).
- Rootfs delta đúng {cardv, sc7a20.ko}; libflow.so và 4 lib khác identical EN/VI.
- cardv SHA khớp contract doc; JSON template byte-context (module_websocket.cpp);
  `SendGPSSpeedToScreen`/`nmea_BDGSV2info_na` VI-ONLY; `nmea_satinfo` EN-ONLY.
- Symbol diff tái lập đúng 9 hàm đổi size + EN-only 4 / VI-only 2.
- Audio assets chứng minh 6 warning class; FCW/HMW identical, 5 WAV VI thu lại.
- model.txt identical 6 ID; git_commit khác.
- adas .rodata nằm trong 1,140 LZO blocks → string-proof trực tiếp BLOCKED trung
  thực, kèm oracle (block0 → ELF, full file → SHA) + lệnh reproduce.
- Local CI: 16 headers standalone + cmake build + 2 ctest + 6 pytest — ALL GREEN.
- Daemon chạy thật: `c2m-enhance --scenario fcw --ticks 3` ra JSON/tick,
  transport=0 (DryRun).
- Fixture path: decode 4 frame không warning → fcw/pcw/ldw/lead đúng.
- Bắt được 3 bug thật nhờ build/test: mock field cũ, thiếu AdasRaw.deviate_state,
  const-correctness Poll, lane lift nesting.

## WHAT REMAINS UNKNOWN

```text
UNKNOWN: unit/sign mọi distance/TTC/headway/coords; enum warning/label/type/deviate;
  VB/SAG/HMW trigger mapping; TSR enablement; ScreenAudioMsg; transport vật lý M4;
  WS path + source string; adas .rodata trực tiếp (chờ LZO).
```

## STOCK COMPATIBILITY IMPACT

Zero: chỉ đọc ảnh firmware (read-only), Web/daemon port riêng, M4 L3 blocked,
không flash, không sửa stock. `EnhanceCore` không giữ capability transmit.

## PERFORMANCE IMPACT

Header-only + daemon nhẹ (poll 200ms, bus 512 events); Python chỉ chạy host.
Chưa đo trên SSC8838G (cần cross-toolchain, để dành).

## RISKS

- adas-side key routing vẫn HIGH-CONFIDENCE (không CONFIRMED) tới khi có LZO/pcap.
- MinGW build chứng minh logic, chưa phải ARM cross-build.
- VI audio thu lại nhưng nội dung (tiếng Việt?) chưa nghe kiểm chứng.

## NEXT HIGHEST-VALUE TASK

1. LZO (minilzo build bằng GCC mới có) → trích adas → string-proof trực tiếp →
   nâng key routing lên CONFIRMED.
2. `collect_baseline.sh` trên EN tốt → L0 transport → pcap → L1.
3. ARM cross-toolchain → build target nhúng.
4. OSM VN-scale preprocessing trên host.

Phân loại: CONFIRMED/HIGH-CONFIDENCE/RAW-ONLY/UNKNOWN theo EVIDENCE JSON;
không field nào bịa semantics.
