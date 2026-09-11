# ProMax targeted Xtensa disassembly V5 (rz-asm + Rizin, no Ghidra)

ANALYSIS-ONLY. No firmware/M4/candidates modified. No sniffing. No invented values.
Owner V4 review demanded exactly this: establish working Xtensa disassembly, then
analyze only the anchors (classic `0x3FC82824` + `0x3FC803DF`; XL `0x42000168–9C`,
`0x42000948`, `0x42000BB4`), then stop with recover-or-fail verdicts.

## 1. Environment — ESTABLISHED (first real Xtensa disassembly in this project)

- `Rizin 0.9.1` (winget `Rizin.Rizin`) + `rz-asm -a xtensa -b 32` (Capstone-based,
  "Tensilica Xtensa ... by billow") — CONFIRMED listing in `rz-asm -L`.
- Proven on classic entry `0x40083764`: decodes to valid ESP32 startup
  (`entry a1,0x40`, `l32r`, `call8/callx8`, `movi`, `beqi`) — CONFIRMED.
- Ghidra/IDA absent (no Java); `rizin -q` batch + piped-stdin mapping works
  (fd is 3; `om 3 <vaddr> <len> <fileoff>`); full `aaa` on 1 MB Xtensa exceeds
  10 min — abandoned, replaced by window decode + pattern census below.
- Reusable tooling: `tools/reverse/promax/xtensa_dis.py`,
  `find_entry_prologues.py` (both verified), existing `map_esp_segments.py`.

## 2. Function census (validated pattern, lower bound)

`entry a1,N` = bytes `36 ((N>>3)<<4|1) 00`, verified 6/6 via rz-asm before use.
XL IROM (`0x410018+0x17ADD4`): **9543 entry-a1 candidates** (true function
count higher — other base regs excluded). IROM head `0x410018–0x4124A8`
(~8.5 KB) contains no entry-a1: it is a DATA/descriptor region, not code.
Classic entry-region pattern identical (`36 81 00` = entry a1,0x40).

## 3. XL anchors — decoded

### 3a. 8a7e setup structure (file 0x410188, VA 0x42000168) — PARTIAL

Decoded CODE neighbours are valid BLE-object routines: at `0x4216743C` a
read-modify-write of struct byte `+0x3C` merging a 2-bit field
(`l8ui/and/or/s8i/extui`, property/permission-flag shape); at `0x42167640` a
16-bit unit compare loop (`l16ui/beq/addi 2/j`, UUID/memcmp shape) followed by
an object constructor (zeroes `0x10+` bytes, sets byte0=`0x10`, halfword@2 —
GATT object init shape). Surrounding functions are small Arduino-BLE
accessor wrappers (`l8ui a8,a2,4` / `s8i a4,a2,5`, `call8` into shared
routines). Verdict: registration-adjacent CODE confirmed; which UUID is
service/RX/TX, exact props/permissions/callbacks: still UNKNOWN (no symbols;
call targets unnamed).

### 3b. IROM head descriptor table (file 0x410018–0x410188, VA 0x42000020–90)

91-word dump PROVES a global init/descriptor table: self-pointer + length
header, then repeating (DROM-string, numeric, CODE, DRAM) records —
AlarmAudio/I2S tasks, OBD strings (`IOS-Vlink/18F0/2AF0/2AF1`), IMG strings,
wifi strings, `pong/dev/ping` JSON pointers, and the 8a7e run:

```text
… DROM->"…8a7e0002…" | 0x0000FFF1 (numeric!) | CODE 0x42167668 (the struct-init above)
  | DROM->"…8a7e0003…" | DROM->"…Promax XL…8a7e0001…"
```

So `8a7e0002` is structurally paired with 16-bit id `0xFFF1` and a handler
(`0x42167668`); `8a7e0001/0003` follow as string refs. This is the strongest
role evidence to date (PARTIAL): a registration record exists, but
service-vs-characteristic, properties, and callback semantics remain unlabeled
without symbols or dynamic tracing. String adjacency was NOT used as proof —
co-location inside one pointer table with code/numeric fields was.

### 3c. Live-key consumers (0x42000948, 0x42000BB4) — consumption HIGH, mapping UNKNOWN

Owning code (first entry-a1 after the data region, VA `0x420024B0`) opens with
`l32r a10,[0x42000028]` — a direct load from the descriptor-table head —
then byte-field compare branches; neighbouring routines call into
ESP-log/NVS/Ticker-Preferences paths (literals: `Ticker`,
`/Users/chameleon/.platformio/…`, `r: %d`, `begin`, `putInt`, `nvs_set_i32`,
`movi a12,0x3E8` timeout wrappers). I.e. the code around the key consumers is
settings-persistence/notification plumbing, consistent with the V4 finding
that nav keys ride the same key-table machinery as config keys. No
key→type/destination/default/range edge recovered: no `getInt/getString`
symbols, no store-to-state offsets named. Parser entry: located approximately
(literal-pool neighbourhood), control-flow: NOT recovered.

## 4. Classic anchors — DEFINITIVELY BLOCKED (method ceiling, not absence)

Absolute-LE32 scan over IRAM/IROM/DRAM finds zero refs for 8a7e/dev/bare AND
zero for validator strings (`/config.txt` VA `0x3F480655`, DTBK) — the method
is invalid on the IDF4/Arduino classic build (L32R literal addressing differs
from XL's absolute pools), so classic data-xrefs are UNRECOVERABLE by this
route. Full-analysis (`aaa`) route exceeds practical timeout. Classic roles /
parser / state: UNKNOWN, with the exact Ghidra recipe pinned in
`ghidra_export_xrefs.py` (DROM VAs `0x3FC82824`, `0x3FC803DF`).

## 5. Stop verdicts (recover-or-fail per owner list)

- Service/char roles: FAIL (PARTIAL structure only) — XL record shape recorded.
- Callbacks (write/notify handlers): FAIL — candidates unnamed (`0x42167668`, …).
- Parser entry: PARTIAL — neighbourhood + consumer code class located, flow open.
- Key→type/state mappings: FAIL — no row proven (layout doc stands withheld).
- Display consumer chain: FAIL — render functions unidentified.
- Turn/lane/alert enums, `rate:4`, stale timeout, `hi`, `st/avgL/lan`, phone
  source: unchanged UNKNOWN (no new evidence this pass).
- Recovery level: **LEVEL 2 partial (unchanged)** — framing + XL consumer
  location + descriptor-table shape are new, but no level requires less than
  roles (L1), so the level does not advance. Emulator gate HELD (no live-frame
  extension). Hardware sniff: still USEFUL_LATER per V4 gate (handlers not
  named, control-flow open); the next step remains Ghidra on the now-pinned
  addresses, not capture.

## 6. Highest-confidence new finding

XL IROM-head descriptor table pairing `8a7e0002 ↔ 0xFFF1 ↔ CODE 0x42167668`
inside a global (string, numeric, CODE, DRAM) init table, with neighbouring
code proven to be GATT-object init/comparison routines — the first
code-backed (not string-backed) 8a7e registration evidence.
