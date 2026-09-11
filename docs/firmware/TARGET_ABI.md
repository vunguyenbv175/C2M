# Target ABI — derived from stock EN binaries + filesystem (static only)

All claims below are static observations with file+offset evidence. Nothing is
claimed as device-tested.

## 1. CPU / ELF (CONFIRMED, byte-measured)

| fact | evidence |
|---|---|
| 32-bit little-endian ARM EXEC | `build/fw_bin_en/cardv` ELF magic `7f 45 4c 46`, EI_CLASS=1 (32-bit), EI_DATA=1 (LE) @ offset 0; e_type=0x2 (EXEC), e_machine=0x28 (EM_ARM) @ offset 16 |
| same class for adas | `build/fw_bin_en/adas` EI_CLASS=1, EI_DATA=1, e_machine=0x28 (same offsets) |
| EABI v5 + hard-float | e_flags=`0x5000400` on BOTH binaries (top byte `0x05` = EABI v5; bit `0x400` = `EF_ARM_ABI_FLOAT_HARD`; soft bit `0x200` clear) @ offset 36 |
| loader | `PT_INTERP` = `/lib/ld-linux-armhf.so.3` on both (cardv `.interp` @ file `0x154`) |
| libc baseline | glibc 2.30 (`lib/libc.so.6` -> `libc-2.30.so`, `libm-2.30.so`, `libpthread-2.30.so` in rootfs cpio); stock cardv's max `GLIBC_*` version need is `GLIBC_2.29` (parsed `.gnu.version_r`, 10 Verneed entries) — within the 2.30 baseline |
| compilers observed | cardv `.comment` @ file `0x12ae30`: `GCC: (GNU) 9.1.0`; adas `.comment`: `GCC: (GNU) 9.1.0` + `GCC: (Linaro GCC 4.9-2017.01) 4.9.4` (third-party libs) |
| kernel | modules under `bootconfig/modules/4.9.227/` + `/customer/modules/4.9.227/`; `kernel.es` is a uImage (`27 05 19 56` magic @ offset 0) |

## 2. `.ARM.attributes` decode (CONFIRMED — `tools/fw/arm_attributes.py`)

Identical tag set on cardv and adas (cardv block @ file `0x12ae41`, len `0x33`):

```text
== build/fw_bin_en/cardv  e_flags=0x5000400 EI_OSABI=0
  CPU_name='7-A', CPU_arch=10 (v7), CPU_arch_profile=65 ('A'),
  ARM_ISA_use=1, THUMB_ISA_use=2 (Thumb-2), FP_arch=4 (VFPv3-D16),
  ABI_PCS_wchar_t=4, ABI_VFP_args=1, CPU_unaligned_access=1 (+ FP model/align/enum rows)
== build/fw_bin_en/adas  e_flags=0x5000400 EI_OSABI=3
  (same tag set and values)
```

Consequences (binding on our build flags):

- `Tag_CPU_arch=10` + profile `'A'` → `-march=armv7-a`.
- `Tag_FP_arch=4` = **VFPv3-D16** → `-mfpu=vfpv3-d16`. This is the exact,
  most conservative evidence-supported FPU.
- `Tag_ABI_VFP_args=1` + hard-float e_flags → `-mfloat-abi=hard`.
- **`Tag Advanced_SIMD_arch (12) is ABSENT on both binaries` → no stock
  evidence for NEON/Advanced SIMD. NEON is NOT enabled.** An earlier revision
  of this doc/toolchain used `-mfpu=neon` on the assumption that ARMv7-A
  implies it; that assumption is withdrawn (review F2).
- Decoder note: the stock section-length field counts its own 4 length bytes
  (`len(rest)+4`, GNU quirk) — reproduced byte-exactly by the gate unit test.

## 3. Reproducible cross-build contract

- Source: `fw/device_minimal/c2m_idle.c` (C99, only `<stdio.h>/<unistd.h>`).
- Toolchain file: `fw/device_minimal/toolchain-armhf.cmake`
  (`arm-linux-gnueabihf-gcc`, `-march=armv7-a -mfloat-abi=hard
  -mfpu=vfpv3-d16`, `-Os`, `-static`).
