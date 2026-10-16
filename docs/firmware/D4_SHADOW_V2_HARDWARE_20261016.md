# D4 shadow v2 — finite hardware run, 2026-10-16

**One complete RAM-only run: valid DB,10/10 GPS reads OK, fresh from sample2;
prior transient stale not reproduced. No production deployment/advisory acceptance.**

## Authorization and identity

Owner reconnected after the notified parked/healthy v2 session request. Actual
camera-facing IPv4/interface was rediscovered; exact camera UUID and existing
strict owner SSH host pin were rechecked. Debug was active on AP-only
`192.168.1.1:2222`, finite1200-second window, with uptime about123 seconds in
initial preflight. No listener restart, extension or automated reboot was used.

A preliminary single GPS-file context read did not meet the local near-zero
speed context check. The agent stopped before native execution and asked the
owner explicitly. Owner confirmed **vehicle fully parked and app/live view,
recording and Vietnamese ADAS normal**. This physical confirmation, not GPS
speed inference, authorized the subsequent finite run. No GPS decoder,
freshness threshold or firmware setting was altered to pass the check.

Private preflight evidence:
`C2M_HW_20261012/06_candidate_D4/shadow_v2_preflight_20261016_102555/`.
Raw GPS/context bytes are private and not reproduced here.

## Exact binary and lifecycle

- Source: `85d7f2d9189084b1d3168743c5a5f88d376c007a`.
- Private bundle: ARM/QEMU CI `38842731209`; general Linux/Chrome CI
  `38842722272` attempt2 PASS on the same source.
- Shadow27264 bytes, SHA-256
  `45260c0c10274c851531472e2fbf573e901f6b6dfdd751842e20644d8391893e`.
- Manifest SHA-256
  `6208c66d02870e89df86816b3b51c817238a1295c3ab566863d8ea447c8fc413`.
- Reviewed runner: `build/run_d4_shadow_v2_reviewed.py`; its bytes matched the
  independently reviewed local hash before use. Historical v1 runner/pins
  were not overwritten or reused for v2.

The source/run/manifest/binary pins were checked locally again. Only the shadow
was uploaded, into a fresh root-private0700 random tmpfs directory. Target
length/SHA-256 were checked before chmod/execution. Pure target D4 self-test
passed under `timeout -t 10 nice -n 10`; one `--observe` ran under
`timeout -t 20 nice -n 10` and naturally completed10 samples. Exit0, exact
RAM cleanup marker, and a separate cleanup/health check all succeeded.
No other diagnostic binary or second `c2m-signs` producer ran.

Private run evidence:
`C2M_HW_20261012/06_candidate_D4/shadow_v2_20261016_102955/`.
`session_results.json`, `v2_samples.json` and `evidence_manifest.json` retain
safe parsed results and hashes alongside private command/stdout/stderr captures.

## Same-poll result

Fixed package DB was valid, count **12708**. Each row reported
`observer_simulation_not_production_delivery`; `status_writes=0`.

| Samples | Advisory state | GPS result | GPS fresh | UTC step | Freshness branch |
| --- | --- | --- | ---: | --- | --- |
| 1 | warming_up | ok | 0 | first | first_anchor |
| 2–10 | ready | ok | 1 | one_step | advancing |

Relative poll intervals in milliseconds:
`[0,1003,1015,1000,1006,1002,1001,1000,1000,1001]`.
First0 is the schema's no-prior-poll sentinel; subsequent intervals were
1000–1015ms, sum9028ms. These are core-feed intervals, not read durations or
absolute clock values.

No adapter-invalid, unstable, I/O failure, repeated GPS second, regression,
timeout or tolerance rejection occurred in these10 polls. No active advisory
or event was selected (`active=0`, `code=none`, event counter0). This was a
parked observation, not a road-heading/nearby-sign delivery test.

**This run does not explain v1 samples8–9.** They were captured at another
time without same-poll diagnostics. One clean finite window cannot establish
continuous reliability, exclude intermittent read/timestamp failures or justify
relaxing freshness. No automatic second run was attempted to chase the issue.

## Preservation and final checks

Before/after command exit0 verified the same pins:

- Installed old D4 producer:
  `761b6ab98e59da15fedf65883d6cb5f95ac66319a45aba1648fbd078f90361c0`.
- Private D4 DB:
  `3bcf871956c61484858bef783187319fa5f9ae0da0c214c2c14afb1d62de411c`.

The installed producer PID was unchanged. It still reported `stale`; shadow
freshness does not update or repair production web state. No status-file
writer was added and no production process was stopped/replaced.

Recording status1 persisted, and the current recording segment grew in the
captured before/after metadata. Stock cardv, ADAS and lane workers remained
present; AP HTTP reported active after the run. No shadow process survived in
the final process inventory. Each of the three runner SSH commands emitted the
same missing `/home/root` chdir warning, while command exit0 and all lifecycle
checks succeeded. No directory/config change was attempted to suppress it.

Owner explicitly confirmed **app/live view, recording and Vietnamese ADAS
still normal after the run**. Hardware access is stopped; no new queries are
needed to document this result. Owner may disconnect camera Wi-Fi.

No flash, persistent write, calibration/license/audio/model change, speaker or
browser beep, AP/STA operation, UART read or cardv/M4 observer was used.

## Remaining boundaries

- Installed production D4 is still old; no corrected deployment is accepted.
- Prior transient freshness loss remains unexplained and longer stability
  is unverified.
- Real directional nearby-sign applicability, UI delivery, road test and beep
  remain unaccepted. A shadow simulation is not production delivery or legal
  speed/overspeed evidence.
- AP+STA, Bluetooth RF and M4 rendering status are unchanged by this GPS run.
- Any new hardware run or proposed production replacement needs a separately
  notified session/plan, fresh parked/healthy confirmation and identity checks.
