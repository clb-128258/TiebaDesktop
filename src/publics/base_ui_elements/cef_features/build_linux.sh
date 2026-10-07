#!/bin/sh
# 编译 CEF 桥接库与子进程 helper（Linux），并把 CEF 运行时拷贝到 binres/cef。
#
# 用法：
#   CEF_ROOT=/opt/cef_binary_xxx_linux64 ./build_linux.sh
#   ./build_linux.sh /opt/cef_binary_xxx_linux64
#
# 与 Windows 的 run_build.bat 逻辑保持一致：
#   1) 编译桥接库（libcef_bridge.so）与子进程 helper；
#   2) 把这两者拷到 src/binres/cef/；
#   3) 依据 cef_exclude_list.txt，把 CEF 发行版 Release/ 与 Resources/ 下的运行时
#      （libcef.so、*.pak、icudtl.dat、locales/ 等）一起拷到 src/binres/cef/，
#      开发用的头文件、静态库、调试符号等不会被拷进去。
#
# 编译产物：
#   src/binres/cef/libcef_bridge.so
#   src/binres/cef/cef_bridge_helper
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BINRES_DIR="$SCRIPT_DIR/../../../binres"
DEST_DIR="$BINRES_DIR/cef"
EXCLUDE_FILE="$SCRIPT_DIR/cef_exclude_list.txt"

echo "TiebaDesktop CEF bridge builder (linux)"
echo "About CEF: need to use version 109.1.18+gf1c41e4+chromium-109.0.5414.120."

# 与 run_build.bat 一致：优先使用环境变量 CEF_ROOT，没有再用第一个参数
if [ -z "$CEF_ROOT" ]; then
    CEF_ROOT="$1"
fi

if [ -z "$CEF_ROOT" ] || [ ! -f "$CEF_ROOT/include/cef_app.h" ]; then
    echo "CEF_ROOT does not look like a CEF binary distribution: $CEF_ROOT" >&2
    echo "Please set CEF_ROOT (or pass it as the first argument) to the CEF binary distribution directory." >&2
    exit 1
fi

# 转成绝对路径：脚本后面会 cd 到 build 目录，相对路径会失效
CEF_ROOT=$(cd "$CEF_ROOT" && pwd)

if [ ! -d "$BINRES_DIR" ]; then
    echo "binres directory was not found: $BINRES_DIR" >&2
    exit 1
fi

# 归一化路径，日志里就不会出现一串 ..
BINRES_DIR=$(cd "$BINRES_DIR" && pwd)
DEST_DIR="$BINRES_DIR/cef"

cd "$SCRIPT_DIR"
mkdir -p build
cd build

cmake .. -DCMAKE_BUILD_TYPE=Release -DCEF_ROOT="$CEF_ROOT"
cmake --build . -j

cd "$SCRIPT_DIR"

# ---------------------------------------------------------------- 拷贝桥接库
echo "copying cef binary..."
mkdir -p "$DEST_DIR"
# 桥接库必须和 helper、libcef.so 放在同一目录，否则 CEF 子进程会因找不到依赖而启动失败
cp -f "$SCRIPT_DIR/build/libcef_bridge.so" "$DEST_DIR/libcef_bridge.so"
cp -f "$SCRIPT_DIR/build/cef_bridge_helper" "$DEST_DIR/cef_bridge_helper"
chmod +x "$DEST_DIR/cef_bridge_helper"

# ---------------------------------------------------------------- 拷贝 CEF 运行时
# 排除规则与 Windows 的 xcopy /exclude 对齐：
#   - 以分隔符（反斜杠或 /）开头的行按“目录名”匹配，命中整棵目录；
#   - 其余行按文件名/扩展名匹配（例如 .lib 表示所有 *.lib 都不拷贝）。
is_excluded() {
    _path="$1"
    _name=${_path##*/}
    [ -f "$EXCLUDE_FILE" ] || return 1
    while IFS= read -r _pat || [ -n "$_pat" ]; do
        _pat=$(printf '%s' "$_pat" | tr -d '\r')
        [ -z "$_pat" ] && continue
        case "$_pat" in
            \\*|/*)
                _dir=${_pat#\\}
                _dir=${_dir#/}
                _dir=${_dir%/}
                [ -n "$_dir" ] || continue
                case "/$_path/" in
                    *"/$_dir/"*) return 0 ;;
                esac
                ;;
            *)
                _pat=${_pat%\\}
                _pat=${_pat%/}
                [ -n "$_pat" ] || continue
                case "$_name" in
                    *"$_pat"*) return 0 ;;
                esac
                case "$_path" in
                    *"$_pat"*) return 0 ;;
                esac
                ;;
        esac
    done < "$EXCLUDE_FILE"
    return 1
}

copy_cef_tree() {
    _src_root="$1"
    if [ ! -d "$_src_root" ]; then
        echo "  skip (not found): $_src_root"
        return 0
    fi
    echo "  copying $_src_root"
    ( cd "$_src_root" && find . -type f -print ) | while IFS= read -r _rel; do
        _rel=${_rel#./}
        [ -n "$_rel" ] || continue
        if is_excluded "$_rel"; then
            continue
        fi
        _target="$DEST_DIR/$_rel"
        mkdir -p "${_target%/*}"
        cp -f "$_src_root/$_rel" "$_target"
    done
}

if [ ! -f "$EXCLUDE_FILE" ]; then
    echo "WARNING: exclude list not found, the whole runtime will be copied: $EXCLUDE_FILE" >&2
fi

copy_cef_tree "$CEF_ROOT/Release"
copy_cef_tree "$CEF_ROOT/Resources"

echo "CEF bridge has been built:"
echo "  $DEST_DIR/libcef_bridge.so"
echo "  $DEST_DIR/cef_bridge_helper"
echo "  CEF runtime is in $DEST_DIR"
