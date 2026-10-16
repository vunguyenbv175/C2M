# D5-VI release and approved updater-card staging — 2026-10-16

## Completed, not a hardware flash

Owner requested full Vietnamese firmware + all D4 custom functions, no20-minute
SSH limit and useful additions, then explicitly approved replacement of ONLY
four updater-root files on the identified card after all gates passed.

**Package preparation and card staging completed. NO camera access or flash was
performed.** VI ADAS/recording/app/AP/GPS/M4 hardware behavior and SSH beyond
20minutes remain separate acceptance steps. Earlier VI ADAS symptoms may have
been unfamiliar settings, per owner; incompatibility/failure is not diagnosed.

## Validated composition

- Full stock VI `V2023.09.20.1_C2M_U_FR_WIFI_VI.tar`, SHA256
  `f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa`.
  VI kernel/cardv/ADAS/models are not mixed with EN. Device config/calibration/
  license preservation remains the stock updater behavior, no reset or forced
  recalibration. Existing vendor calib_success greeting remains event-driven.
- All prior D4 C/D/D3/D4 assets: eight selected VI WAVs, minimal idle, checked
  experimental TSR profile, AP-only web/connectivity gates, same private
  directional12708-point R.420/R.421 DB and isolated signs producer.
- D5-only `c2m-debug` build: `window_sec=0,lifetime=boot`, no listener deadline.
  Key-only owner access/AP192.168.1.1:2222/wlan0 and no-forwarding retained.
  Idle sessions600s; AP loss/signal/owned-child exit stops listener, no autorestart.
  Concurrent D4 default120-minute change is retained, not used as a D5 cap.
- GPS fractional-word0..999 correction with advancing-UTC freshness retained.
  Exact VI/EN stock path tuples supported without changing target permissions;
  mixed VI1000/1001 ownership and root inode1 metadata preserved in rebuild.
- On-demand `/bin/sh /customer/c2m/health.sh --snapshot` only; no boot loop,
  UART/USB/WS client, GPS payload logging or process/config modification.
- No new ADB authorization, M4 fake-sign/speed sender, warning-slot substitution,
  auto-STA, pairing, boot greeting, camera-speaker advisory or safety-ready claim.

## Build and independent readback

Source `fd7bd6a0c28477aaaccc4ee5784066300113a2da`.
Manual ARM/package workflow **38902291605 PASS**; general CI **38902290701 PASS**
on that source. Private vault delivery commit
`619e7fbb6313603d4a7d7ec4abd3a45c2db71699`, path
`deliverables/20261016-d5-vi-r38902291605/c2m-flash/`.

Required no-op/mutated UBIFS manifest, exact VI repack, protected VI deep hash,
non-customer partition identity, exact17-file deploy, stock ABI/BusyBox/QEMU,
Chrome/browser, native+ARM real-Dropbear synthetic loopback and lifetime
supervisor gates passed. Actual corrected producer ARM runtime passed using
VI private-sysroot `/tmp`0755 uid1000/gid1000, not normalized root1777. Synthetic
valid100/200/999, invalid1000, stale-clearing/reacquisition and SIGTERM passed.
This is not live GNSS or road-sign acceptance.

Private release readback verified10 package-member checksums,57 source hashes
against exact Git commit and re-extracted delivered customer manifest (including
VI root1000:1000/0755). The first local `git archive` retrieval applied Windows
CRLF conversion to text members; rejected by checksums, NEVER used for prep/card.
Separate retrieval with explicit autocrlf=false/eol=lf matched all hashes.

CI stock VI token20230920185743 was preserved. Local version-only preparation
changed the inner14-digit token, outer sysVer and derived MD5 to
**20261016000001**. ALLOWLIST-OK, all payloads/other script bytes unchanged,
4/4 local readback and separate VI deep validation **VALID33/33** passed.

Prepared folder (private/local):
`build/d5-vi-r38902291605/C2M_FLASH_D5_VI_20261016000001/`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| SigmastarUpgradeSD_SSC8838G.bin |60899352|`aaef1ff9e4875f157abe573055fd9d523c85173ebcaffa07f82daf5a63c70eae`|
| adas_upgrade.sh |2972|`0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b`|
| minieye_firmware.md5 |66|`007d14704a756da6877d1c2e6002df516efe2360d46ad5927367dacaf272f20d`|
| sysVer.txt |26|`bc1d13a5e778f81f8fdb814a47ffcbffc416d12e85e07587ec0297e3976909f5`|

Installed producer SHA256
`ac9b19faec88eb00380b6dead78c5984ab725b1726c72be6bb87db060009c900`;
lifetime supervisor SHA256
`a353309a829bf77b43006e3b9f1992577d0cb5172d90603ad94b42ed5226fe57`.
Neither is evidence of installation on the camera.

## Card staging result

Fresh identity immediately before writes: D:, label C2M_FLASH_B, removable
FAT32, disk1 SMI USB DISK33201061888B, MBR partition1 33200013312B,
volume33183236096B, non-system/non-boot. Existing D4 token20261015000001 and
all4 pre-recorded hashes matched; frozen source and rollback files rechecked.

Only4 root updater members replaced, sysVer last after all temp-file hashes
passed. Full readback **4/4 SHA256 matches above**. Root member names unchanged;
Normal/Event/Photo/C2M_DIAG metadata inventory unchanged. No format, media
content reads/deletion, camera connection or automatic flash. Volume label
remains C2M_FLASH_B; the name is historical, updater bytes are now D5-VI.
Owner should safely eject before removing card; not yet reported ejected.

## Rollback and evidence

Frozen known D4 original token20261015000001 retained locally. A separate
version-only rollback token **20261016000002**, higher than D5, passed local
ALLOWLIST-OK/readback. Directory:
`build/d5-rollback-frozen/C2M_FLASH_ROLLBACK_D4_EN_20261016000002/`.
It is NOT mixed on the D5 card and not device-update-accepted or flash-proven.
Firmware rollback does not automatically revert persistent TSR flags or erase
calibration/license/settings. Never force reset/recalibration for rollback.

Private11-file evidence:
`C2M_HW_20261012/08_candidate_D5_VI/card_preparation_20261016_195223/`.
Manifest SHA256
`eee4c2d8bf98a42f0b01989eee9d362446ce154729ab16b1a8c758b3fbb6a2ce`.
No vendor/key/audio/private DB bytes are published in this report.

## Failed/interrupted build history retained

- 38898326900: no-op mismatch from old uniform EN ownership; fixed per manifest,
  including newly protected root inode, not waived.
- 38900546920: Linux stock-path harness feature-macro ordering; fixed test header
  order without weakening compiler/error checks.
- 38900840477: stock-QEMU shell environment missing in final mutation step;
  fixed explicit sysroot export. Prior runtime/debug gates had passed.
- 38901595471 and38901734390: explicitly canceled for reviewed packaging fixes
  (root-run mutation of ownership-preserved private tree, independent VI repack
  selector). Not counted as successful builds or hardware evidence.
- 38902291605: complete PASS, the ONLY delivery used above.
