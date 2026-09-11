# 10 — Coding Agent Workplan

## Mission

Use the two vendor images as a **good/bad differential oracle**.

Do not rewrite the system yet.

## Priority 0 — preserve evidence

Commit only reports/scripts/hashes that are safe to publish.

Do not commit:
- user license,
- serial numbers,
- private calibration if sensitive,
- vendor binaries if redistribution is uncertain.

## Priority 1 — reproduce this static analysis

Create scripts:

```text
tools/fw/carve_upgrade.py
tools/fw/tree_hash_diff.py
tools/fw/elf_overlay_report.py
tools/fw/string_symbol_diff.py
```

All reports should be reproducible from the two input TARs.

## Priority 2 — Ghidra project for `adas`

Import both:

```text
EN adas V23.07.29.1
VI adas V23.08.04.1
```

Use function matching.

Focus first on:
- startup/init,
- config parsing,
- license/check-SN,
- ringbuf input,
- IPU init,
- camera fault path,
- ScreenService init,
- TSR init,
- error returns.

Produce:

```text
docs/reverse/ADAS_FUNCTION_DIFF.md
```

with exact addresses and pseudocode snippets only where needed.

## Priority 3 — understand ADAS appended payload

The `adas` executable has ~10 MB beyond normal ELF sections.

Required questions:
- what format/container is it?
- does code read its own executable?
- is the overlay encrypted/compressed?
- what does `--fs=3602` mean?
- what is `--m0`?
- why does `m0` differ?
- does overlay include model/license/config data?

Do not call it “model data” until proven.

## Priority 4 — `cardv` diff

Function-match both cardv builds.

Start at:

```text
SendADASInfoToScreen
SendGPSInfoToScreen
SendGPSSpeedToScreen  [VI-only]
DeviceSendMsgToScreenTask
DisplayVideoYuv422
GPS parsing
raw_adas producer
G-sensor config handling
poweroff changes
```

Deliver:

```text
docs/reverse/CARDV_FUNCTION_DIFF.md
```

## Priority 5 — M4 protocol

Static anchors:

```text
screen_service.cpp
screen_export_port = 26012
sdk_use_msgpack = true
libflow WebSocket support
cardv Send*ToScreen functions
```

Then validate on hardware.

Deliver:
- passive decoder,
- pcap scenarios,
- MessagePack schema,
- ownership/proxy diagram.

## Priority 6 — TSR

Trace:

```text
TsrProcess
ReadTsr
SetTsrResult
SpeedLimitReporter
TsrWarning
```

Determine:
- detector/model used,
- exact supported sign classes,
- runtime enable gate,
- where speed limit is sent,
- whether M4 receives it,
- whether Vietnam factory profile sets `enable_tsr=true`.

## Priority 7 — regression bisect

Follow `09_REGRESSION_BISECT_PLAN.md`.

The first high-value runtime test is VI `adas` on an otherwise-working EN base, using a reversible temporary path.

## Priority 8 — build C2M Enhanced only after interfaces are known

Target architecture:

```text
stock recorder/media
stock app
stock M4
stock ADAS provider
        +
RoadIntelligence
VietMap
TPMS
Voice
Web Admin
selective custom AI
```

## Mandatory reviewer rules

Reviewer rejects:
- invented ports,
- invented packet fields,
- claims that VI is “better because newer”,
- claims that TSR is enabled merely because code exists,
- claims that M4 is RNDIS merely because usbnet modules exist,
- full-flash testing before reversible userspace tests are exhausted.

## First owner report

Create:

```text
docs/C2M_EN_VI_OWNER_DELTA_REVIEW.md
```

It must answer:

1. What is definitely different?
2. Which differences can plausibly kill ADAS?
3. What is the minimal safe experiment to separate ADAS-binary vs cardv/kernel causes?
4. What exact stock interfaces are worth reusing?
5. What M4 protocol facts are static-confirmed vs runtime-unverified?
