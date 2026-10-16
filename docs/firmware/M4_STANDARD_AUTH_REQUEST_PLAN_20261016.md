# M4 standard owner authorization request — 2026-10-16

## Approved next scope, not a fake-sign sender

Owner requested proceeding after the one-CNXN probe proved an AUTH responder.
When asked specifically about a dedicated laptop key and one standard public-key
approval request, owner gave broad permission to proceed. That does not require
bypassing authentication or relaxing preservation of recorder/AP/ADAS.

The earlier probe's native-connection gate remains FAILED; see
`M4_ADB_AUTH_STOP_HARDWARE_20261016.md`. A new attempt requires a fresh healthy
baseline, all three native legs established, sufficient existing finite SSH
window and owner at the screen. No forced reconnect/reset/flash or hidden menu.

One NEW standard ADB request can test whether normal owner authorization exists:

1. New dedicated RSA2048 key generated on the owner WORKSTATION only. Private
   file stays outside repository and camera. Android public encoding is
   independently checked (524B struct, modulus/inverse/RR/exponent65537,
   canonical base64). No private bytes logged, bundled or uploaded.
2. New `c2m-m4-authorize` gets only the711B public payload in stdin from a
   bounded private RAM file. No key compiled into ELF/public CI. Bundle/source/
   manifest/binary sizes+hashes checked before execution.
3. Fixed USB1-1 VID2207/PID0013, interface2 ff/42/01, bulk04/85 max512;
   read cached USB descriptors, claim/release ONLY interface2. RNDIS0/1 left
   bound, no USB reset/mode/driver change or additional application client.
4. Exactly one CNXN (24+7) then, ONLY on valid AUTH TOKEN, one
   AUTH RSAPUBLICKEY type3 (24+711). With zero pre-existing trusted keys it is
   standard to offer the public key directly. No signature/key guessing or
   bypass. Maximum4 OUT calls/766 bytes,4 IN calls,35s internal window and
   one30s reply wait after offering key, no retry loop.
5. If an authorization dialog is visible, owner may choose one-time Allow;
   do not select Always Allow. The actual M4 may have no such UI or may handle
   authorization differently; one-time/nonpersistent authorization is NOT
   guaranteed by the packet. If no UI/response, stop without changing settings.
6. Only a validated device CNXN after the public-key request counts as
   `authorization_granted`. AUTH again means not granted, even with exit0.
   Timeout means no response, not no ADB/no widget support. An early CNXN also
   does not establish acceptance of the new key.
7. NO service/shell OPEN, app installation, file readback, UI modification,
   fabricated sign/speed, calibration/config/audio/model/firmware change in
   this scope, even if authorization succeeds. No CLSE on a nonexistent service.

ADB dialog fingerprint is MD5 of the decoded public struct (a UI identifier,
not a security hash). Expected fingerprint and public-payload checksum are
retained privately outside the repo; compare the fingerprint locally if a
prompt appears. Never accept a different key prompt.

## Completed outcome and input correction

Final source `141cbc60cd09935e7eb488bd4d0ab7de25611792`, ARM run38889073536
PASS; one request executed at17:56,766B TX,33.271s native elapsed, no response,
no authorization, interface released and RAM cleanup verified. All three native
connections and recorder/AP/process/hash checks passed in snapshots; owner
reported normal and no dialog. No retry. See `M4_STANDARD_AUTH_HARDWARE_20261016.md`.

Owner then explicitly reconfirmed only ONE button and NO touch input. The
Android-style tap-Allow instruction above was an unverified UI assumption,
not a supported operation on this M4. Do not repeat it or invent button/input
sequences. No supported authorization selection method is established.

Owner briefly reported the GPS icon unlit in2D, then said GPS returned before
any requested GPS read-only diagnosis was executed. That transient has no
established cause; no ADB/GPS/config/restart follow-up was performed. Native
GPS continuity or ADB causation cannot be inferred from the icon alone.

## Gates and preservation

Portable public-key/frame validation + actual source fake-USB success/failure
state-machine tests, pure ARM self-test, stock-QEMU missing-USB/sentinel/actual
import gates are mandatory. QEMU missing USB is NOT hardware acceptance.
Private publication only, with public allowlisted safe logs/hash manifests.

Runner stages exact packed binary+public payload to private camera tmpfs,
checks hashes, splits local RAM files, runs self-test, executes once with
external45s timeout, removes all named RAM files and verifies directory absent.
No private key needs to exist on camera. Stdin is a finite regular RAM file
with EOF, not a potentially stalled interactive key feeder. Source imports
permit read/open/ioctl for this bounded device path, not general networking or
file creation/writers.

Pre/post checks must preserve AP, real advancing recording metadata, stock
cardv/ADAS/D4 PIDs and installed producer/DB hashes, as well as all three native
M4 connections. Any difference is a failed gate and stops further access;
owner-visible normal behavior does not waive it. No automatic listener
restart/extension or retry. A requested VI flash remains a separate conditional
experiment assessed in `M4_EN_VI_RENDER_TEST_ASSESSMENT_20261016.md`.
