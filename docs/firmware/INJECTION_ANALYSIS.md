# Safest enhancement injection layer — static analysis (no firmware modified)

Method: read-only carve (carve_upgrade.py) + gzip-cpio parse
(extract_rootfs_cpio.py) + UBIFS inventory/extract (ubifs_ls.py,
ubifs_extract_file.py). All paths below are ON-DEVICE absolute paths.
UBIFS image paths omit the mount prefix (`/wifi/x` in image =
`/customer/wifi/x` on device).

## 1. Writable / persistent / executable layers

| # | FILE | OFFSET/SCRIPT LINE | INTERPRETATION | CONFIDENCE |
|---|---|---|---|---|
| 1 | rootfs `etc/profile` (cpio `etc/profile`, lines 8-10) | `mount -t ubifs ubi0:miservice /config`, `mount -t ubifs ubi0:customer /customer`, `mount -t ubifs ubi0:oneed_cust /oneed_cust` | Three UBI volumes are mounted RW at boot; `/customer` (ubi0:customer, 0x5000000 = 80 MB per U-Boot script) is the large writable/persistent store | CONFIRMED (byte-present in EN rootfs cpio) |
| 2 | rootfs `etc/profile` line 12 | `LD_LIBRARY_PATH=...:/customer/wifi/lib:/customer/minieye/adas/third_lib` | Customer-layer `.so` files are on the loader path — a new daemon can ship its own libs under `/customer` without touching rootfs `/lib` | CONFIRMED |
| 3 | rootfs `etc/profile` line 11 | `PATH=...:/bootconfig/bin:/oneed_cust/UI/bin:...:/customer/wifi` | `/customer/wifi` is on root's PATH | CONFIRMED |
| 4 | `customer.es` UBIFS inventory (227 files) + `adas_service.sh`/`mutualism` already execute from `/customer` | `demo.sh:107` launches `/customer/minieye/adas/adas_service.sh start`; `run.sh` executes `./mutualism` from the customer dir | Customer UBIFS is mounted EXECUTABLE (stock code runs from it daily) — a new `/customer/c2m/*` binary will execute | CONFIRMED (running-stock-proven) |
| 5 | `demo.sh:74-76` (`bootconfig/demo.sh` in rootfs cpio) | `cp /customer/cardv /bootconfig/bin/` + `chmod 777` + `cardv ... &` | The running `cardv` is a COPY of a customer-layer file — but replacing `/customer/cardv` means replacing stock cardv: FORBIDDEN by safety rules, noted only to explain why we do NOT use this path | CONFIRMED (and explicitly REJECTED as injection point) |

## 2. Startup ordering (rootfs `bootconfig/demo.sh`, 118 lines)

`etc/init.d/rcS` -> `/etc/profile` (mounts) -> `source /bootconfig/demo.sh` ->
insmod SoC stack (lines 6-35) -> `source /oneed_cust/sensor_insmod.sh` (:39) ->
`source /config/misc_profile.sh` (:43) -> `source /oneed_cust/create_soft_link.sh`
(:44) -> `cardv &` (:76) -> customer `.ko` insmods (:77-91) ->
`/customer/wifi/rcInsDriver.sh` if present (:99-101) ->
`/customer/minieye/minieye_daemon.sh &` (:103) ->
`(adas_license_restore.sh; adas_upgrade.sh; adas_service.sh start) &` (:107).

- No wildcard drop-in directory (`for f in /customer/*.sh`, `run-parts`,
  `init.d`) exists anywhere in `demo.sh`/`profile`/`rcS` — verified by full
  118-line read. Therefore a ZERO-modification auto-start (drop a file, change
  nothing) is NOT statically proven. Any auto-start needs a ≥1-line hook edit
  in a customer-layer script. (CONFIRMED absence.)
- `demo.sh` itself lives in rootfs (read-only NAND cpio) — editing it would
  mean rebuilding rootfs: REJECTED (higher risk than customer hook).

## 3. Hook candidates (lowest-risk first)

| rank | FILE (on-device) | LINE | INTERPRETATION | CONFIDENCE |
|---|---|---|---|---|
| H1 (preferred) | `/customer/wifi/rcInsDriver.sh` (image `/wifi/rcInsDriver.sh`, 933 B, sha `855705c9…`) | append after line 3 (`sleep 1`): `/customer/c2m/c2m-idle &` | Already executed by stock `demo.sh:99-101` AFTER cardv start, in background-tolerant context; wifi-driver script has no size/integrity self-check (no `adas_checksize`-style gate covers it) | HIGH-CONFIDENCE (execution proven, no-check observed; boot-timing on hardware still UNKNOWN) |
| H2 | `/customer/minieye/minieye_daemon.sh` (3060 B, sha `b1963f0c…`) | append `... &` line | Same customer layer, runs as daemon already; but this file is a thermal/recording watchdog — editing it couples our hook to safety-adjacent logic | HIGH-CONFIDENCE but DISPREFERRED vs H1 |
| REJECTED | `/config/misc_profile.sh` (163 B, timezone only) | — | miservice volume also holds `cgi_config.bin`/`net_config.bin` calibration-adjacent configs; touching this volume risks config loss | REJECTED |
| REJECTED | `/oneed_cust/*.sh` | — | oneed_cust holds sensor/IQ/camera calibration (`iqfile/`, `ko/imx415_MIPI.ko`); touching camera-adjacent volume is higher risk | REJECTED |
| REJECTED | rootfs `demo.sh`, `cardv`, `adas`, kernel, U-Boot, IPL, CIS | — | Forbidden by safety rules and/or read-only | REJECTED |

## 4. Watchdog behaviour (visible part)

- `/customer/minieye/minieye_daemon.sh` (full 81-line read): reboots (`reboot -f`)
  if recording stalls >150 s or on thermal path; our idle daemon does not touch
  recording state, `/tmp/rec_status`, or FIFOs, so it cannot trip this logic.
  CONFIRMED (file content) for the trigger conditions; timing on hardware UNKNOWN.
- `/customer/minieye/adas/adas_guard.sh` (33 lines): restarts the ADAS `run.sh`
  path every 3 s if dead; it only `grep`s the adas process name, so an extra
  `c2m-idle` process is invisible to it. CONFIRMED.
- `sbin/watchdog` exists in rootfs but no launcher references it in
  `rcS`/`profile`/`demo.sh` → hardware-watchdog behaviour UNKNOWN.

## 5. Conclusion (binding)

- Safest layer: **customer / UBI layer** (`ubi0:customer`): new standalone files
  under `/customer/c2m/` (dynamic stock-ABI daemon binary preferred, static
  fallback; no extra libs) + one appended hook line at H1.
  No stock binary replaced, no rootfs/kernel/bootloader change, no calibration
  touched, no M4 transmit, no camera access.
- Daemon constraints (binding on any B/C build): run as background `&`,
  never block `demo.sh`, only `/tmp/` writes + stdout logging, idle priority.
- Image-build status (Sprint 2): full chain implemented
  (`rebuild_customer.sh` + `mutate_customer.py` + `build_candidates.py` +
  `candidate_diff.py` + manual workflow `firmware-candidateB.yml`); execution
  of `mkfs.ubifs` needs Linux (absent on the dev box) — one command away, not
  fabricated. Hook line: exactly `/customer/c2m/c2m-idle &` appended at EOF
  of `/customer/wifi/rcInsDriver.sh` (see `FLASH_CANDIDATES.md`).
