# Candidate D-TSR experimental build — 2026-10-14

**Status:** HOST-VALIDATED + SD READ-BACK 4/4 VERIFIED; READY FOR OWNER'S
MANUAL EXPERIMENTAL FLASH, not yet device-tested. Owner explicitly requested
an immediate D build/write for direct hardware testing. No automatic camera
update was performed. Frozen A/B1/B2 and installed-C source artifacts stay
unchanged. This is a configuration/warning-profile experiment, NOT proof of
new detector classes, better recognition, or operational TSR output.

## Exact delta from C

- Existing C literal TSR hook removed, replaced by synchronous invocation of
  `/customer/c2m/tsr_profile_boot.sh` before ADAS service startup. Stock hook
  exit status remains preserved; existing mount-wait idle launch retained.
- Added script applies these five statically known gflags (experimental):

  ```text
  --enable_tsr=true
  --tsrw_interval=5
  --tsrw_sli_over_min_ratio=10
  --tsrw_sli_over_min_thresh=5
  --tsrw_sli_host_speed_min_thresh=20
  ```

  Threshold choices are hypotheses from the proposed profile, not measured
  vendor-approved limits. Parsing validates shape/duplicates and explicitly
  inserts missing known keys; unrelated config lines must be byte-identical.
- Encoded `adas.flag` is the only live config file replaced: stage on the
  same filesystem, validate roundtrip/unchanged source, sync + rename.
  Stock unchanged `run.sh` reconciles `adas_de.flag` using its existing MD5
  comparison. This avoids treating two file renames as an atomic transaction.
- Before changing config, creates checked PRIVATE
  `/customer/minieye/config/.c2m-tsr-pre-d/` backup, kept on later boots.
  This is pre-D/post-C, NOT factory/pre-C recovery. Calibration/license and
  other factory flags are not changed. Missing tool/config, invalid base64,
  duplicate/ambiguous keys, incomplete backup or existing stage blocks patch;
  stock boot continues. All operations are bounded by small input size.
- Status copied after card mount to `C2M_DIAG/tsr-profile-D.txt`; contains
  status/version only, no raw config/identity/coordinate payload.
- All eight VI/TTS WAVs, audio list and md5 file unchanged from C. No greeting
  on each boot, per owner's earlier decision. Idle hash unchanged.
- No Warner executable, GPS serial reader, sign database, IPC audio injection,
  model/ADAS/cardv/kernel/rootfs/camera/bootloader/calibration changes.

## Safety and rollback limits

D can reapply the profile at each boot when values differ. An owner-created
`.c2m-tsr-disabled` marker in the config directory makes this D script skip;
no marker is created automatically and no shell access is assumed.
Disabling the script does NOT restore prior values. A config recovery needs
reviewed restoration of the private backup and a hook that cannot re-enable
TSR; C has its own re-enable hook. Flashing A/C alone does not guarantee
config rollback. Do not factory-reset calibration/license. If any regression
appears, stop testing and request a reviewed recovery package/method.

No field reliability claims. Run at a safe parked setup first. Do not exceed
speed limits, create dangerous FCW/LDW/PCW situations, operate an app/laptop
while driving, or rely on TSR instead of actual signs.

## Pipeline/provenance

- Source commit `ae74e12` (pipeline/profile/mutation/tests).
- `firmware-candidateD` run **38524203787** GREEN: host shell tests,
  independent EN/WAV SHA pins, no-op/mutated rebuild, idle ARM ELF,
  exact stock-rootfs QEMU and **6 tests with exact stock BusyBox applets**.
- Final CI customer report: no unexpected paths, all protected payloads
  unchanged. Vault deliverable:
  `deliverables/20261014-r38524203787/c2m-flash/C2M_FLASH_D/`.
- CI stock-token image SHA256
  `5a60de182c1d1504d589bd522df8c9c6a5631619a1460bceda77508619def308`.
- Local fail-closed token-only reversion: `20230803193750` →
  **`20261014000003`**, different from installed C `20261014000002`.
  Proof ALLOWLIST-OK, unchanged bytes outside token and derived MD5/sidecar.
- Final package deep validation **VALID, 33 checks**.
- Final payload re-extraction: profile matches source, legacy C patch absent,
  8/8 WAVs + idle/list/checksum exact C bytes. Semantic C→D customer diff:
  added only `/c2m/tsr_profile_boot.sh`, changed only `/wifi/rcInsDriver.sh`,
  removed none; existing type/mode/uid/gid unchanged. All 10 other load blobs
  byte-identical C→D (including kernel/rootfs/bootloader/oneed_cust).

## Exact on-card identities

| File | Bytes | SHA256 |
|---|---:|---|
| `SigmastarUpgradeSD_SSC8838G.bin` | 58,359,832 | `3e31d33e0a8f9308cf80d4fe0ec521fc0e06d66843c5edc3f3e254b69fefe968` |
| `sysVer.txt` (`sysVer 20261014000003`) | 26 | `a98d47e3f15e4743b2cf64bd1619db159612e863fe8112de66bafeab2d3cacc8` |
| `minieye_firmware.md5` | 66 | `7187ea0cb44ab17b5e8336f707dd49d78f9ffddbeebcbf801f1cf23bd9423b32` |
| `adas_upgrade.sh` (stock) | 2,972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |

TAR `EN_D_TSR_EXPERIMENT.tar`: SHA256
`fb137cf3108e7e2d15fa075ab255e94450d75dc7af7772d9e700db7789f97473`.
Profile script SHA256:
`4eae4a8eff40d4a4069a99c5bb75ed329f11fcd590a7fbf4ac1e273d90b6939b`.

Private evidence: `build/candidate-d/` and
`C2M_HW_20261012/05_candidate_D/` (before-card snapshot, local scripts).
Public evidence only source/contracts/hashes/test reports; no firmware bytes,
private backup/license/raw flags/audio assets/sign data published.

## Card deployment

D: existing 32 GB flash card (not the 59 GB MINIEYE recording card), FAT32,
`C2M_FLASH_B` label retained. Disk/partition verified before staging and again
before replacement; current on-card C hashes checked before overwrite.
Four files staged + flushed + readback, then replaced (sysVer last), final
4/4 byte-readback verified and volume cache flushed. Final NOT dirty,
Healthy. No format/chkdsk/log deletion. SVI + existing diagnostic directory
retained. User still must use safe eject and manual power-off/insert/power-on.

## Test D in this order (pending)

1. Flash with stable supply; wait for normal live view without interrupting
   update, decline unexpected format/reset prompts.
2. Validate recording/app/stock audio before road tests. No new startup voice
   is expected; absent per-boot greeting is not profile failure.
3. Use the recording card for at least 6 minutes. Read back
   `C2M_DIAG/tsr-profile-D.txt` plus START/HB and test clips. Status examples:
   `APPLIED_WAIT_STOCK_REDECODE`, `ALREADY_APPLIED`, or a specific BLOCK.
   These identify configuration application, not runtime inference.
4. Have a passenger observe app/M4, or use recordings, on normal lawful
   drives past actual speed signs. Record each actual value, displayed value,
   any warning, misses/false positives and latency. No output still requires
   separating detector/gate/display; no recognition improvement is assumed.
5. Height/weight/traffic-light outputs remain independent UNVERIFIED features.
   Do not test unsuitable clearance or overweight conditions.
6. Unexpected reboot, recording failure, missing normal ADAS warning or noisy
   distracting alerts: STOP, preserve logs/clips and request recovery review.
