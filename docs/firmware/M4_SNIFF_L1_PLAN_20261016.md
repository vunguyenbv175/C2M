# M4 RNDIS usb0 passive sniffer — L1 plan (offline, no camera contact) — 2026-10-16

## Goal

Decode what the two proven native M4 legs already carry, without sending
anything and without opening a second `:8080` client:

- `adas:26012` libflow/MessagePack candidate (`vehicle`, `ped`, `lane` topics).
- `cardv:8080` minieye-websocket JSON candidate (`GPSSpeed`, `StorageStatus`, …).

L0 is proven (RNDIS `usb0`, camera `.123` ↔ M4 `.129`, both ESTABLISHED).
L1 (schema/receiver) is NOT proven. No replay is proposed until L1 decodes
prove schema and harmlessness.

## Observer design (new, offline-first)

New RAM-only source `fw/m4_sniff/m4_usb_observe.c`:

- Fixed interface `usb0`, no CLI override (filter-bypass denial).
- CLI only `--observe | --self-test | --help`, stdout summary only.
- Receive-only `AF_PACKET/SOCK_RAW` attach via `bind()`; NO transmit:
  no `send/sendto/sendmsg/connect`, no `ioctl/setsockopt` state change,
  no promiscuous toggle, no file writes, no status-file touch.
- Finite: 20 received packets max, 512B snaplen, 96B payload prefix per
  record; 15 poll calls (each waits AT MOST 1s), 30s monotonic bound,
  signal-stop, external timeout still required. This is **NOT a guaranteed
  15-second capture**: traffic-ready polls consume the budget immediately.
- Schema `m4_sniff=observer_v3`: shared tested formatter emits L7 bytes only,
  IP/UDP lengths exclude Ethernet padding, invalid/fragment/ARP frames emit
  empty `payload_hex`. `payload_len` is advertised transport payload size;
  `captured` is actual retained bytes; `truncated` explicitly marks omission.
  IHL/TCP offset and one VLAN tag are supported; no IPv6/QinQ or reassembly.
- IPv4 source/destination, ports, TCP sequence/ack and flags are metadata.
  These help identify directions and gaps; they do NOT reconstruct missing
  bytes. Each record is a partial prefix, not necessarily one complete WS
  frame/MessagePack object. ACK-only traffic consumes packet/poll budget too.
- A 6144-byte record budget plus bounded preamble/summary keeps stdout below
  8192 bytes (hardware wrapper lifecycle tokens also bounded). Stop reason
  `output_budget_partial` is normal bounded sampling, not complete capture.
- Protocol-zero nonblocking AF_PACKET socket queues no traffic before binding
  `usb0`; each receive also checks its returned ifindex. No promiscuous mode,
  BPF bypass or new application connection is introduced.

V1 frame-start dumping and V2 are superseded, NOT hardware-approved. Static
preflight review found V2 dumped frame headers at offset zero for invalid/ARP
frames and counted Ethernet padding as payload. Previous V2 claims of safe
payload-only output and complete 15s duration are withdrawn; no V1/V2 native
sniffer was uploaded/executed on camera. QEMU's absent-interface test alone
cannot validate the successful capture/parser path.
- Graceful when `usb0`/raw socket is absent (CI/QEMU path):
  `completion=iface_unavailable|capture_unavailable`, exit 0, still finite.
- `--self-test` is pure synthetic Ethernet/IP/TCP/UDP/ARP parsing with
  options/frag/truncation cases, no network.
- Every run labels
  `delivery_sim=observer_simulation_not_production_delivery`,
  `status_writes=0`, `transmit_bytes=0`.

Build `fw/m4_sniff/build_arm.sh` reuses the exact stock-ABI pattern
(ARMv7-A hard-float VFPv3-D16, time32/off32, old startup,
`/lib/ld-linux-armhf.so.3`, `glibc<=2.30`, `check_elf.py`, QEMU pure tests).
Target build defines no TEST macros.

Host gate `tests/test_m4_sniff.py` (portable CLI + Linux runtime),
QEMU gate `tools/fw/test_ram_m4_sniff_stock_qemu.py`
(missing-`usb0` finite path, sentinel status file unchanged),
hardware runner `build/run_m4_sniff_v3_reviewed.py`
(exact pinned binary/manifest/source/run, parsed current link, raw lifecycle
markers, pre/post health and unchanged native legs, exact RAM cleanup,
installed producer PID/hash unchanged, private `C2M_HW_*` evidence only).
Old `build/run_m4_sniff_reviewed.py` now refuses hardware execution.

## Why not `tcpdump` or a second `:8080` client

- Camera has no `tcpdump`; no package is installed.
- `cardv:8080` holds one global client pointer; even a receive-only second
  client steals/clears the M4 stream. Prohibited with M4 attached.
- `adas:26012` multi-client behavior is unverified; no test client is opened
  from the laptop. Only the camera-local raw observer sees both legs without
  joining either session.

## Preservation

- No replacement/stop of installed `c2m-signs`, no shared status writer,
  no second writer of any status file, no Wi-Fi/AP/STA change, no
  UART/FIFO/CGI/warning injection, no M4 firmware change.
- Hardware run only in a newly notified stationary session with healthy
  recording/app/ADAS confirmation, fresh camera-facing IPv4, pinned host key,
  UUID check, finite SSH window, `timeout -t` + `nice -n 10`, exact cleanup.
- Raw captures stay in private `C2M_HW_*` with manifest; public repo gets only
  safe counts/hashes/schema, never payload bytes, keys, DB, or credentials.

## Status

Owner later confirmed ready. A fresh UUID/host-pinned READ-ONLY preflight
at `m4_sniff_preflight_20261016_122434` found current USB legs, active finite
SSH, running recorder/ADAS and unchanged D4 assets. No sniffer upload/execution
yet: V2 was held for static-review blockers, fixed offline as V3. Local-only
V3 runner is separately named `build/run_m4_sniff_v3_reviewed.py` and fails
until exact source/run/manifest/binary pins are approved. It requires parsed
current RNDIS/ARP/route/ESTABLISHED legs and validates raw lifecycle output
without fabricating self-test markers. Raw capture must stay private.
Next: synthetic successful parser/output tests → ARM CI/QEMU/import gate →
exact pinned bundle → finite hardware run if owner readiness/window remain
valid → offline decode. No replay, M4 widget support or full L1 acceptance is
implied by any earlier build-only result.
