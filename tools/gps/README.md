# tools/gps — RAM-only read-only GPS decode status sampler

`c2m_gps_probe.c` is an independent diagnostic observer, not the production
D4 producer (`fw/d4/main.c` untouched) and not a GPS driver. Fixed
`/tmp/car_info` only (`C2M_GPS_DEFAULT_PATH`, no overrides).

Motivation: diagnose whether the installed D4 producer sees advancing GPS
without killing or restarting it. The observer performs only the same
regular-file read the producer does (`c2m_gps_read` on the existing file);
it never opens UART, vendor IPC, or any device node.

## Privacy and safety

* Structural decode status only. Coordinates, speed, course, subsecond
  fraction and UTC values are never printed and never referenced by the
  observer TU (host test proves absence).
* Per-sample output is exactly `sample=N result=<ok|invalid|io_error|
  unstable|unsupported> fresh=<0|1>` plus fixed header/summary.
* No status-file writes, no UART, no network, no shell, no file overrides.
* Freshness is the production gate verbatim
  (`c2m_gps_freshness_update`: 2.5 s stale window, 3 s delta tolerance, two
  strictly advancing UTC seconds required). Failures feed `NULL` per header.

## Bounds (fixed)

samples 10, interval 500 ms. No CLI override exists.

## CLI (explicit)

* `--observe` — 10 read-only samples at 500 ms from the fixed path
  (Linux only; non-Linux exits 3).
* `--self-test` — pure synthetic fixtures only (no files, clock, env).
* `--help` — usage.

Any other arity or flag exits 2.

## Host build/test (no firmware, no camera)

```sh
cc -std=c99 -O2 -Wall -Wextra -Werror \
  tools/gps/c2m_gps_probe.c fw/d3/gps_snapshot.c \
  -I fw/d3 -o /tmp/c2m-gps-probe -lm
/tmp/c2m-gps-probe --help
/tmp/c2m-gps-probe --self-test
python3 tools/gps/test_c2m_gps_probe.py -v
```

Portable `--self-test`/`--help` are validated on this host. `--observe`
requires Linux and an existing `/tmp/car_info`; it is not executed by host
tests.

## RAM-only ARM build (parent CI, manual workflow)

Exact `fw/d4/build.sh` + `fw/d3/build.sh` compat pattern: generated wrappers
with ALL system headers before `fw/d3/compat.h`, ARMv7-A hard-float
VFPv3-D16, time32/off32, old `start.S`, `check_elf.py --allow-dynamic`
(glibc<=2.30, loader `/lib/ld-linux-armhf.so.3`), QEMU pure `--self-test`
and `--help`. Fail-closed, no pipes hiding exit. Saves logs, versions,
hashes.

```sh
sh tools/gps/build_gps_probe_arm.sh --out /tmp/gps-probe-arm --sysroot work/sysroot
```

Artifacts: `c2m-gps-probe`, `gps-probe-selftest-arm.txt`,
`gps-probe-help-arm.txt`, `objects/c2m-gps-probe.versions.txt`,
`gps_probe_arm_hashes.txt`, `objects/toolchain_version.txt`.

## Later on-camera RAM use (delayed)

Same discipline as `tools/wifi/README.md`: stationary confirmation, fresh
private `/tmp` directory, stream + SHA-256 verify before exec, pure
`--self-test` first, then finite `--observe`, stream results back, trap
removes only own files, recheck producer health. `/tmp` only. Never restart
the installed D4 producer for diagnosis.
