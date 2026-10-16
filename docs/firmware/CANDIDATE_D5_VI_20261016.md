# Candidate D5-VI — full Vietnamese firmware base, 2026-10-16

## Owner request and corrected assumptions

Owner requests a flash package based on the Vietnamese firmware, containing all
D4 features, removing the first20-minute SSH limitation, plus useful additions.
This authorizes package preparation, not a camera connection or flashing now.

Owner clarified that previous apparent VI ADAS failure could have been settings
unfamiliarity. **VI ADAS is unverified, not diagnosed incompatible or broken.**
Earlier EN-golden/VI-regression analysis is historical and cannot settle this.
Keep existing calibration/license/settings; do not force activation/recalibration.

## Exact intended composition

| Component | D5 behavior |
| --- | --- |
| Vendor base | Full `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`,58122240B SHA256 `f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa` |
| Kernel/cardv/ADAS/libraries/models | VI stock, not an EN/VI hybrid; protected VI cardv/ADAS pins and non-customer partition identity independently checked |
| Existing C/D/D3/D4 | Eight selected VI WAVs including prior green-light WAV, minimal idle, checked TSR profile, AP-only web/connectivity gates, isolated GPS/offline signs producer and same private directional12708-point DB |
| SSH | Dropbear2026.94, same owner Ed25519 key, AP-only192.168.1.1:2222/wlan0, **no20-minute listener deadline** (`window_sec=0,lifetime=boot`) |
| SSH safety retained | No password/forwarding, persistent private hostkey reused, child-owned listener verification, AP-loss stops own listener, no autorestart loop; idle sessions still600s |
| GPS correction | Current decoder accepts raw fraction0..999 and still requires advancing UTC seconds/freshness; no UART reader, no GPS writer |
| New health command | `/bin/sh /customer/c2m/health.sh --snapshot`, on-demand only, reads existing small statuses and `/proc`; reports counts/three native links without coordinates/keys/config/media content |
| Release provenance | Separate D5-VI name, pinned input/source/tool/test/hash evidence, locally prepared distinct update token only after CI readback |

The health command's recording flag is NOT proof of segment growth, GPS fix,
ADAS quality or uninterrupted delivery. It never starts a WS client or reads
raw GPS/USB/UART. No boot health loop or new SD diagnostic writes are added.

All D4 constraints remain: browser beep opt-in/default off, no camera-speaker
advisories, experimental nearby GPS-area points not legal limits/camera TSR,
AP preserved/no auto-STA, no Bluetooth capability bypass, no M4 sign injection,
no ADB authorization retries at boot, no warning-slot repurposing or fake speed.

“Full VI base” deliberately replaces vendor EN core with VI on a later flash;
it does not claim EN core preservation. The exact VI core is preserved **within
this package**. Device-specific calibration/license/configuration remain the
vendor updater's preserved data, not data copied from generic VI defaults.
The stock updater is full firmware, not a customer-only flasher.

## Offline evidence

VI cardv1225780B SHA256
`56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23`;
VI ADAS11653870B SHA256
`997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1`.
Validator defaults remain EN; explicit VI profile selects independent hardcoded
VI pins. A candidate cannot provide arbitrary hashes to bless itself.

Bounded offline symbol/Capstone review of exact cardv binaries reconfirmed VI
`WriteGpsInfoForCardvUI` (Thumb VA0x8578D,112B) copies0x1C0 to carInfo+0x330,
file writer length0x1C8. Core RMC/time/info conversions retain the same field
contract and raw1–3-digit fraction; VI NMEA/screen dispatch still differs.
This supports decoder layout reuse, not live fix or rendering acceptance.

Offline VI rootfs runtime files matched all four previously independent runtime
pins exactly (loader/libc/libm/libgcc). The D5 workflow must recheck these from
the pinned VI archive, never substitute EN sysroot bytes. Matching userspace
ABI plus QEMU tests do not prove hardware/kernel/ADAS functionality.

First D5 CI38898326900 stopped at no-op rebuild because the legacy tool
uniformly chowned EN1001:1001 onto mixed VI1000/1001 files. This failed result
is retained. Rebuild now applies per-entry stock ownership, including explicit
root inode1 (VI1000:1000/0755), instead of weakening manifest comparisons.
Exact VI `/tmp` and config ancestry tuples were also added to the isolated
services; the production producer must run its QEMU fixture with VI `/tmp`
1000:1000/0755 rather than normalize it to root1777. No target permissions
are changed to satisfy these checks. The default D4 branch's concurrent120-
minute listener change is retained; D5 still selects the separate lifetime
edition. None of these offline checks diagnoses the previous ADAS symptom.

## Validation and release boundaries

Required: VI input pin, derived PRIVATE package contract, no-op customer rebuild,
protected VI deep validation, customer mutation allowlist and full-partition
identity, exact deploy list, stock ABI/BusyBox/ARM-QEMU tests, real native/ARM
Dropbear synthetic-key loopback tests, lifetime supervisor stop/AP-loss/foreign
listener gates, producer synthetic fraction100/200/999 versus1000/staleness,
Chrome/browser tests and public artifact allowlist. Vendor bytes, keys, firmware,
audio, private DB and full package contract stay private.

CI retains the stock VI update token, not directly ready for the newer installed
D4 token. Separate local version-only preparation must pin all4 input members,
change only the outer/inner14-digit token and derived MD5, then verify readback.
No drive/card staging/formatting is implied. Freeze the existing known D4-EN
release and source pins for rollback; a VI-stock reference A is NOT EN rollback.
Rollback firmware does not automatically reverse persistent TSR profile flags.

## Hardware acceptance (not performed by package creation)

Only after separate notice/approval, safe stationary power and identified updater
media: check boot/app/AP/actual recording growth, GPS fix outdoors, M4 native
connections/2D–3D, Vietnamese ADAS settings/audio and calibration state. Check SSH
past20minutes without changing its listener, but no automatic test reboot or
listener restart. UI settings may explain old VI behavior; record actual values
privately rather than reset/guess. Stop on degraded recording/AP/ADAS or changed
native connection gates. No claim that D5 fixes M4 signs or3D speed.
