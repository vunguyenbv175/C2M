# ProMax BLE runtime evidence schema V1

All runtime evidence lives under `PROMAX_BLE_CAPTURE_<YYYYMMDD>/`
(created by `tools/reverse/promax/init_ble_capture_dir.sh`).

## 1. Layout

```text
00_manifest/MANIFEST.txt      session metadata (date/operator/phone/ProMax/app/session id)
01_phone/PHONE_INFO.txt       model, Android version, HCI-toggle + export method used
02_hci/btsnoop_hci.log        RAW capture (never edited) + SOURCE.txt (origin path/method)
03_gatt/DISCOVERY.txt         service/char/descriptor/props/CCCD dump + handles.csv map
04_event_log/event_log.csv    manual T0–T10 log (append-only)
05_packets/table.json         parser output packet table (schema §2)
06_correlation/corr.json      correlator output (schema §3)
07_protocol/FRAMING.txt       framing verdict + field-candidate table + role resolution
08_summary/VERDICT.txt        final RX/TX/roles/level/gate verdicts for the session
```

## 2. Packet table row (`05_packets/table.json`)

```text
index, ts_iso, ts_raw_us, direction(phone_to_air|air_to_phone|UNKNOWN-from-tshark),
hci(CMD|ACL|EVT|...), att_op(0x..), att_op_name(WRITE_REQ|WRITE_CMD|NOTIFY|INDICATE|...),
handle(0x....), uuid(from handles.csv), payload_hex, payload_ascii, acl_handle,
l2cap_cid, note(MTU values, LE-conn-interval, runt/non-ATT flags)
```

Direction glossary (fixed): RX = ProMax receives from phone (== phone_to_air
writes); TX = ProMax sends to phone (== air_to_phone notify/indicate).

## 3. Correlation output (`06_correlation/corr.json`)

```text
packets_used, events, cadence_per_handle[{n, median_gap_s}],
clusters[]: {event, iso_time, packets, per_handle{count, dirs, lengths, uuid}, diffs[]},
candidate_changes[]: {handle, offset, events[], repeat_count, confidence}
```

## 4. Confidence + PROVEN rules

LOW = single observation. CANDIDATE = same (handle,offset) change across ≥2
events (tool-capped; tool never emits PROVEN). PROVEN (human only) = repeated
controlled changes correlate consistently AND direction/framing independently
hold. FRAMING ∈ {PROVEN, PARTIAL, UNKNOWN}; encrypted/compressed payloads →
`PAYLOAD_ENCODING_UNKNOWN`, no guessing. STALE_TIMEOUT ∈ {value/unit, PARTIAL, UNKNOWN}.
