# D3 connectivity + online GPS/TSR providers (2026-10-14)

This is a development investigation, not a claim that Wi-Fi STA, Bluetooth, or an
online service has been tested on the physical camera. Priority: produce a
working GPS advisory + native TSR feature, not more D2 rollback work.

## Firmware-grounded capability matrix

| Capability | Grounding | Verdict |
|---|---|---|
| 802.11 AP | Customer \`wifi/ap.sh\`, \`hostapd\`, \`udhcpd\`, \`wlan0\` | Stock AP software present |
| 802.11 STA | \`wifi/sta.sh\`, \`wpa_supplicant.conf\`, DHCP, \`nvconf\` | STA code path present; association/internet UNTESTED |
| AP + STA together | \`apsta_switch.sh\` stops one before starting other | Stock AP XOR STA, concurrency UNVERIFIED |
| Wi-Fi silicon | Customer \`wifi/lib/8821cs.ko\` | Realtek RTL8821CS driver present, board subtype unknown |
| Bluetooth/BLE silicon | RTL8821CS family includes BT 4.2 via UART (module dependent) | POSSIBLE at chipset level, board wiring UNKNOWN |
| Bluetooth runtime | No verified BlueZ, HCI, or C2M Bluetooth client/server in repository evidence | NOT DEMONSTRATED; do not equate with physical impossibility |
| GPS engine | Stock \`cardv\` NMEA/GpsTask; \`fw/warner\` host replay | Code evidence; live non-consuming feed UNKNOWN |
| Online Lily API | Lily APK teardown identified bundled vnsigns and Overpass requests | No supported public Lily sign API verified |
| Online OSM | Overpass \`way[maxspeed]\` / sign queries documented | Suitable online data source with rate limiting + caching; accuracy varies |

RTL8821CS combo module reference is hardware capability, not a board-level
C2M module/antenna/UART/firmware proof. Avoid buying an ESP32 solely for
Bluetooth until the device HCI/UART inventory is done.

## Practical D3 modes, ordered by low-friction value

1. **OFFLINE**: built-in GPS + known directional sign DB + native TSR. No
   network dependence; never present a GPS-only point as a proven speed limit.
2. **STA / INTERNET**: when parked during development, associate with a
   known, owner-controlled 2.4/5 GHz AP/hotspot using stock STA path. Retrieve
   scoped road/maxspeed/sign data from Overpass or an authorized provider.
   Normalize and persist a timestamped/attributed cache. Restore AP so stock
   UTOUR GO phone connectivity is not silently broken. This may not allow
   simultaneous AP and Internet.
3. **AP / PHONE RELAY**: phone joins camera AP; a companion can use its
   cellular data to fetch provider results and transmit normalized records
   on a new C2M port. Confirm Android cellular routing under Wi-Fi-without-
   Internet rather than assuming it works. This preserves the camera AP.
4. **AP+STA virtual interfaces**: optional experiment only if \`iw list\`
   supported interface combinations and runtime driver test prove it; never
   infer from chip brochure.
5. **Bluetooth**: optional future channel if on-device HCI + UART wiring,
   BT firmware/driver and actual GATT client all prove usable.

## Online provider contract

All providers (local Lily-derived *private* DB, OSM/Overpass, a future
permissioned Lily API, an optional commercial licensed map API) implement a
single normalization layer:

\`\`\`text
RoadSignObservation {
  source: offline | osm_overpass | authorized_api | camera_tsr,
  type, value_kmh?,
  position?, road_id?, direction_deg?, confidence?,
  observed_at?, fetched_at?, expires_at?, source_license?
}
\`\`\`

- There is **no verified official Lily online sign endpoint** in APK findings.
  Lily-style behavior uses its bundled vnsigns DB plus OSM Overpass API
  (four candidate endpoints seen in code). Don't label Overpass a Lily API.
- Never call Overpass for every GPS fix. Batch by region, cache on SD and
  back off on HTTP 429/timeout. OSM public instances are shared/limited.
- Road segment maxspeed is NOT the same as a point-sign or current legal
  speed-limit state; preserve source, direction, road match, confidence and
  age so fusion can distinguish them.
- If Wi-Fi is unavailable, use cached/offline data and native TSR.
- Private user-provided \`signs_vn.bin\` is not redistributed, and use
  rights/licensing for each other source must be checked before deployment.

## Short live probe (do not require UART / do not alter settings)

Run \`sh tools/device/c2m_connectivity_probe.sh > /mnt/mmc/C2M_DIAG/connectivity.txt\`
from an authorized camera shell, or package it via an explicitly chosen
diagnostic hook for an upcoming developer build. **No shell path has been
established as available to the owner today.** Save the output privately:
network MACs, SSIDs and interfaces may disclose device information.

1. Baseline with stock AP operating: capture process names, links,
   \`iw list\` combinations, HCI availability, \`/proc/net/wireless\`, vendor
   modules, UART nodes and network routes.
2. Park camera and test STA association with a known hotspot using the stock
   configuration/mode-switch workflow; confirm an actual IP/DNS/HTTPS GET,
   not merely the existence of \`wpa_supplicant.conf\`. Recheck recording.
3. Switch back to AP and verify official app access/recording.
4. If HCI exposes a device, inventory driver/firmware and validate discovery
   with standard tools; if HCI is missing, distinguish missing UART wiring,
   kernel BT/HCI, firmware and tools. Do not claim BLE support by chip alone.
5. Do not attempt AP+STA concurrently before \`iw list\` and real interface
   combinations show compatibility.

## Prototype code staged alongside this document

- \`tools/m4/tsr_event_lab.py\`: schema-only postprocessor for existing native
  TSR MessagePack capture, without guessing speed units/sign class.
- \`tools/m4/test_tsr_event_lab.py\`: synthetic tests for both known keys,
  malformed frames and non-leakage of values.
- This branch deliberately does **not** contain a finished flashing image,
  online-client daemon, live GPS reader or Bluetooth integration.

## Next build acceptance (feature-focused)

- One live GPS observation without interfering with cardv/GPS reader.
- One normalized offline sign candidate with road/direction matching.
- One fetch+cache+offline-fallback from a permitted online provider on a
  demonstrably reachable network (STA or phone relay).
- One real TSR frame decoded to a typed sign schema (if stock emits it).
- One real screen/audio event only after the output path is observed and
  matches protocol; leave other functionality untouched.
