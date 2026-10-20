# D4 offline area-sign advisory + C2M voice — 2026-10-20

Status: **field hotfix deployed, host/synthetic audio passed, real-sign drive
and owner audible confirmation pending.** No reflash, no token change, no
stock camera/kernel/ADAS/cardv/model/audio change.

## 1. Field finding: D4 `no_database`

The installed D4 producer was alive and the private DB was correct:

```text
pid 882  /customer/c2m/c2m-signs --serve
DB       /customer/c2m/signs-d4.bin
size     1,270,812 bytes
sha256   3bcf871956c61484858bef783187319fa5f9ae0da0c214c2c14afb1d62de411c
api      http://192.168.1.1:8099/api/signs
state    no_database
```

The DB was not being loaded because the checked-path guard in
`fw/d4/main.c` accepted `/customer` only as `0755 1001:1001` (or VI
`0755 1000:1000`), while this stock EN customer UBIFS root is
**`0775 1001:1001`**. `checked_parent()` therefore failed before the DB loader.
The existing D3 path evidence already documents the 0775 stock EN customer
root; the D4 guard had not been aligned with it.

Source fix (`4cfb891`): accept the exact stock EN `/customer` tuple
`0775 1001:1001`; do not chmod the stock path and do not reinterpret a speed
limit. `tests/test_d4_stock_paths.py` now accepts 0775 for the exact EN tuple
and still rejects `1000:1000 0775`, generic uid-1000/1001 writable ancestry and
non-directories.

