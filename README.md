# C2M Enhanced Firmware / Reverse Engineering

Reverse engineering and stock-compatible enhancement of the MINIEYE / UTOUR C2M platform.

## Strategy

**Keep stock + enhance.** Preserve the stock app, recorder, camera/ISP/media stack, useful stock ADAS and M4 display. Observe and reuse stock interfaces first; augment safely; replace only after evidence and benchmark.

```text
OBSERVE STOCK -> REUSE STOCK -> AUGMENT -> BENCHMARK -> REPLACE SELECTIVELY
```

## Firmware ground truth

```text
V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
  = GOLDEN / ADAS confirmed working on the user's physical C2M

V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
  = vendor Vietnam donor/regression build / ADAS did not work on same C2M
```

Original-image hashes and expected repository paths are documented in `firmware/original/README.md`.

## Start here

For coding agents / reviewers:

```text
docs/master/CURRENT_ARCHITECTURE.md
docs/master/AGENT_KICKOFF.md
```

Current owner delta review:

```text
docs/C2M_EN_VI_OWNER_DELTA_REVIEW.md
```

## Current major findings

- Rootfs EN/VI is extremely similar: only `cardv` and `sc7a20.ko` differ.
- ADAS symbol-name surface is unchanged between builds.
- The six embedded CNN/model blobs are **byte-identical EN vs VI**.
- `m0` is the AES-128-encrypted six-record model offset/size directory.
- VI updates `m0` consistently for moved model offsets.
- The complete `adas` size increase of **17,862 bytes** lies in seven non-model interstitial regions.
- `cardv` VI contains a real GPS/NMEA + M4/display refactor but its core resolved ADAS-forwarding call sequences are largely stable.
- ADAS `ScreenService` has static default port **26012**, with `libflow` WebSocket + MessagePack plumbing.
- `cardv` has a separate WebSocket candidate on **8080** using subprotocol `minieye-websocket`.
- Physical M4 transport is still runtime-unproven; do not assume `usb0` until off/on capture proves it.

## Reverse-engineering documentation

```text
docs/firmware_en_vi/          package/boot/kernel/rootfs/ADAS/config/audio reports
docs/reverse/                 ADAS package, cardv and M4 protocol reverse
docs/runtime/                 safe physical-device capture/classification workflow
```

Especially useful:

```text
docs/reverse/ADAS_PACKAGE_LOADER_V1.md
docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md
docs/reverse/CARDV_STATIC_DIFF_V1.md
docs/reverse/M4_STATIC_PROTOCOL_V1.md
docs/reverse/LIBFLOW_WIRE_PROTOCOL_V1.md
docs/runtime/DEVICE_BASELINE_CAPTURE.md
docs/runtime/ADAS_FAILURE_CLASSIFICATION.md
```

## Reproducible tooling

Firmware / ADAS:

```text
tools/fw/carve_upgrade.py
tools/fw/tree_hash_diff.py
tools/fw/elf_overlay_report.py
tools/fw/elf_dynsym_diff.py
tools/fw/elf_function_diff.py
tools/fw/thumb_callgraph_diff.py
tools/fw/adas_m0_directory.py
tools/fw/adas_gap_report.py
```

Read-only device evidence:

```text
tools/device/collect_baseline.sh
tools/device/compare_baselines.py
tools/device/classify_adas_state.py
tools/device/capture_interface_pcap.sh
```

M4:

```text
tools/m4/discover_transport.py
tools/m4/libflow_protocol.py
tools/m4/libflow_subscriber.py
tools/m4/decode_payload.py
tools/m4/cardv_status_client.py
```

## Next physical-device workflow

On known-good EN, capture M4 connected and disconnected:

```sh
sh tools/device/collect_baseline.sh en_good_m4_on
sh tools/device/collect_baseline.sh en_good_m4_off
```

On a workstation:

```sh
python3 tools/m4/discover_transport.py <m4_off_capture> <m4_on_capture>
python3 tools/device/classify_adas_state.py <en_good_capture>
```

Only after the M4 interface is proven:

```sh
sh tools/device/capture_interface_pcap.sh <verified-interface> m4_idle 60
```

With recovery proven, the highest-value ADAS regression experiment is a **temporary EN-base + VI-adas userspace test**, not a full NAND reflash.

## Evidence rules

Every reverse-engineering claim should be tagged:

```text
CONFIRMED
HIGH-CONFIDENCE
HYPOTHESIS
UNKNOWN
```

Do not invent protocol fields, ports, packet layouts, feature states, or safety claims without evidence.
