# Cross toolchain for the minimal device binary.
# Evidence-grounded target (docs/firmware/TARGET_ABI.md, decoded stock
# .ARM.attributes: CPU_arch=10/v7, profile 'A', FP_arch=4/VFPv3-D16,
# VFP_args=1, NO Advanced_SIMD tag): ARMv7-A + hard-float + VFPv3-D16.
# NEON is deliberately NOT enabled (no stock evidence for Advanced SIMD).
#
# Static link: removes the target glibc/loader version dependency entirely
# (no PT_INTERP, no NEEDED, no GLIBC version needs — all proven by
# fw/device_minimal/check_elf.py). Tradeoff: larger binary (~0.5-1 MB vs
# ~10 KB dynamic; negligible against the 80 MB customer volume) and no
# shared-lib servicing (irrelevant for a marker/idle daemon).
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
add_compile_options(-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -Os -Wall -Wextra)
add_link_options(-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -static -Wl,-z,noexecstack)
