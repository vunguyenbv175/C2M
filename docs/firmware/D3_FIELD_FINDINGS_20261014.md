# D3 first field read-back and browser form failure — 2026-10-14

## Scope and status

Owner reports manual D3 flash, native Wi-Fi form returning
`{"ok":false,"error":"origin_or_host_rejected"}`, and a continuing format
prompt on the 32GB updater/recording trial card. Owner switched to a MINIEYE
recording card, then attached that card to the laptop for read-back. No agent
flash, card format, filesystem repair, credential saving, Wi-Fi association,
UART access, radio scan, or camera reconfiguration was performed here.

The laptop connection profile was the expected camera AP. Requests were bound
to the laptop's camera-facing IPv4 and gated on the authorized stock camera
UUID before querying D3. Stock CGI and native D3 page/status were reachable;
this is runtime evidence for isolated D3 services, not a complete flash-memory
identity check. The stock firmware-version API still returns the unchanged EN
product version, not the locally prepared updater token.

## Confirmed browser bug

The real flashed camera returns:

```http
Referrer-Policy: no-referrer
```

An isolated Chrome instance loaded the native page at its canonical IPv4 and
port `8099`. A native form POST to a deliberately **nonexistent** D3 API route
(no state-changing handler) generated:

```http
Host: <verified camera AP IPv4>:8099
Origin: null
```

The camera returned `403 origin_or_host_rejected`, exactly reproducing the
owner's error. The page origin itself was the correct `http://<AP IPv4>:8099`.
A separate direct request with a canonical Origin/current CSRF and no saved
Wi-Fi config reached `409 no_safe_config` without queuing a request. Thus the
Host/Origin rejection is separate from credential validity or STA capability.

A second isolated Chrome test changed only that browser page's referrer
policy to `same-origin` using a DOM meta tag (no camera change). The identical
nonexistent-route form then generated the canonical Origin and reached
`404 not_found` instead of the Host/Origin rejection. This provides an A/B
browser reproduction of the source correction; it is not a saved-credential
or association test.

**Source correction:** change the response policy to `same-origin`. Do not
accept `Origin: null` or remove exact Host/Origin, CSRF, subnet, or AP validation.
`same-origin` still suppresses referrers to different origins. The correction
is not installed on the camera by a repository edit.

Private local HTTP/browser evidence (tokens redacted):

- `build/d3-field-live/live_get_capture.json`
- `build/d3-field-live/browser_origin_probe.json`
- `build/d3-field-live/browser_origin_same_origin_override.json`

## AP+STA remains unproven

The real native status response contained:

```json
{
  "ap_active": true,
  "config_saved": false,
  "connect_pending": false,
  "controller_status_available": true,
  "sta_supported": "no",
  "sta_state": "unsupported",
  "last_error": "ap_not_verified",
  "bt_presence": "not_seen"
}
```

This means the controller's **initial** nl80211 AP check failed; it is not proof
that the hardware lacks concurrent AP+STA. D3's web service independently sees
an active AP using wireless/IPv4 ioctls. The original controller groups query
failure, unexpected name/type, and missing AP frequency under one error, then
labels them unsupported. It also does not automatically retry this initial
probe as AP startup settles. Missing frequency, a startup race, or a
query/parser/driver mismatch are possibilities, not established causes.

No upstream credentials were used, and no concurrent association was tested.
The existing association-only/DHCP-missing release limit still applies.

## Passive Bluetooth result

The D3 card log is complete and reports:

```text
verdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE
radio_test=NOT_PERFORMED
state_changes=NONE
```

No kernel HCI, Bluetooth rfkill entry, named device-tree node within the probe
bounds, or inspected Bluetooth userspace tools were observed. **Do not state
that the physical camera definitely has no Bluetooth.** The result is kernel
exposure only; no RF activation, scan, pairing, module load or UART attach.

## Recording-card read-back

Current card identity differs from the earlier recording-card inventories:
USB SM3350, physical size **63,281,561,600 bytes**, partition1 offset **0**,
full-disk size. Windows describes the partition as FAT16/MbrType4 while the
mounted filesystem is **FAT32**, label **MINIEYE**, Healthy/NOT Dirty. This
metadata discrepancy was recorded, not repaired; do not substitute the older
62,239,277,056-byte / 16-MiB-offset identity.

Read-only inventory found:

- Root `.MINIEYE` and three ordinary zero-byte `.sstar.format` markers.
- **168 Normal MP4 and 8 Event MP4**; one photo inspected by metadata only.
- All **176 MP4 containers** opened with a metadata-only PyAV/libav fallback
  (`ffprobe` unavailable). No frame decoding, playback or private media copy.
- Newest eight container headers: 3840x2160 HEVC main stream, 640x360 H.264
  secondary stream, approximately 30 fps and AAC.
- **22 consecutive Normal files** beginning at 21:34:27 through 21:55:25,
  approximately 21m29s summed declared duration, align with D3 diagnostic
  timestamps starting at 21:34:26. Strong chronological support for recording
  in the owner-reported D3 session, not decoded-media or ADAS proof.
- `boot.seq=13`; matching rotating slot has START `marker=ok` at uptime7 and
  heartbeats through uptime1207: approximately 1,200 seconds logger liveness.
- Eleven copied diagnostic files rehashed **11/11 equal**; file inventory and
  card identity stable. No card writes, reset, formatting, or repair.

Private capture:
`C2M_HW_20261012/05_candidate_D/d3_field_20261014_221127/card/`.
FAT timestamps, rotating slots and the unverified camera clock limit chronology.
The card was in the laptop during the live API queries, so the camera's
`SD STATUS=2` / zero-capacity response must not be classified as a recording
failure.

## TSR profile is blocked

Current card status is:

```text
TSR_PROFILE v=D2 status=INPUT_SIZE_BLOCK
```

D3 deliberately retained the D2 profile script/version. This status means the
current boot's profile application stopped at its encoded input-size guard;
it is **not** `APPLIED_WAIT_STOCK_REDECODE` and not detector/sign-warning proof.
No runtime config was read or patched in this capture. Previous persistent
flags may still exist; the blocked status alone neither confirms nor reverses
them. Determine the actual input state read-only before changing the guard.

## Same-card format trial result

Owner reports the 32GB updater card **still requested format** after D3 flash.
The directory-only trial did not solve acceptance. Adding more ordinary
folders or flashing the same payload again is not justified by this result.
No fabricated root/DCF markers or format-complete metadata were created.
Keep the working recording card intact while investigating a separately
verified, owner-authorized initialization approach.
