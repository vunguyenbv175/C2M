# C2M Enhanced Firmware / Reverse Engineering

This repository documents the reverse engineering and enhancement plan for the MINIEYE / UTOUR C2M platform.

## Current strategy

**Keep stock + enhance.** Preserve the stock app, recorder, camera/ISP stack, useful stock ADAS and M4 display. Observe and reuse stock interfaces first, then augment with RoadIntelligence, VietMap, TPMS, voice, web admin and selective custom AI.

Core rule:

```text
OBSERVE -> REUSE -> AUGMENT -> BENCHMARK -> REPLACE SELECTIVELY
```

## Firmware baselines

- `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar` — **GOLDEN / ADAS works on the physical device**.
- `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar` — **Vietnam/vendor donor + regression build; ADAS did not operate on the same device**.

Vendor firmware binaries are intentionally not committed here. Their hashes, partition maps and differential evidence are stored in the documentation.

## Documentation

- `docs/master/` — current enhancement architecture and coding-agent kickoff.
- `docs/firmware_en_vi/` — detailed EN-vs-VI firmware reverse engineering, evidence, M4 analysis and regression-bisect plan.

## High-value workstreams

1. EN/VI ADAS regression bisect.
2. M4 ScreenService / display protocol reverse engineering.
3. Stock ADAS IPC reuse: vehicle, lane, pedestrian, distance/TTC and TSR.
4. Stock app compatibility.
5. RoadIntelligence / VietMap / TPMS / local voice / web admin.

## Evidence rules

Every reverse-engineering claim should be labeled as one of:

```text
CONFIRMED
HIGH-CONFIDENCE
HYPOTHESIS
UNKNOWN
```

Do not invent protocol fields, ports, packet layouts or feature states without evidence.
