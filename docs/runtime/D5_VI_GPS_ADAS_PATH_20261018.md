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

## Activation-threshold distinction

The last independently verified all-High postboot snapshot contains `headway_warning_speed_thresh=30` and `ldw_speed_start=60`. The former is named for headway/HMW; the latter is for LDW. The owner's app label is not enough to assign the30 value to every collision-warning branch. FCW-specific gating and units still need traced code/caller evidence. A later attempted live config read did not succeed, so these are explicitly snapshot values, not a claimed fresh live read.

No warning provocation, threshold lowering, fake speed, license/calibration change, UART attach, process restart or deployed repair was performed. Successful settings readback/process presence still do not establish driving warning health.
