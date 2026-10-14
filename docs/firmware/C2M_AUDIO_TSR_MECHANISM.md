# C2M audio + TSR mechanisms (stock EN static evidence, 2026-10-14)

All paths below are IMAGE-RELATIVE (`/customer/...` on device). No device
shell was used; no firmware built yet.

## Audio playback path

- ADAS does NOT play sound itself: the `adas` binary has no wav/alsa/fifo
  strings, only `--audio_list_file=audios.txt`. Playback is done by `cardv`
  (which references `/oneed_cust/audio/*.wav` system sounds and the
  `play_wifi_voice` / `play_wav_cmd` fifo commands).
- `/minieye/adas/audios.txt` maps warning IDs to wav files:
  `fcw/hwm/vb/stop_and_go/ldw/pcw/fail/calib_success/tlr_green_on`, with
  duration-ms, privilege and loop fields. `tlr_green_on.wav` is listed but
  MISSING from the image (traffic-light audio slot exists, file absent).
- WAV format (checked `adas_activated.wav`): RIFF/WAVE, PCM16, mono,
  24000 Hz. Replacements must use the same encoding.
- Integrity: `adas_checksum.sh` (`md5sum -c md5sum.txt`) has NO caller in
  the boot path (stock boots fine despite the missing tlr wav), so it is
  treated as legacy/dead — PROVEN further 2026-10-14: stock `md5sum.txt`
  lines for FCW/HMW/LDW do not match the shipped file bytes either
  (e.g. FCW listed `08998a0f…`, file md5 `c61c15d8…`, byte-identical across
  EN/B4/C images), yet stock ADAS runs. Any wav/audios.txt change must still
  update `md5sum.txt` for consistency (`md5sum.txt` lists run.sh, audios.txt
  and all wavs, but not itself); vendor-stale lines for untouched files are
  preserved verbatim. `adas_checksize.sh` checks SIZES from
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
  (base64/md5sum/sed). Rollback = flash without the hook change; device
  config untouched by hand.

## Startup greeting options

1. Replace `adas_activated.wav` (plays at every ADAS activation — the
   effective startup moment). Same swap pattern as warning wavs, no new
   mechanism. RECOMMENDED.
2. Hook-triggered fifo play at boot: needs `play_wav_cmd`-style command
   discovery in cardv (RE work, deferred).
3. Replace a oneed system wav (e.g. Record_On): requires extending the
   B-pipeline allowlist to `oneed_cust.es` (new contract exception, deferred).

## Vietnamese audio source

No VI TAR is available locally (vault holds EN only); the VI donor wavs
documented in `08_AUDIO_VIETNAM_LOCALIZATION.md` cannot be extracted until
a VI image is obtained. Practical sources: owner-recorded voice (phone mic
is fine) or TTS, converted to PCM16/mono/24kHz. Keep each clip within the
original duration OR update `audios.txt` duration + `md5sum.txt` together.
