# M4 RNDIS usb0 passive sniffer — V3 finite capture, L1 incomplete — 2026-10-16

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
V3 host checks now exercise the real shared formatter (not just source-token
checks): ordinary/options/VLAN TCP payload, ACK padding, UDP lengths,
fragments, invalid/truncated headers, snaplen truncation, output bound and
null-input handling. Windows: 6 pass, Linux-only absent-interface case skipped.
Initial Linux CI `38856651684` failed in the include-harness feature-macro
ordering; corrected in `8767d21` (`38856891002`: Linux7/7 + ARM/QEMU PASS).
Final `b40a276` also parses the actual readelf symbol-name column (not trailing
version-index) and requires receive imports, so the forbidden-import gate
cannot pass by parsing an empty/wrong name set.

## Final V3 preparation and closed window

- Exact source: `b40a276bf4c45c22f96d8d282c86551b4725ddba`.
- Manual ARM workflow `38857027117`: PASS, including Linux7/7 synthetic
  checks, ARM ELF/ABI build, pure ARM self-test, stock QEMU absent-interface
  path/sentinel preservation, and actual undefined-import no-transmit gate.
- Private vault commit: `0881e68e8aa934ac51e6ce65d00a1ae37e8d0546`;
  `deliverables/20261016-ram-debug-r38857027117/m4-sniff-bundle`.
- ELF11736B SHA256:
  `58259c85dcf811174281ea2f9767d74302409efd5261021a3db95a4b41640f4e`.
- Manifest2035B SHA256:
  `fd857ebcf212aba09b03f3c5bb111dd520fd478fe2c0a6c6bd9b28dfcafaa6ff`.
- Bundle retrieved with byte-preserving `git show` (no Windows newline
  conversion); all checksums, source hashes, public manifest equality and
  full ARM ELF gate passed locally. Pinned V3 runner local-only check passed.
  Binary/vendor bytes remain private; public reports contain no payload.

At13:14 local time the owner asked to continue. Fresh laptop discovery found
Wi-Fi IPv4 `192.168.1.10`; bound camera UUID and local host pin check passed,
but TCP2222 returned connection refused. This is **SSH unavailable**, consistent
with finite-window expiry, not an authenticated read of debug status or proof
of the exact expiry reason. Private local evidence:
`C2M_HW_20261012/07_m4/m4_v3_window_check_20261016_131423/window_check.json`.
No retry, listener restart/extension, upload, native observer execution or M4
application connection followed. No raw M4 capture exists from this session.
The earlier12:24 health observations are not a fresh13:14 recording/ADAS check.

Next: separately notified owner-controlled fresh boot/debug session, with
stationary hardware and normal original functions confirmed, then recheck
UUID/host pin/source IPv4/current USB legs and finite SSH window before the
already prepared V3 run. Do not extend the old window to compensate for time
spent on offline fixes. No replay, M4 widget support, full L1 acceptance or
hardware-success claim is implied by these build/local checks.

## Later fresh owner session — finite execution, not full L1

Owner reported reconnected and original functions normal. New source discovery,
UUID/host pin and active SSH passed. First13:21 preflight stopped before upload
because the established26012 leg was absent (8080 and ADAS-owned24012 present).
Read-only ownership/current-link follow-up found26012 had appeared; a new
preflight passed the unchanged required26012+8080 gate. Exact V3 ran ONCE at
`m4_sniff_v3_20261016_132219`:15 records,8 data prefixes retaining768B, exit0,
exact RAM cleanup; no transmit or new application client. Pre/post original
processes/assets/AP/recording and all three USB port pairs were preserved.
Owner subsequently confirmed normal functions, M4 in3D. Hardware access stopped.

Every data prefix was still truncated (96B versus108–204B TCP payload). Partial
outer/inner MessagePack header structure and topic names are visible:
`ped`/`vehicle` on26012 and `lane` on24012. No complete application frame or
inner key value,8080 status message, sign/speed widget or replay was proven.
See `M4_SNIFF_V3_HARDWARE_20261016.md` for exact lifecycle, preservation and
private-manifest hashes. Further capture improvement must be prepared offline,
retain complete bounded small payloads and distinguish ACK/work/byte/time
budgets before a separately notified hardware session.
