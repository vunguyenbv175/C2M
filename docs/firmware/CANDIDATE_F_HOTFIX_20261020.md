# Candidate F hotfix — boot voice timeout + day/night transition monitor — 2026-10-20

## 1. Field finding

Owner flashed Candidate F token `20261019000001` on 2026-10-20. The camera
booted, ADAS was normal, but there was **no greeting and no light advisory**.
A read-only SSH session on the C2M AP (`192.168.1.1:2222`, key-only) found:

- all five F files under `/customer/c2m`, including `boot_voice.sh`;
- the launch line in `/customer/wifi/rcInsDriver.sh`;
- `/tmp/cardv_fifo` present and `cardv` running;
- `/tmp/c2m_voice_status` = `greeting=play-failed`.

Root cause: the C2M stock BusyBox is **v1.20.2**, whose timeout syntax is
`timeout [-t SECS] [-s SIG] PROG ARGS`. The old script used the coreutils-style
`timeout 5 sh -c ...`; BusyBox tried to execute `5` and returned
`timeout: can't execute '5'`. `_fifo_write` therefore failed before writing the
FIFO, so the greeting and both the boot and periodic advisories never played.
The host tests had not exercised the device BusyBox syntax (the source comment
matched the old `timeout 5` assertion).

## 2. Fix applied

- `_timeout_init` probes `timeout -t 1 true` (BusyBox) and `timeout 1 true`
  (coreutils), then `_timeout_run` uses the matching form. If `timeout` is
  absent, a background watchdog bounds the command.
- The boot hook now waits up to 30 s for the FIFO, retries the greeting 4 times
  and the advisory 3 times, and writes `tz`/`local` fields to the status.
- A detached monitor (`--monitor-only`, started with `setsid`/`nohup`) checks the
  local clock every **30 s**. On a dark/bright change it plays exactly one
  advisory and records it in `/tmp/c2m_light_monitor_status` and
  `/tmp/c2m_light_monitor.log`. The monitor is seeded with the boot state and
  does not repeat the boot advisory.
- The local schedule is the stock 06:00:01–17:59:59 window, but computed in
  **UTC+7 (Vietnam)** because this camera's shell clock runs in UTC. An optional
  `/customer/c2m/voice_tz_offset` file overrides the offset (`0` when the camera
  clock has already been set to local time; valid range -12..14).
- The optional `c2m-light` AE helper remains boot/manual-only; the periodic
  monitor never opens a second ISP client.
- No headlight output is switched. The wavs remain spoken reminders only.

## 3. Device hotfix

The installed file was replaced through SSH, with a backup:

- target: `/customer/c2m/boot_voice.sh` (mode 0755, uid/gid 1001)
- backup: `/customer/c2m/boot_voice.sh.pre-hotfix-20261020`
- old: 4,987 bytes, SHA256 `d38c778da4c10c5744346dddecb02acdfb5dfabf052f0fd022d5b0023a31afeb`
- new: 13,828 bytes, SHA256 `8743ad0baa84716d0459c9d3640f263cfa9216c08ad8345e7cd8dd77af2b67a0`

`sysVer`/token remains **`20261019000001`**. This is a file-level hotfix, not a
new flash package. The private-vault F deliverable and the tokenized local
package still contain the pre-hotfix `boot_voice.sh`; a clean reflash needs a
new token/package.

## 4. Evidence from the field test

Manual boot phase after the hotfix:

```text
greeting=played light=dark source=theme detail=schedule=06:00:01-17:59:59 tz=7 local=2026-10-21T05:07:21+0700 advisory=played
```

Monitor start:

```text
2026-10-21T05:07:25+0700 monitor=start seed=dark retry=0 tz=7 interval=30s
```

Transition tests used the optional offset file to move the local clock across
the boundaries without changing the system clock:

- offset `8` → local 06:08 → dark→bright:
  `monitor=transition state=bright advisory=played`;
- offset `7` → local 05:09 → bright→dark:
  `monitor=transition state=dark advisory=played`;
- offset file removed → default +7; no repeat at the same state.

The status proves the FIFO command was sent; the owner still needs to confirm
that the greeting and both advisories were audible. The C2M AP dropped during
the test (Wi-Fi moved to APIPA), then returned. The camera had rebooted; the
hotfixed script was still installed (`8743ad0b...`) and the real boot hook ran:

```text
greeting=played light=dark source=theme detail=schedule=06:00:01-17:59:59 tz=7 local=2026-10-21T05:10:08+0700 advisory=played
2026-10-21T05:10:11+0700 monitor=start seed=dark retry=0 tz=7 interval=30s
```

So boot-after-reboot is verified at FIFO/status level. The owner then confirmed
the actual audio: the boot greeting and the boot “Bật đèn xe” advisory were
audible after this reboot (2026-10-21 ~05:33 local). The periodic transition
audio is the remaining check.

## 5. Remaining acceptance

- Reboot with the hotfixed script: **PASS** at status level and **owner-confirmed
  audible** (one greeting and the boot “Bật đèn xe” advisory) at
  2026-10-21 ~05:33 local.
- While driving, confirm the 06:00:01 local dark→bright and 18:00:00 local
  bright→dark transitions each produce one advisory, no repeat. The 30 s
  transition behaviour was already exercised with the offset test; the real
  wall-clock transition audio is the remaining field check.
- Confirm ADAS/FCW/HMW, recording, AP/SSH and Vietnamese system audio remain
  normal. The recordings were intact after cleanup (Normal 260, Event 13,
  Photo 1, C2M_DIAG 11); the monitor uses the shared cardv audio FIFO, so real
  driving arbitration with ADAS warnings is still unmeasured.
- Card cleanup **done over SSH**: the stock updater had already removed
  `SigmastarUpgradeSD_SSC8838G.bin` and `sysVer.txt`; the remaining
  `adas_upgrade.sh` and `minieye_firmware.md5` were removed from `/mnt/mmc`.
  All four updater names are now absent; no recording/diagnostic file was
  touched. Evidence: `work/private-f-local-20261019/card_cleanup_report.json`
  (local, ignored by git). A later boot cannot re-run the pre-hotfix F package.
- Rollback package to E2 content is local: token `20261020000001`, at
  `work/private-f-local-20261019/rollback-e2-20261020000001/out/`; never stage it
  on the same card as F. It is host-byte proof only, not device-tested.
- If the monitor process dies, there is no separate respawn; a reboot restarts
  it. If that matters, add a supervisor in a later package.

## 6. Repo follow-up

`fw/voice/boot_voice.sh` and `tools/fw/test_bootvoice_gates.py` were updated so
future CI packages include the BusyBox timeout fix, the monitor, and the local
timezone default. The existing F CI run `39287717224` and vault deliverable
remain the pre-hotfix evidence; no new CI run is claimed for this hotfix yet.
