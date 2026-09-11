cmake_minimum_required(VERSION 3.16)
project(c2m_enhanced VERSION 0.2.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(MSVC)
  add_compile_options(/W4 /WX)
else()
  add_compile_options(-Wall -Wextra -Werror)
endif()

add_library(c2m_headers INTERFACE)
target_include_directories(c2m_headers INTERFACE include)

# Gate D: real daemon skeleton (host/mock/read-only).
add_executable(c2m-enhance src/enhance/main.cpp)
target_link_libraries(c2m-enhance PRIVATE c2m_headers)

# Host smoke covering EF-A01..A04+A06 + F1 read-only gate.
add_executable(smoke_enhance tests/smoke_enhance.cpp)
target_link_libraries(smoke_enhance PRIVATE c2m_headers)

enable_testing()
add_test(NAME smoke_enhance COMMAND smoke_enhance)
add_test(NAME c2m_enhance_tick COMMAND c2m-enhance --scenario fcw --ticks 3 --period-ms 1)
