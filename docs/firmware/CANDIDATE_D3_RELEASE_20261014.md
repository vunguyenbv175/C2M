# Candidate D3 release — Wi-Fi/AP+STA and passive Bluetooth — 2026-10-14

**Status: HOST-VALIDATED + FLASH CARD READ-BACK 4/4 VERIFIED;
MANUAL CAMERA FLASH PENDING.** D3 source commit `8a8320d`; firmware pipeline
run `38550553664` GREEN, general CI run `38550548495` GREEN.

The earlier connected 59GB `MINIEYE` recording card was not written. Later,
the connected card was positively reidentified as the 32GB `C2M_FLASH_B`
updater card with verified D2 payload. At 17:47 +07:00 it was staged with D3,
read-back verified 4/4 and cache-flushed. No format, repair or log deletion;
final volume Healthy and NOT Dirty. No camera flash was performed by the agent.

## What is different from D2

- Native Vietnamese Wi-Fi page at port `8099`, served only after verifying
  stock `wlan0` is an active AP with an IPv4 address. It is not wildcard-bound
  and does not replace GoAhead or the official app.
- Page can save an SSID/password privately and separately queue an explicit
  connection request. It shows AP, STA, controller and passive Bluetooth
  status without showing passwords. It has no format, reboot, record, flash,
  factory-reset or `nvconf` endpoint.
- Controller verifies a real kernel nl80211 interface combination containing
  AP + managed interfaces in one combination, requires the current AP
  frequency, creates only its own `c2msta0`, and never invokes the stock
  exclusive `apsta_switch.sh`, `ap.sh` or `sta.sh`. If capability is not
  proven, it refuses instead of turning off the AP.
- Pinned WPA2/nl80211 client is bundled (`wpa_supplicant 2.12`, static libnl)
  because the inspected EN customer/rootfs had `sta.sh` references but no
  executable supplicant. ARM ELF, loader/glibc gate and QEMU `-v` self-test
  pass. No real radio association was performed in CI.
- Bluetooth probe is read-only and saves `C2M_DIAG/bluetooth-D3.txt`. It
  reports `HCI_PRESENT_NOT_RADIO_TESTED` or
  `NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE`; no pairing, RF activation, module
  load, UART open or Bluetooth scan. The result is also consumed by the Wi-Fi
  status page as `seen`, `not_seen` or `unknown`.
- Strict GPS `/tmp/car_info` snapshot decoder is included as host-validated
  reusable code only; it does not run as a D3 GPS warning daemon. Correct
  contract is offset `0x330`, length `0x1c0`, signed NMEA DDMM coordinates,
  not the earlier incorrect offset-zero/decimal-degree assumption.

## Preserved functionality

D3 keeps C/D2 EN core, C Vietnamese audio and unchanged idle/status service,
D2 TSR profile, cardv, models, camera, kernel, rootfs, bootloader,
calibration/license and recording. No sign DB, Warner GPS warning daemon,
new detector, M4 injection or new audio backend is included.

## Explicit limits

- AP+STA support is capability-gated but **not field-proven**. Same-channel
  operation may require the upstream hotspot to use the camera AP channel.
- D3 currently stops at WPA association status (`associated_no_ip`); DHCP,
  default route and Internet proof are deliberately not included. The private
  `build/d3-dhcp-draft/` work is not part of this release.
- Bluetooth result is not available until the owner boots D3 and reads the
  recording card diagnostic file. Kernel HCI absence is inconclusive about
  physical hardware.
- TSR recognition/display/audio of real signs remains unproven; D3 does not
  claim to add a detector.

## Gates and identities

- Pipeline: `firmware-candidateD3`, run `38550553664`, all steps GREEN:
  D2 tests, exact BusyBox probe tests, ARM/glibc/QEMU builds, native web and
  Wi-Fi self-tests, customer rebuild, deep 33-check validation and allowlist
  diff.
- Final payload was fetched from private vault, version-reverted locally only:
  old token `20230803193750` → new token `20261014000005`.
- Reversion verdict `ALLOWLIST-OK`; inner bytes outside the 14-byte token and
  derived MD5/sidecar are unchanged. TAR deep verdict `VALID` (33 checks).
- Final extracted customer proof: C/D2 audio and idle unchanged; protected
  loads unchanged; versus D2 added only `/c2m/boot.sh`, `/c2m/c2m-web`,
  `/c2m/c2m-wifi`, `/c2m/connectivity_probe.sh`,
  `/c2m/wpa_supplicant`; changed only `/wifi/rcInsDriver.sh`; no removed
  paths; existing metadata unchanged.
- Final TAR SHA256:
  `0098557324206923ddb83242e45d57d753071e92fc15d76ab6d9f64982af2888`.
- Final inner image SHA256:
  `7e4623ab427c32bc74299002b3203e4a2a6a6052a2be780622cfef25cb3414b2`.
- `sysVer.txt` after local preparation contains `20261014000005`.
- All final-payload extraction proofs say `PASS_FINAL_HOST_PAYLOAD_NOT_DEVICE_TESTED`.
- On-card D3 report: `build/candidate-d3-final/on_card_d3_verification.json`,
  `READY_FOR_MANUAL_D3_FLASH_NOT_DEVICE_TESTED`, 4/4 exact bytes and hashes.
- Physical flash media: USB SM3350, disk1, MBR, 33,201,061,888 bytes;
  partition1 offset1,048,576, size33,200,013,312, FAT32 XINT13, label retained
  `C2M_FLASH_B`. Only the four updater files replaced, sysVer last.

## Hardware use

Do not copy raw CI vault files. Use only the separately locally reverted
four-file D3 folder after checking its hashes. Keep the 32GB flash card
separate from the 59GB recording card. Before owner-authorized flash, recheck
physical disk identity and preserve diagnostic files. Use stable power and
manual recovery media. After boot, check live view, recording, app/AP, ADAS
Vietnamese audio, D2 profile status and reboot stability before trying Wi-Fi.

For Wi-Fi: join the camera AP, open `http://<camera-AP-IP>:8099/`, save a
network, then explicitly connect. The page will report whether the driver
supports AP+STA; it must not claim Internet until a future DHCP/route helper
is independently added. For Bluetooth: read `C2M_DIAG/bluetooth-D3.txt`.
