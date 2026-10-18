# Owner-approved continuous diagnostics add-on — 2026-10-18

## Status

**Installed and collecting on the camera's SD card.** One-sample smoke test returned0; continuous status reports `card_result=0`, `truncated=0`, `state=running`. Card log grew from2,299 bytes (smoke) to10,000 then17,261 and48,081 bytes while sample sequence advanced to25. Reinvoking the isolated launcher left the same single logger PID, confirming its no-duplicate guard.

The startup hook is installed and verified, **and automatic startup after a natural power cycle was subsequently observed**: after an owner-initiated natural power cycle (no forced reboot), the launcher started exactly one logger (`PID 1047`, `state=running`, `card_result=0`, `truncated=0`) with no duplicate. No camera reboot was forced for either test. Full-card/removal, actual8MiB rotation and long-drive acceptance remain pending; offline bounds/tests are not substitutes.

The owner explicitly requested detailed continuous camera-side logs, including future boots, for debugging ADAS and other subsystems without a laptop connection. This supersedes the earlier two-hour, single-boot proposal. It does not authorize resets, recalibration, license changes, firmware replacement or vendor-service restarts.

## Intended scope

- Independent diagnostic process; no network listeners, new M4 stream client, settings writes or stock-process control.
- Camera-side sampling every five seconds, with real time **and monotonic uptime** (camera wall time can jump).
- Process identities/start times, CPU/RAM, recording/status indicators, safe GPS freshness flags, network/link counters and configuration change fingerprints.
- Do not log raw GPS coordinates/speed payloads, recordings/media names, full flag files, calibration geometry, license/SN material, SSH keys or challenges.
- Fixed private card directory `/mnt/mmc/C2M_DIAG/continuous` with bounded rotation, target **16 × 8 MiB = 128 MiB**. Oldest diagnostic generations may be replaced; no unrelated files/video are deleted.
- No automatic upload. Logs remain on the owner's card until explicitly retrieved. Preserve the full diagnostic directory privately after a fault; share sanitized summaries rather than raw files by default.
- The 64 GB card had about 5.4 GB free at preparation time. Capacity is not permission to grow logs without a bound; recording storage and a low-free-space guard take priority.
- Refuse symlink/foreign objects and unmounted/full-card destinations. Do not delete or rotate video or pre-existing vendor logs.
- Start once per boot through a small isolated launcher. Back up and verify the exact original D5 `boot.sh` before appending its launcher; do not re-execute the existing boot services during installation.
- The existing ADAS, recording, C2M services and SSH settings must remain untouched. Only the independent logger is launched/signaled for installation or rollback.
- Installer verifies artifact hashes again before activation and reconstructs the exact permitted boot addition from the pinned original. File/directory fsync support on the device was verified; this is not a guarantee against arbitrary power-loss damage.
- Disable marker: `/customer/minieye/config/.c2m-continuous-diag/disabled`; presence prevents the next boot launch. Creating it does not stop an already-running logger.
- Rollback must verify both the current modified-boot hash and backed-up original hash, stage the original with preserved executable metadata, syntax-check, then rename. Signal only the exact diagnostic PID after validating `/proc/PID/cmdline`; never use `killall`, restart vendor services or remove card logs.
- The launcher once guard records a launch attempt, not proven collection. Validate logger PID, status and card-file growth separately. A failed launch is not automatically retried at boot.

## Installed artifacts and storage

| Item | Installed location / SHA-256 |
|---|---|
| Logger (67,896 bytes, static ARM hard-float) | `/customer/c2m/c2m-diag` — `fe53d8bb2e0d38bc245dae4da39695bd574d73e1b04e9685669072c15c43a5c3` |
| Launcher | `/customer/c2m/continuous_diag_boot.sh` — `8e7d620f7ee109843820d2858387effca1d6421cad2eecd57c59b44fcc1e0933` |
| Original boot backup | `/customer/minieye/config/.c2m-continuous-diag/boot.original.sh` — `1f40dfbd804092625c890725d3787187a07e00607023c1cde8fc0f6c34b4269b` |
| Boot with isolated addition | `/customer/c2m/boot.sh` — `11fd19ca0820413e60e22307ab5ebf7e83f420492901995bd706bdecc81a4f87` |
| Install manifest / pending copy | `/customer/minieye/config/.c2m-continuous-diag/` |
| RAM status and singleton lock | `/tmp/c2m-continuous-diag/` |
| Card logs | `/mnt/mmc/C2M_DIAG/continuous/current.log`, `log01.log` … `log15.log` |

Final review fixed a fail-closed directory-enumeration bug: each `readdir()` now resets/checks errno, refusing an incomplete namespace scan on SD I/O failure. The earlier staged candidate was **not executed**; it was replaced with the reviewed hash above before smoke testing/activation.

The original vendor ADAS/lane/recorder PID list stayed identical across installation. All four ADAS/calibration source/decoded hashes stayed unchanged. Only independent logger artifacts and the explicitly authorized boot addition were changed; no vendor service was restarted.

## Recorded schema

- One bounded text sample per five seconds with `real_ms`, `mono_ms`, logger PID/sequence, clock/page conversion values and RTC-shift marker.
- Process tuples include canonical name, PID, PPID, state, start ticks, CPU ticks, RSS, threads, FD counts and sampled peaks; appeared/disappeared is not automatically labeled restart.
- Meminfo/load/CPU/network counters; local-port TCP connection counts without peer addresses.
- Four config fingerprints are explicitly **CRC32**, size and mtime, **not cryptographic integrity hashes**. Exact numeric calibration state1/2 only; no geometry or full flags.
- Safe allowlisted status fields, GPS freshness only; no coordinates, speed, distance or event payloads. Numeric recording/status values are preserved without inventing semantics.
- Kernel non-consuming bounded snapshot produces CRC/counts of fault categories every60 seconds, not raw dmesg.
- Existing vendor log is read incrementally at most16KiB/sample: fixed category counts only (seamless mux, ADAS audio/message tokens, error/fail), never raw log lines. Counts can overcount mentions or miss tokens across chunk boundaries; they are clues, not definitive warning events.
- Status `card_result`:0 persisted,1 unavailable/general failure,2 low space (<32MiB),3 unsafe namespace,4 write/fsync failure. `truncated=1` marks capped output.

