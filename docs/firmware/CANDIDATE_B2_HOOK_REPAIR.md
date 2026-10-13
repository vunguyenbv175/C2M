# B2 hook repair — code fix + execution tests (2026-10-14)

**Status:** IMPLEMENTED + HOST-TESTED. No firmware image built here, no card
written, no device flashed. Field acceptance still BLOCKED pending a pipeline
rebuild, fresh update token, and a new flash trial.

## Defect (recap)

`tools/fw/mutate_customer.py` appended the daemon launch line at EOF, after
the stock hook's terminal `exit $?`. The hook is executed by `demo.sh`, not
sourced, so the launch never ran. See `CANDIDATE_B2_HOOK_FAILURE.md`. An
independent read-only validation confirmed the same root cause and recommended
this repair shape.

## Fix (`tools/fw/mutate_customer.py` only)

When the hook ends with a terminal `exit ...` line (the stock shape), insert
this block BEFORE it instead of appending after it:

```sh
_c2m_rc=$?
/customer/c2m/c2m-idle >/dev/null 2>&1 &
exit $_c2m_rc
```

Properties, each covered by a test:

- Reachable: the launch sits before the terminal exit on the normal path.
- Stock exit status preserved: `$?` is saved BEFORE the background launch
  (a background `&` would otherwise overwrite it). A hardcoded `exit N` is
  kept verbatim; bare `exit` / `exit $?` become `exit $_c2m_rc`.
- No foreground wait: backgrounded with `&`; stdio detached so a blocking
  console can never stall the hook.
- Failure isolation: a missing/failing binary cannot change the hook's exit
  status or hang the boot path.
- Fail-closed: repaired hooks are refused a second mutation (double-repair
  guard); hooks without a terminal exit keep the legacy EOF append, which is
  reachable by falling off the end.

## Verification (host, no firmware)

- `tests/test_candidate_b.py`: new 2b (exact repaired bytes for a
  terminal-exit hook, dead-shape rejection, double-repair refusal), 2c
  (execute mutated hooks under `sh`: exit codes 0/3 preserved, fake daemon
  launched in background, hook returns promptly, missing binary isolated),
  2d (stock-like Wi-Fi-OFF branch with stubbed `nvconf`: daemon launched,
  exit 0). Suite: `candidate-b synthetic: OK`.
- Real stock hook (933 bytes, local-only bytes, NOT in repo): repaired to
  991 bytes (+58), tail exactly the block above, `sh -n` clean.
- Unchanged suites still pass: `test_reversion_sd_package.py` (36),
  `test_firmware_pipeline.py`, `fw/device_minimal/test_sdlog.py`.
- `git diff --check` clean. Daemon source (`c2m_idle.c`) untouched, so the
  runtime marker stays `c2m-idle 0.2.0-sdlog1`.

## Addendum — bounded mount wait (2026-10-14, after field evidence)

The hookfix flash proved the repaired launch executes
(`START v=0.2.0-sdlog1 ... uptime=6` on the flash card), but the recording
card showed normal MP4 recording with NO `C2M_DIAG`: the daemon initializes
its SD log stream once at startup, and at `uptime=6` the recording card is
not yet mounted. The block therefore waits for the mount first:

```sh
_c2m_rc=$?
( _c2m_n=0
while [ $_c2m_n -lt 30 ]; do
grep -qs ' /mnt/mmc ' /proc/mounts && break
sleep 2
_c2m_n=$(($_c2m_n + 1))
done
/customer/c2m/c2m-idle >/dev/null 2>&1 & ) >/dev/null 2>&1 &
exit $_c2m_rc
```

Uses only `grep`/`sleep`/`$(( ))`; the waiter is backgrounded AND detached
so the hook still exits immediately; a never-mounted card still gets the
daemon after 60 s. Real stock hook: 933 → 1132 bytes, `sh -n` clean.

Tests added (`tests/test_candidate_b.py` 2e): mount-gated ordering (daemon
starts only after the mount appears, proven via a builtin-only stub call
counter) and wait expiry (daemon still starts). Test-harness lesson
recorded: Git/MSYS `sh` prefers `/usr/bin` over inherited PATH AND mangles
drive-colon entries on inner `export PATH`, so stubs for stock tool names
must win via MSYS-form (`/c/...`) inner export, use shell builtins only, and
the waiter subshell's stdio must be detached or test pipes never drain.

## Explicitly NOT done here

- No `customer.es` / inner / TAR rebuilt: that requires the Linux pipeline
  (`mkfs.ubifs`, root, private vault TAR) via
  `.github/workflows/firmware-candidateB.yml`, which now describes the
  insert-before-exit mutation in its release notes.
- No update token chosen: the rebuild MUST use a fresh 14-digit token
  differing from BOTH `20230803193750` and the installed `20261012000001`,
  in both `sysVer.txt` and the inner script, with fresh MD5/SHA256.
- SD mount timing remains an open device condition: the daemon initializes
  its diagnostic stream once at startup. If the repaired run still yields no
  `C2M_DIAG`, that — not the hook — is the next suspect. No speculative
  mount-wait loop was added to the boot path.
- Frozen A/B1/B2 artifacts and hashes untouched; this repair becomes a new
  separately-hashed artifact at build time.
- No SD writes performed; the inserted `C2M_FLASH_B` card still holds the
  defective reversion and MUST NOT be flashed again (its token is also
  already installed, so the bootloader would skip it anyway).
