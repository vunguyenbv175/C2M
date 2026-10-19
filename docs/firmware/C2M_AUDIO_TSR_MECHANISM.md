# C2M audio + TSR mechanisms (stock EN static evidence, 2026-10-14)

All paths below are IMAGE-RELATIVE (`/customer/...` on device). Static
analysis was performed without a device shell. Candidate C was subsequently
built and flashed on 2026-10-14; the owner reports Vietnamese warning audio.
TSR recognition/output and the effective device flags remain unverified.

## Audio playback path

- ADAS does NOT play sound itself: the `adas` binary has no wav/alsa/fifo
  strings, only `--audio_list_file=audios.txt`. Playback is done by `cardv`
  (which references `/oneed_cust/audio/*.wav` system sounds and the
  `play_wifi_voice` / `play_wav_cmd` fifo commands).
- `/minieye/adas/audios.txt` maps warning IDs to wav files:
  `fcw/hwm/vb/stop_and_go/ldw/pcw/fail/calib_success/tlr_green_on`, with
  duration-ms, privilege and loop fields. `tlr_green_on.wav` is listed but
  MISSING from the stock EN/VI images; Candidate C adds this asset. Having
  the slot/file does not prove the traffic-light event will fire.
- WAV format (checked `adas_activated.wav`): RIFF/WAVE, PCM16, mono,
  24000 Hz. Replacements must use the same encoding.
- Integrity: static boot-path inspection found NO caller of
  `adas_checksum.sh` (`md5sum -c md5sum.txt`). Stock boots despite the missing
  tlr wav; 2026-10-14 inspection also found stale FCW/HMW entries (e.g. FCW
  listed `08998a0f…`, actual md5 `c61c15d8…`, identical B4/C bytes). This
  supports treating it as non-gating on the observed boot path, NOT proof
  that it is never called in any mode. Any wav/audios.txt change must still
  update its matching `md5sum.txt` lines (`md5sum.txt` lists run.sh,
  audios.txt and wavs, but not itself); vendor-stale lines for untouched
  files are preserved verbatim. `adas_checksize.sh` checks SIZES from
  `filesize.txt`, which lists `run.sh` (1584 B) but NO wavs/audios.txt —
  so wav swaps need no size bookkeeping, while any `run.sh` edit MUST
  update `filesize.txt` too.

## ADAS flag source (TSR)

- `run.sh` decodes base64 `/customer/minieye/config/adas.flag` to
  `adas_de.flag` (re-decodes when md5 differs), then launches `./mutualism`.
- `mutualism.txt` / lane binaries consume
  `--flagfile=/customer/minieye/config/adas_de.flag`; the `adas` binary
  defaults include `--enable_tsr=false` with a real TsrWarning pipeline and
  an embedded `tl` model (see `03_ADAS_ENGINE_TSR_AND_REGRESSION.md`).
- `/minieye/config/` in the image holds only `.gitkeep`: `adas.flag` is
  factory-provisioned device-side and SURVIVES flashing (updater backs up
  `/customer/minieye/config`; A-flash kept calibration working).
- TSR enable strategy (no `run.sh` edit needed): our boot hook runs BEFORE
  `adas_service.sh` (`demo.sh`: hook ~:100, adas :107), so it can patch the
  decoded flag + re-encode consistently with stock tools
  (base64/md5sum/sed). The current implementation writes BOTH persistent
  device flag files, has no original-config backup, and silently skips a
  file without the literal `--enable_tsr=false`. Therefore the effective
  runtime setting still needs evidence. IMPORTANT: flashing A/B without
  this hook does NOT guarantee TSR is disabled again, because config is
  preserved. Firmware rollback and config rollback are separate tasks;
  an explicit, owner-authorized recovery path must preserve calibration,
  license and all unrelated flags.

## Startup greeting options

1. Replace `adas_activated.wav`: `audios.txt` maps this asset to
   `calib_success`, not a per-boot greeting. The owner reported Vietnamese
   warnings but no greeting after flashing C (2026-10-14), consistent with
   this mapping; the exact event trigger has not been captured at runtime.
   Same swap pattern as warning wavs, no new mechanism. Owner chose to keep
   vendor behavior; no forced calibration or custom per-boot greeting.
2. Hook-triggered fifo play at boot: needs `play_wav_cmd`-style command
   discovery in cardv (RE work, deferred).
3. Replace a oneed system wav (e.g. Record_On): requires extending the
   B-pipeline allowlist to `oneed_cust.es` (new contract exception, deferred).

### Implemented in Candidate F (2026-10-19)

Owner overrode the earlier "no greeting each boot" decision. F adds a detached,
one-shot hook `/customer/c2m/boot_voice.sh` launched from `rcInsDriver.sh`
before the bounded SD mount wait. It uses option 2 above:

- `audioplay 1 dev0 /customer/c2m/Boot_Greeting.wav` into `/tmp/cardv_fifo`
  (the stock-verified command form) plays the Vietnamese greeting;
- `/customer/c2m/c2m-light` reads the stock read-only ISP AE query
  `MI_ISP_AE_QueryExposureInfo(0,0,&info)` and the `LVx10` field at
  `info+0x230`, threshold 500 (the stock `cardv_detect_FCamAEToPWM`
  comparison), median of five samples;
- exactly one reminder is played: dark → `Light_Dark_TurnOn.wav`
  ("Bật đèn xe"), bright → `Light_Bright_TurnOff.wav` ("Tắt đèn khi trời sáng");
- invalid/unknown AE or a missing FIFO/asset ⇒ no advisory (fail-closed);
  the hook logs one status line to `/tmp/c2m_voice_status`.

This shares cardv's audio decoder. The greeting runs early in the stock boot
path (before ADAS service), and arbitration with ADAS startup audio has NOT
been measured. F is voice-only: no C2M headlight output exists or is claimed.
Details and pins: `docs/firmware/CANDIDATE_F_BOOT_VOICE_20261019.md`.

## Vietnamese audio source

The hash-verified VI TAR has now supplied seven changed ADAS wavs; FCW/HMW
remain unchanged. Private assets are in vault `assets/vi-audios/` with
`SHA256SUMS.txt`. Candidate C adds Vietnamese TTS "Đèn xanh" (1128 ms,
PCM16/mono/24 kHz) for the missing traffic-light file. No firmware/audio
bytes are published in the public repo.

Measured from final C wavs: LDW 1579 ms vs listed 1003 ms; PCW 1535 vs 1211;
SAG 1920 vs 1112; VB 1579 vs 1152; calib_success 2261 vs 2047; fail 3925 vs
3562. The VI donor uses the same list despite different wav lengths. Do not
assume the duration field is harmless or that speech is clipped: measure
complete playback and warning preemption first. If list durations need
changing, update `audios.txt` and its md5 line together under an explicit
allowlist; preserve warning priority/loop fields.
