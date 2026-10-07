#!/bin/sh
# TiebaDesktop 统一编译脚本（Linux）。
#
# 用法（在任意目录下执行都可以）：
#   bash src/build-all.sh                              # 只编译音频解码库
#   bash src/build-all.sh /opt/cef_binary_xxx_linux64   # 顺便编译 CEF 桥接库
#
# 与 Windows 的 src/build-all.bat 对应，差别是：
#   - winrt_url_share（WinRT 分享桥）是 Windows 专属组件，Linux 下没有对应实现，自动跳过；
#   - CEF 目录既可以作为第一个参数传入，也可以事先设置环境变量 CEF_ROOT；
#     两者都没有时不编译 CEF（沿用源码树里已经编译好的桥接库）。
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CEF_ARG="$1"

echo "TiebaDesktop Total C++ Builder (linux)"
echo "NOTICE: make sure cmake and a C++ compiler (gcc/g++) are installed."
echo "About CEF: need to use version 109.1.18+gf1c41e4+chromium-109.0.5414.120 and provide built path as the first arg for this script."

# ---------------------------------------------------------------- 1) 内置音频解码库（mp3 + amr-nb）
bash "$SCRIPT_DIR/publics/audio_decoder/build_linux.sh"

# ---------------------------------------------------------------- 2) winrt_url_share（Windows 专属）
echo "winrt_url_share is windows only, skipped"

# ---------------------------------------------------------------- 3) CEF 桥接库（可选）
if [ -z "$CEF_ARG" ] && [ -z "$CEF_ROOT" ]; then
    echo "CEF build skipped"
else
    if [ -n "$CEF_ARG" ]; then
        CEF_ROOT="$CEF_ARG" bash "$SCRIPT_DIR/publics/base_ui_elements/cef_features/build_linux.sh"
    else
        bash "$SCRIPT_DIR/publics/base_ui_elements/cef_features/build_linux.sh"
    fi
fi

echo "ALL builds complete."
