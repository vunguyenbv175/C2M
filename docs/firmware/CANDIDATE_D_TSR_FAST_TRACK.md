# Candidate D-TSR — fast track after C / muse.ai inputs (2026-10-14)

**Plan status: direct experiment now built at owner's explicit request.**
See `CANDIDATE_D2_TSR_LF_FIX_20261014.md`: corrected D2 profile is
host-validated and SD read-back verified, manual device flash pending. The
first D token was superseded after a final-LF preservation review. This does
NOT prove TSR recognition/output. Owner prioritizes sign/TSR over a diagnostic-only
release; experiment permission supersedes the earlier no-build gate, not
byte/backup/stock-preservation verification rules. Current installed package is C, token
`20261014000002` (owner-reported flash).

## 1. Inputs accepted

- `56eca24`: four static TSR/EN-VI/GPS reports and `fw/warner` prototype.
- `dfae204`: Lily/Waze APK reports + Lily database converter.
- Private owner-provided root `signs_vn.bin`: 2,855,112 B, 28,551 records,
  SHA256 `7b3fdf9fd13107acd51bdd3a1c814da301672fb482cd32790d371ccd2b4a3bf5`.
  Explicitly ignored, not committed/published. Extraction/access is not proof
  of license to redistribute, freshness or road-level accuracy.
- C evidence already on laptop: newer START/HB + scoped decode of 8 clips;
  owner confirmed the observed power cycle was deliberate.
- Owner has not yet driven through signs to test C TSR; cam cannot be turned
  on for live capture now. Do not turn this into a claim of C failure.

## 2. Route with the shortest path to a real feature

### A — Camera TSR: retain EN detector and fix only demonstrated gaps

Stock EN has actual TSR functions and output fields; VI does not add a
proved detector/class capability. Keep EN `adas`, `cardv`, model blobs,
rootfs/kernel/media/calibration/license unchanged, preserve C Vietnamese
wav assets and the accepted no-boot-greeting behavior.

C already attempts `enable_tsr=true`. Therefore a new enable-only image is
NOT a demonstrated recognition upgrade. D must deliver something C has not
proved: controlled flag application + valid detection output + user-visible
warning/display for at least a tested class. Threshold tuning alone changes
warning behavior, not detector accuracy or sign coverage.

Static observation leads:
- `AdasCollectService`, `collect_export_port=25012`, static default bind
  `collect_export_addr=127.0.0.1` (loopback; runtime override/path/output still
  unverified); TSR topic `tsr`, keys `tsr_trace_res_list`, `tsr_warning`.
  No external response at 25012 is expected if this default remains; it is
  NOT proof that TSR failed. Do not invent `enable_collect_service`: no such
  flag was found. D experiment does not expose new listening interfaces.
- `AdasScreenService`, static port 26012; actual production WebSocket path,
  source and TSR distribution to it still unverified.
- Libflow envelope/subscription exists in `tools/m4/libflow_protocol.py`.
  Static TSR names are recognized but schema/units remain unverified; no
  semantic injection is authorized. Host-only `tools/m4/capture_tsr_readonly.py`
  now enforces identity-first, bounded capture and sends only the stock TSR
  subscribe frame; its runtime result is still UNVERIFIED.
- Stock shell contains `audioplay 1 dev0 <absolute WAV path>` to cardv FIFO.
  This is stronger static evidence than internal function `play_wav_cmd`.
  It still does NOT prove safe arbitration with stock safety warnings during
  recording, or authorize device FIFO writes for probing.

### B — GPS DB advisory: reuse data only where direction is evidenced

Host validation of `signs_vn.bin`:

| Type | Total | Known application heading |
|---|---:|---:|
| R.420 (populated-area begin) | 6278 | 6278 |
| R.421 (populated-area end) | 6430 | 6430 |
| P.127 (speed limit) | 15343 | **0** |
| P.125 / P.130 / P.131a | 500 | **0** |

Four headings of 360 normalize to 0. UTF-8/coordinate ranges and exact record
length pass. Unusual speed values (37/87/89/49/51) are flagged for review,
not rounded or announced as correct limits.

A private directional review subset has 12,708 R.420/R.421 records,
1,270,812 B, SHA256
`491622fdfaab6d00bdc9553e17fa062429cf8b5193c77d27985fe896688fe2d5`.
It is staged under ignored `build/`, not deployed. Heading meaning `u`,
accuracy/update date and same-road matching still need validation. R.420
alone does not establish a numeric legal limit (vehicle/road/rules differ).

Do NOT enable all 15,343 speed pins using proximity alone: parallel roads,
opposite direction and junctions can produce confidently wrong warnings.
The fastest GPS feature would be advisory “approaching populated area/end”
for a validated route, AFTER a non-consuming live GPS source and output
backend are proved. Camera TSR remains the speed-limit path for now.

## 3. Changes completed on host (not firmware deployment)

- CI Linux hook fixture chmod/PATH errors fixed; no product gate was waived.
- Host `tools/fw/tsr_profile.py`: strict base64, existing-key-only changes,
  duplicate/ambiguous TSR rejection, unchanged unrelated bytes, staged pair
  with hash-only report. No cam write/network/automatic restore.
- `fw/warner`: explicit regular-file HOST/REPLAY; no ttyS1/S2 or default live
  input; bounded log/EOF handling; parser rejects missing checksums, shifted
  empty fields, NaN/Inf and malformed coordinates/time/course.