- **Static link (deliberate):** removes the target glibc/loader version
  dependency entirely — no `PT_INTERP`, no `DT_NEEDED`, no `GLIBC_*` version
  needs (all three absences are asserted by `check_elf.py`, not assumed).
  Tradeoffs, accepted for this daemon: larger binary (~0.5–1 MB vs ~10 KB
  dynamic — negligible against the 80 MB customer volume); no shared-library
  servicing (irrelevant for a marker/idle process); glibc static NSS/users
  paths unused (the daemon uses only stdio/sleep/file-write).
- Behaviour contract (also enforced by CI ELF check, never by execution):
  start -> print `c2m-idle <version>` -> create `/tmp/c2m_idle.marker`
  (best-effort, ignored on failure) -> sleep/idle loop. No socket, no M4,
  no camera, no ADAS, no config write.
- GitHub job `arm-minimal` (`.github/workflows/ci.yml`, Ubuntu 24.04):
  installs `gcc-arm-linux-gnueabihf` + `ninja-build`, configures with an
  absolute `${{ github.workspace }}` toolchain path and `-G Ninja`, builds,
  records `arm-linux-gnueabihf-gcc --version` + `dpkg-query -W` package
  versions to `toolchain_version.txt`, compiles our TU once more to
  `c2m_idle_check.o` with the same flags, then runs the ELF gate
  (`fw/device_minimal/check_elf.py`, static mode + TU proof). The artifact is
  labelled HOST-CROSS-BUILT, NOT device-tested.
- Known, bounded deviation (measured in CI, not hidden): the final static link
  carries `Advanced_SIMD_arch=1`, merged by the linker from Ubuntu's static
  libc objects (built with the distro default FPU) — NOT from our code. The
  gate proves our TU NEON-free (`tu.no_simd` on `c2m_idle_check.o`,
  `FP_arch=4`, `VFP_args=1`) and records the inherited tag explicitly
  (`--object` + `--allow-libc-simd`; without a passing TU proof the tag still
  FAILs). Residual risk — a static-libc code path emitting NEON on a D16-only
  core — is a hardware-execution question, closed only by the B bring-up boot
  test, and is stated as such.
- Pinning status (honest): the toolchain is **runner-pinned + version-recorded**
  (Ubuntu 24.04 image; exact compiler/package versions logged per build), NOT
  fully pinned — no container digest or apt version lock is in place (review F4).
- Gate unit test `fw/device_minimal/test_check_elf.py` (host, no toolchain or
  firmware needed) locks the attribute interpretation and version comparison
  against the exact measured 51-byte stock attribute block.
- Minimum compiler assumption: any GCC >= 9 with an `arm-linux-gnueabihf`
  target that accepts `-mfpu=vfpv3-d16 -static`.

## 4. Dynamic-link compatibility (reference only, not our build path)

Kept for reviewers auditing stock binaries: `check_elf.py --allow-dynamic`
asserts `PT_INTERP=/lib/ld-linux-armhf.so.3`, `NEEDED ⊆
{libc.so.6, libm.so.6, libgcc_s.so.1}`, and max `GLIBC_*` need ≤ 2.30.
Measured on stock cardv: interp PASS, GLIBC max `GLIBC_2.29` PASS, NEEDED
correctly FAILs the minimal allowlist (cardv links 49 libs incl. `libmi_*` —
proof the gate is not vacuous).

## 5. UNKNOWN (explicit)

- Exact SoC stepping / FPU revision beyond the attribute bytes above.
- Kernel `.config` / device-tree / NAND geometry beyond the U-Boot script's
  `mtdparts` line.
- Whether on-device `ld-2.30` would accept a runner-built dynamic binary
  (moot for the static path, but stated: static removes the question rather
  than answering it).
- Runtime behaviour of any kind — no execution claim until hardware.
