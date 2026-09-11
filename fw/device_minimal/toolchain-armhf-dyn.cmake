# Dynamic variant: stock-loader-compatible minimal binary (P0 preferred path).
# Same evidence-grounded CPU/FPU contract as the static toolchain
# (-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16, NO neon), but dynamically
# linked against the stock loader path with glibc symbol versions pinned by
# glibc_compat.h (max need <= 2.30, proven by check_elf.py --allow-dynamic).
# No -static: the final binary carries ONLY our own objects' attributes, so
# no inherited Advanced_SIMD tag (unlike the static link, which merges
# Ubuntu libc.a attributes). If the gate ever reports a SIMD tag or a
# GLIBC need above 2.30 here, the failure is real and must be fixed, not
# waived — there is no --allow-libc-simd on this path.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
# Freestanding startup (sources coupled in CMakeLists.txt): our own _start
# binds __libc_start_main@GLIBC_2.4; the toolchain crt1.o would bind 2.34.
set(C2M_USE_CUSTOM_START ON CACHE BOOL "use freestanding start.S")
add_compile_options(-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -Os -Wall -Wextra
  -include ${CMAKE_CURRENT_LIST_DIR}/glibc_compat.h)
add_link_options(-march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -nostartfiles -no-pie
  -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 -Wl,--no-undefined -Wl,-z,noexecstack)
