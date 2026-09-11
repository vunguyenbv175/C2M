# Cross toolchain for the minimal device binary (ARMv7-A hard-float).
# Runner provides: gcc-arm-linux-gnueabihf (ubuntu-24.04 apt).
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
add_compile_options(-march=armv7-a -mfloat-abi=hard -mfpu=neon -Os -Wall -Wextra)
add_link_options(-march=armv7-a -mfloat-abi=hard -mfpu=neon)
