# Candidate E — EN core (D4-debug asset set) + VI system audio, flash-ready — 2026-10-18

## Owner request (2026-10-18)

Owner asked to rebuild the EN line ("làm bản flash mới bản eng lại"), inheriting
the latest assets ("kế thừa bản mới nhất"), and to transfer ALL Vietnamese audio
over ("chuyển tất cả audio bản việt sang") because the previous EN build still
played some English system audio.

## What E is

- **Base = the D4-debug asset set** — the exact EN-line recipe the owner ran as
  token `20261015000001`: C/D/D3/D4 assets plus the owner-authorized AP-only
  debug SSH service (Dropbear 2026.94, `c2m-debug` supervisor, `debug_boot.sh`,
  pinned owner Ed25519 pub, stock glibc-2.30 NSS module). No stock
  camera/kernel/ADAS/cardv/model binary changes.
- **Audio**: exactly the **17 `/audio` wavs of `oneed_cust.es`** whose EN and
  VI bytes differ are replaced with VI donor bytes (all RIFF PCM16 mono 24 kHz,
  sha256-pinned): Card_Err, Card_Format_Done, Card_Format_Fail,
  Emergency_FileFull, Format_Card, Insert_Card, Ota_Update_Ok, Rec,
  Record_Off, Record_On, Replace_Card, Shutter, Stop_Rec, Video_Locked,
  Video_Unlock, WiFi_Close, WiFi_Open. The five language-neutral wavs
  (Button, Power_On, Power_Off, RecordingBell, SystemTestSound) and
  `/defconfig/cgi_config.bin` stay EN. Every other oneed file is byte-identical.
- ADAS audio is unchanged from the D4 line (7 VI wavs + `tlr_green_on.wav`);
  FCW/HMW wavs are byte-identical between EN and VI in both builds.
- A deep scan confirmed no other firmware audio exists: rootfs decompressed
  content matches EN↔VI in audio names/magics; miservice/misc carry none.

## Evidence chain

- **CI (manual workflow `firmware-candidateE.yml`, from `main`)**:
  - run `39129764399` (plain-D4 base) — all gates green but **SUPERSEDED, not used**
    (lacked the debug SSH asset set).
  - run `39131110803` (D4-debug base) — **the delivered one**; all gates green:
    host E tests 8/8, exact 17-wav swap gate, P1o/P2o oneed no-op+mutation
    rebuilds (`verify_b_manifest` kind=oneed OK), Dropbear build + SSH
    host/ARM gates, both deep validations VALID, allowlist diff
    `ALLOWLIST-OK` with `oneed_authorized=true`
    (customer.es 39743488 → 42536960, delta 2793472; oneed_cust.es
    3555328 → 3301376; E stock-token inner sha256 `570b16fb…`).
- **Private vault**: `deliverables/20261018-e-r39131110803` (commit
  `9ff281407917d8722d8ac16890090624cfd233f2`) — raw four-file package (stock
  token `20230803193750`), evidence, dropbear open source. Retrieved locally with
  `core.autocrlf=false`; all four member sha256 verified against the CI
  `SHA256SUMS.txt`.
- **Local version-only preparation** (`tools/fw/reversion_sd_package.py`,
  fail-closed): `20230803193750 → 20261016000003`, verdict `ALLOWLIST-OK`,
  4/4 readback; proof in `local-version-proof.json`. Deep validation of the
  minted tar: **VALID (33 checks)**; minted tar sha256 `c6ecf291…`.
- **Card staging** (D: `C2M_FLASH_B`, SMI USB DISK disk 1, FAT32)
  **4/4 readback-verified**:
  | member | bytes | sha256 |
  |---|---|---|
  | SigmastarUpgradeSD_SSC8838G.bin | 60899352 | `c2a05cf82c41e6a8aa811f9f91cf6d5d96ca340b68a71568707bb9dbd0c02d95` |
  | adas_upgrade.sh | 2972 | `0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b` |
  | minieye_firmware.md5 | 66 | `829907937a1ea919f2b67cdfe0e076e32c870343bbdd5025149eb62ceb6de619` |
  | sysVer.txt | 26 | `ad58a6d560e375bb2419a52eae101969d5b566fffe95b1d77982566e759d8dbb` |
  - Inner bin md5 matches its sidecar exactly (`baa8f9098429955ad8f54df64d2af526`);
    the token string `20261016000003` occurs exactly once in the inner image and
    the stock token occurs zero times.
