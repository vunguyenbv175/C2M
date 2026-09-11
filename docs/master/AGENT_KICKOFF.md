# C2M Coding-Agent Kickoff

You are working directly on `vunguyenbv175/C2M`.

Read first:

```text
docs/master/CURRENT_ARCHITECTURE.md
docs/C2M_EN_VI_OWNER_DELTA_REVIEW.md
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md
docs/reverse/CARDV_STATIC_DIFF_V1.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/runtime/DEVICE_BASELINE_CAPTURE.md
docs/runtime/ADAS_FAILURE_CLASSIFICATION.md
```

## Ground truth

```text
EN 2023-08-03 = GOLDEN; ADAS works on user's physical C2M.
VI 2023-09-20 = vendor Vietnam donor/regression; ADAS did not work on same C2M.
```

Do not infer that VI is preferable because it is newer.

## Current strongest findings

```text
six embedded ADAS model blobs are byte-identical EN/VI
m0 is the encrypted six-record model offset/size directory
VI model offsets are internally consistent
all +17,862 bytes of VI adas growth are in seven interstitial non-model regions
cardv core ADAS forwarding call sequences are largely stable
VI has a real GPS/NMEA/M4 refactor
M4 ScreenService static default is port 26012
ScreenService/libflow uses WebSocket + MessagePack
```

## Immediate work order

### 1. Runtime evidence

Use the read-only collector; do not change stock state:

```text
tools/device/collect_baseline.sh
tools/device/classify_adas_state.py
tools/device/compare_baselines.py
```

Classify ADAS A–F before proposing a fix.

### 2. M4 transport

Compare M4 OFF vs ON with:

```text
tools/m4/discover_transport.py
```

Only capture an interface once runtime evidence identifies it:

```text
tools/device/capture_interface_pcap.sh
```

No warning injection during discovery.

### 3. ADAS package validation

Trace readers/validators of:

```text
/proc/self/exe
FLAGS_m0
BitAnswer
license/check-SN
AES/decrypt functions
seven interstitial package regions
```

Do not call those regions license/protection data until code references prove it.

### 4. Good/bad userspace bisect

Highest-value reversible test:

```text
EN known-good base + VI adas executable launched temporarily
```

Never overwrite the golden executable for the first test.

Interpretation:

```text
VI adas fails on EN base
  -> stay inside VI adas package / config-validation investigation

VI adas works on EN base
  -> move to cardv/raw_adas/kernel/driver boundary
```

## Hard rules

```text
READ-ONLY-FIRST
EVIDENCE-FIRST
NO FULL NAND FLASH FOR BISECT
NO BOOTLOADER/KERNEL MODIFICATION DURING DISCOVERY
NO INVENTED M4 FIELDS OR PORTS
NO MODEL REPLACEMENT YET
NO STOCK APP BREAKAGE
NO CLAIM THAT TSR IS ENABLED UNTIL RUNTIME CONFIG PROVES IT
```

Every reverse-engineering claim must be labeled:

```text
CONFIRMED
HIGH-CONFIDENCE
HYPOTHESIS
UNKNOWN
```

## Commit discipline

Prefer small commits grouped by evidence/tool/report.

For every new reverse tool:

```text
1. deterministic/read-only where possible
2. machine-readable JSON output
3. concise Markdown interpretation
4. synthetic smoke test if the input format can be mocked
```

Do not commit user serial numbers, private license material, calibration secrets, credentials, API keys, or proprietary provider dumps.
