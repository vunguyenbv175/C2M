# M4 visible active-test boundary — 2026-10-16

## Correction to the earlier conclusion

The owner is right: no active display-value trial has been performed. Native
GPSSpeed packets on the USB link do NOT establish whether M4 would draw a
value under a controlled different condition. “No widget command found” is
not “M4 cannot render speed/signs”. Firmware replacement is NOT demonstrated
to be required. Exact receiver software is one investigation route, not the
only possible route before any harmless test.

No previous CI, payload decode or owner confirmation is an active test result.
In particular V4 mode was not timestamp-confirmed as3D; do not use it as a
simultaneous3D-versus-speed observation. The26012 reconnect verdict remains
FAILED, cause unknown; no silent retry or gate relaxation.

## A useful visible trial, without a dangerous semantic substitution

First candidate: one **small nonzero brightness change**, then restore the
actual observed initial value. Alternative: existing day/night display theme,
only if stock value range and control path are verified. Both are known stock
info classes; neither is a speed/sign widget test. They can establish a
controlled camera→M4 visible effect while3D stays active, nothing more.

The test must use a proven stock setter that causes the EXISTING cardv server
to write to its native M4 client. A new WebSocket client to camera8080 cannot
deliver to M4 and can steal/clear its single global client pointer. Do not use
that, guessed control CGIs, raw TCP injection, fd/memory hooks or process stop.
Do not fake storage/recording/ADAS/calibration state for a visible icon.

Before execution:

1. Prove exact setter, accepted types/range, affected config/persistence and
   any recorder/ADAS/reboot side effects from exact stock evidence.
2. Verify original readback and stock restoration path. If persistent, obtain
   explicit approval for that exact setting and compare restored value/health.
   Do not describe it as RAM-only or promise automatic rollback without proof.
3. Fresh owner stationarity/normal-functions/3D confirmation and separately
   notified current camera session; no reuse of old SSH/IP/window evidence.
4. Finite one-change/one-restore, no black-screen value, no replay loop, no
   calibration/EN/model/audio/license/recorder/AP/D4 changes. Stop on health or
   link difference; report actual outcome including restoration failures.
5. Owner reports whether brightness/theme visibly changed and restored.
   If unchanged, possibilities include overwritten value, wrong channel,
   ignored setter/value or unsupported display behavior; NOT proof of no3D
   speed/sign support.

No verified implementation of this setter is claimed by this plan. Do not run
until the exact evidence and bounded restoration procedure are reviewed.

## A second route found in ALREADY saved USB evidence

`m4_passive_20261016_111525/usb_func.stdout` contains interface `1-1:1.2`:
class/subclass/protocol `ff/42/01`,2 endpoints. Those descriptors match the
standard Android Debug Bridge interface signature. RNDIS uses the separate
`.0/.1` interfaces. This was missed in the earlier receiver-artifact inventory.

This is an **ADB-signature interface observed**, not a working/authorized ADB
session, shell, root access, device version or recovery/update mechanism.
No ADB handshake/command has been sent. Do not infer bootloader/loader mode
from `rk312x/2207:0013`; do not switch USB mode, detach RNDIS, guess credentials,
bypass authorization or install an updater. An explicitly approved finite
identification-only session could assess a supported receiver-readback path
later; it must stop on authorization/health/interface conflict, not modify UI.

## Native setter investigation, exact binary and scripts (offline)

EN cardv SHA256
`344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c`
contains exported Thumb `WSSetBacklightLevel(int)` at VA `0x6fe71` (136B),
which clamps integer brightness to1..10 before emitting `DispBrightSet`.
`SendBacklightLevelInfoToScreen` is VA `0x83391`; display-mode sender VA
`0x83425`, setter VA `0x83405`, `ScreenDisplayMode` object VA `0x3123a8`.
These prove sender behavior, NOT a callable independent control on the native
M4 connection. No runtime function call/memory modification was attempted.

Three camera web files were extracted OFFLINE from the existing customer
image and matched golden manifest hashes (no vendor script was executed):

- `CGI_PROCESS.sh` SHA256 `b43a404b6ec6e0c772e9b4e74cb23a431e293cb9c9809580d6aed8d6537f39c2`.
- `CGI_COMMAND.txt` SHA256 `9c9a7dc7b05e6b30df1a89c32bc43203dcbaa9aeede71330d6272a2b39ef8f2e`.
- `cammenu.xml` SHA256 `d3145a6740cd6a5d76147adaa3f41dd99c8ce6dac22c00541c4a6bc1809c682a`.

They expose camera `Brightness`/`BKlight` controls with a different0..100
domain and persistent `nvconf` updates. Exact case/mapping and whether this
changes recorded-image ISP vs M4 backlight are unresolved. A CGI example's
128/255 does not agree with that script clamp. Thus do NOT issue that setter
as a “harmless M4 brightness” trial; it could change the camera image/config.
Fixture brightness7 is now within a proven sender clamp but still does not
supply the safe invocation/restore route. No guessed FIFO/CGI call is justified.

## Approved new read-only and handshake route

A newly approved16:10 sysfs-only session reconfirmed `.2` number2 ff/42/01
and independent bulk endpoints04/85,512B. No USB transaction/claim/native
upload occurred; required connections/D4 PID unchanged, recorder advanced.
Owner explicitly approved preparing/gating then ONE active ADB identification
handshake (no AUTH reply/key/shell/UI), separately notified immediately before
execution. See `M4_ADB_IDENTIFICATION_PLAN_20261016.md`. This offers a possible
receiver evidence route, not proven access or a speed/sign test result.

## What is still blocked

Additional GPSSpeed sender, fabricated speed/limit, collision/lane/ped warning
injection, repurposed seconds/TTC and arbitrary extended UI remain unverified.
Do not claim a harmless brightness/theme test resolves those safety gates.
The practical immediate task is verify the native stock visible setter, not
repeat the same payload capture or require vendor firmware as a foregone fact.
