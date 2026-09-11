# EN vs VI ADAS Regression — Conclusion Report V1

**Date:** 2026-09-11  
**Repository:** `vunguyenbv175/C2M`  
**Status:** static-analysis conclusion before decisive on-device A/B test

## 1. Executive conclusion

The two vendor firmware packages should now be treated as a **good/bad differential pair**:

```text
EN 2023-08-03 = GOLDEN WORKING BASELINE
VI 2023-09-20 = VENDOR VIETNAM / DONOR / REGRESSION BUILD
```

Real-device ground truth from the same C2M unit is:

```text
VI firmware -> ADAS did not operate
EN firmware -> ADAS operated
```

Static reverse engineering has eliminated or strongly downgraded most obvious explanations.

The current best conclusion is:

> **The VI failure is unlikely to be caused by different AI models, a deliberately changed `raw_adas` writer contract, a rewritten BitAnswer/license implementation, or a rewritten core ADAS-to-M4 semantic sender. The remaining high-value failure surface is runtime integration: process startup, camera/frame availability, IPU/NPU initialization, persistent calibration/config state, and the VI kernel/media/memory environment.**

This is not yet a proof that the VI kernel itself is the root cause. The decisive next test is a reversible run of the **VI `adas` executable on the otherwise working EN base**.

---

## 2. Ground truth and analysis policy

The physical-device observation is stronger than version naming or static strings.

Therefore:

```text
newer != better
VI != baseline
```

All hypotheses are ranked against the known behavior of the user's actual unit.

No destructive full-NAND experiment should be performed while a reversible userspace experiment can answer the same question.

---

## 3. What has been proven NOT to explain the regression

### 3.1 Different CNN/model weights — effectively excluded

The stock `adas` executable contains six embedded model blobs corresponding to:

```text
d0
v_a
v_t
p_r
road
tl
```

`FLAGS_m0` was reverse engineered and decrypted as an AES-128 directory containing six `(offset, size)` pairs.

For EN and VI:

- all six model sizes are identical;
- all six model SHA-256 hashes are identical;
- VI updates the absolute offsets in `m0` correctly.

Therefore:

```text
VI does not contain different CNN weights for these six embedded models.
VI does not contain a simple stale-m0 model-offset bug.
```

Confidence: **CONFIRMED**.

---

### 3.2 Broad ADAS algorithm rewrite — very unlikely

EN and VI `adas` binaries retain the same dynamic-symbol name surface.

The main reported function-size delta is:

```text
SystemInit(unsigned int)
EN 124 bytes
VI 100 bytes
```

Both still execute the important platform initialization sequence:

```text
MI_SYS_Init
MI_SCL_CreateDevice
IPUCreateDevice
```

The visible `SystemInit` difference is primarily a shorter failure-logging path in VI.

Function/call-graph comparison shows the main executable structure is highly stable.

Confidence:

```text
Broad rewrite: LOW probability
Subtle same-size implementation/data changes: still possible
```

---

### 3.3 BitAnswer/license implementation rewrite — strongly downgraded

The license subsystem is real and active, but the major implementation paths checked are unchanged between EN and VI.

The following functions/paths have been shown byte-identical or instruction-equivalent:

```text
Bit_Login
Bit_ReadFeature
Bit_CheckOutSn
Bit_CheckOutFeatures
Bit_SetRootPath
internal BitAnswer dispatcher used by SetRootPath
```

The `/proc/self/exe` reference was also corrected:

```text
/proc/self/exe
    -> obtain current executable path
    -> obtain executable directory
    -> helper can build .bitanswer.volume path
```

It is **not** evidence by itself that BitAnswer hashes the whole `adas` executable or validates the seven high-entropy interstitial regions.

Important distinction:

```text
UNCHANGED LICENSE CODE
!=
IDENTICAL RUNTIME LICENSE STATE
```

A device-specific license/config/calibration state can still cause runtime differences even when code is identical.

Confidence:

```text
Source-level BitAnswer implementation regression: LOW probability
Runtime license/state interaction: still OPEN
```

---

### 3.4 Changed `raw_adas` writer contract — strongly downgraded

`cardv` is the likely camera/media producer feeding the ADAS process through `CRingBuf`.

Both EN and VI retain the same visible producer contract:

```text
CRingBuf endpoint: "raw_adas"
constructor parameters: same
RequestWriteFrame call pattern: same
CommitWrite call pattern: same
```

Normalized executable comparison shows the core logic of:

```text
send(CRingBuf*, StreamPack&)
adas_minieye_send_frame_task(void*)
```

is semantically/instruction equivalent across EN and VI in the executable regions checked.

