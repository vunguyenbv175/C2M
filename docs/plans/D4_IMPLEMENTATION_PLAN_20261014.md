# C2M D4 — Kế hoạch triển khai Road Intelligence + màn hình M4

**Ngày:** 2026-10-14  
**Trạng thái:** PLAN / KHÔNG PHẢI firmware đã phát hành  
**Nguồn nền:** `main@4f601ab9` (D3 source hiện có), nhánh nghiên cứu `research/d4-traffic-sign-providers-20261014`.  
**Phạm vi:** chỉ nghiên cứu/lập kế hoạch D4 ở nhánh hiện tại; D3 được đội coding agent phát triển/thử nghiệm riêng. **Không tự merge D4 vào D3, không sửa firmware D3 hoặc flash thiết bị trong giai đoạn lập kế hoạch.**

## 1. Quyết định kiến trúc

**Mục tiêu sản phẩm:** C2M cảnh báo đúng biển báo/giới hạn tốc độ trên tuyến thực với GPS, dữ liệu đường/biển offline, và (nếu được chứng minh) kết quả TSR gốc; cảnh báo bằng màn M4 và/hoặc âm thanh tiếng Việt mà **không làm ảnh hưởng ghi hình/ADAS/app gốc**. Internet chỉ dùng để tải/cập nhật dữ liệu theo lô; hệ thống phải hoạt động được khi offline.

**Quyết định ưu tiên:** M4 là **Gate 0 / nút thắt tích hợp đầu ra hiển thị**, nhưng đừng biến nó thành blocker tuyệt đối cho toàn bộ D4. Có một plan B: trong trường hợp M4 chỉ hiểu các bản tin stock và không có widget biển tốc độ, ship giá trị offline GPS + cảnh báo tiếng Việt/web trên C2M, rồi tách firmware/protocol M4 riêng sau. Không giả định M4 là một màn hình có thể stream framebuffer; **ưu tiên tái sử dụng semantic messages đã xác minh**.

Nguyên tắc: `data` của OSM/Lily/Mapillary ≠ suy đoán luật giao thông chắc chắn; `GPSSpeed` không được thay bằng `speed_limit`; `ScreenModeSet` / `StorageStatus` không được lợi dụng để giấu dữ liệu biển/TPMS; không giả dạng FCW/PCW/LDW hoặc chỉnh sửa kết quả ADAS stock.

## 2. Bằng chứng hiện có / chưa có

| Thành phần | Đã có | Chưa có |
| --- | --- | --- |
| D3 | firmware pipeline D3 run 38550553664 PASS, cuối D3 source `8a8320d`, CI `main@4f601ab9` PASS; thẻ D3 đã được chuẩn bị/đọc lại 4/4 file | biên bản GitHub gần nhất ghi **manual flash + runtime C2M chưa PASS**; owner phải xác nhận boot/recording/ADAS/app |
| Giao diện D3 | `fw/d3/web.c` (AP port 8099), controller AP+STA, bundled WPA2 supplicant | STA thật/AP+STA chưa chứng minh; DHCP/IP/DNS/Internet chưa có |
| GPS | `fw/d3/gps_snapshot.c/.h`: đọc thụ động `/tmp/car_info` offset `0x330`, dài `0x1c0`, signed NMEA DDMM, RMC freshness gate | test giá trị thực của thiết bị, chưa có live GPS daemon |
| M4 ScreenService | ADAS `26012` + libflow WebSocket binary, outer + inner MessagePack; topic `vehicle/ped/lane` | M4 có thực sự nhận cổng này, đường truyền vật lý và UI biển tốc độ |
| cardv status | WebSocket `8080`, subprotocol `minieye-websocket`, JSON `GPSSpeed`, `GPSLevel`, `ScreenModeSet`, `StorageStatus` | M4 thực nhận bản tin nào; `GPSSpeed` là tốc độ xe, không phải giới hạn tốc độ |
| TSR | `TsrProcess`, `ReadTsr`, `SpeedLimitReporter`; D2 flags | capture `tsr_warning/tsr_trace_res_list` thật, enum/value/unit, on-screen proof |
| Âm | C/C2/D3 có WAV ADAS Việt, `cardv` có xử lý audio / FIFO | contract **phát một audio tùy chỉnh từ D4** không chen FCW |
| Offline | `fw/warner` HOST/REPLAY; OSM R-tree prototype `tools/road/osm_preprocess.py`; Lily-derived private `signs_vn.bin` 28.551 bản ghi | hướng của 15.343 P.127 trong DB hiện unknown; license tái phân phối; map matching đúng chiều |
| Online | OSM Overpass có `maxspeed`; VietMap SDK có Speed Alert enterprise | Internet C2M; VietMap consumer mặc định KHÔNG chứng minh API biển báo |

