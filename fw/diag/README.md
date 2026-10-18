# Continuous passive card diagnostics (owner add-on)

This component samples selected camera diagnostics every **5 seconds**, for as long
as its process runs, and retains bounded text logs on the card. It does not control
ADAS, recording, Wi-Fi, calibration or other vendor services. This is **owner-specific
boot integration, not a D5 release build**: neither `fw/d3/boot.sh`, the frozen D5
manifest nor release workflows are changed by this component.

Only source, a launcher, offline tests and build instructions belong here. No
compiler, executable, raw device logs, device identifiers, private access scripts
or license data are included. There is intentionally no remote installer.

## Build (host only)

Use an independently installed **Zig 0.14.1**. From the repository root in
PowerShell, choose an existing output directory **outside the repository**:

```powershell
.\fw\diag\build.ps1 -Zig 'C:\tools\zig-0.14.1\zig.exe' -Output "$env:TEMP\c2m-continuous-diag"
```

The static ARM hard-float musl build uses exactly:

```text
zig cc -target arm-linux-musleabihf -mcpu=cortex_a5-d32-neon-fp16-vfp4-vfp4d16-vfp4d16sp-vfp4sp-vfp3-vfp3sp+vfp3d16+vfp3d16sp -static -Os -Wall -Wextra -Werror continuous_diag.c -o <external-output>
```

**Do not replace the feature list with `-mcpu=cortex_a5 -mfpu=vfpv3-d16`.**
With Zig 0.14.1 that simpler invocation retained CPU defaults for NEON/VFPv4.
The explicit exclusions target Cortex-A5 with VFPv3-D16, without NEON/FP16.
Expected ELF properties are ELF32 little-endian ARM, hard-float EABI, no
`PT_INTERP`/`PT_DYNAMIC`, Cortex-A5 attributes, `Tag_FP_arch=4` and no nonzero
Advanced SIMD attribute. No device is accessed by the build script. Builds are
repeatable with the pinned compiler/flags; hashes may depend on toolchain and
build environment and are not a release-signing mechanism.

## CLI and owner boot integration

On the camera, once separately installed by its owner:

```sh
/customer/c2m/c2m-diag --once
/customer/c2m/c2m-diag --run
```

Exactly one argument is required, with no output-path override. Both modes
require root and use the same mount, namespace and singleton checks. `--once`
collects one sample (exit 0 on persisted sample, 4 on card failure); CLI/non-root
errors exit 2, unsafe/duplicate RAM namespace exits 3. `--run` has no lifetime
deadline and no self-restart. SIGTERM/SIGINT only request this logger's exit.
Do not run `--once` alongside an existing `--run` instance.

`continuous_diag_boot.sh` is the source of an optional owner-managed launcher.
It requires the real, non-symlink directory
`/customer/minieye/config/.c2m-continuous-diag`, and a regular executable
`/customer/c2m/c2m-diag`. A `disabled` file (or symlink at that path) prevents
launch. It atomically creates `/tmp/c2m-continuous-diag-start.once`, then starts
`--run` in the background with all standard streams detached. It never creates
the opt-in directory or rewrites boot files. The owner must separately arrange
invocation from their local boot customization; no generic boot patch is shipped.
The once-per-boot marker deliberately prevents automatic retries if startup
fails. Adding `disabled` only prevents future launches; it does not stop an
already running process. No health/calibration/startup-check script is invoked.

## Writes, safety checks and retention

- Card output is fixed at **`/mnt/mmc/C2M_DIAG/continuous`**. Before creating
  directories or writing logs, numeric `/proc/<own-pid>/mounts` must identify the
  exact `/mnt/mmc` mount from `/dev/mmcblk0` or `/dev/mmcblk0p1`, read-write,
  backed by a block device with matching device number. A second mount check
  precedes append. No fallback writes to rootfs when the card is absent.
- At least **32 MiB available** is required by `fstatvfs` before card directory
  creation/logging. Directories are descended using anchored `openat` with
  `O_DIRECTORY|O_NOFOLLOW`. Root ownership is required; FAT directory modes are
  not required to be 0700. Regular files must have one link; unsafe files are
  refused. This is not protection against a concurrent hostile root writer.
- The namespace must be empty, or contain the exact `owner.v1` marker
  (`C2M_DIAG_V1` plus LF) and only recognized logs with matching headers.
  Unexpected, malformed, linked or oversized entries cause refusal, **not
  cleanup**. The namespace directory scan resets `errno` immediately before
  **each** `readdir`, so helper calls cannot turn normal EOF into a false error;
  actual directory-read errors still fail closed.
- `current.log` plus `log01.log` through `log15.log` are each at most **8 MiB**:
  **128 MiB total log contents**, plus a tiny ownership marker and filesystem
  metadata. Rotation occurs before append would exceed a slot. `log01` is the
  newest archive. Only the validated fixed oldest slot is deleted. Samples are
  bounded below 15,000 bytes. Chronology follows the rename chain, independent
  of RTC changes. Card descriptors close after each sample.
- `fsync` is used on observed process/config/RTC changes or every 60 seconds;
  there is no global sync. There are no sockets, subprocesses, USB/IPC/control
  operations, settings writes, stock-process signals or license access.
- RAM state is limited to root-owned mode-0700 `/tmp/c2m-continuous-diag`, with
  persistent mode-0600 `lock` held by nonblocking `flock`, and atomic `status`
  replacement via exclusively created `status.new`. A stale `status.new` is not
  overwritten; investigate rather than deleting blindly. The lock is never
  unlinked, avoiding split-lock races. The launcher also owns its RAM once marker.

