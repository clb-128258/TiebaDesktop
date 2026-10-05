#!/bin/sh
# 编译内置音频解码库（Linux，支持 mp3 与 amr-nb）
#
# 优先使用 cmake 构建；系统内没有 cmake 时退化为直接调用 gcc/g++。
# 编译产物会被拷贝到 src/binres 下，供 Python 通过 ctypes 加载。
set -e

# 脚本自身的目录与产物目录都用绝对路径，避免受当前工作目录影响
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BINRES_DIR="$SCRIPT_DIR/../../binres"

if [ ! -d "$BINRES_DIR" ]; then
    echo "binres directory was not found: $BINRES_DIR" >&2
    exit 1
fi

cd "$SCRIPT_DIR"
mkdir -p build

AMR_INCLUDE="-Iamrnb/oscl -Iamrnb/dec/src -Iamrnb/dec/include -Iamrnb/common/include -Iamrnb/common/dec/include"

if command -v cmake >/dev/null 2>&1; then
    cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    cmake --build . -j
    cd "$SCRIPT_DIR"
else
    echo "cmake not found, fallback to gcc/g++"
    mkdir -p build/obj
    # 内嵌的 opencore-amr 需要按 C 编译（其中使用了 C 的 register 关键字）
    for src in amrnb/common/src/*.cpp amrnb/dec/src/*.cpp amrnb_dec.c; do
        gcc -O2 -std=c11 -fPIC -x c $AMR_INCLUDE -c "$src" -o "build/obj/$(basename "$src").o"
    done
    g++ -O2 -std=c++17 -fPIC -fvisibility=hidden -DTIEBA_AUDIODEC_EXPORTS \
        $AMR_INCLUDE -c tieba_audiodec.cpp -o build/obj/tieba_audiodec.o
    g++ -shared -fvisibility=hidden -o build/libtieba_audiodec.so build/obj/*.o -lm
fi

cp -f "$SCRIPT_DIR/build/libtieba_audiodec.so" "$BINRES_DIR/libtieba_audiodec.so"
echo "Audio decoder has been built: $BINRES_DIR/libtieba_audiodec.so"