Nguồn chính: `docs/design/M4_ADAPTER_DESIGN.md`, `docs/hardware/C2M_M4_PASSIVE_CAPTURE_RUNBOOK.md`, `docs/reverse/M4_STATIC_PROTOCOL_V1.md`, `docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md`, `docs/firmware/CANDIDATE_D3_RELEASE_20261014.md`, `docs/research/D4_TRAFFIC_SIGN_DATA_SOURCE_DECISION_20261014.md`.

## 3. Kiến trúc mô-đun D4

```text
              C2M GPS /tmp/car_info (passive, validated)
                           |
                           v
   Stock TSR event -> [Road/heading match] <- Offline OSM roads/maxspeed
    (if proven)            ^                       ^
                           |                       |
                  Offline signed signs       Cache update source
                        (licensed)           (OSM/authorized API)
                           |
                    RoadIntelligence
                           |
  normalized AdvisoryEvent {sign_type, value?, source, road_id,
      direction, confidence, freshness, applicability, event_time}
                           |
                      OutputRouter
                      /        \
          M4Adapter (gated)   AudioAdapter (gated)
                 |                   |
           stock M4 screen      controlled Vietnamese WAV
                 \
                optional D3 local web status/debug (no fake result)
```

Keep provider-neutral business logic separate from M4 bytes, vendor packet enums, and cardv FIFO syntax. Favor small bounded C/C++ components, read-only SQLite/compact DB on SD, no Python runtime required on C2M. Host preprocessing may use Python. Prototype paths:
- `include/c2m/road/*` / `src/road/*`: track, road matching, sign source + fusion.
- `fw/d4/*`: limited on-device GPS/feed/cache/alert daemon after ABI evidence.
- `src/display/m4_adapter.cpp`, `src/audio/*`: output adapters only after explicit output gate.
- `tools/m4/*`: offline decoder, capture analysis, guarded replay.
- `tools/road/*`: host dataset build/coverage checks.
- `tests/d4/*` and `docs/evidence/d4/*`: reproducible tests and redacted proofs.
These are suggested paths, **not claims that D4 code already exists**.

## 4. Gates bắt buộc, theo thứ tự

### G0 — Reverse và chứng minh output M4 (ưu tiên số 1)

**G0A: Inventory & transport L0 — không gửi packet tùy chỉnh**

1. Confirm D3 (or current known-good firmware) actually boots, video recording, ADAS, AP/app and M4 working. Record firmware token and exact HEAD. If D3 not hardware validated, run passive tool only on a known-good baseline; do not assume D3 works.
2. Collect 2 comparable read-only captures `M4_OFF` / `M4_ON` with `tools/device/capture_c2m_m4_runtime.sh` or `tools/device/collect_baseline.sh`; use `tools/m4/discover_transport.py` to compare interface, USB VID/PID, ARP, TCP connection, owning process, `26012`/`8080`. Document possibility of M4 ↔ C2M through USB Ethernet, serial or another dedicated device. Neither `usb0` nor IP `192.168.32.123` is proven physical transport until device evidence.
3. If there is **no authorized shell**: host-side inspection of any externally accessible USB connection / network (no guessed UART), or prepare *a distinct owner-approved passive diagnostic-only capture path* during a later tested firmware build; mark L0 `BLOCKED_NO_DEVICE_ACCESS` meanwhile. Do not silently add a daemon or flash just to collect data.
4. Result file `docs/evidence/d4/M4_G0A_TRANSPORT.md`: `PROVEN` / `PARTIAL` / `BLOCKED`; interface + peer + socket owner or explicit alternatives; no screenshots/config secrets/serials in public repo.

