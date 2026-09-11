# ProMax live value parser V1 (bare-table consumers located; control-flow open)

Analysis-only. Addresses as VA + file offsets (memory-map doc).

## Consumer clusters (XL-S3 OTA, HIGH that code reads live keys)

IROM file `0x410948–0x410984` (VA `0x42000948…`): 7+ consecutive DROM words
walking settings keys `…buzzer_enabled/obd_spd_adjust/wifi_ssid_key/…/last_scr`
into `hi/unix` (file `0x410960` → `…last_scr\0hi\0unix`), then CODE words
`0x4216CF9C/0x42085808/0x42085C20/…` — a char* key table with handler tail;
nav keys appended to the config-key block. Structure PARTIAL (entry
size 4B pointer confirmed; key→handler pairing unproven).

IROM file `0x410BB4–0x410C40` (VA `0x42000BB4…`): ~20 DROM words hitting
successive byte positions inside the bare table (`…F7A/F7D/F82/F86/…
/FB1`: `last_scr/hi/unix/nav/spd/…/Overflow`), interleaved with unrelated
literals (`AT SH %s`, PNG `PLTE/tEXt`, `digest/last/bool WebServe`,
`memory leak/IDF`) then CODE words — nearby functions' literal pools, i.e.
MULTIPLE code sites reference live keys (HIGH for consumption, no single
dispatch table).

So the bare keys are: (a) tailed onto a settings key table consumed with
code pointers, and (b) referenced by several functions' literals. Key→field
table (§11): KEY set CONFIRMED; TYPE/DESTINATION/DEFAULT/NULL-behavior/RANGE
all UNKNOWN (no `getInt/getString/getBool/getFloat/isNull` symbols; no
disassembly). Priority order preserved from V3; nothing promoted.

## Parser implementation (§13)

Custom minimal JSON matcher (HIGH, unchanged): escape map `//""\\b.f.n.r.t`,
literals `false/null`, NUL key table, zero cJSON/ArduinoJson/nanopb symbols
in all images. The escape/false/null block is now LINKED to consumer code
(the same IROM pools reference both settings and nav keys), not mere
adjacency — but object-iteration/key-lookup/number-vs-string parsing routines
are unidentified (no control-flow). Classic linkage unproven (pointer method
invalid there).

## Framing/direction/type-discrimination (§14–§15)

Packet boundary (LF vs GATT-write vs length-prefix vs brace-count vs
reassembly), MTU fragmentation, buffer-reset, `Overflow ######` branch:
UNKNOWN (overflow string has consumer refs but no branch recovered).
Whether live objects carry `t/v/type/nav` discriminator vs implicit identity:
UNKNOWN (no live-value bytes exist statically; `hi`+`unix` framing hypothesis
remains LOW). `ping` (phone→HUD?) vs `pong/dev` (HUD→phone?) directions:
UNPROVEN — no notify/write binding.

## Value semantics (§16–§23)

- `spd`: integer-log evidence ONLY — `nav       : %d` + `spd       : %d`
  existed in exactly one commit (60ab7b3, Aug 21 2026) and were removed the
  next commit; HEAD has zero nav-adjacent format strings. Verdict: `%d`
  suggests integer handling at that commit (MEDIUM, transient); wire
  type/range/sentinel/conversions (`*3.6`, clamps) NOT RECOVERED.
- `lim`: unit/sentinels/offset/beep chain NOT RECOVERED.
- `trn`: all 11 meanings UNKNOWN (no switch/jump-table proof).
- `dst/rmin/rkm`: units (m/km), trip-vs-maneuver, rounding NOT RECOVERED.
- `exit` vs `st`: `exit` slot HIGH, `st` want-only with no slot; exit-number
  vs road-text vs motorway-label UNKNOWN; `st` handling UNKNOWN.
- `alrs/avg` (+want-only `avgL`): bit/switch/array semantics UNKNOWN.
- `hi` (new): framing/time-type hypothesis only (LOW); parser→dest→consumer
  trace stops at literal-pool refs. Do NOT expand to heading/highway.
- Missing `st/avgL/lan`: classified — `lan`: UNKNOWN (no slot, no second
  site); `avgL`: UNKNOWN (same); `st`: UNKNOWN (same). None meets
  HANDLED_ELSEWHERE/OPTIONAL_UNUSED/VERSION_ONLY proof bars (no second
  parser/object/alias/binary evidence); all remain UNKNOWN, not optionality
  claims.
- `rate:4` (§24): UNKNOWN (Hz/period/version/profile unproven; no timer
  bound). Stale timeout (§25): UNKNOWN (no `unix`/tick/timeout comparison
  chain; `unix` key is a timestamp candidate only).

## Destination structure (§12)

Base pointer/globals, field offsets/sizes/types: NOT RECOVERED
(OFFSET table withheld rather than invented). Reverse-from-renderer (§27)
attempted via policy keys only; render functions unidentified without
disassembly.
