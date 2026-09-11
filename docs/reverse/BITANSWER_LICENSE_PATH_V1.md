# BitAnswer / License Path V1 — EN vs VI

## Purpose

Determine whether the EN-working / VI-bad ADAS regression is plausibly caused by a changed BitAnswer/license/package-validation path.

This report corrects an earlier over-interpretation of the `/proc/self/exe` string and now includes exact function-byte comparison of the deep BitAnswer entry points.

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

That local helper appears in a `Host` / `Port` path and handles slash/colon/bracket-style host formatting. It is a networking/address helper, not evidence of package-volume validation.

## `BitAnswer::SetRootPath`

Wrapper:

```text
BitAnswer::SetRootPath(char const*)
  -> Bit_SetRootPath(...)
```

`Bit_SetRootPath` is byte-for-byte identical between EN and VI once the function is extracted at its own symbol boundary:

```text
EN Bit_SetRootPath @ 0x1659ac, size 52
VI Bit_SetRootPath @ 0x165994, size 52
SHA-256(function bytes): identical
```

Both execute the same internal dispatch sequence and use operation value `0x2a`.

## Deep BitAnswer function comparison

The deeper functions most relevant to login and feature gating were extracted by dynamic-symbol address/size and compared directly.

All of the following are **byte-for-byte identical EN vs VI**:

```text
Bit_Login
  size 140 bytes
  EN @ 0x163e2c
  VI @ 0x163e14

Bit_ReadFeature
  size 148 bytes
  EN @ 0x1640ac
  VI @ 0x164094

Bit_CheckOutSn
  size 274 bytes
  EN @ 0x16542c
  VI @ 0x165414

Bit_CheckOutFeatures
  size 292 bytes
  EN @ 0x165654
  VI @ 0x16563c

bit_answer7b8cce65b03d11e5957f4c34888a5b28
  size 180 bytes
  EN @ 0x163d78
  VI @ 0x163d60
```

The consistent address delta is the global `-0x18` layout shift caused by the earlier 24-byte `.text` shrink; the actual bytes in these functions are unchanged.

This is much stronger than a call-graph-only match: the deep login/feature entry points themselves did not change implementation.

## `BitAnswer::Login` wrapper

Both builds retain the same wrapper shape:

```text
if already logged in:
  increment/use existing login state
else:
  call Bit_Login(...)
  on success store login parameters/state
```

Its raw wrapper bytes contain shifted literal/code references, but its target `Bit_Login` implementation is exactly identical.

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
- `Bit_SetRootPath`, `Bit_Login`, `Bit_ReadFeature`, `Bit_CheckOutSn`, `Bit_CheckOutFeatures`, and the tested internal dispatcher are byte-identical EN/VI.
- package tail differs only in `m0`, whose meaning is already understood.

### DOWNGRADED HYPOTHESES

```text
"VI changed the BitAnswer login/feature-check implementation and therefore ADAS died."
```

Static evidence now strongly argues against this.

```text
"The seven changed high-entropy gaps are definitely BitAnswer integrity metadata and make VI fail."
```

There is still no direct static reader/xref proving this.

### STILL OPEN

- same BitAnswer code acting on different device-specific runtime license/custom-info state;
- whether `.bitanswer.volume` is actually used on this SKU through indirect dispatch;
- an as-yet-unidentified opaque reader of package interstitial bytes;
- failures outside license: media/ringbuffer, kernel/IPU, startup ordering, calibration or output path.

## Regression-ranking impact

The static evidence now shifts the leading hypotheses toward runtime integration:

```text
1. kernel/media/memory/frame-path integration
2. runtime startup/config/calibration state
3. same license code receiving different runtime state/data
4. package interstitial metadata only if a real reader/xref is proven
5. deliberate raw_adas writer contract change — already low probability
6. changed BitAnswer login/feature implementation — strongly downgraded
7. different CNN weights/models — effectively excluded
```

## Next work

1. inspect kernel/media/memory delta, especially the VI framebuffer reservation and camera/IPU path;
2. collect EN runtime baseline: `cardv`, `adas`, `raw_adas`, IPU, shared memory, ScreenService;
3. compare VI only with safe recovery, or use reversible `EN base + VI adas` launch;
4. continue searching for a proven reader of the interstitial package bytes before treating them as causal.
