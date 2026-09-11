cmake_minimum_required(VERSION 3.16)
project(c2m_idle C)
add_executable(c2m-idle c2m_idle.c)
target_compile_definitions(c2m-idle PRIVATE C2M_IDLE_VERSION="0.1.0-sprint1")
