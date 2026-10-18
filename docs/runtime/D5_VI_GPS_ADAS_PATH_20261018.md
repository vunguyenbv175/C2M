# VI GPS display versus ADAS speed path — 2026-10-18

## Owner evidence and correction

After normal driving with no warnings heard, the owner stopped safely and reported that M4 still shows GPS and its 2D view displays GPS speed. This is meaningful counterevidence to a blanket claim that all camera GPS is absent. It does not by itself measure the freshness or validity of the speed record consumed by ADAS.

Five bounded samples of the documented /tmp/car_info GPS region were all zero (see D5_VI_ADAS_REBOOT_READBACK_20261018.md). This establishes the C2M file-consumer problem, **not that the separate ADAS feed is zero**. Do not repair the antenna, UART or thresholds based only on this file.

## Previously known EN/VI differences

VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md documents EN-only Is_Gps_info/nmea_satinfo/nema_calc_checksum/g_zkw_gps_module and VI-only nmea_BDGSV2info_na/SendGPSSpeedToScreen. SendGPSInfoToScreen changes from112 to92 bytes. These are static differences, not a proven warning-failure cause. Mere existence of SendGPSSpeedToScreen is not evidence of an active implementation: the current VI symbol is only4 bytes; call/branch behavior must be checked rather than inferred from its name.

## Renewed static trace of the pinned VI cardv

The existing extracted cardv has the independently pinned VI identity. Read-only ELF/Capstone analysis was performed locally; no target process memory, vendor observer stream or UART was opened.

- `GpsTask` calls `nmea_parse1` at0x873e8, `GpsSetInfo2Chunk` at0x873f6 and `WriteGpsInfoForCardvUI` at0x87456 on their respective branches. These are separate publication paths; static call presence does not prove runtime branch activity.
- `WriteGpsInfoForCardvUI` copies0x1c0 bytes of nmeaINFO into carInfo+0x330 and calls IPC_CarInfo_Write_PartInfo with offset0x330/length0x1c8. This is the UI file path used by C2M.
- `GpsSetInfo2Chunk` uses a distinct compact object, `gstGpsInfoChuck`: if input signal at+0x20 is nonzero, it converts nmeaINFO speed at+0x58 to an unsigned integer, stores a halfword at compact-record+0x14, and writes validity1 at+0x1d. The invalid branch writes a different sentinel and clears validity. This is a source-level model of the emitted code, not a live sample.
- `GpsGetChunk` copies0x68 bytes from gstGpsInfoChuck to g_gpsInfoChuck_user and returns that compact copy (with additional processing unrelated to this conclusion).
- `adas_mineye_flow_vehicle_task` calls GpsGetChunk at0x7728a. It checks `virtualSpeed`; for its normal-sentinel branch it checks compact-record validity at+0x1d and, when valid, loads speed from+0x14 at0x775cc before float conversion/serialization. Otherwise it writes the literal float65535.0 to the candidate speed field. This invalid fallback is **not zero**; how the downstream ADAS consumer interprets it still needs analysis. No speed override was written.
- `SendGPSInfoToScreen` also calls GpsGetChunk. This supports a shared compact-source relationship with the display path, but it does not prove which 2D renderer/path produced the owner's observation or the downstream ADAS interpretation.

Thus all-zero UI-file GPS and a functioning display can coexist without proving ADAS has no speed. Needed evidence is the compact-record validity/update path and downstream vehicle-speed handling; do not fabricate a speed or consume M4's single-client observer streams to test it.

## Downstream consumer: invalid sender speed is converted to zero

Pinned VI ADAS SHA-256 `997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1` was independently rehashed before ELF analysis. The EN comparison is pinned `0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043`.