RAM status fields are `version`, `pid`, `sample`, `monotonic_ms`, `card_result`,
`truncated`, `state`. `card_result` is 0 success, 1 unavailable/general failure,
2 below free-space threshold, 3 unsafe namespace, 4 sample write/fsync failure.
Some creation/header/rotation errors use the general-failure code. Card failures
are reported without stopping continuous sampling. Status updates themselves
can fail; do not treat an old status file as proof of current health.

## Data recorded (no raw sensitive input)

Each bounded text sample includes logger PID, per-invocation sequence,
`CLOCK_MONOTONIC` milliseconds, camera `CLOCK_REALTIME` milliseconds, tick rate
and page size. `real_ms` is **camera time, not host receipt time**. Divergence
over 2 seconds is reported as `rtc_shift_ms`.

- Allowlisted processes: adas, lane_accelerator, lane_postprocess, mutualism,
  cardv, c2m-idle/signs/debug/web/wifi, dropbear, goahead. Kernel-truncated comm
  names map to canonical names. No command lines/argv are read. `p=` fields are
  name, PID, PPID, state, start ticks, user/system ticks, RSS pages, VmRSS KiB,
  threads, FD count, sampled RSS peak and FD peak. `appeared`/`disappeared` refer
  to PID/start pairs, **not inferred service restarts**. Limits: 128 tracked
  pairs, 4096 proc entries and 4096 FDs per sampled process.
- Selected numeric meminfo, load averages and aggregate CPU ticks; sampled peak
  used memory where MemAvailable exists; wlan0/wlan1 byte/error/drop counters.
  TCP/TCP6 table scans are bounded to 8192 rows each, with established/listening
  counts only for local ports 80, 8080, 24012, 26012 and 2222. No addresses output.
- `/tmp/rec_status2`, `rec_status`, `sd_status`: strict unsigned decimal only,
  at most UINT32_MAX, with at most one optional trailing LF.
- D4 status: enum state, boolean gps_fresh/active, numeric sequence. Debug:
  enum state/lifetime, numeric window_sec. Wi-Fi: enumerated sta_state,
  sta_supported, bt_presence, dhcp_helper. Unknown/freeform fields never output.
- Four config files (`adas.flag`, `adas_de.flag`, `calib.flag`, `calib_de.flag`):
  explicitly labeled **CRC32**, size and mtime, with at most 64 KiB read each.
  No contents stored. `calib_state` accepts a single exact whole
  `--install_calib_state=1` or `=2` line from calib_de.flag; otherwise unknown 0.
- Non-consuming `klogctl(3)` READ_ALL snapshots, at most 16 KiB every 60 seconds:
  CRC32 and line counts for segfault, Out of memory, Oops:, watchdog, I/O error.
  No raw kernel output or consuming/clearing operation.
- Existing `minieye.log`: at most 16 KiB/sample, initially seeking to its last
  16 KiB and resetting on file identity change/truncation. Only byte/reset/backlog
  indicators and ordered substring counts: Seamless, minieye_msgpack, GPS time,
  FCW, HMW, LDW, PCW, SAG, VB, adas_fail, tlr_green_on, error, fail.

## Offline tests

From the repository root:

```powershell
python -B fw/diag/test_diag_contract.py
gcc -std=c11 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation fw/diag/test_core.c -o "$env:TEMP\c2m-diag-test-core.exe"
& "$env:TEMP\c2m-diag-test-core.exe"
git diff --check
```

For a POSIX host, use an external temporary output path instead of the Windows
`.exe` path. The C test covers CRC32, strict number/calibration parsing, comm
mapping, proc stat parsing, mount allowlisting, rotation boundary checks,
privacy allowlists and bounded formatting. The Python tests check source
contracts for passive behavior, mount/free-space ordering, fixed paths,
namespace safety, the per-iteration `readdir` errno regression, bounded rotation,
privacy output selection, launcher behavior and exact compiler flags. They
neither execute the production logger nor access a camera. Textual checks are
regression guards, not a full security proof or ELF instruction validation.

## Known limitations

- Rotation is not a crash-transactional journal. Power loss during renames may
  leave archive gaps; an interrupted append may leave a partial last line.
  Invalid headers fail closed. Preserve and investigate such logs rather than
  automatically deleting them. fsync does not guarantee FAT/controller recovery.
- Hot-unplug can race mount validation. Cards are not pinned by physical UUID;
  alternate aliases/partitions and read-only mounts are intentionally rejected.
  Blocking filesystem syscalls have no timeout/worker, so a failing card can
  stall the logger. Do not infer a fixed performance/IO overhead from the 5s
  target interval; there is no benchmark here.
- Namespace markers/headers are not cryptographic ownership proofs. No defense
  against concurrent root modification is claimed. Config read/stat observations
  can race replacement; CRC32 is a collision-prone change detector, not integrity.
- Process/FD snapshots race process exit/reuse. PID/start pairs reduce ambiguity
  but do not create an atomic snapshot; counts and peaks are sampled, not absolute
  maxima. Raw CPU ticks are output without computing per-process deltas. Tracking
  limits, read failures and sample truncation can omit observations.
- Recording categories are case-sensitive substring occurrences, not decoded
  events. They can overcount ordinary mentions, miss tokens crossing read
  boundaries and stop matching at embedded NUL. `GPS time` is an unverified
  pattern, not a guarantee that every time event is detected. Kernel counts
  describe overlapping bounded snapshots, not cumulative new faults.
- Offline tests do not exercise Linux mount/symlink/rotation/singleton/signal
  integration. Host compilation and static ARM compilation are not camera runtime
  tests. A reported owner smoke sample with `card_result=0` does not establish
  absent/full-card, rotation, power-loss, reboot or long-duration reliability.
  Those require separately authorized owner checks; no such checks run here.
