# ProMax nav-state model V1 (vocabulary → handshake → display-policy)

Research-only. No struct offsets invented. Fields without firmware proof are marked UNKNOWN.

## 1. Proven vocabulary (byte-exact)

Handshake block `firmware.bin@0x180200-0x180500` (also XL `guition_ota@0x68AE0-0x68C00`):

```text
{"v":1,"t":"pong"}\n
{"v":1,"t":"dev","name":"Promax","fw":"1.0.0","proto":[1],"want":{"rate":4,"fields":["nav","spd","lim","trn","dst","exit","st","eta","rmin","rkm","avg","avgL","alrs", "lan"]},"can":["speed","limit","turn","street","eta","avgzone","alerts"],"transport":"ble"}\n
"t":"ping"
```

- `t ∈ {ping,pong,dev}` only — CONFIRMED (no `nav/spd` value packet in any image).
- `want.fields` = subscription request (rate 4 — unit unproven, likely Hz) — HIGH.
- `can[]` = renderable subset — HIGH.
- Short keys (`nav/spd/lim/trn/dst/exit/st/eta/rmin/rkm/avg/avgL/alrs/lan`) imply pre-normalized sender — MEDIUM.
- `FFF0/FFF1/FFF2/FFF3/180A/2A26/8a7e0001/2/3/VIETMAP_HUD` contiguous in same block — CONFIRMED.
- Hex `pong`: `7B 22 76 22 3A 31 2C 22 74 22 3A 22 70 6F 6E 67 22 7D 0A` — CONFIRMED.

Absent (CONFIRMED absence in ProMax classic): `lane/left/right/straight/uturn/roundabout/camera/radar/traffic/school/hazard/heading/compass/reroute/overspeed/tunnel/junction/navigation` (beyond handshake keys), all Vietnamese NFC strings.

XL settings-only Vietnamese cluster `@0x7Cxxx` (`Âm lượng/Còi cảnh báo/Nháy khi quá tốc độ/Độ sáng/Hướng…`, `120m/00:00/109°/Lê Văn Thiêm` near `brightness/orientation/volume/delay_warning/blink_screen/buzzer_enabled`) — CONFIRMED, not nav values.

## 2. Normalized internal state — NOT RECOVERED

No ELF/symbols; merged flash; no struct layout proven. Per-field table is therefore:

| Field | Offset | Size | Type | Writer | Reader | Screen consumer | Protocol source | Confidence |
|---|---|---|---|---|---|---|---|---|
| speed | — | — | — | — | — | — | `want:spd/can:speed` intent only | UNKNOWN |
| speed_limit | — | — | — | — | — | — | `want:lim/can:limit` intent only | UNKNOWN |
| turn_type | — | — | — | — | — | — | `want:trn/can:turn` intent only | UNKNOWN |
| turn_distance | — | — | — | — | — | — | `want:dst` intent only | UNKNOWN |
| road_name | — | — | — | — | — | — | `want:exit/st/can:street` intent only | UNKNOWN |
| lane | — | — | — | — | — | — | `want:lan` intent only | UNKNOWN |
| warnings | — | — | — | — | — | — | `want:alrs/can:alerts` intent only | UNKNOWN |
| eta/rmin/rkm/avg | — | — | — | — | — | — | `want` intent only | UNKNOWN |

Do NOT implement from this table. Use neutral C2M proposal instead (main report §21).

## 3. Display rendering state machine (proven policy keys only)

`DTBK@firmware.bin:0x3E0304` defaults: `display_rotation=1, show_clock=1, led_color=0xff0000, led_brightness=9, logo_text=WAZE, speed_limit_offset=0, night_brightness=5, welcome_text=, show_text_kmh=1, show_speed=1, obd_scan_duration=0, show_number_marker=1, beep_limit_change=0, screen=0, sleep_screen_mode=1, keep_awake_on_obd=1, show_weather=1, boot_screen_duration=1` (+ `screen 0=full/1=limit-only`, rotation 0–7, duration 0–255s, JPEG 240×240 <100KiB via FFF3/128B+DTBK; XL 360×360 <512KiB via IMG_START/END/256B).

| State/Event | Display | Priority | Timeout | Audio | Next |
|---|---|---|---|---|---|
| boot | logo/JPEG + welcome_text | low | `boot_screen_duration` 0–255s | — | config screen |
| no connection | `sleep_screen_mode` 0=off/1=mochi/2=image | low | latched | — | reconnect |
| limit change | limit numeral + marker 0–130 | med | latched while valid | `beep_limit_change` optional | same |
| OBD scan | scan UI 5/10s | med | `obd_scan_duration` | — | live/keep-awake |
| night | dim to `night_brightness` | low | ambient (sensor unproven) | — | day |
| nav guidance | UNKNOWN (no arrow/lane/font/icon handler proven) | — | stale>~3s→hide (proposal) | local beep/voice (proposal) | same/hide |

Priority/override/timeout/blink for nav: UNKNOWN. `arrow/lane/font/icon/blink` zero app hits — CONFIRMED absence.
