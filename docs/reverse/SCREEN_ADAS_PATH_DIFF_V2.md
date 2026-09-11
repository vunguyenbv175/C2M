# ADAS / M4 Screen Path Differential V2 — EN vs VI

## Purpose

Test whether the VI regression changed the core stock ADAS-to-screen semantic sender enough to explain the user's observation that ADAS did not operate.

The comparison uses the exact `adas` and `cardv` binaries reconstructed from the original vendor firmware images.

## `cardv` status path

`SendADASInfoToScreen()` is 380 bytes in both cardv builds.

```text
EN @ 0x83184
VI @ 0x9a20c
```

Thumb-2 disassembly shows the executable instruction flow is the same. The PC-relative strings resolve to the same commands in both builds:

```text
ps | grep 'adas --fs' | grep -vE 'sh|grep'
grep 'install_calib_state=2' /customer/minieye/config/calib_de.flag
```

The function therefore mainly derives stock screen ADAS/calibration status from:

```text
is the adas --fs process present?
is install_calib_state=2 present?
```

It is not the full 3D object transport.

## `DeviceSendMsgToScreenTask()`

Both builds keep the same 80-byte task and the same loop/call order:

```text
sleep
WSGetConnectStatus
SendADASInfoToScreen
GetADASStatus
SendGPSInfoToScreen
SendBacklightLevelInfoToScreen
SendDisplayModeToScreen
SendStorageInfoToScreen
SendWifiStatusToScreen
SendAudioRecordStatusToScreen
```

The VI GPS implementation differs elsewhere, but the core screen task does not remove/reorder ADAS status handling.

## ADAS-side `ScreenService`

### Init

```text
ScreenService::Init()
EN @ 0x7deb0, size 120
VI @ 0x7deb0, size 120
```

The function bytes are **exactly identical**.

### Vehicle warning sender

```text
ScreenService::Send<sdk::C1VehicleWarning>
size 584 bytes
```

The executable prefix through offset `0x214` (532 bytes) is byte-for-byte identical.

All 13 EN/VI byte differences occur after that boundary in the trailing literal/data pool.

### Vehicle measurement sender

```text
ScreenService::Send<vector<sdk::C1VehicleMeasureRes>>
size 2112 bytes
```

The executable prefix through offset `0x808` (2056 bytes) is byte-for-byte identical.

All 14 differing bytes are in the final 56-byte literal/data pool.

### Pedestrian sender

```text
ScreenService::Send<vector<sdk::C1PedRes>>
size 2116 bytes
```

The executable prefix through offset `0x80c` (2060 bytes) is byte-for-byte identical.

All 14 differing bytes are in the final 56-byte literal/data pool.

The literal-pool differences are consistent with moved code/rodata targets elsewhere in the executable; they are not executable instruction changes in these sender implementations.

## What this proves

### CONFIRMED

- VI retains the same `cardv` ADAS status polling logic.
- VI retains the same screen-task ordering.
- ADAS `ScreenService::Init()` is byte-identical.
- vehicle-warning, vehicle-measurement and pedestrian ScreenService executable code is byte-identical.
- the checked stock semantic sender implementations were not source-level rewritten in VI.

### Implication

The hypothesis:

```text
"VI ADAS inference works, but the core stock semantic M4 sender implementation was changed/broken"
```

is now lower probability.

This does **not** rule out:

- M4 physical transport/runtime connectivity failure;
- a lower transport/library/runtime issue despite identical sender code;
- `adas` process never reaching ScreenService because startup/input/IPU failed;
- GPS/display additions affecting other screen states;
- incompatible M4 firmware/hardware outside the checked sender functions.

## Strong diagnostic consequence

Because `cardv::SendADASInfoToScreen()` explicitly checks for the `adas --fs` process, a device that shows ADAS inactive on M4 may simply be reflecting that the ADAS process is absent/crashed rather than a changed screen protocol.

Runtime capture should therefore classify process/frame/IPU state before attempting any M4 protocol patch.

## Updated likely order

Combined with:

- identical six CNN model blobs;
- correct VI `m0` offsets;
- byte-identical deep BitAnswer login/feature functions;
- unchanged raw_adas writer contract;

current static priority becomes:

```text
1. kernel/media/memory/frame-path integration
2. runtime startup/config/calibration state
3. same license code acting on different runtime state
4. M4 transport/runtime connectivity only if adas inference is proven alive
5. package interstitial data only if a reader/xref is proven
```

## Next test

Use the existing read-only collector first on known-good EN:

```sh
sh tools/device/collect_baseline.sh en_good_m4_on
```

Then compare M4 disconnected. A VI capture should only be taken when recovery is proven, or use the safer reversible `EN base + VI adas executable` experiment.
