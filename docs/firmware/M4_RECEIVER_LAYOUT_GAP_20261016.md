# M4 receiver/layout gap after native V4 decode — 2026-10-16

## What changed today

The original V4 capture can now be decoded directly, without a private manual
HTTP-header removal step. This is OFFLINE workstation work only; no further
camera access, native program, replay, forced reconnect or update was performed.

- Bounded initial HTTP Upgrade parser:4096B headers,32 lines,1024B/line,
  CRLF/ASCII/duplicate/body/extension checks; no scanning inside unknown bytes.
- Contiguous segmented headers and following WS frames use the same TCP
  sequence/dedup/conflict rules. Pending HTTP across missing/truncated bytes
  stops; request/response pairing is exact reversed4-tuples only.
- RFC6455 key/accept matched privately; keys/headers/paths/host/accept values
  are never published. Passive framing match is NOT device authentication or
  proof that a display component supports the decoded message.
- `GPSSpeed` receive-only shape now reports allowlisted field names/types and
  stock type match. It remains `DENY`, never a transmit shape/ALLOW-L2 control.
- Two formerly unrecognized `ped` messages are `pedWarning`:
  exact dict fields `ped_on`, `pcw_on`, both bool. Static evidence already lists
  these protocol-semantic names (EN offsets `0x156c3c/0x156c48/0x156c50`, VI
  `0x156c24/0x156c30/0x156c38` in `EVIDENCE_ADAS_STRINGS.json` and high-confidence
  `adas.ped.pedWarning_path` in `EVIDENCE_STOCK_ADAS_SCHEMA.json`). Two complete
  native examples now corroborate that shape. No state values are published.
- Bool schema validation rejects int0/1/list/missing/extra fields. No numeric
  warning conversion; `normalize_adas.py` and its `is_danger` PCW driver remain
  untouched. `pedWarning` replay remains default-deny; L3 remains BLOCKED.

Direct decode of the hash-verified ORIGINAL stdout yields:

| Service | Native message | Complete count |
| --- | --- | --- |
|8080 |`GPSSpeed` |10 |
|24012 |`lane / laneWarningRes` |16 |
|26012 |`vehicle / vehicleWarning` |5 |
|26012 |`vehicle / vehicleMeasure` |4 |
|26012 |`ped / pedestrians` |2 |
|26012 |`ped / pedWarning` |2 |

**39 complete server application messages**,29 ADAS body schemas recognized,
10 receive-only GPSSpeed messages still semantic-DENY. All retained flow runs
have zero observed TCP gaps/conflicts/truncation;26012 request/101 match. A
masked client subscription is not a complete server outer+inner application
message and is not counted. Sparse received-packet numbering is not TCP loss.

Private follow-up reports are separate from the finalized22-file hardware
manifest: `C2M_HW_20261012/07_m4/m4_v4_offline_followup_20261016/`.
Original stdout SHA256 remains
`fda40b20f0942c50eb0cb70e9ebd8a1cc026ff88dfa6a005cfd815ac2d1fcabe`;
all22 original evidence files still verify. Existing source/binary/manifest
pins for ARM run38866208565 are historical and were NOT rewritten/rebuilt.

**The V4 unchanged26012 connection gate still FAILED.** Better offline decode
does not undo the reconnect, establish its cause or authorize another run.

## Implementation boundary: camera sender is not the M4 renderer

Existing EN/VI C2M assets contain camera-side `cardv` and ADAS ScreenService
senders. Local bounded inventory found no M4 receiver binary/source, M4 update
package,3D layout asset, M4 version string or verified speed-widget enable.
`rk312x` USB identification is not receiver source/version evidence.

`ScreenModeSet/theme` describes day/night, not a proven2D/3D/widget switch.
`SpeedStamp`/`SpeedUnit` belong to camera video OSD; no proof that these gate
owner's2D display or can add an independent3D widget. Qt strings in a camera
image do not identify M4's renderer. Additional GPSSpeed would duplicate a
native stream, not create a widget, and is still prohibited.

TSR schemas remain separate static/CollectService evidence, not a proven M4
sign slot. No sign frame in a short stationary sample proves neither support
nor absence. Do not turn a safety-distance/TTC/vehicle/ped slot into speed or
a traffic sign. Numeric legal limits are not vehicle speed.

## Public manual cross-check (not matching firmware proof)

Source retrieved over verified HTTPS on2026-10-16:
<https://spedal.cc/download/MINIEYE-C2M-024C3109-EN.pdf>

This is a public MINIEYE **C2M camera/monitor manual**, not an exact UTOUR M4
receiver firmware/version identifier. Footer identifies MINIEYE/Spedal and
`support@spedaltech.com`; local SHA256
`434a9a4a92fe867412c9e2db76eda6a8b014cc4b8c0c76cae6a16288c30c1191`.
18 PDF pages; metadata creation/modification2023-03-24 (metadata, not verified
release date). The file was read locally with a PDF text extractor; no manual
or firmware binary was added to the public repository.

- PDF page16, printed English-14, labels **3D road viewing** and
  **Safe Distance Index**. It defines the latter as a time factor in seconds,
  calculated using front-car distance and current vehicle speed. This supports
  the owner's distinction from a speed reading. It does NOT establish the
  native field, units/rounding/validity rules or exact TTC/headway mapping.
- Same page: “With the upgrade of AI algorithm functions, the display contents
  will be upgraded from time to time. Please refer to the actual product.”
- PDF page17, English-15, describes the top button switching3D to real-time
  view and status items (sound recording, phone connection, memory card, GPS).
  It does not document a speed-in3D or sign-icon enable. This is documentation,
  not a request for the owner to try new button/reset operations.
- Page18 explicitly says actual functions/pictures may differ and actual
  product prevails. Advertising/manual illustrations cannot establish this
  owner's receiver capabilities.

Public support search found no confirmed M4 receiver-specific firmware file or
safe official update procedure for this exact unit. App camera OTA is not
proof of an M4 update. No third-party APK/firmware or camera OTA is prescribed.

## Next actionable boundary

To implement a genuine3D speed/sign widget, obtain the **exact M4 receiver
software/update package and supported recovery/update procedure**, or an
explicit vendor-supported widget API for that variant. Prefer seller/vendor
support via existing purchase records; do not guess a firmware from camera
version or a look-alike product. Keep the working unit unchanged meanwhile.

There is no evidence-backed camera-only patch to deliver this3D feature yet.
This is a specific missing implementation artifact, not a need for another
capture of the same stream. D4 browser advisories remain a separately approved
feature, not a claimed substitute for M4 rendering.