- **Rollbacks kept locally only** (never staged together with E):
  the earlier `rollback_d5vi_20261016000004` (D5-VI content) and
  `rollback_d4en_20261016000005` (D4-EN original) mintings were deleted when
  the E2 bundle took token 0004; the current fallback is
  `rollback_e_20261016000005` (E content, `ALLOWLIST-OK`); D5-VI/D4-EN
  fallbacks are re-mintable on request with fresh tokens.

## Candidate E2 — post-flash follow-up build (2026-10-18 late)

Owner-approved bundle for the second flash: **E content unchanged + two deltas**:
1. `c2m-wifi` ancestor fix (`0c53462`) so the controller starts and reports the
   honest capability verdict instead of `private_paths_or_supplicant_unavailable`.
2. **Lifetime-boot SSH debug edition**: `build_dropbear.sh --lifetime`
   (`window_sec=0`, status `lifetime=boot`) — no supervisor deadline, same as
   the current VI line; AP startup still bounded at 60 s and AP
   loss/SIGTERM/child exit still stop the owned listener.

- CI `firmware-candidateE.yml` run **39141030235** (main `f257d12`): all green;
  allowlist diff `ALLOWLIST-OK`, `oneed_authorized=true`, customer delta
  identical to E (+2793472), stock-token inner sha256 `74f464cc…`;
  `debug_report.json` proves `lifetime=true, lifetime_edition=boot,
  window_sec=0` (rebuilt `c2m-debug` `df3edd2e…`).
- **Private vault**: `deliverables/20261018-e-r39141030235` (commit `6aba707`);
  all four member sha256 verified against the CI `SHA256SUMS.txt`.
- **Local version-only preparation**: `20230803193750 → 20261016000004`,
  verdict `ALLOWLIST-OK`, 4/4 readback; outputs: bin
  `3654dda9607b17b29beff113cc3fa97507cf87afeaf6daadd915d65f506847cc`,
  sysVer.txt `cb05b7833bc87a01bf2418dc0bbe837c1a74796bc248c91223a10586675df4f7`,
  minieye_firmware.md5 `a5c86e8c80b2f946f8bcde795d51516da87cbe00aad258a8a68dc3116f1b4903`,
  adas_upgrade.sh unchanged `0e18c91f…`; new inner md5 sidecar
  `466d877c7bb9da71fc33e46196729cc7`. Deep validation of the minted tar
  **VALID (33 checks)**; minted tar sha256 `fbb7450f…`.

### E2 post-flash inspection — 2026-10-19 (owner-reported flash + observed SSH)

Owner flashed E2; a read-only SSH session (AP-only `192.168.1.1:2222`,
dedicated key) observed:

- Host key changed after the flash as usual; the E-era pin
  `SHA256:clbNRtL12T2uQZN+8NyYjLt+pB5jFmnmv2avAPMbD5U` was archived and the new
  owner-controlled pin is
  `SHA256:ehLL+1VV+L4vcCDSEOXDGoldTdt+XuFkHdWQNMwxFXo`.
- Assets match the E2 build exactly: `c2m-debug` `df3edd2e…` (lifetime
  edition), `c2m-wifi` `3c617f6e…` (ancestor fix), `c2m-web` `653a144e…`,
  `dropbear`/`dropbearkey`/`debug_boot.sh`/`libnss_files.so.2`/`boot.sh`/
  `wpa_supplicant` unchanged.
- **`c2m-wifi` is running** (`--serve` with the stock paths) and the status
  file reports the honest verdict `sta_supported=unknown`,
  `last_error=capability_combinations_empty` — the
  `private_paths_or_supplicant_unavailable` failure is gone.
- **Lifetime SSH live**: `/tmp/c2m_debug_status` shows `state=active`,
  `reason=listening`, `window_sec=0`, `lifetime=boot` — no supervisor
  deadline.
- Vietnamese system audio intact (spot samples `Card_Err` `9e26a864…`,
  `WiFi_Open` `8d167d9e…`); services healthy (cardv, minieye, c2m-idle,
  c2m-signs, c2m-web, ADAS/lane, hostapd 5 GHz AP); recording active.
- Not full acceptance: owner to confirm sounds, live view and ADAS/FCW/HMW
  behavior as usual. Rollback to the previous E content remains prepared
  locally (`rollback_e_20261016000005`).

