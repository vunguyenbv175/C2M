# c2m-warner — HOST/REPLAY GPS sign advisory

This component is a **host-side replay harness**, not a vision TSR, not a device
GPS daemon, and not a verified C2M runtime integration. It is intentionally
blocked from live-device operation until an explicit, passive source and its
I/O contract are verified. It does not open a tty, read stdin, touch audio,
write a display or FIFO, or send data over a network.

The user's component structure/API is retained; parser, DB integrity and
matching guards have been hardened. The executable now accepts only an
explicit regular-file replay:

```text
c2m-warner --replay <regular NMEA file> -s <signs.db> [-l <append-only log>]
```

All options are required except `-l`; unknown, duplicate, or incomplete
arguments fail closed. `--replay` rejects `/dev` paths, standard input, device
nodes, FIFOs, directories, and (on the host) symlinked input files. The replay
exits at EOF; it does not retry or busy-spin. Oversized or otherwise malformed
lines are discarded through their newline rather than parsing a tail fragment.

## What this is

```text
main.c    explicit HOST/REPLAY loop; bounded private alert log
nmea.c    parse and checksum-verify supported RMC sentences
warner.c  offline sign matching engine
db.c      existing binary sign-database loader
```

A sign database supplies **GPS advisory candidates**, not camera recognition.
The owner has now provided a real Vietnam dataset privately (see below), but
no verified live device input, display, audio or alert transport is supplied
by this repository. Loading the database does not establish a deployed TSR
or a safety-grade road matching function.

## Build and test

```sh
# From repository root; keep artifacts in the ignored build/ directory.
cmake -S fw/warner -B build/warner-host
cmake --build build/warner-host
ctest --test-dir build/warner-host

# direct host build, if CMake is unavailable (directory must exist)
gcc -std=c99 -Wall -Wextra -Os -o build/warner-host/warner_host \
    fw/warner/main.c fw/warner/warner.c fw/warner/nmea.c fw/warner/db.c -lm
```

A replay must contain checksummed, valid RMC records and must be a regular file;
there is no implicit `/dev/ttyS*` default. A minimal EOF test can be made from a
known valid RMC fixture (the checksum must match the exact sentence):

```sh
python3 fw/warner/tools/build_signs_bin.py --demo /tmp/signs.bin
printf '%s\n' '$GPRMC,123519,A,1046.320,N,10641.400,E,80.0,90.0,230394,,,A*77' > /tmp/replay.nmea
./build/warner-host/c2m-warner --replay /tmp/replay.nmea -s /tmp/signs.bin
```

The command should terminate at EOF. For a meaningful alert test, use a valid
RMC fixture positioned near a demo sign. Do not substitute a tty, pipe, stdin,
or a device path. The GPS-derived clock is explicitly labelled
`SIMULATION`: it uses only RMC time-of-day, rejects repeated/backwards samples,
and conservatively accepts only a last-minute-to-first-minute midnight wrap.
It does not claim a real date or a real monotonic clock.

## Database — owner-private, host validated only

Owner-provided `C:\Code\C2M\signs_vn.bin` has 28,551 records / 2,855,112 bytes,
SHA256 `7b3fdf9fd13107acd51bdd3a1c814da301672fb482cd32790d371ccd2b4a3bf5`.
Counts: R.420=6278, R.421=6430, P.127=15343, P.125=108, P.130=121,
P.131a=271. The source is NOT committed/redistributed; rights, update date,
road-level accuracy and application-heading semantics need separate review.

**All 15,343 speed-limit entries have unknown application heading**, as do
500 prohibition entries. Only the 12,708 R.420/R.421 entries carry direction.
The matcher suppresses unknown-direction signs, so this DB cannot yet give
credible automatic speed-limit alerts. A private filtered review artifact
keeps R.420/R.421, not a deployed nationwide road speed-limit database.

```sh
python3 tools/inspect_signs_bin.py /private/signs_vn.bin \
  --report /private/signs_report.json \
  --directional-out /private/signs_directional.bin
python3 tools/build_signs_bin.py --demo /tmp/signs.bin
python3 tools/build_signs_bin.py --sqlite signs.db /tmp/signs.bin
python3 tools/test_signs_tools.py
```

Format: magic `C2MSDB01`, little-endian u32 count, then 100-byte records
(double latitude, double longitude, float heading, `type[16]`, `label[64]`).
The loader requires exact size, finite coordinates/headings, valid UTF-8 and
at most 40,000 records; malformed/truncated/appended files fail as a whole.
Heading 360 is normalized to 0. Generation is deterministic, UTF-8 safe and
atomic; SQLite input is read-only. Replay requires regular non-symlink paths.

## Logging and privacy

Logging is optional (`-l`). It is append-only and capped at 64 KiB based on the
existing file size across runs. A full file, failed `fwrite`, failed `fflush`,
or size-inspection failure disables logging cleanly without stopping replay.
Alert log records contain a sign index and derived distance/ETA, but no precise
latitude/longitude, replay path, or GPS coordinates by default. Stdout is only
the existing host-readable simulation alert text; no audio, display, FIFO, or
other output hook is enabled.

## Runtime capability status

There is deliberately **no live GPS feed, verified database deployment, or
verified output contract** here. Do not restore the old unsafe tty advice or
silently consume `ttyS1`/`ttyS2`; shared serial ownership and passive tapping
must be established by a separate, explicit review before any future mode is
considered. Preserve the user's stock firmware and code. This replay harness
is evidence generation and engine testing only, not permission to deploy a TSR.
