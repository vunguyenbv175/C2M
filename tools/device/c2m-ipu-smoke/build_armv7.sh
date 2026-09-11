#!/bin/sh
# build_armv7.sh — cross-build helper (workstation only). Needs private vendor headers/libs.
# Usage: C2M_IPU_SDK_DIR=/path/to/private/sdk sh build_armv7.sh
# Toolchain: arm-linux-gnueabihf-g++ -march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -Os (per TARGET_ABI.md, NO neon).
set -u
: "${C2M_IPU_SDK_DIR:?set C2M_IPU_SDK_DIR to private SDK dir (never committed)}"
CXX="${CXX:-arm-linux-gnueabihf-g++}"
"$CXX" -march=armv7-a -mfloat-abi=hard -mfpu=vfpv3-d16 -Os \
  -DC2M_IPU_HAVE_VENDOR_HEADERS \
  -I"$C2M_IPU_SDK_DIR/include" -I. \
  main.cpp -o c2m-ipu-smoke -L"$C2M_IPU_SDK_DIR/lib" -lmi_ipu -lmi_sys
echo "built: c2m-ipu-smoke (verify with check_elf: interp /lib/ld-linux-armhf.so.3, GLIBC<=2.30, no SIMD)"
