# ProMax BLE capture analysis plan V1

PREPARATION ONLY. Pipeline (each step's output feeds the next; stop and record
UNKNOWN rather than bridging gaps by inference):

1. **Parse.** `parse_promax_ble_capture.py` on `02_hci/btsnoop_hci.log`
   (+ `--gatt handles.csv`) → `05_packets/table.json`. Sanity: both directions
   present; ATT WRITE_REQ/CMD + NOTIFY/INDICATE visible; MTU + LE interval noted.
   Empty/trivial output → capture failed, redo session (do NOT reinterpret).
2. **Correlate.** `correlate_promax_nav_session.py table.json event_log.csv`
   (`--offset-s` only with clock-photo justification) → `06_correlation/corr.json`.
   Read: per-event clusters, per-handle cadence, candidate byte diffs.
3. **Framing.** For each ATT-bearing handle: test payload bytes for JSON /
   JSON+LF / newline-delimited / length-prefix / CBOR / msgpack / binary-TLV /
   ASCII key=value / fragmented-JSON. Verdict per handle → `07_protocol/FRAMING.txt`.
   High-entropy/opaque → PAYLOAD_ENCODING_UNKNOWN.
4. **Field deltas.** Around each visual change (speed/limit/turn/distance/ETA/
   alert/start/stop): OLD→NEW per OFFSET/PATH with EVENT/DIRECTION/
   REPEATABILITY → candidate table (schema doc §4). PROVEN only per PROVEN rules.
5. **UUID roles.** Resolve 8a7e0001/2/3 → service/characteristic + properties +
   direction + confidence (schema §2 glossary). RX/TX labels relative to ProMax.
6. **Negotiation.** Search packets for `dev/want/can/rate`: record sender side,
   order, whether `rate:4` appears on air. Names alone prove nothing.
7. **Live keys.** For each of `unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/
   alrs/hi` observed on air: direction, type, example values, correlation,
   cadence, confidence. No static interpretation beyond runtime evidence.
8. **Stale.** From T10: last nav update → last packet → display-clear timestamp
   → disconnect timestamp → STALE_TIMEOUT value/unit/PARTIAL/UNKNOWN.
9. **Verdict.** Write `08_summary/VERDICT.txt`: roles, RX/TX, framing, field
   table status, level reassessment (L3 needs roles+framing+schema proven),
   emulator gate (stays HOLD until direction+framing+core-fields proven AND
   control channels separated), sniff sufficiency.

Replay/emulator/write-injection remain BLOCKED regardless of capture richness
until all four gate conditions hold. One session answers what it answers;
a second controlled session (not a reinterpretation) resolves the rest.
