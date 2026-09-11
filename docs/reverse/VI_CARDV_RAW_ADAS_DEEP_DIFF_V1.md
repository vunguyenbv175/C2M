# VI cardv / raw_adas Deep Differential V1

## Verdict

The EN and VI `cardv` binaries differ globally, especially in GPS, G-sensor, restart, and display-facing code, but the recovered `raw_adas` producer helpers and visible ring-buffer call contract are semantically unchanged. A deliberate producer-contract rewrite is therefore **DOWNGRADED**. Whether VI actually produces valid frames at runtime remains **UNKNOWN**.

## Binary identity

```text
EN size: 1,225,780 bytes
EN SHA-256: 344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c

VI size: 1,225,780 bytes
VI SHA-256: 56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23
```

The equal file sizes do not imply binary equality. The SHA-256 values prove different builds.

## Symbol-level delta

The reproducible dynamic-symbol comparison reports:

```text
EN symbols: 4,478
VI symbols: 4,476
Common: 4,474
EN-only: 4
VI-only: 2
Size-changed common functions: 9
```

EN-only symbols:

```text
Is_Gps_info(unsigned char*)
nmea_satinfo(int, _nmeaINFO*)
nema_calc_checksum(unsigned char*, int*)
g_zkw_gps_module
```

VI-only symbols:

```text
nmea_BDGSV2info_na(_nmeaBDGSV*)
SendGPSSpeedToScreen(int)
```

Size-changed functions include GPS parsing, `SendGPSInfoToScreen`, G-sensor handling, system restart, and `minieye_init`. These changes prove VI development in GPS, sensor, power/restart, and display integration. They do not prove a changed camera-frame contract.

Canonical symbol evidence:

```text
docs/reverse/EVIDENCE_CARDV_SYMDIFF.json
```

## Exact raw_adas string evidence

The endpoint token occurs exactly once in each binary:

```text
EN raw_adas file offset: 0xFF340
VI raw_adas file offset: 0xF5794
```

The offset movement reflects changed binary layout. The presence and spelling of the endpoint are unchanged.

Canonical token evidence:

```text
docs/reverse/EVIDENCE_CARDV_CONTRACT.json
```

## Recovered producer API

Both builds import and call the same relevant ring-buffer API:

```text
CRingBuf::CRingBuf(char const*, char const*, int, int, bool, bool)
CRingBuf::RequestWriteFrame(unsigned int, __FRAME_E, __CRB_WRITE_MODE_E)
CRingBuf::CommitWrite(unsigned int, int*, int*)
```

Within `adas_minieye_send_frame_task(void*)`, both builds prepare the same visible constructor semantics and retain the same request/write/commit pattern.

The normalized executable code of these high-value helpers is identical:

```text
send()
adas_minieye_send_frame_task(void*)
```

This is strong static evidence against a deliberate source-level rewrite of the `raw_adas` writer.

## Producer-to-consumer contract

The statically recovered flow is:

```text
camera/media pipeline
  -> cardv producer task
  -> CRingBuf endpoint raw_adas
  -> RequestWriteFrame
  -> copy/populate frame storage
  -> CommitWrite
  -> ADAS ringbuf_vehicle consumer
```

ADAS defaults identify the consumer expectation as:

```text
--camera_input=ringbuf_vehicle
--ringbuf_name=raw_adas
--image_width=1920
--image_height=1440
--vehicle_run_freq=10
```

The endpoint name and visible writer calls align across EN, VI, and the consumer configuration.

## Metadata status

The static comparison proves the API call surface but does not recover or validate all live frame metadata. The following are **UNKNOWN**:

- Pixel format.
- Width and height delivered at runtime.
- Stride and plane layout.
- Buffer length and alignment.
- Physical versus virtual address use.
- Frame type enumeration value.
- Timestamp representation and monotonicity.
- Sequence counters.
- Producer cadence and dropped-frame behavior.
- Cache maintenance and ownership transfer.
- Whether VI allocates the shared ring successfully.
- Whether `cardv` starts the producer task before the ADAS consumer times out.

No report should claim format equality merely from identical normalized helper code.

## Upstream failure modes still consistent with the evidence

Even with unchanged writer helpers, VI can fail to supply ADAS frames if any earlier boundary fails:

