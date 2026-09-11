cmake_minimum_required(VERSION 3.16)
project(c2m_ipu_smoke CXX)
# Private vendor headers/libs are NEVER vendored. Supply via -DC2M_IPU_SDK_DIR=<private dir>
# containing include/mi_ipu.h + lib/libmi_ipu.so etc. Without it, only docs build.
option(C2M_IPU_HAVE_VENDOR_HEADERS "Link against private vendor headers/libs" OFF)
add_executable(c2m-ipu-smoke main.cpp)
target_compile_features(c2m-ipu-smoke PRIVATE cxx_std_11)
if(C2M_IPU_HAVE_VENDOR_HEADERS)
  target_compile_definitions(c2m-ipu-smoke PRIVATE C2M_IPU_HAVE_VENDOR_HEADERS)
  target_include_directories(c2m-ipu-smoke PRIVATE ${C2M_IPU_SDK_DIR}/include)
  target_link_directories(c2m-ipu-smoke PRIVATE ${C2M_IPU_SDK_DIR}/lib)
  target_link_libraries(c2m-ipu-smoke PRIVATE mi_ipu mi_sys)
endif()
