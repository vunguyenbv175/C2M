# Target ABI — derived from stock EN binaries + filesystem (static only)

All claims below are static observations with file+offset evidence. Nothing is
claimed as device-tested.

## 1. CPU / ELF (CONFIRMED, byte-measured)

| fact | evidence |
|---|---|
| 32-bit little-endian ARM EXEC | `build/fw_bin_en/cardv` ELF magic `7f 45 4c 46`, EI_CLASS=1 (32-bit), EI_DATA=1 (LE) @ offset 0; e_type=0x2 (EXEC), e_machine=0x28 (EM_ARM) @ offset 16 |
| same class for adas | `build/fw_bin_en/adas` EI_CLASS=1, EI_DATA=1, e_machine=0x28 (measured same offsets) |
| Application profile, ARM+Thumb-2, VFP | `.ARM.attributes` @ cardv file offset `0x12ae41` (len `0x33`): `aeabi` + `Tag_CPU_arch=0x0A` (ARMv7), `Tag_CPU_arch_profile='A'` (0x41), `Tag_ARM_ISA_use=1`, `Tag_THUMB_ISA_use=2`, `Tag_FP_arch=4`; adas carries the same `aeabi` attribute block (same byte pattern at its own `.ARM.attributes`) |
| ABI/EABI | hard-float EABI: `PT_INTERP` = `/lib/ld-linux-armhf.so.3` (cardv `.interp` @ file `0x154`, also present in adas @ file `0x154`-area `idx=340`); `lib/libc-2.30.so` + `lib/ld-2.30.so` in rootfs cpio |
| libc | glibc 2.30 (`lib/libc.so.6` -> `libc-2.30.so`, `libm-2.30.so`, `libpthread-2.30.so`, `libdl-2.30.so`, `librt-2.30.so` in rootfs file list) |
| compilers observed | cardv `.comment` @ file `0x12ae30`: `GCC: (GNU) 9.1.0`; adas `.comment`: `GCC: (GNU) 9.1.0` + `GCC: (Linaro GCC 4.9-2017.01) 4.9.4` (third-party libs) |
| kernel | modules under `bootconfig/modules/4.9.227/` + `/customer/modules/4.9.227/`; `kernel.es` is a uImage (`27 05 19 56` magic @ offset 0) |

Interpretation (HIGH-CONFIDENCE, not CONFIRMED): ARMv7-A + VFPv3-class SoC
(SigmaStar SSC8838G per image name — chip identity itself is label-only, not
silicon-proven here). Minimum assumption for our own code: `-march=armv7-a
-mfloat-abi=hard -mfpu=neon` builds a compatible static-ish binary; anything
narrower (e.g. armv6, soft-float) is UNSUPPORTED.

## 2. Dynamic loader / runtime libs

- Loader: `/lib/ld-linux-armhf.so.3` (rootfs `lib/ld-linux-armhf.so.3`).
- `LD_LIBRARY_PATH` on device (from rootfs `etc/profile`): `/lib` plus
  `/oneed_cust/UI/lib`, `/customer/wifi/lib`, `/customer/minieye/adas/third_lib`.
- cardv NEEDED (measured from `.dynstr` @ file `0x23594`): `libdl`, `libpthread`,
  `libgcc_s`, `libmi_*` (SigmaStar), `libflow.so`, plus standard `libc`.
- adas NEEDED (string-measured): `libc`, `libm`, `libpthread`, `libgcc_s`,
  `libmi_ipu/sys/scl/ive`, `libflow`, `libringbuf`, `libshared_env`,
  opencv 4.1 set, glog/gflags, `libcam_*_wrapper`.
- Our minimal binary avoids ALL of these: static where possible, else only
  `libc` NEEDED. No `libmi_*`, no `libflow`, no opencv.

## 3. Reproducible cross-build contract

- Source: `fw/device_minimal/c2m_idle.c` (C99, only `<stdio.h>/<unistd.h>`).
- Toolchain file: `fw/device_minimal/toolchain-armhf.cmake`
  (`arm-linux-gnueabihf-gcc`, `armv7-a + hard-float + neon`).
- Behaviour contract (also enforced by CI ELF check, never by execution):
  start -> print `c2m-idle <version>` -> create `/tmp/c2m_idle.marker`
  (best-effort, ignored on failure) -> sleep/idle loop. No socket, no M4,
  no camera, no ADAS, no config write.
- GitHub job `arm-minimal` (`.github/workflows/ci.yml`) builds it with
  `gcc-arm-linux-gnueabihf` on `ubuntu-24.04` and asserts
  `e_machine == EM_ARM (0x28)` + `EI_CLASS == 1` via
  `fw/device_minimal/check_elf.py`. The artifact is labelled
  HOST-CROSS-BUILT, NOT device-tested.
- Minimum compiler assumption: any GCC >= 9 with `arm-linux-gnueabihf`
  target; link defaults to dynamic + hard-float; `-static` is allowed but
  NOT required (glibc-static absent on many runners, so CI uses dynamic).

## 4. UNKNOWN (explicit)

- Exact SoC stepping / FPU variant beyond the attribute bytes above.
- Kernel `.config` / device-tree / partition NAND geometry beyond the
  U-Boot script's `mtdparts` line.
- Whether `ld-2.30` accepts binaries built against newer glibc (we build
  against the runner's glibc — older-symbol compatible by using only
  `printf/sleep/fopen`; `check_elf.py` does NOT prove loader acceptance,
  only class/machine).