## Tokens

`20261015000001` installed D4-debug · `20261016000001` D5-VI ·
`20261016000002` D4-EN rollback (prepared, unused) · `20261016000003`
Candidate E (flashed, verified) · **`20261016000004` Candidate E2 (to flash)**
· `20261016000005` rollback to E content (local only; the obsolete
D5-VI/D4-EN mintings of 0004/0005 were deleted and are re-mintable on
request).

## Owner acceptance checklist (separate from CI; not hardware-proven here)

1. Flash via the standard updater card (no resets, no recalibration, no license
   changes). Keep the recording card contents untouched.
2. Verify on camera: boot + recording + stock AP; SSH debug reachable on
   192.168.1.1:2222 (key-only, no 20-minute limit); system sounds in Vietnamese
   (card insert/remove, format, record start/stop, Wi-Fi, low-card, video lock);
   ADAS warnings as before; FCW/HMW on a drive (unchanged EN core).
3. If anything regresses, report it; the matching rollback package can be
   staged on request (0005 → back to the current E content; D5-VI/D4-EN
   fallbacks re-mintable with fresh tokens).

## Repo changes enabling E

`tools/fw/mutate_oneed.py` (new), `tools/fw/verify_b_manifest.py` kind=oneed,
`tools/fw/build_candidates.py --oneed-cust` (+ forwarded diff authorization),
`tools/fw/candidate_diff.py` oneed authorization, host gates
`tools/fw/test_candidate_e_gates.py` (8 tests), and the manual workflow
`.github/workflows/firmware-candidateE.yml`. All fail closed; every payload
outside the authorized swaps is preserved byte-identically.

## Post-flash inspection — 2026-10-18 (owner-reported flash + observed SSH)

Owner flashed E and connected to its AP. A read-only SSH session (AP-only
`192.168.1.1:2222`, dedicated key, strict pinned host key) then observed:

- Debug/D3 assets match this build exactly: `dropbear` `988369a5…`,
  `dropbearkey` `afa48a01…`, `c2m-debug` `565830f1…`, `debug_boot.sh`
  `378bd43f…`, `libnss_files.so.2` `381a2aa8…`, `boot.sh` `1f40dfbd…`,
  `c2m-wifi` `d047ff80…`, `c2m-web` `b1dd97af…`, `wpa_supplicant`
  `97355222…` (all 1001:1001, expected modes).
- **The 17 swapped system wavs are live**: sampled `/oneed_cust/audio` files
  match the pinned VI sha256 exactly (Card_Err, WiFi_Open, WiFi_Close,
  Shutter, Record_On, Record_Off, Insert_Card, Stop_Rec); 22 wavs total;
  language-neutral wavs and ADAS audio unchanged.
- Services healthy: `cardv`, `minieye_daemon`, `c2m-idle`, `c2m-signs`,
  `c2m-debug`, `c2m-web`, ADAS/lane processes, hostapd 5 GHz AP; recording
  card active.
- Host key changed after the flash as usual; the D5-era pin was archived and
  the new owner-controlled pin is
  `SHA256:clbNRtL12T2uQZN+8NyYjLt+pB5jFmnmv2avAPMbD5U`.

### Found and fixed in source: `c2m-wifi` refused to start

Symptom: `/tmp/c2m_wifi_status` reported
`last_error=private_paths_or_supplicant_unavailable` and no `c2m-wifi`
process existed. Root cause (device-verified + static): the stock EN
customer UBIFS root `/customer` is **0775 1001:1001**; `eff7040` began
preserving exact stock ownership in rebuilds, so E's `/customer` is 0775
(earlier rebuilds normalized it to 0755, which is why D4/D5 field images
passed). `stock_config_ancestor()` in `fw/d3/wifi_control.c` listed only the
0755 variant for `/customer`, so `safe_dir()` rejected the ancestor walk and
the controller exited before any capability observation. The debug
supervisor's table already accepted 0775 — only the wifi controller was
missing it.

Fix committed (`527907a`, source + host gate `tests/test_d3_vi_paths.py`):
accept `1001:1001` at both 0755 (legacy rebuild) and 0775 (stock UBIFS
root). **Not deployed** — the current E flash still reports the failure; the
fix ships with the next firmware build. STA itself remains blocked by the
installed single-interface driver (`CONFIG_IFACE_NUMBER=1`), so this is a
status-correctness fix, not STA enablement.

