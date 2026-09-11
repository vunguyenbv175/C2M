cmake_minimum_required(VERSION 3.16)
project(c2m_enhanced VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_library(c2m_headers INTERFACE)
target_include_directories(c2m_headers INTERFACE include)
# Host smoke test (needs Linux g++ / clang++ with C++17):
#   cmake -S . -B build && cmake --build build && ./build/smoke_enhance
add_executable(smoke_enhance tests/smoke_enhance.cpp)
target_link_libraries(smoke_enhance PRIVATE c2m_headers)
enable_testing()
add_test(NAME smoke_enhance COMMAND smoke_enhance)
