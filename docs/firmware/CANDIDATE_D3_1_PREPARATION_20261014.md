# Candidate D3.1 — verified corrective flash-card preparation — 2026-10-14

**HOST-VALIDATED + UPDATER CARD READ-BACK 4/4 VERIFIED; MANUAL D3.1 CAMERA
FLASH PENDING.** Original D3 was owner-flashed with token `20261014000005`.
Corrective source commit `32bea6f` adds controller fixes to browser-policy
correction `51e905a`. General CI run `38595722292` passed. Manual private
firmware pipeline run `38595723994` also passed all gates: ARM/ABI/QEMU,
13 connectivity tests, 15 web tests, two real Chrome tests, seven controller
tests, two mutation tests, and GPS tests (one non-Linux-only skip).
Private retrieval, local reversion to the fresh token, deep 33-check VALID,
and final extraction passed. At 23:20 +07:00, the positively reidentified
32GB updater card was staged/read-back verified, cache-flushed and rehashed
4/4. No format, marker synthesis or agent camera flash.

## Narrow corrective scope

- `Referrer-Policy: same-origin` fixes the confirmed Chromium HTTP-form
  `Origin: null` rejection, without accepting null/foreign origins.
- Exact Host/Origin/CSRF/AP/subnet validation is retained. Real Chrome
  loopback native-form and opaque-origin-negative tests are mandatory.
- Controller failed AP observations are unknown, with specific query/name/
  type/frequency causes; no hardware-absence claim from failed observation.
- Missing/malformed/unusable combination proof stays blocked. `no` requires
  complete valid evidence lacking adequate AP+managed capacity.
- Bounded startup capability observations only: maximum 30 total attempts,
  at least two seconds between attempt starts; stop upon conclusive evidence,
  config/request intent, association-owned artifacts or operation/failure.
- Explicit user connect can rediscover nl80211 after initial discovery failure.
- Web allowlist displays the new fixed controller errors, never arbitrary
  strings or credentials.

This fixes a usable UI failure and incorrect/transient controller reporting.
It does **not** prove same-channel radio association, add DHCP/routes/Internet,
fix card format acceptance, or deploy new TSR/GPS warning functionality.

Preserve C Vietnamese audio/stock greeting semantics, original D2 TSR script
and bounds, idle/boot integration, stock app/AP, recorder, core firmware,
models, calibration/license, and vendor updater. No marker spoofing, UART,
FIFO/M4 injection, stock Wi-Fi exclusive switch, or radio activation.

## Verified corrective token and payload

Locally reverted **`20261014000006`** identifies the prepared corrective
candidate. CI retains the stock token; never stage raw CI members or mix
tokens/hashes. Do not reuse `20261014000005` for this update.

- Final inner image: 60,264,472 bytes, SHA256
  `07fd7756baaa172341de8337085807722d48e33df912a237c701800639e4bf33`.
- Final TAR SHA256:
  `d00647df44a6e047e27184faf53905814ed945c27b2900f8be6a12a31338c56e`.
- `sysVer.txt` SHA256:
  `616d3c6058dd2035801d37cd0701c97c2d138db96422a3c9d27689fd4f9632f8`.
- MD5 sidecar SHA256:
  `1a021142293c6598008bf14cf97c829b8c3eb23f8c4460199fbeabee303f7bfa`.
- Stock updater SHA256 unchanged:
  `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b`.
- Version-only reversion verdict `ALLOWLIST-OK`; TAR deep verdict `VALID`,
  all 33 checks passed. Final extraction matches exact CI service hashes.
- Semantic delta versus original D3: **only** `/c2m/c2m-web` and
  `/c2m/c2m-wifi` changed, no added/removed paths, all existing metadata
  unchanged. Boot hook, TSR script/bounds, passive BT script, supplicant,
  idle, Vietnamese audio/list/checksum and ten noncustomer loads unchanged.

Private final files/reports: `build/candidate-d3-1-final/`.
Private raw vault path:
`deliverables/20261014-r38595723994/c2m-flash/C2M_FLASH_D3/` is **not** the
locally reverted flash payload. Retrieval used binary `git show`, no checkout,
reset or modification to existing private-vault staged work.

## Card safety

A later read-only inventory reidentified the connected media as the original
32GB updater: USB SM3350 disk1 MBR, 33,201,061,888 bytes, FAT32 partition1 at
1,048,576 of size33,200,013,312, label `C2M_FLASH_B`, Healthy/NOT Dirty.
Before replacement, all four on-card original D3 hashes matched prepared
`20261014000005`; original files were privately backed up and verified.
After replacement, all four D3.1 files match exact bytes and hashes of the
verified final payload. `sysVer.txt` was renamed last, cache flushed and
4/4 members reread/rehashed. Card remains Healthy/NOT Dirty. Existing
directory-only trial and diagnostics are preserved. The root has no recorder
`.MINIEYE` marker; the owner reports original D3 still asked to format.
D3.1 does not claim to change that behavior.

On-card report:
`build/candidate-d3-1-final/on_card_d3_1_verification.json`, verdict
`READY_FOR_MANUAL_D3_1_FLASH_NOT_DEVICE_TESTED`.
Private original-card backup:
`C2M_HW_20261012/05_candidate_D/d3_1_card_stage_20261014_231957/`.

Do not infer that drive `D:` always identifies this card. Reidentify before
any later write. Never put updater payload on the MINIEYE recording card by
accident, format either card, fabricate markers or remove logs/video.

## Completed and pending gates

Completed: private build all-green; ARM/glibc/QEMU; Linux/controller parsers
and Chrome; customer rebuild; deep validation; exact changed-service checks;
fresh-token version-only reversion; deterministic TAR; deep 33-check VALID;
final extraction; and updater-card staging/read-back.

Pending only: owner manual flash and real native-form/AP/controller/recording
checks. After flash, verify live view, recording, Vietnamese ADAS audio and
reboot first. Then open the native page at `http://192.168.1.1:8099/`; the
form should no longer produce `origin_or_host_rejected`. Check status before
entering any upstream credentials. If the page still reports unknown, collect
the exact named `last_error`; do not force STA mode or accept a format prompt.

The prepared D3.1 package still does not add DHCP/routes/Internet, Bluetooth
RF testing, sign recognition, GPS warning arbitration or a TSR guard change.

The previously observed `INPUT_SIZE_BLOCK` has no live `adas.flag` byte count
or hash; do not enlarge its guard or imply TSR recognition now works.
