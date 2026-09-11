# Báo cáo Delta — đáp ứng GATES_A_F_DELTA_REVIEW (R1–R9)

Trả lời `docs/reviews/2026-09-11_GATES_A_F_DELTA_REVIEW.md` + cập nhật
`docs/master/DEBUG_MEMORY.md` theo protocol (giữ lịch sử SUPERSEDED).

## WHAT WAS BUILT

P0:

```text
R1: IAdasProvider::PollAt(now_ms) + IClock/ManualClock; EnhanceCore::Tick
    truyền caller time; test advancing-time C++/Python (fresh@1200/stale@1601).
R2: is_second_crucial -> metadata only (raw.second_crucial_count), không tạo lead;
    schema wording + cả 2 normalizer + test đồng bộ (option 1).
R3: ci.yml chỉ clean-checkout (cmake/ctest/headers/pytest, KHÔNG firmware);
    firmware-evidence.yml riêng (manual); local_ci.py --strict/--evidence.
```

P1:

```text
LZO: tools/fw/lzo_blockdec.c (project code) + minilzo upstream (tool-time) ->
    build/lzo_blockdec; lzo_helper.py batch; ubifs_extract_file.py fallback.
adas EN/VI trích đúng hash canonical (0dcc6982…/997b71c2…).
EVIDENCE_ADAS_STRINGS.json: 71 tokens, 68 BOTH counts identical.
Schema regen 53 fields (17 CONFIRMED/8 HIGH/25 RAW-ONLY/3 UNKNOWN);
key routing -> CONFIRMED; TSR/ScreenAudioMsg/pedWarning rows mới.
readelf symtab adas: 3875/3875/3875 đúng, SystemInit 124->100.
```

P2:

```text
R5: IDisplayPlanner (pure) + IStockTransmitter::Transmit(msgs, AllowTransmit);
    core chỉ phụ thuộc planner; zero-sender test giữ.
R6: lateral_raw/longitudinal_raw/long_dist_raw/ttc_raw/ego_speed_raw/distance_raw.
R8: score = distance_m + 1.0*heading + 500m oneway-violation; fixture way104
    chứng minh closest-beats-heading; parse_maxspeed explicit 7 reasons.
R9: planned_messages populate từ Plan, assert trong smoke.
R7: Gate E relabel SYNTHETIC toàn bộ.
```

## WHAT WAS PROVEN

- Local CI strict + evidence: headers/ctest/pytest/evidence-no-drift ALL GREEN.
- Daemon chạy thật, planner-only.
- Schema JSON regenerate deterministic (không drift).
- 4 bug mới do build/test bắt (const Poll, daemon field, lane lift đã sửa trước;
  đợt này: ripple PollAt/planner/R6 — compiler bắt hết).

## WHAT REMAINS UNKNOWN

- Remote GitHub CI: chưa xem được kết quả sau push — owner xác nhận giúp.
- TSR enablement, wire units/enums, transport vật lý, WS path/source (như cũ).
- Producer/consumer xref sâu (callsite) vẫn dựa prior work; string presence đã CONFIRMED.

## STOCK COMPATIBILITY IMPACT

Zero: chỉ đọc ảnh firmware; không transmit (type-level); L3 BLOCKED giữ nguyên.

## PERFORMANCE IMPACT

Batch LZO 1 subprocess/file; daemon/pipeline như cũ. Chưa đo trên thiết bị.

## RISKS

- minilzo GPL chỉ dùng tool-time, không vendor vào repo (đã tách template).
- Score road weights (1.0/500m) heuristic cho fixture, cần tune với dữ liệu thật.
- Reviewer cần duyệt lại các verdict CONFIRMED mới nâng.

## NEXT HIGHEST-VALUE TASK

1. Owner xác nhận GitHub Actions xanh sau push.
2. EN baseline capture → L0/L1 (P3 hardware).
3. ARM cross-build.
4. OSM VN-scale + tune road weights.