**G0B: Actual payload L1 — stock only**

5. Use passive pcap on **verified** interface or read-only subscriber `tools/m4/libflow_subscriber.py` (`26012`), `tools/m4/cardv_status_client.py` (`8080`) when authorized and reachable. For libflow, subscription request is a protocol handshake, **not** an ADAS warning; don't mislabel it zero-transmit. Use finite capture windows; no payload injection. Decode with `tools/m4/decode_payload.py`, `tools/m4/libflow_protocol.py`.
6. Distinguish: (A) screen accepts semantic `speed-limit` message, (B) screen merely receives stock vehicle/lane/status, (C) screen fed framebuffer/YUV, (D) M4 runs an independent UI/firmware. For each, prove by runtime bytes/behavior; don't infer from a symbol string.
7. Reconstruct **who renders**, **who owns transmit endpoint**, key names + enum + units, display refresh requirements and whether an existing speed-sign widget exists. A real speed-limit M4 icon must not be inferred from `GPSSpeed`/turn `sign`.

**G0C: Harmless, stationary replay L2, then D4 sign proof L3**

8. Only if G0A+B proven, run a **single** controlled L2 replay matching a captured stock benign message via `tools/m4/replay_guard.py` and `tools/m4/m4_policy.json`, stationary bench, explicit owner permission and reversible exit. If transport does not accept replay, label `L2_BLOCKED` and stop sending.
9. Check the guard: allowed L2 candidates `DispBrightSet`, `StorageStatus`, `ScreenModeSet`, `ClientConn` *after actual schema/authority confirmation*. Existing guard DENIES `vehicleWarning`, `vehicleMeasure`, `pedestrians`, `laneWarningRes`, `AdasStatus` and all unknown semantics. **Do not bypass or weaken it to force a result.** Avoid even benign replay that would change brightness/mode unexpectedly; use captured value.
10. For **G0C sign icon**: unlock a **new, explicit L3 test lane** only after L2 success + proven M4 UI widget/protocol, domain-separation review and owner-approved isolated bench. One test sign `60` on stationary test screen (not on-road simulation), then automatically revert; verify video/photo evidence of icon and no corruption of stock display. **If no native speed-limit widget/protocol is found, verdict `M4_CUSTOM_SIGN_NOT_SUPPORTED_YET`, NOT PASS.** Do not send arbitrary `speed_limit` via `GPSSpeed`, fake safety warnings, or raw guessed JSON to production screen.

**G0 PASS full M4:** repeatable stock path, controlled L2, one actual M4 sign icon from D4 sender with captured proof, fallback restores stock view, no stock regression.
**G0 PARTIAL:** L0/L1 decoded, but custom sign render not established. Continue other D4 lanes; M4 integration remains blocked.
**G0 STOP:** intermittent M4 crash/flicker, ADAS warning misrouting, no proven receiver contract, payload changes affecting driving warnings.

**Fallback output decision:** If G0 PARTIAL/NO-GO after targeted efforts, publish a D4 basic track with GPS+offline engine, existing D3 web status or a separately validated audio adapter. Do not market M4 sign display or modify proprietary M4 firmware by default. Dedicated M4 firmware RE is an independent future workstream requiring M4 firmware image and hardware recovery.

### G1 — Live GPS and road-direction matching

