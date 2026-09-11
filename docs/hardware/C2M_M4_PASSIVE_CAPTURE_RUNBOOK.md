# C2M M4 Passive Capture Runbook — L0/L1 only (no injection)

**Safety:** passive observation `READ_ONLY`. pcap only on verified interface, finite, no filter bypass. L3/L4 `BLOCKED`. L2 only per gate table below.

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
