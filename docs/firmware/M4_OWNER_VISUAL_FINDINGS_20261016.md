# M4 owner photos and dynamic warning bar — 2026-10-16

## Sources and correction

Owner supplied four images in the conversation: the first two show the owner's
physical M4, the last two are advertising illustrations. They are not native
protocol captures or M4 firmware/version evidence. No camera connection or
hardware command was used to review them; images are not copied into the public
repository.

After the initial photo comparison, owner explicitly clarified:

> nó có thanh phía trên, hiện khi có cảnh báo, giờ chủ yếu chỉ thấy giây đếm ngược va chạm

Meaning: the top bar appears with warnings; the owner mainly sees a
collision-related seconds/countdown value there.

**Correction:** the empty upper part of the owner's photographed3D scene is
one transient UI state, NOT proof of a missing top toolbar, unsupported warning
UI, truncated framebuffer or a different renderer build. The previous initial
assistant interpretation that the whole top bar was absent is withdrawn.
Owner confirms a working conditional warning bar; no deliberately induced
collision warning or moving-vehicle test is requested to demonstrate it.

## Observed versus reported

| Evidence | Supported observation | Not established |
| --- | --- | --- |
| Owner image1,2D | Live road video, black upper status strip with icons | Which component draws each icon; exact image speed digits/units; M4 firmware version |
| Owner image2,3D | Own-car graphic and forward blue region on light background; no warning bar visible in this snapshot | Permanent lack of a bar, lack of all live ADAS data, renderer ownership or missing pixels |
| Owner later clarification | Top bar appears for warnings; owner mainly sees collision-related seconds/countdown | Exact native field, units/rounding/validity mapping, or whether it is formally TTC versus another warning metric |
| Owner historical2D/3D report |2D shows vehicle speed; owner has never seen vehicle speed or a sign in3D | A speed/sign widget disabled in settings versus absent support, missing input or another conditional display policy |
| Advertising images3–4 | Illustrations have orange bars, vehicle/pedestrian/lane-like symbols, numeral `0.5`, and circular40/60 badges | Current owner's model/version supports those elements, live recognition, native field mappings, units, event lifetime or actual operating footage |
| Later annotated advertising image5 plus owner explanation | `0.5` is labelled “Chỉ số khoảng cách an toàn”; owner identifies collision-related seconds, not vehicle speed | Native TTC versus headway mapping; vehicle-speed support in3D or real sign display |

Owner subsequently supplied a fifth, annotated advertising illustration.
Its arrow explicitly labels the `0.5` field **“Chỉ số khoảng cách an toàn”**
(safe-distance indicator). Owner states this is the collision countdown in
seconds, not vehicle speed. This establishes the advertised UI role as a
safety/following-distance warning value; do not retain vehicle speed as an
alternative interpretation of that numeral.

The image/owner explanation does not yet map the field to native `ttc`,
`headway` or another scalar, including exact units/rounding/validity/lifetime.
Time-to-collision and time headway are different quantities; do not equate
these internal fields merely from a marketing label. This protocol distinction
does not reopen the resolved question of whether `0.5` denotes vehicle speed.

The annotated illustration does not demonstrate a vehicle-speed widget in3D.
Circular40/60 badge artwork in the earlier advertisements remains separate:
it is a reason to investigate intended sign/limit display, not evidence of
working TSR on this unit, an installed widget or a supported injection command.

## Separate feature questions

1. **Conditional stock warning bar:** owner-reported present/working; preserve
   existing vehicle/lane/pedestrian warnings and their presentation.
2. **Vehicle speed in3D:** still not observed. Existing stock outbound
   `GPSSpeed` and the separate camera OSD path do not prove a3D speed widget.
3. **Traffic sign/limit in3D:** never observed by owner. No verified native
   display schema/receiver/widget/enable control has been found. Never reuse
   the collision countdown, vehicle speed or another warning slot for a limit.
4. **D4 offline advisories:** browser-only experimental nearby-area path;
   a finite GPS shadow is not M4 delivery, camera TSR or legal-speed evidence.

The working dynamic bar narrows the investigation: the display is not simply
missing all upper UI, but its warning behavior does not prove support for
persistent speed or sign-specific rendering. A single clean own-car screenshot
also cannot prove successful ADAS object inference or a failed data link.

Local source/document review still found no verified3D speed/sign enable
control, matching M4 renderer/layout assets or M4 update package. Existing
`ScreenModeSet/theme` describes day/night, not a proved2D/3D/widget switch.
These are limits of the recovered material, not proof of hardware incapability
or that changing M4 firmware is necessary. No production code was changed.

## Physical control and missing identity evidence

Owner clarified that the M4 has **one button on top**, used to switch between
the two screen types (2D live video and3D ADAS). No settings/version menu is
reported. Stop requesting a version page that the owner has no known way to
access. M4 firmware/software version remains UNKNOWN, not inferred from camera
firmware, advertising or exterior shape. The normal physical toggle is proven
by owner use; its internal message/renderer implementation is still unverified.

Do not try guessed long-press/double-press/hidden-menu sequences, reset, remove
the screen or alter calibration to obtain identity information. No assumption
that the button enables speed/sign widgets or maps to `ScreenModeSet/theme`.

Continue the offline investigation with the exact camera firmware, known
sender paths and available documentation. An original advertising product
link/claimed model or an already-visible label would be optional corroborating
identity evidence, not a prerequisite requiring hardware manipulation. Camera
firmware version alone is not necessarily the M4 renderer version.

A photo/video of the bar when it occurs naturally can later help distinguish
warning values from speed/sign output, but do not create a hazard or ask the
driver to photograph it while moving. Such media still would not prove the
native protocol field without additional evidence.

Continue offline with `M4_SPEED_FIELD_FINDINGS_20261015.md` and
`M4_SIGN_DISPLAY_FINDINGS_20261015.md`. No camera session is opened by this
clarification. Still prohibited: second cardv `:8080` observer with M4 attached,
guessed CGI/layout switches, semantic/warning injection, UART/FIFO writes,
display-plane changes or unverified M4 firmware replacement.
