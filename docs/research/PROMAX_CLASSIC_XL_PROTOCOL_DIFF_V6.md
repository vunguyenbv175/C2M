# ProMax Classic-vs-XL protocol diff V6 — semantics only

ANALYSIS-ONLY. Compares recovered semantics only (§16); no identity assumed.
Classic = `firmware.bin` @ `fd58197` (ESP32, IDF4/Arduino). XL = `guition_ota_v1.bin`
@ `f678b2c` (ESP32-S3). V6 recovered no new semantics on either side.

| Item | Classic | XL | Verdict |
|---|---|---|---|
| Handshake `pong/dev` JSON block (v1/ping/dev+want+can) | byte-exact block present | byte-exact block present (`guition_ota@0x68AE0`) | SAME (only PROVEN row) |
| UUID roles (service/RX/TX for 8a7e0001/2/3) | UNKNOWN | PARTIAL-structure/UNKNOWN-semantics | UNKNOWN |
| Framing (JSON+LF hypothesis) | UNPROVEN | UNPROVEN | UNKNOWN |
| Nav key set/types/destinations | UNKNOWN | UNKNOWN | UNKNOWN |
| Callback structure (write/notify) | UNKNOWN | UNKNOWN | UNKNOWN |
| Negotiation (dev/want/can/rate) | UNKNOWN | UNKNOWN | UNKNOWN |
| State schema (offsets/types) | UNKNOWN | UNKNOWN | UNKNOWN |
| Display consumer chain | UNKNOWN | UNKNOWN | UNKNOWN |

Net: one SAME (handshake vocabulary block), zero CHANGED proven, remainder
UNKNOWN/untestable without method recovery. XL variants beyond v1 (waveshare/
guition v2, beta channel) were NOT compared — out of scope for this pass.
