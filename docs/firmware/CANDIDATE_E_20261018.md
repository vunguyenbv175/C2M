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
  `rollback_d5vi_20261016000004` (D5-VI content) and
  `rollback_d4en_20261016000005` (D4-EN original content); both
  `ALLOWLIST-OK` version-only.

## Tokens

`20261015000001` installed D4-debug · `20261016000001` D5-VI (current on camera)
· `20261016000002` D4-EN rollback (prepared, unused) · **`20261016000003`
Candidate E (staged, to flash)** · `20261016000004`/`0005` local rollbacks.

## Owner acceptance checklist (separate from CI; not hardware-proven here)

1. Flash via the standard updater card (no resets, no recalibration, no license
   changes). Keep the recording card contents untouched.
2. Verify on camera: boot + recording + stock AP; SSH debug reachable on
   192.168.1.1:2222 (key-only, no 20-minute limit); system sounds in Vietnamese
   (card insert/remove, format, record start/stop, Wi-Fi, low-card, video lock);
   ADAS warnings as before; FCW/HMW on a drive (unchanged EN core).
3. If anything regresses, report it; the matching rollback package can be
   staged on request (0004 → D5-VI, 0005 → D4-EN original).

## Repo changes enabling E

`tools/fw/mutate_oneed.py` (new), `tools/fw/verify_b_manifest.py` kind=oneed,
`tools/fw/build_candidates.py --oneed-cust` (+ forwarded diff authorization),
`tools/fw/candidate_diff.py` oneed authorization, host gates
`tools/fw/test_candidate_e_gates.py` (8 tests), and the manual workflow
`.github/workflows/firmware-candidateE.yml`. All fail closed; every payload
outside the authorized swaps is preserved byte-identically.