- DB loader rejects incomplete/extra/invalid records, count bounded 40,000;
  builders read SQLite read-only, sort deterministically, truncate UTF-8
  safely and write atomically. Matcher prefilters geography, rejects stopped/
  invalid fixes, suppresses unknown heading and selects nearest across set.
- Native guards + generator tests + deterministic replay added to CI.
  Main is intentionally not a device daemon. Cooldown currently records
  replay selection, not successful delivery; live output needs own policy.

Tests on host: original Warner unit, hostile-input C guards, Python DB guards,
TSR staging guards, existing candidate tests pass. CI `38517508521` on
`e677116` succeeds. Neither CI nor QEMU alone proves camera/GPS/M4 behavior.

## 4. Execution order — do not flash for something C can already show

### Step 1: C stock TSR observation, no settings changes

When owner can power the stationary cam and connect the laptop:
1. Verify AP/route + actual device UUID using the previously verified GET;
   do not probe home router 192.168.1.1 or guess auth.
2. Bound connection/subscription only to statically evidenced stock services.
   Production path/bind/availability are UNKNOWN until handshake/capture.
3. Subscribe TSR without injecting data. Capture finite duration/size privately.
   A zero result on a stationary scene is NOT a detection failure.
4. Drive observation uses passenger/recordings or a previously configured
   read-only logger; driver never operates laptop/app. Test actual safe road
   signs with known value and label output/hit/miss/false-positive/latency.
5. If C already has valid native sign warning/display, no D is required merely
   to re-enable it. D's delta should fix a demonstrated issue only.

If external collector is unavailable, static GPS/UI IPC reader and local TSR
subscriber can be researched on host; do not guess struct offsets, bind ports
or install a serial consumer to get data quickly.

Prepared capture command (DO NOT execute until stationary cam, correct AP and
owner authorization are confirmed; no credential guessing):

```powershell
python tools/m4/capture_tsr_readonly.py --expected-uuid <owner-confirmed-UUID> `
  --stationary-authorized --port 25012 --seconds 15 `
  --out build/tsr-live-private-first
```

The script verifies the known CGI UUID before connecting WS; it does not open
UART/FIFO or set settings. No frames while stationary is not detection FAIL.
A service/path connection failure remains BLOCKED rather than trying random
ports, URL paths or credentials.

### Step 2: reviewed flags/recovery for a D candidate

- Capture permitted private actual flag snapshot; do not infer it from binary
  fallback values. Backup now is post-C, never call it pre-C.
- C hook re-enables false every boot. Any disable/rollback must account for
  the running hook BEFORE changing flags; firmware rollback and config
  rollback are separate.
- D initially preserves stock detector/thresholds; no blind “5 km/h/10%/5 s”
  tuning. Those values are a hypothesis in muse.ai's design, not measured.
- Deploy policy requires owner authorization for persistent config; absent,
  duplicate or corrupt keys fail closed. Atomic per-file replacement alone
  does not make an encoded/decoded two-file update transactional.
- A profile can be built/tested now. Deployment is blocked until the stock
  load precedence, recovery and permission are verified. No license/calib
  reset, no blind insertion/rewriting of unrelated flags.

### Step 3: one proved user-visible output

- First reuse native stock output if it works; otherwise develop ONE adapter
  (prefer short Vietnamese audio) from actual captured TSR event semantics.
- Fixed event-to-WAV mapping, not database free-text to shell commands.
- Limit repeats/bursts, require fresh result/validated limit, keep native
  FCW/PCW/LDW priority. No arbitrary FIFO strings or M4 semantic injection.
- GPS source: safe fan-out or verified read-only UI IPC snapshot, never read
  UART concurrently with cardv. Settings such as GpsDisp/Edog are not lat/lon.
- Stock Edog has a real switch (`Camera.Menu.Edog`, FIFO `edog 1`) in static
  CGI evidence, but `/edogs` is NOT proved a local DB path; missing audio/data
  contracts mean enabling it is not a deployment plan.

### Step 4: package only the functional slice that passed

Build from EN golden + pinned C audio + reviewed feature delta. Narrow
manifest allowlist; rootfs/ADAS/model/kernel unchanged. Private assets only,
ARM ABI/loader + exact-stock QEMU for new binary, no-op/mutated rebuild,
deep validation, re-extraction, fresh token (different from installed C),
SD identity/read-back and owner-approved flash. Stock updater is destructive
full-flash even when only customer bytes change; do not dispatch for log-only
features labeled “TSR upgraded”.

## 5. Fast-track acceptance and current blockers

**Feature PASS requires**: tested real sign recognized/validated, correct
user-visible output, defined behavior on missing/stale result, repeats limited,
recording/audio unaffected; results documented per class. No claim of all VN
signs or safety-grade accuracy. A silent logger is prototype/partial, not PASS.

**Current blockers** (not solved by changing token or packing binaries):
- Cam not available now for permissible live TSR/output capture.
- Effective factory flags + load precedence/recovery not observed.
- Output arbitration, units/enums and screen-supported fields unverified.
- Non-consuming live GPS position/course contract not yet verified.
- Speed-sign DB application headings absent; rights/freshness need review.

Continue offline tests/adapters/reverse while these are blocked; next physical
step is bounded read-only inspection of C, NOT another mandatory diagnostic
flash. This avoids a wasted flash and preserves the owner's working recorder.