Therefore:

> A deliberate source-level rewrite of the `raw_adas` writer contract is not a good explanation for the failure.

However, this does **not** prove that frames actually arrive at runtime.

The same writer code can fail because of:

```text
upstream camera producer failure
shared-memory allocation failure
startup-order issue
kernel/media-driver issue
memory-layout issue
runtime configuration
```

Confidence:

```text
Writer-contract change: LOW probability
Runtime frame absence: still HIGH-value suspect
```

---

### 3.5 Core ADAS-to-M4 semantic sender rewrite — strongly downgraded

The ADAS-side screen service retains the same core implementation.

Evidence checked includes:

```text
ScreenService::Init()
vehicle-warning sender
vehicle-measurement sender
pedestrian-result sender
```

The executable code for the main senders is byte-identical; observed differences are in literal pools/address relocation caused by binary layout changes.

`cardv::SendADASInfoToScreen()` is also structurally stable.

This reduces the probability of:

```text
"ADAS inference is fine, but VI accidentally removed the main semantic M4 ADAS output path"
```

There are still real VI display changes, especially GPS/speed/display work, but the core ADAS semantic sender examined did not disappear.

Confidence: **HIGH** that core checked paths were not rewritten.

---

## 4. Real VI changes that remain relevant

### 4.1 Kernel changed

The VI firmware ships a newer kernel payload.

Static compressed-image comparison alone cannot reliably identify the exact semantic kernel delta.

Kernel/runtime behavior therefore remains an important boundary to test on-device.

---

### 4.2 VI adds an 8 MiB framebuffer reserved-memory region

VI bootargs add:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

This is a real memory-layout difference.

Possible relevance:

```text
framebuffer/display allocation
shared-memory pressure/layout
media buffers
IPU/NPU-related contiguous memory interaction
```

No causal link to ADAS failure has yet been proven.

---

### 4.3 `cardv` changed substantially outside the core raw-ADAS writer

VI `cardv` includes deliberate changes concentrated in:

```text
GPS/NMEA parsing
GPS-to-screen behavior
G-sensor handling
power/restart behavior
```

VI adds:

```text
SendGPSSpeedToScreen(int)
```

while the core `raw_adas` writer and checked ADAS status paths remain stable.

This supports the interpretation that the September build was a genuine vendor feature/refactor release, not a simple language-only image.

---

### 4.4 SC7A20 G-sensor driver changed, but not broadly

The SC7A20 driver delta is narrow.

A changed function is:

```text
Gsensor_int2_enable_store()
```

VI adds a call to:

```text
gsensor_clear_interrupt_status_register()
```

and one observed register-value change is:

```text
register 0x32
EN -> 0x02
VI -> 0x08
```

This currently looks more like an INT2/sensitivity behavior fix/refactor than a plausible direct cause of total ADAS failure.

It should not be treated as root cause without runtime evidence.

---

## 5. High-entropy interstitial package regions: corrected interpretation

The VI `adas` file is 17,862 bytes larger.

All six embedded model blobs are unchanged, so the size growth occurs in seven high-entropy interstitial regions around them.

Initially this looked like a strong package-validation suspect.

Further reverse engineering reduced that confidence:

- the plaintext package tail has the same 121 flag names and values except `m0`;
- `m0` is now understood and valid;
- no second plaintext offset field points into those gaps;
- `/proc/self/exe` is not proof of whole-executable validation;
- checked BitAnswer paths are unchanged.

Therefore:

> The seven regions are still structurally interesting, but there is currently no proven reader/validator tying them to the VI failure.

They should no longer be ranked above runtime integration without new xref evidence.

---

## 6. Current failure model

The most plausible remaining failure chain is:

```text
VI kernel / media / memory / startup environment
                |
                v
camera producer / shared frame availability
                |
                v
raw_adas runtime endpoint
                |
                v
ADAS process startup / frame acquisition
                |
                v
IPU/NPU/model initialization
                |
                v
inference + warning/output
```

The externally observed symptom "ADAS not working" can result from failure at any earlier stage.

For example:

```text
adas process absent
adas process restart loop
adas process alive but no raw_adas frames
frame path alive but IPU init fails
inference alive but calibration suppresses warnings
inference alive but output path unavailable
```

Static analysis cannot distinguish these final cases reliably.

---

## 7. Current ranked hypotheses

### R1 — runtime camera/media/memory/startup integration

**Priority: VERY HIGH**

Includes:

```text
raw_adas exists but receives no frames
camera producer starts differently
shared-memory allocation fails
media pipeline startup ordering changes
kernel/media interface mismatch
VI framebuffer reservation affects memory layout
IPU/NPU runtime init fails
```

