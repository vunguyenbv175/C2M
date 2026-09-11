# BitAnswer / License Path V1 — EN vs VI

## Purpose

Determine whether the EN-working / VI-bad ADAS regression is plausibly caused by a changed BitAnswer/license/package-validation path.

This report corrects an earlier over-interpretation of the `/proc/self/exe` string.

## High-level stock license path

The exported wrapper remains:

```text
LicenseService::Login()
  -> LicenseService::SetRootPath()
  -> BitAnswer::SetRootPath(...)
  -> GetPlatformUuidStr(...)
  -> BitAnswer::SetCustomInfo(...)
  -> BitAnswer::Login(...)
```

The BitAnswer wrapper API also exposes feature read/write/query, check-out/check-in, encrypt/decrypt feature, update/revoke and data-item operations.

## `/proc/self/exe` correction

The only direct `/proc/self/exe` literal reference identified in the BitAnswer code is inside:

```text
EN bit_answer7bbdf7d2b03d11e582834c34888a5b28
   start 0x106128, size 72

VI same symbol
   start 0x106110, size 72
```

Static Thumb-2 disassembly shows this helper does only:

```text
readlink("/proc/self/exe", caller_buffer, ...)
NUL-terminate on success
return read length
```

It does not hash or scan the executable.

A second helper:

```text
EN bit_answer7b36e4f5b03d11e592a84c34888a5b28 @ 0x116430, size 106
VI same symbol @ 0x116418, size 106
```

uses the executable path and truncates it to its directory. The function bytes are identical EN vs VI.

Therefore:

> `/proc/self/exe` is currently evidence of executable-directory discovery, not evidence that the seven interstitial high-entropy regions are validated.

## `.bitanswer.volume`

Another exported 48-byte helper:

```text
EN bit_answer7b36e4f5b03d11e568784c34888a5b28 @ 0x11649c
VI same symbol @ 0x116484
```

performs the following semantic sequence:

```text
get executable directory into caller buffer
append literal ".bitanswer.volume"
return append/copy result
```

The differing raw bytes are explained by shifted PC-relative literal references; the semantic instruction sequence is the same.

No ordinary direct BL caller of this exported helper has yet been found in the main executable. It may be consumed through BitAnswer internal dispatch/function tables or be an exported utility that is not used in this SKU. Do not infer more without a proven xref.

## Important xref correction

Two calls previously noticed near:

```text
EN 0x116c1c and 0x123484
VI 0x116c04 and 0x12346c
```

are **not** calls to the `.bitanswer.volume` builder. They target a local helper immediately following it at:

```text
EN 0x1164cc
VI 0x1164b4
```

That local helper is used in `Host` / `Port` processing and manipulates slash/colon/bracket-like host formatting. It belongs to a networking/address path, not proof of package-volume validation.

## `BitAnswer::SetRootPath`

Wrapper:

```text
BitAnswer::SetRootPath(char const*)
  -> Bit_SetRootPath(...)
```

`Bit_SetRootPath` is instruction-identical between EN and VI after the global `-0x18` layout shift.

```text
EN Bit_SetRootPath @ 0x1659ac, size 52
VI Bit_SetRootPath @ 0x165994, size 52
```

Both execute the same internal dispatch sequence and use the same operation value `0x2a`.

This strongly lowers the probability that the VI regression is caused by a source-level change in the root-path wrapper itself.

## `BitAnswer::Login`

Both builds retain the same wrapper shape:

```text
if already logged in: increment/use existing login state
else:
  call Bit_Login(...)
  on success store login parameters/state
```

Raw bytes differ because code and literal addresses shifted, but the visible call/control-flow shape is unchanged.

The deeper obfuscated `Bit_Login` implementation still needs normalized semantic comparison before the whole license subsystem can be cleared.

## Packaged-tail interaction

The final 3602-byte package tail contains 121 named flags in both builds.

```text
flag names EN = VI: 121/121
all values identical except: m0
```

`m0` has already been proven to encode the six model `(offset,size)` records, and all six referenced model blobs are byte-identical EN vs VI.

No second plaintext packaged-tail pointer/offset field has been found that references the seven interstitial regions.

## Current interpretation

### CONFIRMED

- BitAnswer/license is a real runtime subsystem.
- `/proc/self/exe` helper resolves the current executable path; it does not itself validate executable bytes.
- executable-directory helper is byte-identical EN/VI.
- `.bitanswer.volume` path builder exists in both builds with the same semantics.
- `Bit_SetRootPath` implementation is instruction-identical EN/VI.
- package tail differs only in `m0`, whose meaning is already understood.

### DOWNGRADED HYPOTHESIS

```text
"The seven changed high-entropy gaps are definitely BitAnswer integrity metadata and make VI fail."
```

There is currently no direct static evidence for that statement.

### STILL OPEN

- deeper `Bit_Login` / feature-check implementation differences;
- device-specific license or custom-info behavior at runtime;
- whether `.bitanswer.volume` is used on this SKU through indirect dispatch;
- whether any opaque code path reads package interstitial bytes independently of the known model loader.

## Regression-ranking impact

The static evidence now shifts weight away from a proven package-validation failure and toward runtime integration:

```text
1. runtime frame/media/kernel/memory integration
2. startup/config/calibration/license state on the physical unit
3. deeper Bit_Login/feature-check behavior not yet normalized
4. interstitial package metadata only if a reader/xref is proven
5. deliberate raw_adas writer contract change — already low probability
6. different CNN weights/models — effectively excluded
```

## Next work

1. normalized semantic diff of `Bit_Login` and feature-check internals;
2. runtime EN baseline collector: process, raw_adas IPC, IPU state, ScreenService;
3. compare VI only with safe recovery or use reversible `EN base + VI adas` launch;
4. investigate kernel/media/memory delta, especially the VI framebuffer reservation and upstream camera producer state.
