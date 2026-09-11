# ProMax version-diff matrix V1 (static, offline)

Method: `git --git-dir` log on bare mirrors + `diff_esp_firmware.py` string-set + header/entry compare via `parse_esp_image.py`. No flash/run.

## ProMax classic (promax.git, 119 commits, HEAD fd58197)

| Version/marker | Evidence | Delta vs previous | Protocol relevance |
|---|---|---|---|
| `firmware 7.13→7.18` dailies | commit titles `add 7.15/7.16/7.17/7.18` | opaque binaries, sizes ~4MiB stable | LOW (no literal handler proof) |
| `653afff` LOAD config | title `current-configuration loading` + `index_raw.html:338-341 LOAD` | adds FFF2 `LOAD` query path | CONFIRMED mgmt addition |
| `60c638b` DTBK raw + Dasai Mochi | title + `DTBK` keys + `sleep_screen_mode=1 (mochi)` | adds raw config + sleep mode 1 | CONFIRMED display-policy addition |
| `172705a` adapter | `adapter.json v7.15` + `firmware_adapter.bin` entry `0x40082B24/5segs` vs main `0x40083764/6segs` | new distinct ESP32 binary, BLE-central strings, no nav vocab | CONFIRMED support-HW addition, NOT nav-plane |
| `73b430e` beta channel | `manifestbeta.json` + beta app entry `0x40083644` vs stable `0x40083764`, boot hash `2165b846..` vs stable `5bb2ac0d..` | beta **strips** `pong/dev/8a7e/proto/want` (0 hits) while keeping `FFF0/180A/VIETMAP` | HIGH: nav presence is version-dependent, not monotonic |
| `ccbb393` fix lane image | message only, C-binary tweak | no `lane` literal beyond `want.fields:"lan"` | LOW (lane rendering still unproven) |
| `firmware_no_bl.bin` v7.17 | `E9@0x1000` still present, NVS=`FC`, truncated | packaging variant, not protocol change | CONFIRMED non-change |
| C3/S3 variants | chip5/9, `riscv` vs `xtensa`, `Bluedroid` vs IDF-only | same `VIETMAP_HUD/FFF0/DTBK` keys; C/S lack `8a7e/want/proto` in scanned build (only classic ESP32 + XL have full block) | HIGH: nav-intent block is build-variant-dependent |

## ProMax XL (promax_xl.git, 53 commits, HEAD f678b2c)

| Version/marker | Evidence | Delta | Relevance |
|---|---|---|---|
| `2.17→2.24` | OTA `5916912→5920208` (+~3KiB), full `16711680` stable | incremental; `DTBK@` shift `0x8F36C→0x90C74`, `want` count 1→2 (waveshare v2) | LOW-MEDIUM |
| `d4a7539 scan service uuid` | title + `xl/index.html:268 services:[FFF0]` service-filter connect | discovery change (name→service filter) | CONFIRMED |
| guition vs waveshare | app entry `0x4037E630` vs `0x4037E648`, `DTBK@0x8F36C` vs `0x90A0C` | display-driver variant only | CONFIRMED non-protocol |
| v1 vs v2 | same entries, `Promax XL@0x78B2B→0x78B9F` shift, `8a7e` block shift | rebuild, same handshake | CONFIRMED non-change |
| full vs OTA | OTA `E9@0x0` = app, `AA50 valid=0`, offsets −0x10000 | packaging only | CONFIRMED |

## Cross-family

- Handshake JSON identical modulo `name` (`Promax` vs `Promax XL`) — CONFIRMED (`firmware.bin@0x18025D` vs `guition_ota@0x68B2B`).
- Mgmt split: ProMax FFF1=notify+FFF2=write+FFF3=file(128B) vs XL FFF1=write(256B)+IMG_START/END — CONFIRMED.
- `lane/road-name/roundabout/camera/VIETMAP LIVE` never as literals in any version — CONFIRMED absence.
- SDK: classic `v4.4.4/v4.4.7`, XL `v5.3.2-282-gcfea4f7c98-dirty` + Arduino/NimBLE — CONFIRMED (chip-proof is header, SDK is corroboration).

## How to isolate future handler additions

`python tools/reverse/promax/diff_esp_firmware.py <old.bin> <new.bin> --json` → `strings_added/removed` filtered to protocol vocab. Use on any new backup commit before Ghidra.