1. Base on `fw/d3/gps_snapshot.c`: read **only** `/tmp/car_info` at `0x330` for `0x1c0` bytes (signed NMEA DDMM); use double-read + UTC freshness, non-blocking I/O; **never** open `/dev/ttyS1` or `/dev/ttyS2` when stock `cardv` owns GPS. If missing/invalid/stale, suppress directional speed advice.
2. Host fixtures: NMEA conversion, stale timestamp, jumps, heading at low speed, no fix, torn snapshot, power interruption. Field capture: 10–20 GPS fixes from owner-approved short drive/passive recording; redact precise personal GPS.
3. Offline OSM road graph preprocessing on PC (not PBF parse on C2M). Distinguish ways/sides/turn restrictions, `oneway`, `maxspeed`, `maxspeed:forward/backward`; treat `maxspeed:conditional` / lanes / ambiguous limits as UNKNOWN until parsed explicitly. For parallel roads/intersections consider multiple candidates; abstain when ambiguous.
4. Store compact region DB or read-only SQLite on SD, checksum, index and version. Always record data source, ODbL attribution and applicability; do not repackage privately extracted Lily sign DB without sufficient rights.

**G1 PASS:** continuous fresh GPS on device + at least one real, named test road matched with correct direction and evidence of wrong-side suppression. Host benchmarks and on-device latency/RSS/CPU observed; no extra UART consumption. Do not claim complete nationwide limit coverage.

### G2 — AdvisoryEvent fusion + real output

1. Define typed, provenance-preserving `RoadLimit` (effective on road) vs `PhysicalSign` (point) and `AdvisoryEvent` (display/sound), with `source`, `time`, `expiry`, `road_id`, `direction`, `value_kmh?`, `vehicle_profile`, `confidence`, `evidence_ref`.
2. Priority should be confidence- and freshness-aware; stock TSR is *not automatically always correct*, OSM and physical sign can conflict, and the vehicle's effective legal limit can depend on conditions. Disagreement → advisory unknown / no authoritative speed alert. Implement hysteresis, cooldown, event dedup and per-source TTL.
3. First test without M4: internal event log (bounded/redacted) and Web UI optional status; then connect to **M4 only if G0 full PASS** or **audio only after an independent audio-output contract confirmed**. Existing ADAS WAV Vietnamese success doesn't prove the ability to trigger arbitrary D4 WAV.
4. Audio research: stock `cardv` processes WAV/queue and has `play_wav_cmd`/FIFO strings. Find **real** command grammar and its arbitration/priority; bench-test a low-priority innocuous chime before a spoken `Giới hạn tốc độ 60`. Must not block or interrupt FCW/LDW/PCW; default silent if channel is ambiguous.

**G2 PASS:** controlled example 60 km/h on a correct road produces one human-visible or audible D4 advisory through a **validated** output path, and wrong-road/unknown test produces none; no starve of stock ADAS. Count any fallback as `D4_BASIC`, not `D4_M4`.

### G3 — Live TSR events and two-source fusion

1. Use `tools/m4/capture_tsr_readonly.py` + `tools/m4/tsr_event_lab.py` and static clues `tsr_warning`, `tsr_trace_res_list`; on-device capture only with validated runtime permission/transport.
2. Extract real event schema, enums, units, lifetime and observed class, correlate with known stationary test sign/benign logged event. No guessed speed-limit constants.
3. Merge with GPS road match only when available; TSR missing does **not** stop G1/G2. Never add a second vision model as a condition to ship D4 basic.

**G3 PASS:** at least one real TSR event mapped end-to-end, including source timestamp and unit, plus conflict/expiry tests; else `TSR_RUNTIME_UNVERIFIED`, no marketing claim.

### G4 — Network update / offline fallback (optional, after local value proven)

