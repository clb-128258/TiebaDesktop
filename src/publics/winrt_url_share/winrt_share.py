import ctypes
import os
import platform

from PyQt5.QtWidgets import QWidget

from publics import app_logger

dll = None


def init_library():
    """加载相关dll"""
    global dll

    # 在win10以上系统加载
    if not (os.name == 'nt' and int(platform.version().split('.')[-1]) >= 10240):
        app_logger.log_INFO('[ShareBridge loader] ShareBridge will not load on old Windows versions')
        return

    dll = ctypes.WinDLL("./binres/ShareBridge.dll")

    dll.ShareUrl.argtypes = [
        ctypes.c_int64,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
    ]
    dll.ShareUrl.restype = ctypes.c_long

    app_logger.log_INFO('[ShareBridge loader] ShareBridge has been loaded')


def execute_share_window(hwnd: int, url: str, title: str):
    """
    显示分享窗口

    Args:
        hwnd (int): 模态窗口的父句柄
        url (str): 要分享的 URL
        title (str): 分享窗口标题（只在部分系统有效）
    """
    try:
        if not dll:
            raise RuntimeError(f'DLL library has not been loaded')

        hresult = dll.ShareUrl(hwnd, url, title)
        if int(hresult) != 0:
            raise RuntimeError(f'base cpp error: return code {hresult} (hex {hex(hresult)})')
    except Exception as e:
        app_logger.log_exception(e)


def execute_share_window_for_qwidget(widget: QWidget, url: str, title: str):
    """
    为 Qt 窗口显示分享窗口

    Args:
        widget (QWidget): 要显示的 QWidget 窗口
        url (str): 要分享的 URL
        title (str): 分享窗口标题（只在部分系统有效）
    """
    execute_share_window(int(widget.winId()), url, title)