CI: `firmware-candidateD4` run
[39458556091](https://github.com/vunguyenbv175/C2M/actions/runs/39458556091)
completed green, including the D4 stock-ABI/QEMU and host DB/advisory/web
gates. The private release is in the owner vault:
`deliverables/20261020-d4-r39458556091/`. Only the binary was extracted; the
full D4 package was not flashed and its stock token is irrelevant to the
installed F image.

Installed binary:

```text
sha256 f4adeb01262ae35fc8b2060de48166900df0fa4bcf9e367b5b5577f75bd173e6
size   22,868
backup /customer/c2m/c2m-signs.pre-hotfix-20261020
old    sha256 545efc7be2e1efd52539cf118946abee59dc5f914f26685fee7d59e37786888d
```

`./c2m-signs --self-test` on the camera before installation: `OK`.

After restart the same API returned `state=waiting_gps`, not `no_database`, so
the DB had loaded. At the parked/indoor test point the GPS was not fresh
(`gps_fresh=0`), so `ready`/active was not yet available; this is a GPS
acquisition condition, not a DB failure. The D4 producer stays inactive when
GPS is stale/stopped.

## 2. C2M speaker sign voice

The owner selected the **C2M speaker** (not ESP32) for the first voice test.
The D4 producer itself still has no playback code. A separate, detached bridge
`/customer/c2m/sign_voice.sh` consumes only the fixed, sanitized
`/tmp/c2m_d4_status` file:

- one play per new `event_id`;
- only `state=ready`, `gps_fresh=1`, `active=1`, valid `event_id > 0`;
- `code=residential_start` → `Sign_Residential_Start.wav`;
- `code=residential_end` → `Sign_Residential_End.wav`;
- status file must be ≤3 s old; inactive/stale/no-DB never latches a warning;
- one monitor instance via a `/tmp` lock; signal traps remove the lock and exit;
- FIFO command `audioplay 0 dev0 <absolute wav>`; flag 0 is the waiting form,
  chosen so a sign reminder does not cut stock ADAS audio. It can be delayed
  behind current playback; there is no verified atomic priority broker. This
  is advisory-only, not a safety or legal sign confirmation.
- no network, GPS reader, UART, CAN, ISP/AE or vehicle control in the bridge.

Installed hashes:

```text
sign_voice.sh                 896dfa536a447b0c6444964b912d59849027a9a8478d72f9e4683816d3e3f114
d4_boot.sh (sign launch)      3bdefbec673b4fbfb8cd58fff2a725f494d8ef8f9950f997fd3f8d1d7917a69f
old d4_boot.sh backup         05964911bf05dc35f2dcec5d4efe5ea4d13c525a62b9961d3d6bfedae769c0a7
Sign_Residential_Start.wav    35aa6930e0b95f0be66d4763ca8fd0f31ef93f9c6fba837aeb1d3b71dfd8b460
Sign_Residential_End.wav      f61a1b17be0caa4f79767e5dc9cde07adcfd6074bb3cab02e6153933080c22f6
```

The two WAVs are private owner assets: Vietnamese `vi-VN-HoaiMyNeural`, PCM16,
mono, 24 kHz; speech is “Sắp tới khu vực đông dân cư” and “Sắp hết khu vực
đông dân cư”. The bytes are stored in the private vault, not this public tree.

`d4_boot.sh` now launches the separate bridge only if the regular script is
present/readable; a missing bridge does not affect D4. The stock boot hook is
unchanged. Existing boot greeting/light monitor continues independently.

Synthetic trigger evidence on the camera:

```text
2026-10-20T23:51:41+0000 event=1 code=residential_start advisory=played
```

That timestamp proves the bridge parsed a fixed test snapshot and wrote the
FIFO command; it is **not** proof of audible output. The owner must confirm the
speaker output. If flag 0 is not audible in the field, do not silently switch
to flag 1: flag 1 can cut the shared ADAS decoder and needs explicit risk
acceptance and a new test.

The current monitor is one process and exposes `/tmp/c2m_sign_voice_status`
plus `/tmp/c2m_sign_voice.log`. A real D4 event while moving is still pending.

## 3. TSR / speed-limit boundary

The owner correctly recalled that the TSR profile is present. Current evidence:

```text
/customer/c2m/tsr_profile_boot.sh
/tmp/c2m_tsr_status.txt = TSR_PROFILE v=D2 status=ALREADY_APPLIED
adas process running with the stock flag files
```

The stock ADAS TSR engine/model path is therefore configured, but runtime
recognition/display/event output has **not** been captured or verified. D4 is a
GPS/private-area-DB producer, not a camera TSR consumer. Its status explicitly
keeps `speed_kmh=0`; the D4 DB contains only 12,708 directional R.420/R.421
(area start/end) records and deliberately excludes the 15,343 P.127 speed-limit
points with unknown application heading.

Therefore this deployment does **not** provide a speed-limit voice warning.
A speed-limit feature needs a separate phase: capture/prove the stock TSR
output, or build and validate a camera model/data path. It must not be inferred
from R.420 or from the GPS DB.

## 4. ESP32 contract for the later display

The existing AP-only API is ready for an ESP32 client on the C2M AP:

```http
GET http://192.168.1.1:8099/api/signs
```

```json
{"version":1,"source":"gps_offline","status_available":true,
 "state":"waiting_gps","gps_fresh":false,"active":false,"sequence":62,
 "code":"none","speed_kmh":0,"distance_m":0,"event_id":0,
 "monotonic_ms":4791710,"expires_in_ms":2346}
```

`code` is `none|residential_start|residential_end`; the ESP32 should map it to
its own icon/text and use a changed `event_id` for its own voice. It must treat
`active=false`, stale `expires_in_ms`, `gps_fresh=false` or non-`ready` states
as no warning. No coordinates or DB free text are exposed.

## 5. Remaining field checks

1. Owner confirms the C2M speaker played “Sắp tới khu vực đông dân cư” during
   the synthetic test, or reports no/quiet/delayed audio.
2. Drive with a GPS fix; confirm `/api/signs` reaches `ready` and a real
   R.420/R.421 event plays once and does not repeat on the 5 s hold.
3. Confirm stock ADAS/FCW/HMW, recording, AP/SSH and model audio remain
   normal while the sign monitor runs. The sign bridge is idle unless a new D4
   active event arrives.
4. If audio is not audible with flag 0, decide explicitly whether flag 1
   (preempting stock audio) is acceptable; do not change it silently.
