"""CEF 组件常量"""
import os
import ctypes
import typing

from PyQt5.QtCore import Qt

IS_WINDOWS = os.name == 'nt'

# 链接库文件
BRIDGE_LIB_NAME = 'cef_bridge.dll' if IS_WINDOWS else 'libcef_bridge.so'
CEF_LIB_NAME = 'libcef.dll' if IS_WINDOWS else 'libcef.so'
HELPER_NAME = 'cef_bridge_helper.exe' if IS_WINDOWS else 'cef_bridge_helper'

# 视频播放页使用的本地虚拟主机名
VIRTUAL_HOST = 'clb.tiebadesktop.localpage.jsplayer'
JS_PLAYER_DIR = os.path.join(os.getcwd(), 'ui', 'js_player')

# 「另存为网页」分块传输的块大小（字符数）
_SAVE_HTML_CHUNK = 40000

# cef 事件回调定义
_EVENT_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_char_p)

# OSR 画面回调
_PAINT_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int)

# browser_id -> CefWebView 的映射表
_WIDGETS: typing.Dict[int, 'CefWebView'] = {}

# HTTP 请求 / 响应回调
# 1 = 请求、2 = 响应，body 仅在回调期间有效
_HTTP_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_char_p,
                                       ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                                       ctypes.c_void_p, ctypes.c_int)


class CefEventType:
    """
    CEF 事件类型
    与 cef_bridge.h 中的 CEF_BRIDGE_EVENT_* 保持一致
    """
    CREATED = 1
    CLOSE = 2
    LOAD_START = 3
    LOAD_END = 4
    LOAD_ERROR = 5
    TITLE = 6
    URL = 7
    STATUS = 8
    BRIDGE_MESSAGE = 9
    NEW_TAB = 10
    FULLSCREEN = 11
    CONSOLE = 12
    COOKIES = 13
    DEVTOOLS_CREATED = 14
    DEVTOOLS_CLOSED = 15
    FAVICON_URL = 16
    FAVICON_DATA = 17
    DOWNLOAD = 18
    RENDER_TERMINATED = 21
    CURSOR = 22
    CONTEXT_MENU = 23


# cef_types.h 指针图标类型到 Qt 光标的映射。
# 只列出常用的类型，未列出的统一回落到普通箭头
_CEF_CURSOR_TO_QT = {
    0: Qt.ArrowCursor,  # CT_POINTER
    1: Qt.CrossCursor,  # CT_CROSS
    2: Qt.PointingHandCursor,  # CT_HAND
    3: Qt.IBeamCursor,  # CT_IBEAM
    4: Qt.WaitCursor,  # CT_WAIT
    5: Qt.WhatsThisCursor,  # CT_HELP
    6: Qt.SizeHorCursor,  # CT_EASTRESIZE
    7: Qt.SizeVerCursor,  # CT_NORTHRESIZE
    8: Qt.SizeBDiagCursor,  # CT_NORTHEASTRESIZE
    9: Qt.SizeFDiagCursor,  # CT_NORTHWESTRESIZE
    10: Qt.SizeVerCursor,  # CT_SOUTHRESIZE
    11: Qt.SizeFDiagCursor,  # CT_SOUTHEASTRESIZE
    12: Qt.SizeBDiagCursor,  # CT_SOUTHWESTRESIZE
    13: Qt.SizeHorCursor,  # CT_WESTRESIZE
    14: Qt.SizeVerCursor,  # CT_NORTHSOUTHRESIZE
    15: Qt.SizeHorCursor,  # CT_EASTWESTRESIZE
    16: Qt.SizeBDiagCursor,  # CT_NORTHEASTSOUTHWESTRESIZE
    17: Qt.SizeFDiagCursor,  # CT_NORTHWESTSOUTHEASTRESIZE
    18: Qt.SizeHorCursor,  # CT_COLUMNRESIZE
    19: Qt.SizeVerCursor,  # CT_ROWRESIZE
    20: Qt.SizeAllCursor,  # CT_MIDDLEPANNING
    21: Qt.SizeAllCursor,  # CT_EASTPANNING
    22: Qt.SizeAllCursor,  # CT_NORTHPANNING
    23: Qt.SizeAllCursor,  # CT_NORTHEASTPANNING
    24: Qt.SizeAllCursor,  # CT_NORTHWESTPANNING
    25: Qt.SizeAllCursor,  # CT_SOUTHPANNING
    26: Qt.SizeAllCursor,  # CT_SOUTHEASTPANNING
    27: Qt.SizeAllCursor,  # CT_SOUTHWESTPANNING
    28: Qt.SizeAllCursor,  # CT_WESTPANNING
    29: Qt.SizeAllCursor,  # CT_MOVE
    30: Qt.IBeamCursor,  # CT_VERTICALTEXT
    31: Qt.CrossCursor,  # CT_CELL
    34: Qt.BusyCursor,  # CT_PROGRESS
    35: Qt.ForbiddenCursor,  # CT_NODROP
    36: Qt.DragCopyCursor,  # CT_COPY
    37: Qt.BlankCursor,  # CT_NONE
    38: Qt.ForbiddenCursor,  # CT_NOTALLOWED
    41: Qt.OpenHandCursor,  # CT_GRAB
    42: Qt.ClosedHandCursor,  # CT_GRABBING
    43: Qt.SizeAllCursor,  # CT_MIDDLE_PANNING_VERTICAL
    44: Qt.SizeAllCursor,  # CT_MIDDLE_PANNING_HORIZONTAL
    47: Qt.DragMoveCursor,  # CT_DND_MOVE
    48: Qt.DragCopyCursor,  # CT_DND_COPY
    49: Qt.DragLinkCursor,  # CT_DND_LINK
}


def cef_runtime_dir() -> str:
    """CEF 运行时目录"""
    if IS_WINDOWS:
        return f'{os.getcwd()}\\binres\\cef'

    return './binres/cef'