1. Sensor probe or stream setup.
2. VIF, ISP, or SCL initialization.
3. Contiguous-memory allocation.
4. Producer-thread creation or scheduling.
5. Runtime feature/config gating.
6. Shared-memory endpoint creation.
7. Frame request starvation.
8. Buffer mapping or cache coherency.
9. Startup-order race.
10. Changed kernel behavior beneath identical user-space libraries.

Each remains **UNKNOWN** without runtime evidence.

## Relevant non-producer cardv changes

VI adds or changes code in these areas:

- GPS sentence parsing.
- GPS speed forwarding to the screen.
- G-sensor sensitivity and power-on-by-interrupt behavior.
- System restart/power control.
- `minieye_init` size.

These changes may be useful donor features, especially Vietnamese-region display/GPS behavior, but they should not be conflated with the frame producer contract.

## Display-path separation

`cardv` also participates in screen integration through functions such as:

```text
SendADASInfoToScreen()
SendGPSInfoToScreen()
SendWifiStatusToScreen()
SendDisplayModeToScreen()
SendStorageInfoToScreen()
SendAudioRecordStatusToScreen()
SendBacklightLevelInfoToScreen()
DeviceSendMsgToScreenTask()
```

VI additionally exposes `SendGPSSpeedToScreen(int)`. A regression in this output path could make internally working ADAS appear inactive. It cannot establish that frame production or inference failed.

The runtime investigation must distinguish:

```text
producer absent
producer present but no frames
frames produced but consumer absent
consumer alive but IPU fails
inference alive but activation gate suppresses warnings
warnings emitted but display/audio path fails
```

## Confidence assessment

### CONFIRMED

- EN and VI `cardv` binaries differ by SHA-256 but have equal size.
- Both binaries contain exactly one `raw_adas` token.
- Both import the same relevant `CRingBuf` API.
- Both retain the same visible constructor and request/commit sequence.
- Normalized `send()` and `adas_minieye_send_frame_task(void*)` code is identical.
- VI contains GPS, G-sensor, restart, and display-related symbol changes.

### DOWNGRADED

- A deliberate VI source-level rewrite of the `raw_adas` writer contract.
- Endpoint renaming as the cause.

### UNKNOWN

- Whether the producer task starts in VI.
- Whether frames reach the writer.
- Exact live metadata and format.
- Whether shared-memory allocation succeeds.
- Whether producer and consumer startup ordering differs.
- Whether kernel/media/memory behavior starves or corrupts the path.

## Required runtime capture

On EN and VI, collect read-only evidence for:

```text
cardv process and thread presence
ADAS process and thread presence
raw_adas IPC/shared-memory objects
producer frame count and cadence
consumer frame count and cadence
frame width, height, stride, format, and byte length
sequence and timestamp values
allocation and mapping failures
VIF/ISP/SCL/IPU logs
process startup timestamps and restart history
```

A compact runtime record should contain at least:

```json
{
  "producer_alive": null,
  "consumer_alive": null,
  "raw_adas_exists": null,
  "frames_per_second": null,
  "width": null,
  "height": null,
  "stride": null,
  "pixel_format": null,
  "frame_bytes": null,
  "timestamp_monotonic": null,
  "allocation_errors": []
}
```

`null` must be retained for values not actually observed.

## Reproduction

From repository root, with `readelf` and `llvm-objdump` available:

```powershell
python tools\fw\cardv_ringbuf_contract.py build\fw_bin_en\cardv build\fw_bin_vi\cardv -o build\cardv_ringbuf_contract.json
python tools\fw\cardv_symdiff.py build\fw_bin_en\cardv build\fw_bin_vi\cardv -o build\cardv_symdiff.json
Get-FileHash -Algorithm SHA256 build\fw_bin_en\cardv,build\fw_bin_vi\cardv
```

Canonical static evidence is stored in:

```text
docs/reverse/EVIDENCE_CARDV_CONTRACT.json
docs/reverse/EVIDENCE_CARDV_SYMDIFF.json
docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json
```

## Conclusion

The strongest producer-side static result is negative: VI did not visibly rename or deliberately rewrite the core `raw_adas` writer contract. The remaining producer hypothesis is operational rather than structural. Upstream media availability, allocation, startup ordering, and actual frame metadata remain **UNKNOWN** and require live read-only capture.