# c2m-warner — on-device offline traffic-sign Warner.
# Host test build:  cmake -B build-host && cmake --build build-host
# Device build:     cmake -B build-arm -DCMAKE_TOOLCHAIN_FILE=../device_minimal/toolchain-armhf-dyn.cmake
#                   cmake --build build-arm
# Then: python3 ../device_minimal/check_elf.py build-arm/c2m-warner
cmake_minimum_required(VERSION 3.16)
project(c2m_warner C ASM)

add_executable(c2m-warner main.c warner.c nmea.c db.c)
target_compile_options(c2m-warner PRIVATE -Wall -Wextra -Os)
target_link_libraries(c2m-warner PRIVATE m)
# Same freestanding _start contract as fw/device_minimal (the toolchain's
# crt1.o would bind __libc_start_main@GLIBC_2.34, rejected by the 2.30 loader).
if(C2M_USE_CUSTOM_START)
  target_sources(c2m-warner PRIVATE ../device_minimal/start.S)
endif()

# host-only unit test
add_executable(test_warner test_warner.c warner.c nmea.c)
target_link_libraries(test_warner PRIVATE m)
enable_testing()
add_test(NAME warner_unit COMMAND test_warner)
