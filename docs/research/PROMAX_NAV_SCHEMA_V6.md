# ProMax nav schema V6 — final (parser-gated items stay UNKNOWN)

ANALYSIS-ONLY. Source of key vocabulary: handshake block
(`{"v":1,"t":"dev","name":"Promax",...,"want":{"rate":4,"fields":[...]},...}`,
`PROMAX_NAV_STATE_MODEL_V1.md` §1 — intent strings, NOT type/destination proof).

## 1. Key table (KEY/TYPE/DESTINATION/WRITER/READER/SEMANTIC/CONFIDENCE)

| KEY | TYPE | DESTINATION | WRITER | READER | SEMANTIC | CONFIDENCE |
|---|---|---|---|---|---|---|
| unix | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | handshake/ping intent only | UNKNOWN |
| nav | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want`/`can` intent only | UNKNOWN |
| spd | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:spd/can:speed` intent only | UNKNOWN |
| lim | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:lim/can:limit` intent only | UNKNOWN |
| trn | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:trn/can:turn` intent only | UNKNOWN |
| dst | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:dst` intent only | UNKNOWN |
| exit | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:exit` intent only | UNKNOWN |
| eta | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:eta/can:eta` intent only | UNKNOWN |
| rmin | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want` intent only | UNKNOWN |
| rkm | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want` intent only | UNKNOWN |
| avg | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want` intent only | UNKNOWN |
| alrs | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | `want:alrs/can:alerts` intent only | UNKNOWN |
| hi | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | intent unproven | UNKNOWN |

Parser entry: UNKNOWN (V5 neighbourhood only). Framing: JSON+LF HYPOTHESIS
unvalidated (no callback bytes traced). JSON/parser verdict: UNPROVEN.

## 2. Settings vs live nav (§10 decision)

V5 code-class evidence (NVS putInt/begin, Ticker, ESP-log around key
consumers) is consistent with shared key-table machinery (options A/C shape)
but binds no key to a persistence call. Decision: **UNDECIDED (D: association
unresolved)** — options A/B/C/D all open pending callback binding.

## 3. `rate:4`, enums, stale timeout, direction/negotiation

```text
rate:4 meaning:        UNKNOWN (Hz/seconds/interval/param/count/version all unproven)
dev/want/can roles:    producer/consumer/direction/state-changes UNKNOWN (names-only)
turn enum (trn):       UNKNOWN (no switch table decoded)
alert enum (alrs):     UNKNOWN (no switch table decoded)
lane enum (lan):       UNKNOWN (no switch table decoded)
display consumer chain: state-write → render/send UNRECOVERED (no render fn identified)
stale timeout:         UNKNOWN (no millis/Ticker/last_update binding to nav fields)
phone-source role:     UNKNOWN
```
