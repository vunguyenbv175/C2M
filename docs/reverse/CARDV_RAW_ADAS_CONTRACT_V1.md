# CARDV `raw_adas` Ring-Buffer Contract V1 — EN vs VI

## Purpose

Determine whether the VI regression build changed the `cardv` producer contract feeding stock ADAS through the `raw_adas` ring buffer.

This report compares the exact `bootconfig/bin/cardv` binaries recovered from the EN known-good and VI known-bad rootfs images.

## Binary identity

```text
EN cardv
size:    1,225,780 bytes
SHA-256: 344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c

VI cardv
size:    1,225,780 bytes
SHA-256: 56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23
```

## Relevant imported RingBuf API

Both builds import the same functions:

```cpp
CRingBuf::CRingBuf(char const*, char const*, int, int, bool, bool)
CRingBuf::RequestWriteFrame(unsigned int, __FRAME_E, __CRB_WRITE_MODE_E)
CRingBuf::CommitWrite(unsigned int, int*, int*)
```

The corresponding PLT/GOT relocation structure is present in both builds.

## Ring-buffer constructor contract

Inside:

```text
adas_minieye_send_frame_task(void*)
```

both builds prepare the `CRingBuf` constructor with the same semantic arguments.

Resolved PC-relative strings:

```text
r1 -> "fortest"
r2 -> "raw_adas"
```

Other arguments immediately before the constructor call are also identical:

```text
r3       = 0x400
[sp]     = 2
[sp + 4] = 0
[sp + 8] = 0
```

Thus the stock producer still constructs the same named ring-buffer endpoint in VI:

```text
"raw_adas"
```

with the same visible constructor parameters as EN.

Constructor call sites:

```text
EN  0x9d904 -> CRingBuf constructor PLT
VI  0x739ec -> CRingBuf constructor PLT
```

The absolute addresses differ because the VI binary layout changed; the surrounding instruction sequence and constructor arguments do not.

## `send()` helper contract

The helper:

```text
send(CRingBuf*, StreamPack&)
```

contains the actual ring-buffer write sequence.

Before `RequestWriteFrame`, both builds execute the same instructions:

```text
r3 = 1
r2 = 0
r1 = 0x48
r0 = CRingBuf* / this
RequestWriteFrame(...)
```

Call sites:

```text
EN  0x9d358 -> RequestWriteFrame
VI  0x73440 -> RequestWriteFrame
```

The commit path is likewise instruction-identical before the call:

```text
r0 = saved CRingBuf* / this
r1 = 0xffffffff
...same r2/r3 preparation...
CommitWrite(...)
```

Call sites:

```text
EN  0x9d4aa -> CommitWrite
VI  0x73592 -> CommitWrite
```

## Full executable-instruction comparison

A Thumb-2 normalized comparison was performed after replacing relocation-sensitive absolute branch targets with their symbolic targets.

### `send(CRingBuf*, StreamPack&)`

The first **219 normalized instruction records are identical**.

Those 219 instructions are the executable code region:

```text
EN code starts  0x9d330
EN literal pool 0x9d550

VI code starts  0x73418
VI literal pool 0x73638
```

The first normalized mismatch occurs exactly when LLVM begins decoding literal-pool words as if they were Thumb instructions.

Therefore the executable `send()` logic is semantically instruction-identical under this normalization.

### `adas_minieye_send_frame_task(void*)`

The first **874 normalized instruction records are identical**.

The executable region terminates with the same `nop`:

```text
EN  0x9defe nop
VI  0x73fe6 nop
```

Immediately after that is the function-local literal pool:

```text
EN  0x9df00
VI  0x73fe8
```

The literal values differ because code/rodata addresses moved in the VI build, but the executable instruction sequence before the pool is identical after target normalization.

## What this proves

### CONFIRMED

```text
VI still constructs a CRingBuf endpoint named raw_adas.
EN and VI use the same visible constructor arguments.
EN and VI execute the same RequestWriteFrame call pattern.
EN and VI execute the same CommitWrite call pattern.
The normalized executable code of send() is identical.
The normalized executable code of adas_minieye_send_frame_task() is identical.
```

### Strong implication

A deliberate source-level rewrite of the `raw_adas` writer is now a **low-probability** explanation for the VI ADAS failure.

This does not prove frames actually arrive at runtime. The producer can still fail because of:

```text
upstream camera/frame availability
shared-memory/ring-buffer library behavior
process startup ordering
kernel/media driver behavior
memory allocation/layout
runtime configuration
```

Those require runtime evidence.

## Updated regression ranking

Given this result plus the identical six embedded ADAS model blobs:

```text
1. VI adas self-package/interstitial metadata or validation path
2. runtime startup/config/license/calibration interpretation
3. upstream runtime frame availability despite unchanged writer code
4. kernel/media/memory integration
5. GPS/M4 output refactor if inference is alive but invisible
```

The hypothesis:

```text
"VI cardv intentionally changed the raw_adas writer contract"
```

should be downgraded substantially.

## Reproduction

Use:

```sh
python3 tools/fw/cardv_ringbuf_contract.py \
  cardv_EN cardv_VI \
  -o cardv_ringbuf_contract.json
```

Dependencies:

```text
readelf
llvm-objdump
```

The tool maps ARM PLT stubs back to `.rel.plt`, resolves nearby PC-relative constructor strings, records CRingBuf calls and reports normalized equal-instruction prefixes.

## Next runtime check

On the physical EN baseline, verify that:

```text
cardv is alive
adas is alive
raw_adas-related IPC/shared-memory objects exist
ScreenService :26012 is present
```

Then run the same read-only baseline on VI only when recovery is proven.

If the writer code is unchanged but `raw_adas` runtime evidence disappears on VI, investigate the upstream producer/kernel/media boundary rather than patching this writer function.
