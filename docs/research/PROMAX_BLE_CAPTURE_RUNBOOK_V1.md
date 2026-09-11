# ProMax BLE capture runbook V1 — one controlled live-nav session

PREPARATION ONLY. No hardware required now. No BLE transmission/replay/emulation.
Ground truth: STATIC_ANALYSIS_EXHAUSTED=YES, LEVEL 2 PARTIAL, emulator HOLD,
sniff gate NOW_HIGHEST_VALUE. Target: 8a7e0001/0002/0003 roles, RX/TX, framing,
live fields, cadence, stale behavior.

## 1. Methods (priority order)

A. **Android Bluetooth HCI snoop log** (primary; free, no root normally).
B. **nRF Connect / LightBlue characteristic inspection** (read-only discovery).
C. Rooted-Android bt snoop (only if A export fails).
D. External BLE sniffer (only if A/B insufficient; no purchase by default).

## 2. Android HCI workflow (exact procedure)

1. Phone fully charged; note model + Android version in `01_phone/PHONE_INFO.txt`.
2. Settings → About phone → tap Build number 7× → Developer Options on.
3. Developer Options → **Enable Bluetooth HCI snoop log** → ON.
4. Toggle Bluetooth OFF → ON (restart stack; required on most OEMs).
5. (Optional, improves decode) Settings → forget old ProMax bonds.
6. Start session per `PROMAX_BLE_CAPTURE_EVENT_SCRIPT_V1.md`; log every event
   with wall-clock time (phone clock; photo the phone clock at T0 for sync).
7. Developer Options → HCI snoop OFF after T10.
8. Export `btsnoop_hci.log`:
   - Stock/Pixel path: `adb bugreport` → unzip → `FS/data/misc/bluetooth/logs/btsnoop_hci.log`
     (exact inner path varies by version — UNKNOWN per device, inspect the zip).
   - Some OEMs expose a shareable snoop file via Developer Options or
     `/sdcard/Android/data/` — UNKNOWN per device; if absent use bugreport.
   - File size sanity: a 10-min session is typically 0.5–20 MB; 0-byte or
     124-byte files mean logging never started → redo from step 3.
9. Copy to `02_hci/btsnoop_hci.log`; record source path + method in `02_hci/SOURCE.txt`.
10. No root required unless both export routes fail → escalate to method C.

## 3. GATT discovery workflow (read-only)

1. nRF Connect (free) → SCAN → connect ProMax (do NOT bond unless the real app does).
2. Service discovery (automatic; ATT reads — normal traffic, allowed).
3. For EVERY service/characteristic/descriptor record in `03_gatt/DISCOVERY.txt`:
   service UUID, characteristic UUID, properties (READ/WRITE/WRITE_NR/NOTIFY/
   INDICATE), descriptors incl. CCCD `0x2902`, current CCCD value (read only).
4. Specifically flag 8a7e0001/0002/0003 with handles; build `03_gatt/handles.csv`
   (`handle,uuid,name`) for the parser `--gatt` map.
5. Read static readable values (e.g. Device Name, Appearance) — fine.
6. PROHIBITED: writing any characteristic/CCCD manually, MTU requests by hand,
   pairing-code games, or any injection. Notify traffic comes from the genuine
   app session (method A), never from manual writes.

## 4. Capture-day checklist

- [ ] HCI snoop ON verified (log file grows during a 30-s test toggle)
- [ ] nRF discovery saved + handles.csv built
- [ ] Event script printed; clock photo taken
- [ ] Session executed T0–T10 with all timestamps logged
- [ ] `btsnoop_hci.log` exported, non-trivial size, copied to `02_hci/`
- [ ] Evidence dir created via `init_ble_capture_dir.sh`, manifest filled
- [ ] Parser run → packet counts sane (writes + notifies present)
- [ ] NOTHING transmitted except the genuine app session

## 5. Analysis entry

`python tools/reverse/promax/parse_promax_ble_capture.py 02_hci/btsnoop_hci.log
--gatt 03_gatt/handles.csv --out 05_packets/table.json`
then the ANALYSIS_PLAN doc. Replay/emulator stay blocked (§14 of task order).
