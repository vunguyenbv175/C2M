# M4 standard authorization: no response, no owner dialog — 2026-10-16

## Outcome

One owner-approved standard public-key request was executed after fresh parked,
healthy/M43D confirmation, start notice and exact-source/bundle readback.
**Authorization was NOT granted.** Owner saw no authorization dialog and
reported M4/app/recording/ADAS still normal. No retry or further camera access.

Owner then clarified explicitly: M4 has **one physical button and NO touch
input**. The button's known purpose is2D/3D switching; no authorization UI or
button mapping is known. Instructions to tap Allow/Always Allow assumed an
Android-style UI that was NOT established on this unit. That assumption is
withdrawn; do not request long/hidden presses, reset, or external input injection.

An ADB responder can require authentication without exposing a usable
Android authorization dialog. This is a possibility, not a diagnosis of the
installed daemon/framework. Lack of a dialog here does not establish absent
ADB support, permanent inability to authorize, or unsupported sign/speed UI.

## Exact prepared artifact

- Source `141cbc60cd09935e7eb488bd4d0ab7de25611792`.
- ARM workflow `38889073536`: PASS. Linux source success/failure USB shim,
  public-key/frame tests, owner public encoding tests, ARM pure self-test,
  ELF/ABI, stock-QEMU missing-USB/sentinel/actual-import gates passed.
- Earlier run38888788562 stopped on Linux synthetic-test indentation warning;
  fixed without relaxing `-Werror`. No target attempt used that failed build.
- ELF16216B SHA256
  `f8cdecaf95221d26c955b45040a68512a868c39af397a708ee65442620449813`.
- Manifest2185B SHA256
  `e1c310e9a6f901725d83c94260e9d6a5410142a45956910751552b3468168dab`.
- Private vault `ecba02e544b173ede5df83328afdd4fcf59f7e05`.
- Dedicated RSA private key remained on owner workstation, never uploaded.
  Only a validated711B public key was offered; no key bytes are public here.

## Actual hardware lifecycle

Private session:
`C2M_HW_20261012/07_m4/m4_adb_authorize_20261016_175637/`.

| Measurement | Observed |
| --- | --- |
| Native status / outcome |`authorization_no_response` /`no_response` |
| Public-key request fully sent |1 |
| Outgoing USB bytes / calls |766 /4 (CNXN24+7, AUTH public key24+711) |
| Incoming calls |3 (AUTH header/token received, subsequent header timed out) |
| Native elapsed |33271ms |
| Interface2 claimed / released |1 /1 |
| Native exit |1, expected no-response failure, NOT authorization success |
| Exact RAM cleanup |verified in lifecycle and postflight |
| Owner-observed authorization dialog |none |
| Owner original-function report |normal |

No signature, private key, service/shell OPEN, app installation, UI/sign/speed
injection, firmware flash, reset or explicit settings write was sent. Offering
a public key does NOT prove it was stored or authorized. Retention on M4 was
not inspected and is UNKNOWN; do not promise nonpersistence from this timeout.

## Preservation in snapshots

Preflight uptime133.63; postflight173.03. All three native8080/24012/26012
connections retained the same peer ports. Stock cardv/ADAS/wrapper/D4 process
checks, installed D4/DB hashes, recording status1 with actual advancing segment
metadata and AP activity passed. No media content/fabricated recorder markers.
These snapshots plus owner confirmation do not prove uninterrupted rendering
throughout the interval. They do NOT erase prior V4/ADB-identify failed
connection gates or establish the cause of those earlier differences.

## Private evidence

Raw lifecycle stdout236B SHA256
`4bd4711578c8b5205b692bd8146abc2f3c5ad47ad32ba12f13a920e3b9e8475c`.
Final18-file private manifest SHA256
`d7b5a6f7c84da7141adbc704edee1bdb2618838e62bc131a263e879ab98281a0`.
Readback passed. Raw payloads, public/private key bytes and vendor assets stay
private. The original manifest is finalized, not rewritten for this later
physical-input clarification.

## Later transient GPS icon report (no diagnostic execution)

After the request, owner reported the GPS icon was unlit in M4's2D view and
approved a read-only check. Laptop AP IPv4 was rediscovered and a local-only
regular-record diagnostic script was prepared, but **not executed**: owner
reported GPS had returned before any camera SSH/file-read/upload/UART/ADB
follow-up. No reset/config/flash was performed. Record this as a transient
owner-visible icon report with recovery, cause UNKNOWN; not proof of GNSS
hardware failure, continuous loss of camera fix, an ADB side effect or a verified
repair. Previous postflight preservation snapshots do not cover that interval.

## Consequence

No authenticated receiver readback or fake-sign render test occurred. Do not
repeat the same dialog wait, assume a button can approve it, bypass AUTH or
flash VI to obtain an imagined M4 dialog. Further work must establish an
actual supported authorization/receiver path from evidence. EN/VI camera
comparison alone does not identify the M4 receiver or prove a sign widget.