## Diagnostic boundaries

A process-presence log is not proof that inference, recording or collision warnings are healthy. In particular:

- Saving ADAS configuration intentionally restarts the vendor ADAS/lane chain. PID changes around a config-hash change are not automatically crashes.
- Same-name short-lived `cardv` children may appear while the main recorder PID survives; compare PID **and start time/parent**, not just count.
- `rec_status` value `2` has been observed while cardv logs seamless mux activity. Do not label non-`1` values as definite recording failure.
- ADAS `install_calib_state=1` is accepted by the traced startup path; do not force it to `2`.
- Vendor `run.sh` currently sends ADAS output to `/dev/null`. A passive logger cannot recover discarded application output or guarantee a full stack trace; changing that requires a separately reviewed intervention.
- Kernel fault categories should be counts/classifications only, not raw kernel text containing paths or payloads.
- Card removal, hard power loss or write errors can lose the latest samples. Rotation is a storage bound, not a guarantee of retention or crash consistency.

## Baseline before installation

The preceding laptop-only ten-minute observation completed 120 successful samples. ADAS/lane PIDs and four configuration hashes stayed unchanged; a transient extra `cardv` PID appeared in one sample, without replacement of the main PID. GPS advisory freshness stayed zero. No driving acceptance or repair was claimed.

The owner subsequently confirmed FCW/HMW stayed **High** during both captured page reopens. Actual phone `ADAS.config` response matched `true / 3`; the reported OFF-on-reopen failure was not reproduced in that capture. No functional firmware/app fix has been applied.

## Activation acceptance checklist

Before declaring installed/collecting:

1. Inspect and test logger path validation, bounds, process parsing and privacy filters offline; cross-build a pinned static ARM artifact.
2. Verify exact original boot hash and save a byte-exact backup; reject unknown existing add-on paths.
3. Stage/read back executable and launcher; verify hashes and executable permission.
4. Run one sample with the logger's own singleton/card validation; verify a bounded sanitized card record and explicit collection status. Do not restart stock processes to test it.
5. Atomically append only the isolated startup call; preserve original boot metadata and verify staged/committed hashes and stock-shell syntax.
6. Launch only the logger, then verify PID/executable identity, repeated samples/file growth and storage counters. Reinvoke launcher to prove it does not duplicate the process.
7. Compare ADAS/lane/recorder PIDs and four config hashes against the pre-install baseline. Unexpected changes require investigation, not an automatic retry of ADAS.
8. Confirm separate backup/rollback pins, rotation bound, disable instructions and absence of raw sensitive fields. Do not force a camera reboot solely for acceptance; next-boot auto-start remains pending until naturally observed.

Installer/rollback independent review passed within its scope. That does **not** substitute for logger-source review or hardware collection validation.

## Deployment is not a frozen D5 release update

Any installed `c2m-diag`, launcher and modified `boot.sh` are an explicitly authorized diagnostic add-on, not byte-identical members of the frozen D5 release. Do not overwrite D5 release pins or claim the original manifest still matches all added/modified files. Keep the original boot backup and separate add-on hashes.

## Update later on 2026-10-18 — drive collection, GPS-freshness caveat, owner pivot

- Continuous collection ran across a natural boot and an owner drive:
  ~4.7 h and 3,454 samples recorded by the card logger; cadence stayed 5 s;
  `current.log` reached ~6.07 MB of the 8 MiB bound (rotation pending at
  last check). No forced reboot was used.
- `d4.gps_fresh` **never** reported 1 in any sample, including driving time
  when the separate passive capture proved the GPS speed feed was live.
  Treat `d4.gps_fresh` as an unreliable proxy; it is not evidence that GPS
  or its speed feed is broken.
- Recorder-log token counts (`rec_log_counts`) were nonzero only for index 0
  (`Seamless` mux mentions; e.g. 280×"1" plus a few 9/19/29/33) while
  `minieye.log` itself grew during driving (~359 KB). FCW/HMW/LDW/PCW/SAG/
  VB/`adas_fail`/`tlr_green_on`/`error`/`fail` counts stayed zero. Counts
  remain clues, not warning events (see boundaries above).
- A bounded, reviewed passive loopback capture (RAM-only tool, auto-removed
  after review) during driving saw 596 packets in exactly two flows from
  source port 23666 to the ADAS and lane-postprocess consumers; speed values
  were 68 zero / 150 in [1,10) / 76 in [10,30) / 4 sentinel 65535 — the
  speed feed was genuinely live. No reverse-direction or other loopback
  traffic appeared, so no ADAS warning-channel traffic exists on that
  loopback. That drive stayed below the >30 km/h HMW gate, so HMW silence
  there is expected; FCW silence at those speeds is not explained by these
  counts.
- Owner decision after this evidence: stop the VI FCW/HMW code-level
  root-cause chase ("thôi khó quá") and build a new flash candidate instead:
  **Candidate E = EN core (D4 asset set) plus the checked VI `oneed_cust`
  system-audio swap (17 wavs)**. See `docs/firmware/CANDIDATE_E_20261018.md`.
