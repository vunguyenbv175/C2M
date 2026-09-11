# ADAS Runtime Failure Classification — A to F

## Goal

The VI firmware was observed to have non-working ADAS on the same physical C2M where the EN firmware works. Static reverse has narrowed the delta, but the next step is to classify **where runtime stops** before patching anything.

Use the read-only capture:

```sh
sh tools/device/collect_baseline.sh <label>
```

Then on a workstation:

```sh
python3 tools/device/classify_adas_state.py \
  c2m_capture_<...> \
  -o adas_state.json \
  --markdown adas_state.md
```

The classifier is intentionally conservative. It prefers `UNKNOWN` over claiming that a subsystem failed when the capture does not prove it.

## Classification

### A — ADAS process absent

Observed condition:

```text
no adas process in processes.tsv
no decisive crash evidence required
```

Next checks:

```text
run.sh / adas_service.sh / adas_guard.sh
adas.flag and calib.flag presence
startup exit paths
permissions / executable integrity
```

### B — crash or restart loop

Evidence can include:

```text
SIGSEGV / segmentation fault
abort/assert
killed process
core dump
ADAS present in snapshot but crash evidence in dmesg/logs
```

Next checks:

```text
exact failing stage
package validation / license
IPU init
ringbuffer mapping
shared-library compatibility
```

### C — process alive, input path suspect

Target evidence:

```text
adas process alive
raw_adas / ringbuf_vehicle absent, stale or failing
frame acquisition timeout/error
```

A static baseline alone cannot prove C merely because it does not contain the string `raw_adas`; actual producer/consumer state or frame counters are required.

Next checks:

```text
cardv frame producer
ringbuffer object
frame timestamps/counters
pixel format / dimensions / stride
```

### D — process alive, inference/IPU/model init suspect

Target evidence:

```text
frames arrive
but MI_IPU / CNN/model init fails
or inference never begins
```

Static reverse already proves EN and VI embed the **same six model blobs**, so if D is observed the focus should be:

```text
package/metadata validation
IPU runtime integration
memory layout
kernel/driver behavior
```

rather than different CNN weights.

### E — inference alive, warning/output suppressed

Target evidence:

```text
vehicle/lane/pedestrian results exist
but FCW/LDW/PCW/TSR warning state is suppressed
```

Next checks:

```text
runtime adas_de.flag
warning thresholds
vehicle speed / GPS / calibration gates
TSR enable gate
warning debounce/suppression state
```

### F — ADAS alive, display/audio path suspect

Target evidence:

```text
ADAS results/inference appear alive
but M4/audio shows no ADAS behavior
```

Strong supporting clues:

```text
missing ScreenService listener on 26012
M4 transport absent
cardv -> screen path failure
WebSocket / MessagePack delivery failure
```

Do not classify F from “screen looks dead” alone. Confirm inference/result generation first.

## Known static anchors

```text
ADAS ScreenService default port: 26012
cardv WebSocket candidate:      8080
ADAS camera input:              ringbuf_vehicle
ringbuffer name:                raw_adas
ADAS protocol:                  1.4.0
```

## Recommended evidence sequence

```text
1. EN working + M4 on baseline
2. EN working + M4 off baseline
3. discover_transport.py on M4 off/on
4. classify_adas_state.py on EN baseline
5. only with recovery proven: VI bad baseline
6. compare_baselines.py EN vs VI
7. classify_adas_state.py VI baseline
8. reversible EN-base + VI-adas executable test
```

## Decision tree

```text
ADAS process present?
├─ no
│  ├─ crash evidence -> B
│  └─ no crash evidence -> A
└─ yes
   ├─ crash/restart evidence -> B
   ├─ frame/ringbuffer failure proven -> C
   ├─ frames OK, IPU/model failure proven -> D
   ├─ inference results OK, warning suppressed -> E
   └─ inference results OK, screen/audio fails -> F
```

## Safety

This classification workflow does not require modifying NAND, bootloader, kernel, stock config, or M4 firmware. Keep the known-good EN image and persistent config backed up before any behavioral bisect.
