"""Windows 视觉效果相关类"""
import ctypes
import os

from PyQt5.QtWidgets import QWidget

from publics import funcs, profile_mgr

# --- Windows API 常量与定义 ---
WM_THEMECHANGED = 0x031A
WM_SETTINGCHANGE = 0x001A
# DWM 属性 ID
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 11/Win10 20H1+
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # 旧版 Win10，从 1809 版本开始

dwmapi = ctypes.WinDLL("dwmapi")

def set_window_dark_mode(hwnd, enabled: bool):
    """设置窗口标题栏的深色模式"""
    is_dark = ctypes.c_int(1 if enabled else 0)

    # 尝试使用新版 ID
    res = dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(is_dark),
        ctypes.sizeof(is_dark)
    )

    # 如果失败，尝试旧版 ID
    if res != 0:
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(is_dark),
            ctypes.sizeof(is_dark)
        )


def set_widget_dark_mode(widget: QWidget):
    """为 Qt 窗口设置标题栏颜色"""
    if os.name == 'nt' and widget.isWindow():
        is_dark = profile_mgr.get_theme_policy() == 2
        set_window_dark_mode(int(widget.winId()), is_dark)