- sdk::VehicleInfoRecv::recv unpacks MessagePack keys `speed` and `timestamp`. At0x7e818-0x7e83e it tests abs(float_speed -65535.0)<0.1 and replaces that sentinel with0.0, then stores it at object+8 and refreshes its monotonic arrival timestamp. Thus a stream can be arriving while carrying an invalid speed that becomes zero; arrival freshness alone does not prove valid GPS.
- VehicleInfoRecv::GetResult has an approximately5000ms freshness check and defaults speed to-360.0 when a previously timestamped record is stale. The function also contains separate test_speed and c2l_speed override/cap paths. These were inspected statically only; no override was read from runtime memory or changed. Complete effective-speed attribution requires accounting for these paths and downstream call sites, not only the receiver store.
- RingbufReader::GetFrame calls VehicleInfoRecv::GetResult at0x94d9e and divides the returned km/h float by double3.6 before storing frame speed (0x94db6-0x94dd2). HeadwayWarning constructor reads the exact `headway_warning_speed_thresh` environment key, default30, and divides by3.6 before setting SpeedLine (0xf9d82-0xf9d9c). Input and HMW threshold therefore have a consistent m/s conversion in these traced branches; there is no evidence here of comparing km/h directly against m/s.
- HeadwayWarning::Update stores its speed argument at object+0x40. OnStateOff compares that field against HeadwayWarning::SpeedLine and returns without the transition when speed is lower (0xfa02a-0xfa03c). Consequently **if the receiver's zero is the effective speed reaching this update, threshold30 blocks that HMW transition**. Other target/distance/state gates must also pass; reaching30 does not guarantee a warning.
- FcwState::Update copies FrameInfo+0x14 to speed field+0x28. IsSpeedFitFcw compares it with configured low/high limits, with a distinct <=-99.999 branch that returns true. Invalid-to-zero and stale-negative sentinels therefore must not be conflated. ReloadEnv reads `fcw_warning_speed_threshold` and `fcw_warning_max_speed_threshold` into its low/high fields; the inspected lower-limit default is8.33 and UFCW's `ufcw_min_speed_thresh` default is2.78 (m/s-like values). These defaults are not recovered live overrides. The actual effective FCW limits and all call-site propagation remain to be recovered; the HMW30 result does not establish every warning is blocked.

EN and VI versions of these four examined ADAS functions have the same sizes and recovered floating constants (including65535/0.1/0 and the FCW negative-speed discriminator). This supports a shared branch mechanism but is **not a full instruction/control-flow equality proof**. A VI-specific regression could still be upstream inputs/publication or downstream behavior, rather than these constants.

A synthetic host-only branch model in tools/fw/test_adas_speed_gate_model.py tests sentinel conversion and selected boundaries. It executes no vendor code and uses no private data. It is an explanation/test of the inferred branches, **not live proof that invalid speed caused the observed silence**. A later strictly pinned SSH status attempt timed out; no new live speed-state evidence was obtained and no AP/GPS failure was inferred from the timeout.

## Reconnected read-only follow-up: separate publication branches

Camera reconnected at uptime3555s, same cardv640/adas2069 and logger1117, sample710/card_result0. The regular car_info file is1,050,208 bytes, matching the static carInfo object's size. cardv still holds that file and ttyS1/2; no descriptor was opened through /proc or UART and no process memory was read.

Offline extraction of libIPC_msg.so from both original firmware rootfs archives yielded identical9652-byte libraries, SHA-256 `3e1e82b10dd1d97ab4fdcd807f71f8ce0e149d8ea23475a6cf594c30c36992df`. IPC_CarInfo_Write_PartInfo forwards the supplied length/offset to pwrite. No EN/VI difference was found in this library; matching library bytes do not prove successful runtime writes.

**Important refinement:** in the traced VI GpsTask, the successful-read/parser path calls GpsSetInfo2Chunk at0x873f6, whereas the direct WriteGpsInfoForCardvUI call at0x87456 is reached through poll==0, nmea_zero_INFO and GpsSetInfo2Chunk at0x87440-0x87448. The ordinary parser-success path examined does not directly invoke that file-publication call. Thus the zero file can be a timeout-publication artifact while the compact internal record is updated on a separate path. This invalidates using the file's zero GPS region as sufficient evidence that the internal ADAS source lacks GPS. Other writers/indirect paths and live branch activity remain unverified.

