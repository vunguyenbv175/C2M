# C2M M4 Passive Capture Runbook — L0/L1 only (no injection)

**Safety:** passive observation `READ_ONLY`. pcap only on verified interface, finite, no filter bypass. L3/L4 `BLOCKED`. L2 only per gate table below.

**2026-10-15 correction:** do not open a second WebSocket client to cardv
`:8080` with M4 attached. Stock EN cardv holds one global client pointer;
connecting and later closing even a receive-only observer can steal/clear the
M4 status stream. Decode existing captures instead. The CLI observer now
requires `--confirm-m4-disconnected` and is not a physical M4 delivery test.

**Current feature target:** owner reports speed is already visible in 2D live
video but has never observed vehicle speed or signs in 3D ADAS. The conditional
top warning bar exists and shows collision-related seconds, not vehicle speed.
Preserve that working UI, 2D/GPS and ADAS. Identify the actual renderer/layout
before attempting a 3D speed change; camera OSD alone does not prove a widget.

## Current RAM-only observer (2026-10-16)

L0 was proven as RNDIS `usb0`, camera `192.168.32.123` to M4
`192.168.32.129`, with native established `26012` and `8080` legs; see
`../firmware/M4_TRANSPORT_L0_20261016.md`. Recheck that link each session.
For stock images without tcpdump, use only the separately ABI/QEMU-gated and
exactly pinned finite `fw/m4_sniff` V3 observer and its reviewed local runner.
V1/V2 are withdrawn before hardware execution (payload-label bugs); no new
application socket is needed or allowed for the capture.

V3 captures partial payload prefixes, NOT a reassembled TCP stream. Limits:
20 received packets, 15 poll calls, 30s internal deadline, 6144B record budget,
512B snaplen and 96B per-record payload. Fifteen calls with a 1s maximum wait
are **not** a full 15s sample when traffic is ready. Explicit captured/truncated
and seq/ack metadata expose missing data. Failure to see a UUID/topic is not
proof the stock stream lacks it. No raw output belongs in the public repo.

New owner stationary/healthy confirmation, fresh source IPv4, UUID/host pin,
current link checks, external BusyBox `timeout -t`, exact private RAM cleanup
and pre/post preservation checks are mandatory. Never extend/restart SSH to
finish a capture after its approved window has expired. See
`../firmware/M4_SNIFF_L1_PLAN_20261016.md`.

## 0. Collect (READ_ONLY)

```sh
sh tools/device/capture_c2m_m4_runtime.sh [label]
# writes C2M_HW_<date>/07_m4/m4_<label>_<ts>/ : ports, conns, procs, threads, fd,
# /proc/net/*, ScreenService/libflow sightings, 26012/8080, usb/rndis, 192.168.32.123, screen device nodes, MANIFEST + hashes
```

Manual read-only equivalents (each READ_ONLY):

```sh
cat /proc/net/tcp; cat /proc/net/unix            # look for :659C (26012), :1F90 (8080)
netstat -anp || ss -lntup
ps; ps w; cat /proc/<pid>/cmdline; ls -l /proc/<pid>/fd
ls -la /dev; ls /sys/class/net; ip addr; ip link
ls /sys/bus/usb/devices/  # VID/PID/serial, driver link
```

Passive pcap examples (only if `tcpdump` exists on device AND interface already verified by evidence; finite + interruptible):

```sh
sh tools/device/capture_interface_pcap.sh <verified-interface> m4_idle 60
```

Do NOT install packages on device automatically. Do NOT assume `usb0` until on/off comparison proves it (see `docs/runtime/DEVICE_BASELINE_CAPTURE.md` A/B method).

## 1. M4 level policy (gate table)

```text
L0 transport known ......... allowed when: on/off iface delta + peer/ARP/conn evidence proves interface
L1 passive decoder ......... allowed when: L0 proven; decode captures only, never transmit
L2 harmless replay ......... allowed ONLY after L0+L1 passive proof AND explicit gate pass; candidates ONLY:
     DispBrightSet / StorageStatus / ScreenModeSet / ClientConn
L3 semantic injection ...... BLOCKED (ADAS state, calibration, GPS speed/quality, warning semantics, RecordVoice, unknown)
L4 extended UI ............. BLOCKED
Default deny for everything not listed.
```

## 2. Evidence

`07_m4/m4_<label>_<ts>/` + `L0/L1 verdict` in summary. No transmit logs should exist at L0/L1.