This category currently has the largest unexplained surface consistent with all static evidence.

---

### R2 — same ADAS code/package interpreted differently because of persistent device state

**Priority: HIGH**

Includes:

```text
calibration
adas.flag / adas_de.flag
produce flags
license/custom info
factory feature profile
per-device provisioning
```

The vendor updater preserves `/customer/minieye/config`, so a pure firmware-provided config difference is not the leading explanation.

But the VI executable can still interpret the same persistent data differently at runtime.

---

### R3 — subtle VI `adas` implementation/package difference not exposed by current static normalization

**Priority: MEDIUM-HIGH**

Although the broad code structure is extremely stable, same-sized functions/data can still differ.

This hypothesis is exactly what the EN-base + VI-adas experiment will test.

---

### R4 — VI kernel/media/driver implementation specifically

**Priority: MEDIUM-HIGH before A/B, potentially #1 after A/B**

Do not jump directly to blaming the kernel before testing the VI userspace binary on EN.

If VI `adas` runs correctly on EN, this category becomes the dominant explanation.

---

### R5 — M4/display-only regression

**Priority: LOW-MEDIUM**

VI definitely contains GPS/display changes, but checked core ADAS screen-service paths remain equivalent.

Only promote this hypothesis if runtime evidence shows inference/warnings internally alive while screen/audio output is absent.

---

### R6 — G-sensor driver change

**Priority: LOW**

The observed SC7A20 delta is narrow and looks like INT2/sensitivity handling.

No direct mechanism has yet been shown that would kill the entire ADAS pipeline.

---

## 8. The decisive experiment

The single most valuable next test is:

```text
KNOWN-GOOD EN SYSTEM

EN kernel
EN cardv
EN modules
EN persistent config/calibration/license
EN camera/media environment

        +

VI adas executable only
```

The VI executable should be launched temporarily/reversibly, not written over the only stock copy.

### Outcome A — VI `adas` fails on EN base

Then focus becomes:

```text
VI adas executable
VI package-specific data
same persistent config interpreted differently
calibration/license/feature validation
subtle same-size function changes
```

Kernel/cardv become much less likely.

### Outcome B — VI `adas` works on EN base

Then focus becomes:

```text
VI kernel
VI media/runtime environment
VI cardv upstream producer state
kernel modules/drivers
memory layout / framebuffer reservation
startup ordering
```

This would be very strong evidence that the ADAS binary itself is not the root cause.

---

## 9. Required safety before the experiment

Before any on-device A/B execution:

```text
1. preserve the working EN `adas` binary;
2. back up /customer/minieye/config read-only;
3. record hashes of EN binaries/config;
4. collect an EN runtime baseline;
5. do not flash bootloader/kernel;
6. do not overwrite NAND just to run the VI executable;
7. ensure a known EN recovery path exists.
```

Existing repo tools should be used first:

```text
tools/device/collect_baseline.sh
tools/device/classify_adas_state.py
tools/device/compare_baselines.py
```

---

## 10. Runtime classification target

The next physical-device session should classify VI behavior into one category:

```text
A. ADAS process absent
B. ADAS process starts then crashes/restarts
C. ADAS process alive but raw_adas/frame input absent
D. frame input alive but IPU/NPU/model init fails
E. inference alive but calibration/warning state suppresses output
F. ADAS internally alive but display/audio output fails
```

Do not use the generic statement "ADAS does not work" after this point; every experiment should identify one of these failure classes.

---

## 11. Product-development consequence

Until the exact VI regression is identified:

```text
EN 2023-08-03 remains the runtime baseline for C2M Enhanced.
VI 2023-09-20 is a donor/reference build, not the base firmware.
```

Useful VI assets/features may still be selectively reused:

```text
Vietnamese audio/localization
region defaults
GPS/display improvements
other safe user-space resources
```

but only after independent validation.

Stock ADAS should be preserved and reused rather than rewritten until the runtime failure boundary is known.

---

## 12. Final conclusion

Current evidence supports the following statement:

> **The VI firmware's ADAS failure is not explained by different AI models, a changed core `raw_adas` writer, a changed main BitAnswer/license implementation, or a changed core ADAS semantic M4 sender. The unresolved failure surface is now concentrated in runtime integration and device state: process startup, frame/media availability, IPU/NPU initialization, calibration/config interpretation, and the newer VI kernel/memory environment.**

The project should not spend more time guessing from version strings.

The next engineering milestone is the reversible **EN base + VI `adas` executable** A/B test, followed by runtime classification A–F.
