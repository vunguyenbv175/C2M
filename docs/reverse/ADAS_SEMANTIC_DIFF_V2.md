# ADAS Semantic Diff V2 — EN vs VI

## Executive result

The main ADAS executables are substantially closer at the executable-code level than the raw byte diff suggests.

Using same-name dynamic symbols, Thumb-2 disassembly and resolved direct-call/PLT mapping:

```text
comparable functions:     2734
same call sequence:       2731
changed call sequence:       3
```

The three changed call sequences are:

```text
SystemInit(unsigned int)
lane_calib::LaneCalib::get_extrinsic(double)
vehicle::VehicleAlgo::PedProcess()
```

## SystemInit

This is the only function whose reported symbol size changes:

```text
EN 124 bytes
VI 100 bytes
```

Both retain:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

EN then uses the Google/C++ logging path while VI uses a shorter `fwrite` failure path.

**Assessment:** real code delta, but unlikely to explain complete ADAS failure by itself.

## LaneCalib indirect-call delta

All 75 resolved/direct calls are the same. The only call-sequence token difference is:

```text
EN INDIRECT:r4
VI INDIRECT:r7
```

Function size remains 3132 bytes.

**Assessment:** HIGH-CONFIDENCE compiler/register-allocation noise until a decompiler proves a different indirect target.

## PedProcess indirect-call delta

All 201 resolved/direct calls are the same. The only call-sequence token difference is:

```text
EN INDIRECT:r10
VI INDIRECT:r2
```

Function size remains 5508 bytes.

**Assessment:** HIGH-CONFIDENCE compiler/register-allocation noise until proven otherwise.

## Consequence for regression ranking

The code-level result lowers the probability of a broad algorithmic rewrite in the September VI ADAS executable.

Current ranking:

1. **ADAS appended payload/data package** — highest.
2. **Runtime interaction with VI kernel/cardv/config/license** — high.
3. **Small same-sized code/data constant changes not visible in call graph** — medium.
4. `SystemInit` logging refactor — low.

This does not prove that every same-callgraph function is semantically identical. Constants, literal data and branch conditions can change without changing the call sequence. The next analysis should therefore focus on:

```text
appended payload structure
literal/data references
config/license interpretation
raw_adas runtime input
ScreenService runtime output
```

## Reproducibility

Tool:

```text
tools/fw/thumb_callgraph_diff.py
```

Inputs:

```text
EN customer/minieye/adas/adas
VI customer/minieye/adas/adas
```
