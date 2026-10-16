# M4 ADB-signature identification — one ACTIVE handshake, not rendering — 2026-10-16

## Owner-approved scope

After correcting the unsupported “needs firmware” conclusion, owner confirmed
stationary/healthy camera with M4 in3D and approved a new READ-ONLY path check.
Session `m4_active_path_readonly_20261016_161043` read only sysfs/proc/tool names:

- Current `1-1` is USB2207:0013, bus1/dev2 at that timestamp.
- `.0/.1` RNDIS stays bound to `rndis_host`.
- `.2` number2 is `ff/42/01`,2 BULK endpoints OUT04/IN85, max packet512.
- No `adb`/`adbd` executable found by `command -v`; no existing adb process
  established (the `ps|grep` line matched its own shell text, not an adb daemon).
- No upload/native execution, USB claim/handshake, application client, config
  writer or display change. Recorder metadata advanced; required8080/26012
  connections and D4 PID unchanged. AP and original asset hashes checked.

Private15-file read-only evidence manifest SHA256:
`0bdbc7b4d429239421d1a0ef63e4f352a84186b30d491426a4953dd0c3457071`.
No payload/banner/credentials are published.

Owner subsequently explicitly approved **one finite ADB handshake** after
verification and start notification: response identification/authentication
status ONLY, no shell/app/key/firmware/UI change. The approval is not permission
for an ADB shell if a connection is accepted, nor proof of receiver support.

## Bounded native implementation to gate before hardware

New `fw/m4_adb/m4_adb_identify.c`, separately named binary `c2m-m4-adb`:

- ACTIVE, not passive observer: one standard `CNXN` request31 bytes total,
  header24 + payload7 as separate USB bulk transfers (AOSP USB transport writes
  header/data separately), no retry. At most2 OUT and2 IN transfers.
- Request old protocol version0x01000000, max payload4096, `host::` identity;
  no secret, AUTH signature/public key, A_OPEN/service/shell or secondary command.
- Read and validate exact current sysfs VID/PID/bus/dev; read USB descriptors
  before claim, require exact interface2 ff/42/01 and two expected bulk endpoints.
  Claim/release ONLY interface2; no USB reset/configuration/driver detach,
  RNDIS/application socket manipulation or network probe.
- CLOCK_MONOTONIC5s bound and each bulk call bounded by remaining time;
  external target timeout. Release claimed interface and close on exit/signal.
- Validate reply magic/length/checksum; classify only CNXN or AUTH challenge;
  payload/banner/auth token never printed. AUTH -> stop without response.
- No files created by executable, no settings/app/UI/flash writes. Runner may
  stage exact-size/hash executable in private RAM directory, then exact cleanup.

Public implementation reference:
<https://android.googlesource.com/platform/system/core/+/android-6.0.1_r81/adb/transport_usb.cpp>
(`remote_write` separates header/payload). This is protocol reference, not the
M4 installed source or guarantee its daemon accepts our CNXN.

## Gates

Portable pure descriptor/request/reply tests (malformed/oversize/checksum/
wrong endpoint/direction/identity), bounded successful I/O synthetic tests where
possible, ARM ABI + pure self-test + pinned stock-QEMU no-USB/sentinel/import
checks, exact private bundle/source/manifest pins. CI QEMU is explicitly not a
successful real USB path test. Never run host/QEMU `--probe` with USB1-1 present.

Fresh target window/identity/healthy current native M4 legs must pass again
IMMEDIATELY before native execution; old16:10 health is not evidence of later
window. No SSH restart/extension, no automatic retry if upload/handshake/health
fails. Notify before actual hardware handshake; if window expired, stop.

## Completed hardware outcome

Final source `95283f206765133417c00e7b24e67db0d2f5f09e`, ARM run38881250082
passed. One native request at16:59 returned AUTH-required in7ms;31B TX,
interface2 released, exit0/RAM cleanup verified, no key/AUTH reply/shell/UI.
**Connection gate FAILED:**24012/26012 were not established after, while8080,
recorder/AP/processes remained healthy in snapshots and owner reported M4
normal. No retry/follow-up camera access. See
`M4_ADB_AUTH_STOP_HARDWARE_20261016.md` for exact pins/evidence.

Owner later approved a NEW standard public-key authorization request, not an
extension of that exhausted identification-only scope; see
`M4_STANDARD_AUTH_REQUEST_PLAN_20261016.md`. No bypass or sign injection.

## Interpretation and next approval

- CNXN: daemon accepted initial ADB link; not root/shell/readback/render proof.
- AUTH: authorization required; stop, do not send keys/bypass security.
- Timeout/malformed: inconclusive; do not conclude no ADB, no widget or no M4
  support. No broad scans, repeated tries or USB mode changes.
- Any native M4 link/recorder/AP/ADAS difference: stop and retain failed gate;
  do not silently downgrade failure to an expected reconnect.

No speed/sign/ADAS warning injection is authorized by this handshake. A later
read-only receiver inventory or harmless visible change requires its own
explicit scope and evidence. Existing V4 connection gate remains FAILED.
