cmake_minimum_required(VERSION 3.15)

project(TiebaCefBridge CXX)

# CEF 从 154 起（实际上更早）就要求 C++20：其头文件使用了 std::convertible_to 等 concepts。
# 用 C++17 编译会报 "<concepts> 仅 C++20 可用" 之类的错误。
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# CEF 官方 Windows 发行版使用静态 CRT（/MT），宿主工程必须保持一致，
# 否则链接阶段会报 LNK2038 "RuntimeLibrary" 不匹配（MT_StaticRelease vs MD_DynamicRelease）。
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "build type" FORCE)
endif()

# CEF 二进制发行版根目录（解压后的完整发行版，需包含 include/、libcef_dll/、Release/ 等）
#
# Windows 示例：
#   cmake .. -A x64 -DCEF_ROOT=D:\cef_binary_xxx_windows64
# Linux 示例：
#   cmake .. -DCEF_ROOT=/opt/cef_binary_xxx_linux64
if(NOT CEF_ROOT)
    message(FATAL_ERROR "请通过 -DCEF_ROOT=<CEF 二进制发行版目录> 指定 CEF")
endif()
get_filename_component(CEF_ROOT "${CEF_ROOT}" ABSOLUTE)

# 新版 CEF 要求通过 find_package 加载自己的 CMake 脚本
# （直接 include(cef_variables.cmake) 会报 "Use find_package(CEF) to load this file."）
list(APPEND CMAKE_MODULE_PATH "${CEF_ROOT}/cmake")
find_package(CEF REQUIRED)

# 编译 CEF 官方的 C++ 封装库 libcef_dll_wrapper。
# 不同版本 CEF 的存放位置不同，这里按常见布局依次尝试；若 find_package 已经
# 提供该 target，则直接复用。
if(NOT TARGET libcef_dll_wrapper)
    if(EXISTS "${CEF_ROOT}/libcef_dll/libcef_dll_wrapper/CMakeLists.txt")
        add_subdirectory("${CEF_ROOT}/libcef_dll/libcef_dll_wrapper"
                         "${CMAKE_BINARY_DIR}/libcef_dll_wrapper")
    elseif(EXISTS "${CEF_ROOT}/libcef_dll/CMakeLists.txt")
        add_subdirectory("${CEF_ROOT}/libcef_dll"
                         "${CMAKE_BINARY_DIR}/libcef_dll_wrapper")
    else()
        message(FATAL_ERROR "找不到 libcef_dll_wrapper 的来源，请检查 CEF 发行版目录结构")
    endif()
endif()

# ---------------------------------------------------------------- 桥接动态库

add_library(cef_bridge SHARED cef_bridge.cpp)
target_include_directories(cef_bridge PRIVATE "${CEF_ROOT}")
target_link_libraries(cef_bridge PRIVATE libcef_dll_wrapper)

# 链接 CEF 本体（Windows 是 libcef.lib，Linux 是 libcef.so）与平台标准库。
# 少了这一步，链接阶段会报一大堆 cef_* 无法解析的外部符号。
if(DEFINED CEF_LIB_DEBUG AND DEFINED CEF_LIB_RELEASE)
    target_link_libraries(cef_bridge PRIVATE
        "$<$<CONFIG:Debug>:${CEF_LIB_DEBUG}>"
        "$<$<NOT:$<CONFIG:Debug>>:${CEF_LIB_RELEASE}>")
elseif(DEFINED CEF_LIBRARY)
    target_link_libraries(cef_bridge PRIVATE ${CEF_LIBRARY})
endif()
target_link_libraries(cef_bridge PRIVATE ${CEF_STANDARD_LIBS})

# 显式指定标准，避免后续被 CEF 的 CMake 脚本覆盖回更低版本
set_target_properties(cef_bridge PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)

if(MSVC)
    target_compile_options(cef_bridge PRIVATE /utf-8 /W1)
    # windows.h（由 CEF 头文件带入）会定义 min/max/LoadString 等宏，破坏 CEF 头文件
    target_compile_definitions(cef_bridge PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
else()
    target_compile_options(cef_bridge PRIVATE -Wall)
endif()

# ---------------------------------------------------------------- 子进程 helper

add_executable(cef_bridge_helper cef_bridge_helper.cpp)
target_include_directories(cef_bridge_helper PRIVATE "${CEF_ROOT}")
target_link_libraries(cef_bridge_helper PRIVATE cef_bridge)
set_target_properties(cef_bridge_helper PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)

if(MSVC)
    set_target_properties(cef_bridge_helper PROPERTIES WIN32_EXECUTABLE TRUE)
    target_compile_definitions(cef_bridge_helper PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)
    # 源文件是 UTF-8（含中文注释），不加 /utf-8 会被按本地代码页解析而出错
    target_compile_options(cef_bridge_helper PRIVATE /utf-8 /W1)
else()
    # Linux 下让 helper 与桥接库、libcef.so 的依赖都用同目录（$ORIGIN）解析
    set_target_properties(cef_bridge cef_bridge_helper PROPERTIES
        BUILD_RPATH "$ORIGIN" INSTALL_RPATH "$ORIGIN")
endif()
