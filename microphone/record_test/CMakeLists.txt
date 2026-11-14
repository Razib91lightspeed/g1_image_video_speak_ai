cmake_minimum_required(VERSION 3.16)
project(g1_record_mic LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

set(SDK "/home/unitree/Desktop/razib/unitree_sdk2_official")
set(LIB "${SDK}/lib/aarch64")
set(DDS "${SDK}/thirdparty/lib/aarch64")

find_package(Threads REQUIRED)

add_executable(g1_record_mic g1_record_mic.cpp)

target_include_directories(g1_record_mic PRIVATE
    "${SDK}/include"
    "${SDK}/thirdparty/include"
    "${SDK}/thirdparty/include/ddsc"
    "${SDK}/thirdparty/include/ddscxx"
)

target_link_libraries(g1_record_mic PRIVATE
    "${LIB}/libunitree_sdk2.a"
    "${DDS}/libddscxx.so"
    "${DDS}/libddsc.so"
    Threads::Threads
)

set_target_properties(g1_record_mic PROPERTIES
    BUILD_RPATH "${DDS}"
)
