# D4 offline GPS area-sign advisory — implementation scope — 2026-10-15

## Owner decision and current status

Owner reports D3 works and explicitly requested D4 offline sign warnings.
After explaining that stock playback can interrupt/delay ADAS, owner chose
**web display + optional phone/browser beep**. Camera-speaker and M4 output
are not part of this authorized MVP. Do not represent browser output as
camera audio or camera TSR. This is source implementation, not a deployed
or hardware-accepted D4 release.

D3 first boot/card feedback: private read-only recording-card capture at
`C2M_HW_20261012/06_candidate_D4/recording_card_20261015_132007/` found
`TSR_PROFILE v=D2 status=ALREADY_APPLIED`, `boot.seq=17`, one retained session
with heartbeat through uptime7507 (~2h05m), and another through uptime2408.
These show profile/daemon liveness, not sign recognition or exact NAND image
identity. Card Healthy/NOT Dirty. Mounted MINIEYE physical size63,281,561,600,
partition1 offset0, Windows partition FAT16 but mounted FAT32; no repair.

Laptop Wi-Fi initially had no camera profile and IPv4 APIPA169.254/16;
Ethernet supplied Internet. Do not query the home gateway as if it were the
camera or change network/credentials to bypass this. Live camera GPS
advancement remains unverified until the authorized AP/UUID is reachable.

## Actual feature architecture

```text
stock cardv owns GPS/UART and recording (unchanged)
  -> read-only /tmp/car_info snapshot at offset0x330, bytes0x1c0
  -> existing strict decoder + advancing-UTC/monotonic freshness gate
  -> dedicated low-priority c2m-signs process + private offline area-sign DB
  -> fixed sanitized /tmp/c2m_d4_status snapshot, no coordinates/labels
  -> native AP-only :8099 /api/signs and /signs dashboard
  -> foreground phone browser visual advisory; explicit local short beep
```

No phone GPS, Internet, CDN, remote TTS or external audio is needed. The page
must remain foreground. Phone lock/background, mute/volume/audio routing and
browser autoplay limits can stop output; do not promise autonomous background
warnings. The phone beep can distract acoustically even though stock camera
ADAS output is untouched. Set up while parked; no driver interaction in motion.

## Private database and eligibility

Owner-private source SHA256:
`7b3fdf9fd13107acd51bdd3a1c814da301672fb482cd32790d371ccd2b4a3bf5`.
The source and all derivatives remain ignored/private. Possession does not
prove redistribution rights, freshness, lane/road association or legal limits.

The D4 subset is exactly 12,708 directional area-sign records:

- 6,278 R.420 (begin built-up/residential area).
- 6,430 R.421 (end built-up/residential area).
- No numeric speed-limit records; no current speed-limit or overspeed state.

Subset size1,270,812 bytes; SHA256
`3bcf871956c61484858bef783187319fa5f9ae0da0c214c2c14afb1d62de411c`.
Prepared using `fw/d4/prepare_database.py`, requiring the exact source pin.
Four headings360 normalize to0; unknown application heading remains excluded.
The 15,343 P.127 source pins all lack application heading and are NOT treated
as applying in both directions. Do not infer a numeric50km/h from R.420.

Application-heading and same-road semantics are not field-validated. Output
is visibly labelled **nearby GPS/offline advisory, not lane/direction/legal
speed confirmation**. Conservative bearing/heading filters do not replace
road matching and do not prove applicability on parallel roads/junctions.

## Producer and freshness boundaries

- Separate native process, no `cardv`/`adas` process control, UART reads,
  SysV/libflow/FIFO/M4 audio/display injection or direct MI_AO.
- Descriptor-checked regular private package DB loaded once, bounded40000
  records/4MB; symlink/unsafe owner/mode/path rejected. Replacement invalidates
  the loaded DB rather than silently hot-reloading it.
- GPS reader already validates RMC/fix/signal/calendar/DDMM/finite bounds,
  matching double reads, two advancing UTC-second observations and monotonic
  freshness. Repeated seconds do not refresh; no mtime freshness shortcuts.
- Select one nearest eligible R.420/R.421 only while moving>=5km/h, lookahead
  8seconds/radius150..600m, bearing tolerance30degrees/application45degrees.
- Stable event ID/short hold<=8seconds, per-sign cooldown120seconds committed
  only after successful status publication. GPS invalid/stale/stopped,
  passed/out-of-corridor/disabled/noDB clears active event immediately.
- One atomic private tmp snapshot per second, no per-fix media logging.
  Publisher loss is expired by HTTP/browser within3seconds.
- Status schema uses exact enums and bounded integers; never exposes precise
  coordinates, DB free text, credentials, record payloads or arbitrary errors.

## Why no camera-speaker shortcut

EN static playback review proves the known `audioplay 1 ...` stock command
can stop the current shared audio decoder. Stock ADAS uses that decoder but
its warning priorities are internal to its own producer, not enforced by the
foreign FIFO path. A flag0 alternative waits for playback and may delay ADAS;
checking quiet externally has a race. No verified atomic low-priority broker
or reliable warning-busy API exists. Do not loosen this boundary in D4.

## Build/release acceptance

Preserve current D3.1 Wi-Fi protections, no-auto-connect behavior, C Vietnamese
WAV/list/checksum/greeting semantics, D2 TSR profile, idle/recording/app, all
core/model/calibration/license/kernel/rootfs/bootloader loads.

Manual private-only workflow: `firmware-candidateD4.yml`. Required build
outputs `c2m-signs` and `d4_boot.sh`; exact private DB installed in customer
under a fixed `/c2m` path. No writes to MINIEYE recording card for firmware.

Owner additionally requested Bluetooth investigation at the next flash because
no board photos/documents are available. The next D4 build must include the
reviewed `C2M_D3_PASSIVE_BLUETOOTH_V2` boot probe (bounded SDIO/driver/transport
context, unchanged no-RF/no-UART-access behavior), not merely the earlier V1
probe. This remains a passive capability investigation, not working Bluetooth
or a reason for a standalone diagnostic flash. See
`BLUETOOTH_CAPABILITY_FINDINGS_20261015.md` for acceptance and limitations.

Promotion requires host pure/hostile-input/lifecycle tests, exact stock ARM
loader/glibc/QEMU executable proof, actual Chrome renderer/beep scheduling/
expiry and full synthetic GPS->producer->HTTP->browser route tests; mutation
allowlist/noop rebuild/deep checks and final payload extraction. Host proof
is not live GPS or audible phone delivery proof. Reserve a fresh local token
`20261015000001` only after source/build pins and final extraction pass.

Before saying field-ready: authorized live advancing GPS reaches ready; known
real route/sign shows intended advisories; GPS/API/publisher loss clears;
phone audio observed after gesture; official app/recording/ADAS remain intact.
No hazardous driving induction and no relying on advisory for safety.
