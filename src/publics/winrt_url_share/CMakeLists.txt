cmake_minimum_required(VERSION 3.15)

project(ShareBridge)

set(CMAKE_CXX_STANDARD 17)

add_library(
    ShareBridge
    SHARED
    share_bridge.cpp
)

target_compile_definitions(
    ShareBridge
    PRIVATE SHAREBRIDGE_EXPORTS
)

target_link_libraries(
    ShareBridge
    runtimeobject
)