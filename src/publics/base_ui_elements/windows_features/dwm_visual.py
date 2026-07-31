"""Windows 视觉效果相关类"""
import ctypes
import os
import platform
import sys
from ctypes import wintypes

from PyQt5.QtWidgets import QWidget

from publics import profile_mgr, app_logger, funcs

# --- Windows API 常量与定义 ---
WM_SETTINGCHANGE = 0x001A

# --- Win32 / DWM 常量定义 ---
dwmapi = ctypes.WinDLL("dwmapi")
user32 = ctypes.WinDLL("user32")

# DWM 属性 ID
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 11/Win10 20H1+
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # 旧版 Win10，从 1809 版本开始
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT = 1029


class DWMBACKDROPTYPE:
    AUTO = 0
    NONE = 1
    MICA = 2  # Mica (标准云母)
    ACRYLIC = 3  # Acrylic (亚克力)
    MICA_ALT = 4  # Mica Alt (变体云母)


# DWM 边框扩展结构体
class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


# Win7 Aero 结构体
class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("fEnable", wintypes.BOOL),
        ("hRgnBlur", wintypes.HANDLE),
        ("fTransitionOnMaximized", wintypes.BOOL),
    ]


# Win10 Accent Policy 结构体 (用于 Win10 亚克力)
class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("pData", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


# --- 核心兼容函数 ---
def set_dwm_dark_mode(hwnd: int, dark_mode=False):
    """设置窗口深浅色"""
    if sys.platform != "win32":
        return False

    is_dark = ctypes.c_int(1 if dark_mode else 0)
    # 尝试使用新版 ID
    res = dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(is_dark),
        ctypes.sizeof(is_dark)
    )

    # 如果失败，尝试旧版 ID
    if res != 0:
        res = dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(is_dark),
            ctypes.sizeof(is_dark)
        )

    return res == 0


def set_window_backdrop(hwnd: int, backdrop_type=DWMBACKDROPTYPE.MICA, dark_mode=False):
    """
    为 Windows 7/10/11 设置适配的背景材质 (Mica/Acrylic/Aero)

    :param hwnd: 窗口句柄 (int(widget.winId()))
    :param backdrop_type: DWMBACKDROPTYPE 枚举值
    :param dark_mode: 是否启用深色模式风格
    """
    if sys.platform != "win32":
        return False

    # 获取 Windows 构建号
    win_build = int(platform.version().split('.')[-1])

    # 1. 通用操作：扩展 DWM 帧到整个客户区 (防止背景变黑)
    margins = MARGINS(-1, -1, -1, -1)
    dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

    # -------------------------------------------------------------
    # 策略 A: Windows 11 (22H2+, Build >= 22621) -> 使用标准 API
    # -------------------------------------------------------------
    if win_build >= 22621:
        backdrop = ctypes.c_int(backdrop_type)
        res = dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop),
            ctypes.sizeof(backdrop)
        )
        return res == 0

    # -------------------------------------------------------------
    # 策略 B: Windows 11 早期版本 (21H2, Build >= 22000) -> 兼容旧 Mica
    # -------------------------------------------------------------
    elif win_build >= 22000:
        if backdrop_type in (DWMBACKDROPTYPE.MICA, DWMBACKDROPTYPE.MICA_ALT):
            enable_mica = ctypes.c_int(1)
            res = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_MICA_EFFECT,
                ctypes.byref(enable_mica),
                ctypes.sizeof(enable_mica)
            )
            return res == 0
        elif backdrop_type == DWMBACKDROPTYPE.ACRYLIC:
            return _apply_win10_acrylic(hwnd, dark_mode)

    # -------------------------------------------------------------
    # 策略 C: Windows 10 (Build >= 10240) -> 使用 Accent Policy 降级为亚克力
    # -------------------------------------------------------------
    elif win_build >= 10240:
        if backdrop_type != DWMBACKDROPTYPE.NONE:
            return _apply_win10_acrylic(hwnd, dark_mode)

    # -------------------------------------------------------------
    # 策略 D: Windows 7 / 8 -> 降级使用 DWM Aero 玻璃效果
    # -------------------------------------------------------------
    else:
        if backdrop_type != DWMBACKDROPTYPE.NONE:
            bb = DWM_BLURBEHIND()
            bb.dwFlags = 0x00000001  # DWM_BB_ENABLE
            bb.fEnable = True
            bb.hRgnBlur = None
            res = dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))
            return res == 0

    return False


def _apply_win10_acrylic(hwnd: int, dark_mode: bool) -> bool:
    """Win10 专属亚克力材质底层逻辑"""
    try:
        accent = ACCENT_POLICY()
        accent.AccentState = 3  # ACCENT_ENABLE_BLURBEHIND / ACCENT_ENABLE_ACRYLICBLURBEHIND

        # ABGR 格式的叠加遮罩颜色 (半透明黑/白)
        if dark_mode:
            accent.GradientColor = 0x99000000  # 99 为 alpha 透明度
        else:
            accent.GradientColor = 0x99FFFFFF

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.pData = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception as e:
        app_logger.log_exception(e)
        return False


def get_prefer_backdrop_type():
    """
    获取当前操作系统下最适合的窗口方案
    """
    if sys.platform != "win32":
        return DWMBACKDROPTYPE.NONE

    # 获取 Windows 构建号
    win_build = int(platform.version().split('.')[-1])

    if win_build >= 22000:
        # Win11 使用 mica 材质
        return DWMBACKDROPTYPE.MICA
    elif win_build >= 10240:
        # Win10 使用亚克力材质
        return DWMBACKDROPTYPE.ACRYLIC
    elif 9200 <= win_build <= 9600:
        # Win8/8.1 不使用材质
        return DWMBACKDROPTYPE.NONE
    elif 6000 <= win_build <= 7601:
        # Vista/Win7 使用 Aero 特效
        return DWMBACKDROPTYPE.AUTO


def set_widget_background_mode(widget: QWidget):
    """
    根据用户配置为 Qt 窗口设置背景颜色
    """
    backdrop_type_index = [get_prefer_backdrop_type(),
                           DWMBACKDROPTYPE.MICA,
                           DWMBACKDROPTYPE.MICA_ALT,
                           DWMBACKDROPTYPE.ACRYLIC,
                           DWMBACKDROPTYPE.AUTO]

    if os.name == 'nt' and widget.isWindow():
        is_dark = profile_mgr.get_theme_policy() == 2
        bg_config = funcs.get_dict_value_treely(profile_mgr.local_config,
                                                ['theme_settings', 'background'],
                                                profile_mgr.local_config_model['theme_settings']['background'])

        hwnd = int(widget.winId())
        set_dwm_dark_mode(hwnd, is_dark)

        if bg_config['dwm_bg']['enable']:
            widget.setWindowOpacity(1.0)

            bd_type = backdrop_type_index[bg_config['dwm_bg']['mode']]
            set_window_backdrop(hwnd, backdrop_type=bd_type, dark_mode=is_dark)
        else:
            set_window_backdrop(hwnd, backdrop_type=DWMBACKDROPTYPE.NONE, dark_mode=is_dark)

            window_opacity = round(bg_config['common_bg']['window_opacity'] / 100, 2)
            widget.setWindowOpacity(window_opacity)
