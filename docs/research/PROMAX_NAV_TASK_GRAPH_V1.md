# ProMax nav task graph V1 (edges unproven)

Analysis-only, string-level. No control-flow claimed.

## Tasks observed

- Classic: `xTaskCreate`×1@0x25D122, `xQueueReceive`×2@0x25C9F0, `vTaskDelay`×1@0x25D0F1; `xQueueSend/xTimerCreate/xTaskCreatePinnedToCore` zero; task names stripped (no `ObdBleTask`/`SupervisorTask` in classic) — CONFIRMED counts.
- C3/S3: `ObdBleTask`×1 (C3@0x159460, S3@0x158FE4) amid OBD AT strings — CONFIRMED OBD task.
- Adapter: `SupervisorTask`×1@0x108B4 + `/littlefs` — CONFIRMED.
- XL: `xTaskCreate`×2 + `xTaskCreatePinnedToCore`×1 + `xTimerCreate`×1 + NimBLE `ble_gap/ble_gattc/ble_hs` + `Audio.h` — CONFIRMED richer task set.

## Chain (§17)

```text
BLE write event → characteristic callback → packet parser → nav state → display/render
        UNKNOWN          NOT RECOVERED        bare-table only   UNKNOWN      policy keys only
```

No queue/semaphore/event-group edge ties BLE to parser to display (names stripped; `xQueueReceive` contexts are IDF-internal). Task graph: **NOT RECOVERED**.

## OBD vs nav separation — HIGH

OBD central block (classic@0x18054F–0x1805EE: `AT D/Z/E0/S0/AL/ST/SP/TP/RV/UNABLETOCONNECT/NODATA/ATRV/IOS-Vlink/Viecar/OBD BLE/FAKE_OBD/18F0/2AF0/2AF1`) is contiguous and disjoint from 8a7e/nav block (@0x180200–0x1804E4) and bare table (@0x182800) — CONFIRMED layout. `ObdBleTask` (C3/S3) never neighbours nav keys — CONFIRMED. Buzzer/audio/display-policy keys are settings, not OBD.

## Display-update consumers (§8, reverse direction)

Render-side keys proven (`/config.txt` list, DTBK defaults, `beep.txt`, `MAPVIET`, `km/h`-adjacent `%i`), but the functions reading live `spd/lim/trn` state: NOT RECOVERED (no second key occurrence, no symbols). Reverse trace stops at key vocabulary.
