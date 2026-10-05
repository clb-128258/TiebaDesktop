cmake_minimum_required(VERSION 3.15)

project(TiebaAudioDec C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 默认使用 Release 构建，避免忘记指定构建类型时解码性能过低
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "build type" FORCE)
endif()

# 内嵌的 opencore-amr（AMR-NB 解码器）是 2009 年风格的 C 代码，其中使用了 C 的
# register 关键字，因此这些文件统一按 C 编译（而不是按扩展名当 C++ 编译）
file(GLOB_RECURSE AMRNB_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/common/src/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/dec/src/*.cpp")
set_source_files_properties(${AMRNB_SOURCES} PROPERTIES LANGUAGE C)

add_library(
    tieba_audiodec
    SHARED
    tieba_audiodec.cpp
    amrnb_dec.c
    ${AMRNB_SOURCES}
)

target_include_directories(
    tieba_audiodec
    PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/oscl"
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/dec/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/dec/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/common/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/amrnb/common/dec/include"
)

target_compile_definitions(
    tieba_audiodec
    PRIVATE TIEBA_AUDIODEC_EXPORTS
)

if(MSVC)
    target_compile_options(tieba_audiodec PRIVATE /utf-8 /W1)
else()
    # 只导出 marker 标记过的符号，避免符号表污染
    target_compile_options(tieba_audiodec PRIVATE -Wall -fvisibility=hidden)
    target_link_libraries(tieba_audiodec PRIVATE m)
endif()