# B2 launch hook unreachable — package defect, 2026-10-13

**Status:** runtime acceptance BLOCKED for the existing B2 packages. This
finding does not undo the operator-reported successful firmware flash or
prove the exact installed device filesystem. No new image or card writes were
performed during the recording-card read-back.

## Recording-card observation

Owner returned the recording card after the post-flash Wi-Fi checks. Host
identified `D: MINIEYE`, FAT32, 62,239,277,056 physical bytes, USB/MBR,
partition at offset 16,777,216. This is the recording card, NOT the 32 GB
`C2M_FLASH_B` preparation card. Reader serial alone does not identify the card.

Read-only inventory:

- Root: `.MINIEYE`, `Normal`, `Event`, `Photo`, `System Volume Information`.
- No `C2M_DIAG` directory or matching boot/idle/diagnostic paths.
- 24 nonzero normal MP4 files, total 6,249,512,960 bytes; latest modification
  `2026-10-13T20:09:56+07:00`. These are evidence of recording file creation,
  not video decode/content integrity or ADAS acceptance.
- Volume NOT dirty. No format, deletion, modifications or video/photo-content
  reads performed by the agent.

Private evidence:
`C2M_HW_20261012/03_candidate_B/recording_card_20261013_201634/inventory.json`.

## Exact shipped-package defect

Re-extracted `/wifi/rcInsDriver.sh` from the intended B2 reversion customer
payload. Hook SHA256:
`3ad36a60c7e0fd0c4f3fa03b5d592439db401df09ccc03a4c3ec17751d4d4fac`.
Local extraction output:
`build/b2-sd-v20261012000001/rcInsDriver_reversion.sh` and
`hook_extraction.json`.

Its final lines are:

```sh
exit $?
/customer/c2m/c2m-idle &
```

The unconditional `exit` is line 51; the appended background launch is line
52. Execution of this shell script exits before the added command. Presence
and integrity of `/c2m/c2m-idle` do not establish execution of that binary.

`tools/fw/mutate_customer.py` appends the hook line at EOF. Existing synthetic
mutation tests used a hook with no terminal `exit`, and checked append/payload
shape rather than execution through the actual stock control flow. A binary
self-test is not a launch-hook integration test.

The original B2 and the distinct-token reversion have byte-identical customer
payloads. Changing version metadata enabled a different upgrade identity but
could not fix this pre-existing startup defect. Source B1 shares the EOF
mutation method, but no independent B1 image extraction is asserted here.

## Diagnosis and limits

No logs alone could have been a mount-timing problem. The extracted package
now proves an earlier, definite blocker: its configured launch command is
unreachable on the normal executable-script path. Under the intended installed
package, that path cannot start the B2 daemon, even with a writable SD already
mounted. The device's process list and installed file bytes remain uncaptured.

Stock recorder/API/RTSP responses and recording-file metadata are observed;
full stock acceptance is still incomplete. The About cloud DNS toast remains
a separate app-side issue, not evidence for this startup defect.

## Next allowed work

Do not format, factory-reset, or repeat flashing the same package to seek logs.
No further power-on waiting can make the command after `exit` execute.

A separately authorized repair package must:

1. Place a failure-isolated, background launch on a reachable path BEFORE the
   terminal exit, preserving the stock exit status and original control flow.
2. Test actual script execution with a harmless fake daemon across Wi-Fi-off,
   device-present and device-timeout branches; prove no foreground wait,
   duplicate launch or dependency on network success. Include a regression
   demonstrating the old post-exit append is unreachable.
3. Re-extract and execution-test the rebuilt hook, not only test the daemon.
   Preserve all vendor files beyond the already authorized hook/custom daemon
   changes. Preserve frozen A/B1/B2 and prior artifact identities.
4. Use a fresh matching update token in both version sources, fresh MD5 and
   SHA256, and pass package/UBIFS/ELF/integration checks before a flash trial.
   Reusing `20261012000001` may be skipped by the equality gate after its save.
5. Separately address SD mount timing: B2 initializes its diagnostic stream
   only once. A corrected startup hook alone does not prove the card will be
   mounted at that instant; any retry change needs bounded, failure-safe tests.

No repair is prepared or flashed by this investigation. Current runtime
verdict: NOT_VERIFIED; shipped hook verdict: FAIL_UNREACHABLE; B2 acceptance:
BLOCKED, not PASS or FLASH-PROVEN.

## Repair status (2026-10-14)

Code fix implemented in `tools/fw/mutate_customer.py` + execution tests in
`tests/test_candidate_b.py` (see `CANDIDATE_B2_HOOK_REPAIR.md`). Firmware
rebuild via the Linux pipeline (fresh token, new hashes) is still pending;
no image built, no card written by the repair work.