1. Only if D3 STA+AP **and** DHCP+DNS+HTTPS are actually proven, add a bounded, authenticated updater. D3 currently stops at `associated_no_ip`; capability-gated association is not Internet access. Alternative: update SD on PC or phone relay, with consent, if STA Internet is blocked.
2. OSM extracts/Overpass speed data normalized on a backend/PC, **never every GPS second**. Partition by area, validate geometry/schema/TTL/license, atomic DB swap; retry with backoff; stale/error preserves last licensed DB and marks source stale.
3. Mapillary optional after VN route coverage/token/license check. VietMap Consumer `default` is not a sign source; Driving Alert only with explicit entitlement and published contract. Lily private DB is research input, not redistributable.
4. Do not store service secrets in firmware/repo. Verify private cache and no unexpected GPS outbound transmission.

**G4 PASS:** one permitted update with matching hashes; disconnected replay identical on same DB; corrupt/timeout/429 never breaks recording or DB.

## 5. Delivery slices, dependencies and parallelism

| Slice | Must follow | Deliverable | Exit criteria |
| --- | --- | --- | --- |
| **D4-0 / M4 transport & UI feasibility** | D3-known-good baseline (or current known-good unit); owner-approved capture | M4 evidence L0/L1, protocol matrix, candidate for rendering | `PROVEN/PARTIAL/NO_GO`; never invent M4 path |
| **D4-0b / dataset host lane** | None (parallel to D4-0) | tiny OSM road/sign fixture, local map matcher tests, coverage report | forward/backward/parallel-road/unknown PASS |
| **D4-1 / live GPS + offline engine** | D3 verified boot, passive GPS contract; dataset tests | daemon + offline regional DB, perf log | on-device correct road/direction, no recording regression |
| **D4-2 / output** | G0 PASS for M4, or independent audio proof for fallback | one real icon / one voice warning | output observed, reversible, stock ADAS unaffected |
| **D4-3 / TSR fusion** | real TSR event schema captured | normalized TSR+GPS fusion | one true event + negative cases |
| **D4-4 / update** | validated Internet path or SD/phone update | regional cache updater | reconnect/offline/corrupt-data tests PASS |

**Do not make the entire D4 contingent on a speculative M4 full GUI rewrite.** Parallelize D4-0b with M4 L0/L1, then choose D4_BASIC or D4_M4 based on real evidence.

## 6. Gates CI / field test

**CI host:** all prior D3 tests still green; unit tests for M4 decoder/guard, GPS pure decoder/freshness, road matching (incl. opposite carriageway/conditional), fusion precedence, DB corruption, online 429/no Internet. ARM ELF/ABI + stock-rootfs QEMU self-test; no lib dependency outside pinned sysroot. Firmware rebuilding requires no-op/allowlist diff, 33-check deep validate and original assets exact SHA.

**Performance budget (targets, adjust after baseline):** lightweight daemon ≤5% average CPU and ≤16 MiB RSS during normal drive/recording if the device baseline allows, bounded logs/SD I/O, no process pile-up; explicit measurements required, not assumed. Backpressure/downsample GPS/display to avoid overload. Firmware addition must not interrupt 4K recording or degrade stock ADAS.

**Hardware acceptance:** 3 cold boots, ≥30 min recording with same card, clip decode + timestamp continuity, AP app, sensor/GPS status, no new freeze/reboot. Stage M4 display test stationary first; no trial of synthetic sign while driving. Capture one real example in a safe passenger-observed route later; audio must not mask stock emergency warnings. Flash is **manual owner action only** with exact 4-file prepared payload/version token and known-good recovery.

**Review:** one implementation PR/slice; Codex Combo Review-Normal via **9router** for routine code, Review-Hard via **9router** for IPC/firmware/audio/M4/network/security boundary. **Do not call AO native Review**. Evidence/review verdict bound to exact SHA; review after fixes again. Never merge code into `main` without gates for final SHA and explicit owner device-flash decision. Agent can autonomously work on isolated host code/probes.

## 7. Decision tree / stopping rules

