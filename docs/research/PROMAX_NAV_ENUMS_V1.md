# ProMax nav enums V1 (all value semantics UNKNOWN — absence proofs)

Analysis-only. No speculative rows filled.

## Turn (§9)

| Raw value | Meaning | Evidence | Confidence |
|---|---|---|---|
| — | left/right/slight/sharp/straight/uturn/roundabout/exit/arrive | zero `left/straight/roundabout/uturn/arrow/lane/camera` in classic; `right`×12 = rights/copyright-type noise; XL `left`×10 = AAC-audio noise, `arrow`×1 = LVGL calendar noise (proven non-nav contexts) | UNKNOWN (absence CONFIRMED) |

`trn` key slot HIGH (bare table), value domain NOT RECOVERED (string/int/bitfield/icon-ID all unproven).

## Lane (§10)

| Hypothesis | Evidence | Verdict |
|---|---|---|
| bitmask/array/string/mask+count/preferred/icon | no `lan` NUL slot; no mask/shift/loop/index neighbours; `lane` zero classic | UNKNOWN (NOT RECOVERED) |

`lan` exists in handshake `want` only (classic@0x1802EB, XL@0x68BBC); no parser slot in this build — handling UNKNOWN (different char / newer / display-only).

## Alerts (§11: alrs/avg/avgL)

| Raw | Meaning | Evidence | Confidence |
|---|---|---|---|
| — | speed/red-light/school/hazard/overspeed/police/avg-zone | `alrs/avg` slots HIGH, `avgL` want-only (no slot); zero camera/radar/school/hazard/police app strings; XL `buzzer_enabled/delay_warning/blink_screen/mute` are settings keys, not values | UNKNOWN |

Trace to display/buzzer/`beep_limit_change`: policy keys proven, value path NOT RECOVERED.

## Limit (§12)

Units/sentinel (0/255/-1)/temporary-limit/offset-application/overspeed-threshold: all UNKNOWN. `lim` slot HIGH; `speed_limit_offset/beep_limit_change` policy proven; stored→displayed→beep chain NOT RECOVERED.

## Rate/timeout (§13)

`rate:4` (Hz/seconds/version/batch): UNKNOWN. `timeout`×5 classic are exception/BLE-stack contexts (proven sample @0x257CA6 unwinding); `stale/heartbeat/keepalive` zero classic; XL `keepalive`×2 unexamined. Timestamps: `unix` key HIGH (bare table) = live clock/epoch candidate (LOW semantics). Loss-of-data (hide nav/clear limit/retain street): UNKNOWN.
