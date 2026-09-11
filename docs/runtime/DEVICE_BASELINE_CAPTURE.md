# C2M Runtime Baseline Capture

## Purpose

Static analysis has narrowed the EN-working / VI-bad difference enough that the next decisive evidence must come from the physical C2M.

Use:

```text
tools/device/collect_baseline.sh
```

The collector is designed for the stock BusyBox environment and is **read-only with respect to the C2M runtime**. It only creates files under `/mnt/mmc` (or `C2M_CAPTURE_BASE`). It does not restart, kill, flash, remount, or edit stock services/config.

## Highest-value capture matrix

### A — EN known-good, M4 connected

```sh
sh collect_baseline.sh en_good_m4_on
```

### B — EN known-good, M4 disconnected

Disconnect M4 without changing anything else, then:

```sh
sh collect_baseline.sh en_good_m4_off
```

Compare A/B. This should reveal whether M4 creates:

```text
usb0 or another interface
new USB VID/PID/device
new peer in ARP/neigh
new TCP/UDP/WebSocket connection
new input device
new process/file descriptor
```

### C — VI known-bad

Only if the user intentionally boots the VI image again and has a known recovery path:

```sh
sh collect_baseline.sh vi_bad_m4_on
```

Compare EN/VI to classify failure.

## What is collected

```text
kernel/cmdline/memory/mtd/mounts/modules
process list + cmdlines
status/maps/fds for adas/cardv/mutualism/screen/network processes
TCP/UDP/Unix sockets
ARP/routes/interfaces
sysvipc shared memory/message queues
/tmp, /run, /dev/shm IPC inventory
/dev listing
USB sysfs identity
network-interface sysfs identity
dmesg
hash + size only for selected stock binaries/config files
```

No license/config content is copied by default.

## Ports already worth watching

Static reverse currently gives:

```text
26012 / 0x659c  ADAS ScreenService default export port
8080  / 0x1f90  cardv WebSocket candidate path
```

The collector highlights those ports but does not assume they belong to M4 until runtime evidence proves it.

## Host-side comparison

Copy two capture directories or extract their `.tar.gz` bundles on a workstation, then run:

```sh
python3 tools/device/compare_baselines.py \
  c2m_capture_EN \
  c2m_capture_VI \
  -o compare.json \
  --diff-dir diffs/
```

For M4 transport discovery:

```sh
python3 tools/device/compare_baselines.py \
  c2m_capture_en_good_m4_off \
  c2m_capture_en_good_m4_on \
  -o m4_on_off.json \
  --diff-dir m4_diffs/
```

## Failure classification

The first runtime goal is not “fix ADAS”. It is to classify the VI failure into one of:

```text
A process absent
B process crash/restart
C process alive but raw_adas/ringbuffer absent
D frame path alive but IPU/model init fails
E inference alive but warning/output suppressed
F ADAS alive but M4/audio output path broken
```

Once classified, the good/bad bisect becomes much smaller.

## Safety

Do not run the VI full firmware solely to collect evidence unless EN recovery is proven. The preferred first behavioral bisect remains a reversible temporary launch of the VI `adas` executable on the working EN base.