```text
D3 boots & core stable?
  No -> D4 hardware path blocked, host research/fixtures proceed; leave D3 recovery to D3 lane.
  Yes
   |
   M4 transport L0/L1 proven?
     No -> do not inject, build GPS+offline engine and collect safe evidence.
     Yes
      |
      Harmless L2 replay + stock widget contract proven?
        No -> M4 extended UI = NO_GO now, use audio/web fallback.
        Yes
         |
         Stationary icon "60" rendered, reverted, no stock regression?
           Yes -> D4_M4 path GO; connect GPS events via M4Adapter.
           No  -> D4_BASIC path; do not invent graphics/framebuffer.
```

**Hard STOP:** key/config leakage; synthetic safety warning reaching live display; recorder/ADAS regression; camera crash; unknown/ambiguous GPS treated as legal speed limit; no recovery for modified output path. Rollback separate from config state: preserve calibration/license and owner-created files.

## 8. Evidence file contract / reporting

Within `docs/evidence/d4/` (only redacted markdown/json, **never pcap raw, device identifiers, GPS history, credentials, binaries or private sign DB**):
- `M4_G0A_TRANSPORT.md` — actual OFF/ON diffs, physical interface evidence and confidence.
- `M4_G0B_SCHEMA.md` — observed payload topic/field shapes, transport sender/receiver, unit mapping.
- `M4_G0C_DISPLAY.md` — L2/L3 scope, owner-approved bench test, screenshot/video reference privately held, icon result.
- `GPS_G1_DEVICE.md` — device sample count, freshness, field units, road match negative controls.
- `D4_GATES.md` — exact source SHA, fixture, CI/build run, hardware and no-regression verdict.
- `D4_DECISION.md` — whether `D4_M4`, `D4_BASIC`, `NO_GO`, and next action.

Every claim must be one of `STATIC`, `HOST_TESTED`, `QEMU_TESTED`, `DEVICE_OBSERVED`, `DEVICE_OUTPUT_PROVEN`; do not collapse these into a single PASS.

## 9. Manager agent execution prompt (copy/paste)

> C2M D4 manager: read `docs/plans/D4_IMPLEMENTATION_PLAN_20261014.md` plus `docs/hardware/C2M_M4_PASSIVE_CAPTURE_RUNBOOK.md` and `docs/research/D4_TRAFFIC_SIGN_DATA_SOURCE_DECISION_20261014.md`. D3 is separate and still has hardware gates; never modify D3 lane/main during D4 research. Prioritize **G0 M4** (OFF/ON passive capture → transport L0 → real schema L1 → gated harmless L2 → only if permitted/render contract proven, one stationary sign 60 L3). In parallel implement host-side GPS+offline OSM road-direction fixtures and tests. Reuse `tools/m4/*`, `fw/d3/gps_snapshot.*`, `fw/warner`; do not duplicate. Never fake FCW/LDW or overload `GPSSpeed` as speed_limit. If M4 sign output cannot be proved, choose D4_BASIC audio/web fallback; do not idle. VietMap Consumer API does not prove sign data; keep it optional. Agent autonomously decides safe host/research actions, records exact SHA/CI/evidence, and requests owner only for an actual device capture, privileged connection, manual flash or live output test. For reviews call **Codex Combo Review-Normal/Review-Hard through 9router**, not AO native Review. No merge into main without device and code gates.

## 10. References

- `docs/design/M4_ADAPTER_DESIGN.md`
- `docs/hardware/C2M_M4_PASSIVE_CAPTURE_RUNBOOK.md`
- `docs/reverse/M4_STATIC_PROTOCOL_V1.md`
- `docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md`
- `tools/m4/README.md` and `tools/m4/m4_policy.json`
- `tools/device/capture_c2m_m4_runtime.sh`
- `fw/d3/gps_snapshot.c`, `fw/d3/gps_snapshot.h`
- `fw/warner/README.md`
- `docs/design/ROAD_INTELLIGENCE_DESIGN.md`
- `docs/firmware/CANDIDATE_D3_RELEASE_20261014.md`
- `docs/research/D4_TRAFFIC_SIGN_DATA_SOURCE_DECISION_20261014.md`
