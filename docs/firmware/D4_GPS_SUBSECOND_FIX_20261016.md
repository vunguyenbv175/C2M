# D4 GPS subsecond fix — static proof, 2026-10-16 (local only)

Status: source fix and host regression tests only; not deployed. The flashed
D4-debug build observed on2026-10-16 still rejects live subseconds and reports
stale. Fix investigation/replay used only local captures and synthetic inputs;
no further camera access, deployment or key use was performed for this fix.

## Live blocker (summary only, no coordinates)

`C2M_HW_20261012/06_candidate_D4/live_20261016_070130/`:

- `gps_5x_readonly.command.sh`: five `dd skip=816 count=448` reads
  (`0x330`/`0x1c0`), one second apart.
- `gps_5x_summary.json`: five advancing UTC seconds, RMC mask present
  (`262159` includes `0x0008`), `signal 1`, `fix 3`, nonzero finite speed,
  subsecond raw `0, 100, 200, 200, 300`.
- Old decoder (`>99u` in `fw/d3/gps_snapshot.c`) returns `INVALID` for
  `100/200/300`, repeatedly resetting the freshness anchor. All five captured
  seconds were advancing, but most samples were invalid; live D4 reported
  `stale`. This does not claim it can never briefly acquire at other fractions.

## Static proof (EN stock cardv)

Binary identity from `docs/reverse/EVIDENCE_CARDV_CONTRACT.json`
(byte-exact search in cardv ELFs from original EN/VI rootfs images):

- EN cardv size `1225780`,
  SHA-256 `344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c`.
- Local disassembly snapshots: `build/d3-contract-review/cardv.thumb.txt`,
  `build/d3-contract-review/more-gps.txt` (generated from the same hash).

Functions (Thumb, from `SYMTAB`):

- `_nmea_parse_time 0xe0099 size 188`:
  length gate `cmp #6 / beq`, `blt fail`, `subs #8 / cmp #2 / bhi fail`,
  so accepted lengths are `6` or `8..10`.
  Length 6 uses rodata `0x11ee78` = `%2d%2d%2d` with 3 destinations
  `res+0x0c,0x10,0x14`.
  Length 8..10 uses rodata `0x11ee84` = `%2d%2d%2d.%d` with 4 destinations
  `res+0x0c,0x10,0x14,0x18` via `nmea_scanf 0xe46b0`.
  No `x100`/`x1000` scaling constant (only base-10 `#0xa` inside scanf);
  the fraction after `.` is stored verbatim via `%d`.
- Callers all use the same helper (`bl 0xe0098`):
  `nmea_parse_GPGGA 0xe052b`, `nmea_parse_GPRMC 0xe0969`,
  `nmea_parse_GNGGA`, `nmea_parse_GNRMC`.
- `nmea_GPRMC2info 0xe0f11 size 264`: `ldm r5!,{r0-r3} / stm r4!` followed by
  `ldm.w {r0-r2} / stm.w` copies 7 words `pack+0x00..0x18` to
  `nmeaINFO+0x04..0x1c` verbatim, including the subsecond word to `+0x1c`.
  No range clamp. `nmea_GPGGA2info 0xe0c19` follows the same pattern.
- `WriteGpsInfoForCardvUI 0x76235 size 112`:
  `mov.w r2,#0x1c0` + `add r3,#0x330` + `memcpy`, then
  `mov.w r2,#0x330` + `mov.w r1,#0x1c8` to `IPC_CarInfo_Write_PartInfo`.
  Proves GPS-record-relative `0x1c` = absolute file `0x34c` (`0x330+0x1c`),
  record `0x1c0`, file offset `0x330`.

Conclusion: `nmeaINFO+0x1c` holds the unscaled `.` fraction, 1–3 digits,
numeric range `0..999`. There is no vendor clamp to `99`.

## Unit caveat

Call the member `subsecond_raw`, not `millis` or `hundredths`:

- 3-digit fractions (live `100/200/300`) read as milliseconds.
- 1-digit `.1` stores `1` (not `100`); 2-digit `.12` stores `12` (not `120`).
- Range `0..999` accepts all three widths fail-closed; values `>=1000`
  (including negative `int32` bit patterns read as `u32`) remain `INVALID`.
- Classic `nmealib` docs saying `hsec 0..99` do not describe this vendor
  parser; the disassembly above governs.

## Guard / freshness invariants (unchanged)

- Decode still requires exactly `0x1c0` bytes, `RMC` mask value `8`,
  `signal>0`, `2<=fix<=INT32_MAX`, calendar `2000..2099`, finite signed
  DDMM coordinates, `speed [0,300]`, `course [0,360)`. All failures clear
  `*out`.
- Freshness still requires two strictly increasing UTC-second samples
  agreeing with monotonic time within `3000ms`; repeated seconds never
  refresh regardless of coordinates/subseconds; age `>=2500ms` is stale;
  gaps, regressions, jumps, and failed polls re-anchor and need two fresh
  samples. `decode_utc()` and `sample_in_range()` were both widened to
  `<=999u`; neither was relaxed to accept subsecond-only advance.
- Reader still uses `O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`, bounded
  regular file, two identical `pread()`s at `0x330`, no `mtime` freshness,
  no writes/UART/IPC, no location logging.

## Source patch (not deployed)

- `fw/d3/gps_snapshot.h`: `hundredths` → `subsecond_raw 0..999`;
  `file-relative 0x1c` corrected to `GPS-record-relative 0x1c`
  (`nmeaINFO+0x1c`; absolute `0x34c`).
- `fw/d3/gps_snapshot.c`: `decode_utc >99u` → `>999u`,
  `sample_in_range <=99u` → `<=999u`, with vendor-format comments.
- `tests/test_d3_gps.py`: helper/ctypes renamed; `1000/-1/0xFFFFFFFF`
  invalid; `0/99/100/200/300/999` valid; new fail-closed reset test
  (`1000` resets even with advancing second, then two valid advances
  reacquire), per-raw confirmation test, and synthetic five-sample
  live-shape test (`0,100,200,200,300` → freshness `[0,1,1,1,1]`,
  subsecond-only churn stays `0`). Synthetic coordinates only; no live
  lat/lon copied.
- `tests/test_d4_advisory.py`: frozen driver uses `(now/5)%1000` so frozen
  seconds genuinely exercise `100..900` plus explicit `999`, with
  `REQUIRE(max_seen>=900)` coverage asserts; subsecond churn still stale.

## Host verification

- Windows GCC portable GPS suite:20 tests,16 passed/4 Linux-only skipped.
- Windows advisory suite:10 tests,4 passed/6 Linux-only skipped.
- Actual private five-record capture replayed through the patched host DLL:
  all five decode OK; freshness `[0,1,1,1,1]` using synthetic monotonic
  `0,1000,2000,3000,4000ms`. This is a captured-decode/algorithm replay, not a
  live timing or live D4 producer acceptance. Private report:
  `build/gps-replay-20261016/replay_report.json`; no coordinates, speed,
  heading or raw bytes are included in that report.
- General Linux CI `38829034134` on source `aa3f7b9` passed: full Python
  reader/producer regressions, real Chrome D3/D4/end-to-end suites and existing
  generic ARM idle build/ELF gates. This does not cross-build the updated D4
  producer or prove its exact stock-userspace runtime; those target-specific
  gates remain before RAM evaluation. No updated native ARM binary has been
  uploaded or run on the camera.

The already-flashed build still has the defect; this source fix does not
change it. A later reviewed RAM-only evaluation must be bounded and performed
with stationary hardware. This document and patch do not claim actual
advisories/beep, AP+STA, Bluetooth RF or M4 rendering work.
