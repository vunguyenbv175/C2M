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
- Finite: 32 packets max, 256B snaplen, 64B hex per packet,
  15×1s `poll()`, 30s monotonic bound, signal-stop, external timeout still
  required. Output stays ASCII and under 8KiB.
- Graceful when `usb0`/raw socket is absent (CI/QEMU path):
  `completion=iface_unavailable|capture_unavailable`, exit 0, still finite.
- `--self-test` is pure synthetic Ethernet/IP/TCP/ARP parsing, no network.
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
hardware runner `build/run_m4_sniff_reviewed.py`
(pinned bundle, fresh stationary session, pre/post health, exact RAM cleanup,
installed producer PID/hash unchanged, private `C2M_HW_*` evidence only).

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

Source, ARM build script, host test, QEMU gate and reviewed runner are being
added offline in this change. No camera contact has been made for L1 yet.
Next: host-test PASS → ARM CI PASS → pinned bundle → newly notified hardware
run → offline decode against `M4_STATIC_PROTOCOL_V1.md` topics/keys.
