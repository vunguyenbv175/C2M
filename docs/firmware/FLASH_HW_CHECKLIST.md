# Hardware flash checklist — Candidate A then B (bench procedure)

Prerequisites: bench C2M unit (EN region), known-good SD card, serial log
capture if available, wall-clock + camera pointed at the road scene.
STOP at the first unexpected behaviour; capture logs/photos before retrying.

## One-command package build (on a Linux box with the original EN TAR)

```bash
# A only (works anywhere, no mtd-utils needed):
python3 tools/fw/build_candidates.py \
  --en-tar firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar \
  --workdir build/candidates
# A + B (needs work/customer_B.es from the firmware-candidateB workflow):
python3 tools/fw/build_candidates.py \
  --en-tar firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar \
  --workdir build/candidates --customer-b work/customer_B.es
```

Copy the resulting `EN_REPACK_GOLDEN.tar` / `EN_ENHANCE_IDLE.tar` to the SD
card following the stock upgrade layout (outer TAR members + SD structure
per the vendor upgrade path — do NOT rename inner members).

## Phase A — EN_REPACK_GOLDEN (stock-behaviour proof)

- [ ] A1. Flash Candidate A via the stock SD-card upgrade path.
- [ ] A2. Device boots to live view within the stock time budget (compare
      against a pre-flash baseline recording of the same unit).
- [ ] A3. Camera live view nominal (day scene, no artefacts/freezes 5 min).
- [ ] A4. Recording works (Normal + Event trigger, files appear on SD).
- [ ] A5. ADAS warnings nominal on the bench drive (FCW/LDW/PCW audio + OSD
      as in the pre-flash baseline).
- [ ] A6. M4/display path nominal (brightness/mode changes via stock UI).
- [ ] A7. Wi-Fi AP/STA + app connect nominal.
- [ ] A8. Cold reboot x3: all of the above still nominal (persistence).
- [ ] A9. Record `sysVer` shown on device + pack hashes used.

Phase A PASS = stock behaviour indistinguishable from pre-flash.
Only then proceed to Phase B. A failure here is a PACKAGING bug, not a
tuning issue — do not proceed.

## Phase B — EN_ENHANCE_IDLE (first enhanced boot)

- [ ] B1. Flash Candidate B the same way.
- [ ] B2. Repeat A2–A8 in full (ALL stock functions must remain nominal;
      any regression BLOCKS further B testing and reverts the unit to A).
- [ ] B3. `c2m-idle` process visible (`ps | grep c2m-idle`, exact one instance).
- [ ] B4. `/tmp/c2m_idle.marker` exists with the expected version string.
- [ ] B5. Cold reboot x5: B3+B4 hold every boot, stock functions unaffected.
- [ ] B6. `kill -9 <c2m-idle pid>`: no stock impact; (no respawn expected —
      idle has no watchdog by design); reboot restores B3+B4.
- [ ] B7. 24 h soak (powered, recording): no `minieye_daemon.sh` stall reboot
      attributable to the daemon (compare Logcat/minieye.log against A).

Phase B PASS = A-green + B3–B7 green. Only a Phase-B PASS may relabel the
build from `FLASH-READY` to `FLASH-PROVEN (idle)` for that exact image hash.

## Forbidden during bring-up

Flashing anything not listed here; touching calibration/license; enabling M4
transmit, camera hooks, or ADAS changes; calling any result proven from a
single boot.