A branch-target-normalized reachable instruction check found the same82/58/35 instruction tokens for GpsSetInfo2Chunk/GpsGetChunk/WriteGpsInfoForCardvUI in EN and VI. GpsTask had413 reachable instructions each and five immediate differences at diagnostic sites; referenced pool/global values are not covered by this token comparison. No complete semantic equivalence claim follows.

Bounded reads of the existing vendor log found four older minieye_msgpack lines with a numeric speed token classified zero. They were unchanged across two reads, located thousands of lines before the tail, and originate from cardv recv_msg (a receive/log path), not automatically the periodic speed sender. They are **not present-time driving-speed telemetry** and may describe another message category. No raw payload, coordinates, timestamp or speed history was printed. Existing logs do not yet distinguish valid live ADAS speed from the invalid-sentinel path.

The vehicle task's static send destination is loopback port23666; its separate receive path uses26013/audio. No connection or extra observer client was opened to either, and no M4 stream was consumed. Further live observation needs a reviewed passive, narrowly filtered diagnostic rather than treating an arbitrary client connection as harmless.

## Bounded passive observation of the existing ADAS vehicle feed

A separate RAM-only observer was prepared/reviewed locally and executed once for at most30 seconds. It uses an AF_PACKET SOCK_DGRAM socket with protocol zero until a mandatory BPF filter is attached, then binds only loopback IPv4/TCP server-source port23666 to127.0.0.1. It never opens a TCP client/listener, UART, process memory or M4 stream, changes interface flags, sends packets or controls services. Additional parser/interface/packet-type checks reject outgoing duplicates, fragments and packets at the8192-byte snap boundary. Limits:1024 received events,1024 packets,65,536 total TCP payload bytes, FIFO-only nonblocking stdout and a30-second SIGALRM backstop. Header/filter tests covered all65,536 source ports plus truncation/options/fragment guards; the ARM binary was built with the previously verified Zig archive and statically inspected, SHA-256 `7159175bedb51c6b526bd20e79d4970fc9c29bdc236dfd76ac215ee18fbd4d9e`. Source/binary/capture remain private scratch, not firmware/release outputs.

The capture completed with596 packets/98,960 bytes and no incomplete pcap tail. Offline TCP reassembly found two complete29,204-byte streams without gaps or conflicting overlaps. Complete WebSocket binary frames and outer MessagePack envelopes were decoded, not merely a byte-pattern search. All frames have the exact static sender topic `MINIEYE.VehicleInfo.v2` and an inner map with exactly speed/timestamp.298 frames per stream had strictly advancing timestamps,100–109ms deltas. A read-only /proc/net/tcp plus process-fd symlink inventory maps one existing peer to adas and the other to lane_postprocess; both received identical stream bytes. No new client was opened.

**Per destination:**10/298 frames carried the65535 invalid-speed sentinel,287 were zero and1 was positive. Numeric speed values, UTC, locations and arbitrary payload were not printed. The zero frames are compatible with the owner's safely stopped state; non-sentinel zero does not independently prove a GPS fix. The brief invalid runs establish intermittent invalid-speed messages on the real ADAS feed, **not persistent GPS failure or an explanation of the earlier moving-drive silence**. Packet arrival does not prove all downstream consumer branches executed.

The observer file was removed and its absence independently checked. cardv/adas/lane PIDs remained640/2069/2070/2071; logger sample904/card_result0/truncated0. Future moving-use evidence, if needed, should use a reviewed bounded class-only logger with no owner app interaction while driving; the existing continuous logger does not already record this internal feed. No driving challenge, fake speed, service restart or repair was performed.

## Activation-threshold distinction

The last independently verified all-High postboot snapshot contains `headway_warning_speed_thresh=30` and `ldw_speed_start=60`. The former is named for headway/HMW; the latter is for LDW. The owner's app label is not enough to assign the30 value to every collision-warning branch. FCW-specific gating and units still need traced code/caller evidence. A later attempted live config read did not succeed, so these are explicitly snapshot values, not a claimed fresh live read.

No warning provocation, threshold lowering, fake speed, license/calibration change, UART attach, process restart or deployed repair was performed. Successful settings readback/process presence still do not establish driving warning health.
