cmake_minimum_required(VERSION 3.16)
project(c2m_idle C ASM)
add_executable(c2m-idle c2m_idle.c)
target_compile_definitions(c2m-idle PRIVATE C2M_IDLE_VERSION="0.1.0-sprint1")
# Dynamic stock-ABI toolchain sets C2M_USE_CUSTOM_START: freestanding _start
# (see start.S) because the runner toolchain's crt1.o would bind
# __libc_start_main@GLIBC_2.34, which the 2.30 device loader rejects.
if(C2M_USE_CUSTOM_START)
  target_sources(c2m-idle PRIVATE start.S)
endif()
