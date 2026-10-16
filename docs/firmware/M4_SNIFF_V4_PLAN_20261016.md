# M4 V4 complete-small-payload capture — 2026-10-16

## Deliverable, not another V3 prefix run

V3 hardware safely captured15 packets but every data payload was cut to96B
and no8080 status record was sampled. V4 addresses those observed failures:

- Fixed12s monotonic window, not a count of15 ready polls.
- Capture up to1536 payload bytes, snaplen2048; this covers all108–204B
  payloads actually observed by V3. Larger payloads explicitly truncated.
- Only exact camera `.123`↔M4 `.129` TCP data for services8080/24012/26012
  is stored. ACK-only and unknown traffic still count against work/time.
- Independent per-service16-record/20480-byte quotas prevent fast ADAS data
  exhausting8080's storage quota. These are limits, not delivery guarantees.
- All-receive4096 / all-poll8192 / record48 / text61440B / stdout<65536B
  bounds remain independent. Work/record limits may stop before12s.
- Actual elapsed milliseconds, skipped/quota-skipped counts, per-service counts,
  captured/truncated, direction and seq/ack are retained. No invented bytes.
- Existing receive-only protocol-zero AF_PACKET attach to verified usb0,
  nonblocking receive, ifindex check, no promiscuity/TX/application clients,
  fixed CLI and no camera file/status writer remain unchanged in scope.

Offline decoder `tools/m4/decode_passive_records.py` validates bounded records
and decodes complete WS JSON/libflow MessagePack from only contiguous TCP
bytes. Gaps/truncations/conflicts cannot be patched by guessing. Safe summaries
exclude raw numeric semantic values, coordinates, payload bytes, source strings,
keys, credentials and unknown field names. Complete transport decode is NOT M4
renderer support or an approved replay/injection schema.

## Verification and hardware gate

- Host formatter/parser/selection/quota tests cover full200B payload,1600B
  truncation, snaplen truncation, ACK padding, IP/TCP options, one VLAN tag,
  fragments/invalid headers, null inputs, per-service starvation and byte bounds.
- Offline decoder has synthetic full/concatenated/segmented/gap/retransmission/
  conflict/invalid-framing/privacy tests. No camera used by these tests.
- One manual ARM workflow gates host tests, ABI, pure ARM self-test, stock
  QEMU absent-interface/sentinel path, actual undefined-import no-transmit check,
  then publishes the exact binary to the private vault only.
- New local runner is separately named `build/run_m4_sniff_v4_reviewed.py`;
  default local-only, fails closed until exact source/run/binary/manifest pins.
  V3 runner/bundle not silently repointed. Fresh owner stationary/healthy session,
  IPv4/UUID/host pin, finite active SSH, required current26012+8080 native legs,
  timeout/nice/private RAM lifecycle and pre/post preservation remain mandatory.
- Native V4 capture/parser/quota code and local runner received independent
  static review; no execution blockers found with CI pins intentionally pending.
- Hardware remains untouched while preparation runs. No new SSH window is
  assumed from the prior session. Notify before connecting again; no automatic
  listener restart/extension and no second8080 client.

## Final preparation and hardware result

Manual run `38866208565` PASS on exact source
`43ff7c3dd2de99d47c80c71de50bc822bd9bf90e`; Linux capture8/8 and decoder37/37,
ARM/QEMU/import gates passed. Binary11832B SHA256
`842014346152e2ba21f2604b486ec643de4b80b6bcb08cc642819c6e091fccc4`,
manifest `e959fa1eb167456d547d5a5e9e344ede5e19a900fea01860ccf17dc3b4042cac`.
Private vault `99bfda3fb1bcf3a36162a0100312c0271ded7a86`; local full byte/source/
manifest readback PASS. Owner confirmed reconnected, stationary and normal.

V4 ran once at14:47,12.043s:42 full data records,5646B payload,0 truncated;
exit0 and RAM cleanup verified. **Strict26012 unchanged-connection gate failed**
(client port changed), so not unconditional preservation PASS. No retry or
further device access; owner reported no flicker and original functions normal.
Offline complete server decode recovered39 messages, including10 native
GPSSpeed on8080 and all four known ADAS payload families across24012/26012.
See `M4_SNIFF_V4_HARDWARE_20261016.md` for counts/normalization and remaining
receiver/layout gap. No need for more hardware to finish this sample's decode.

V4 is a diagnostic capture, not production D4 deployment, camera recognition,
3D widget implementation, legal-speed detection or sound delivery. No sign
limit as GPSSpeed, false collision/lane warning or M4 firmware modification.
