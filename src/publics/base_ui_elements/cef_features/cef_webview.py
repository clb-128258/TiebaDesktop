"""
基于 CEF 的跨平台 WebView 实现（Windows / Linux 通用）。

运行所需文件（由 cef_features 的构建脚本生成 / 从 CEF 发行版拷贝）：
    binres/cef_bridge.dll            或 binres/libcef_bridge.so      本项目编译的桥接库
    binres/cef/cef_bridge_helper     或 cef_bridge_helper.exe        CEF 子进程 helper
    binres/cef/libcef.dll            或 libcef.so                    CEF 本体
    binres/cef/ 下的 *.pak、icudtl.dat、locales/、resources/、swiftshader/ 等资源
"""
import base64
import ctypes
import functools
import http.server
import json
import math
import os
import sys
import threading
import time
import typing

from PyQt5.QtCore import (pyqtSignal, pyqtSlot, Qt, QUrl, QTimer, QEvent, QMetaObject,
                          QThread, QAbstractNativeEventFilter, QLocale, QPoint)
from PyQt5.QtGui import QColor, QCursor, QIcon, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QFileDialog, QApplication, QMenu, QActionGroup

from publics import app_logger
from publics.base_ui_elements.common_webview import WebViewProfile
from publics.base_ui_elements import base_ui

IS_WINDOWS = os.name == 'nt'

BRIDGE_LIB_NAME = 'cef_bridge.dll' if IS_WINDOWS else 'libcef_bridge.so'
CEF_LIB_NAME = 'libcef.dll' if IS_WINDOWS else 'libcef.so'
HELPER_NAME = 'cef_bridge_helper.exe' if IS_WINDOWS else 'cef_bridge_helper'

# 视频播放页使用的本地虚拟主机名（与 Windows 端 WebView2 保持一致）
VIRTUAL_HOST = 'clb.tiebadesktop.localpage.jsplayer'
JS_PLAYER_DIR = os.path.join(os.getcwd(), 'ui', 'js_player')

# 「另存为网页」分块传输的块大小（字符数）
_SAVE_HTML_CHUNK = 40000

# 销毁 CEF 浏览器时，Chromium 会往顶层窗口 Post 一个 WM_CLOSE，需要临时屏蔽
_WM_CLOSE = 0x0010
_PM_REMOVE = 0x0001
# 用户主动关闭窗口（标题栏 X / Alt+F4 / 任务栏 / 系统菜单）会先发 WM_SYSCOMMAND(SC_CLOSE)，
# 之后才产生 WM_CLOSE；Chromium 补发的那条是裸的 PostMessage(WM_CLOSE)。
# 用这一点区分「用户要关窗」和「CEF 的残留消息」，避免把用户自己的关闭请求也吞掉。
_WM_SYSCOMMAND = 0x0112
_SC_CLOSE = 0xF060
_USER_CLOSE_GRACE_SECONDS = 1.0
# 关闭守卫：销毁 CEF 窗口后，Chromium 会往宿主顶层窗口补发一个 WM_CLOSE，
# 派发时机不定（实测 1~2 秒，页面复杂时更久），所以要一直挂到真的拦到它为止；
# 超时上限只是兜底。用户主动关窗会先来 WM_SYSCOMMAND(SC_CLOSE)，检测到就立刻撤守卫，
# 因此长时间挂着也不会再挡用户自己的关闭操作。
_CLOSE_GUARD_MAX_MS = 30000


class _WinMsg(ctypes.Structure):
    _fields_ = [('hwnd', ctypes.c_void_p), ('message', ctypes.c_uint),
                ('wParam', ctypes.c_size_t), ('lParam', ctypes.c_ssize_t),
                ('time', ctypes.c_uint), ('pt_x', ctypes.c_long),
                ('pt_y', ctypes.c_long)]


_EVENT_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_char_p)
# OSR 画面回调：buffer 为 BGRA（物理像素），只在回调期间有效
_PAINT_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int)

# browser_id -> CefWebView
_WIDGETS: typing.Dict[int, 'CefWebView'] = {}

# HTTP 请求 / 响应回调：kind 1 = 请求、2 = 响应；body 仅在回调期间有效
_HTTP_CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_char_p,
                                       ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                                       ctypes.c_void_p, ctypes.c_int)


class CefEventType:
    # 与 cef_bridge.h 中的 CEF_BRIDGE_EVENT_* 保持一致
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


# OSR 光标：cef_cursor_type_t（见 CEF 头文件 cef_types.h）到 Qt 光标的映射。
# 只列出常用的类型，未列出的（缩放、自定义光标等）统一回落到普通箭头。
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


class _StrayCloseNativeFilter(QAbstractNativeEventFilter):
    """原生消息过滤器：丢弃「销毁 CEF 子窗口」时 Chromium 给宿主顶层窗口补发的 WM_CLOSE。

    Chromium 关闭自己的子窗口时会给宿主顶层窗口 Post 一个 WM_CLOSE，Qt 收到后会把窗口
    隐藏掉 —— 模态窗口（登录窗口用 exec() 打开）因此会直接退出，看起来像「被关闭」。
    在原生消息层把它丢掉，Qt 就不会产生 Close / Hide，也不必事后补救。

    注意不能「见到 WM_CLOSE 就吞」：用户在守卫有效期内关窗（标题栏 X / Alt+F4 /
    任务栏关闭）同样会走 WM_CLOSE，全吞掉会让窗口关不掉。用户关闭一定先发
    WM_SYSCOMMAND(SC_CLOSE)，所以这里用有没有 SC_CLOSE 来区分两者的来源。
    """

    def __init__(self):
        super().__init__()
        self.target_hwnd = 0
        # 用户关闭意图出现时回调（用来立刻撤掉守卫），由 CefWebView 设置
        self.on_user_close = None
        self._user_close_time = 0.0

    def user_close_requested(self) -> bool:
        """最近是否出现过用户的关闭意图（WM_SYSCOMMAND / SC_CLOSE）。"""
        if not self._user_close_time:
            return False
        return (time.monotonic() - self._user_close_time) <= _USER_CLOSE_GRACE_SECONDS

    def nativeEventFilter(self, eventType, message):
        if not IS_WINDOWS or not self.target_hwnd:
            return False, 0
        try:
            if bytes(eventType) != b'windows_generic_MSG':
                return False, 0
            msg = ctypes.cast(int(message), ctypes.POINTER(_WinMsg)).contents
            if int(msg.hwnd or 0) != self.target_hwnd:
                return False, 0
            if msg.message == _WM_SYSCOMMAND and (int(msg.wParam) & 0xFFF0) == _SC_CLOSE:
                # 用户要关窗：马上撤掉守卫，后面那条 WM_CLOSE 必须放行
                self._user_close_time = time.monotonic()
                callback = self.on_user_close
                if callback is not None:
                    try:
                        callback()
                    except Exception as e:
                        app_logger.log_exception(e)
                return False, 0
            if msg.message == _WM_CLOSE:
                if self.user_close_requested():
                    self._user_close_time = 0.0
                    return False, 0
                app_logger.log_INFO('cef webview: WM_CLOSE trashed')
                return True, 0
        except Exception as e:
            app_logger.log_exception(e)
        return False, 0


_stray_close_filter = _StrayCloseNativeFilter()


def _binres_candidates() -> typing.List[str]:
    # 按优先级列出可能存放 binres 的目录
    candidates = [os.path.join(os.getcwd(), 'binres')]

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, 'binres'))
        candidates.append(os.path.join(exe_dir, '_internal', 'binres'))

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, 'binres'))

    # 源码运行时：src/publics/base_ui_elements/cef_features -> src/binres
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.abspath(os.path.join(module_dir, '..', '..', '..', 'binres')))
    return candidates


def binres_dir() -> str:
    # 返回实际包含 CEF 桥接库的 binres 目录；找不到时退化为存在的目录
    candidates = _binres_candidates()
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, BRIDGE_LIB_NAME)):
            return candidate
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0]


def cef_runtime_dir() -> str:
    # CEF 运行时目录（libcef、资源、locales、helper 都放在这里）
    return os.path.join(binres_dir(), 'cef')


def bridge_path() -> str:
    """
    桥接库的位置。

    必须和 cef_bridge_helper / libcef 放在同一个目录：CEF 的子进程是独立进程，
    Windows 只会从 exe 所在目录找它的依赖 DLL，找不到就会以
    STATUS_DLL_NOT_FOUND(0xC0000135) 启动失败，进而让主进程 CHECK 崩溃。
    """
    runtime_candidate = os.path.join(cef_runtime_dir(), BRIDGE_LIB_NAME)
    if os.path.isfile(runtime_candidate):
        return runtime_candidate
    return os.path.join(binres_dir(), BRIDGE_LIB_NAME)


def is_available() -> bool:
    # 检查 CEF 运行时与桥接库是否齐全
    runtime = cef_runtime_dir()
    return (os.path.isfile(bridge_path())
            and os.path.isfile(os.path.join(runtime, CEF_LIB_NAME))
            and os.path.isfile(os.path.join(runtime, HELPER_NAME)))


def x11_embedding_possible() -> bool:
    # Linux 下 CEF 以子窗口方式嵌入需要 X11（Wayland 会话走 XWayland）
    if IS_WINDOWS:
        return True
    if not os.environ.get('DISPLAY'):
        return False
    qt_platform = os.environ.get('QT_QPA_PLATFORM', '').lower()
    if qt_platform and qt_platform not in ('xcb', 'x11'):
        return False
    return True


def loadLibs():
    # 加载 CEF 依赖
    if is_available():
        _CefBridge.instance()._load_library()
        app_logger.log_INFO(f'CEF runtime found at {cef_runtime_dir()} and loaded successfully')
    else:
        app_logger.log_WARN('CEF runtime is not available, cef webview will be disabled. '
                            f'expected: {os.path.join(cef_runtime_dir(), CEF_LIB_NAME)}')


def isWebViewInstalled() -> bool:
    # 检查当前系统是否可以提供 CEF webview 能力
    if not is_available():
        return False
    if not IS_WINDOWS and not x11_embedding_possible():
        app_logger.log_WARN('cef webview requires X11 (xcb) on linux')
        return False
    return True


def getWebViewVersion() -> str:
    # 获取 CEF 版本号（需要桥接库已加载）
    return _CefBridge.instance().cef_version() or 'CEF'


def _parse_headers_text(text: str) -> typing.Dict[str, str]:
    """把桥接层的 "Name: Value\\n" 文本还原成字典。"""
    headers = {}
    for line in (text or '').split('\n'):
        if not line.strip() or ':' not in line:
            continue
        name, _, value = line.partition(':')
        headers[name.strip()] = value.strip()
    return headers


@_HTTP_CALLBACK_TYPE
def _on_bridge_http(browser_id, kind, url, method, status_code, headers, body, body_len):
    widget = _WIDGETS.get(browser_id)
    if widget is None:
        return
    try:
        payload = ctypes.string_at(body, body_len) if body and body_len > 0 else None
        widget._handle_bridge_http(int(kind),
                                   url.decode('utf-8', 'replace') if url else '',
                                   method.decode('utf-8', 'replace') if method else '',
                                   int(status_code),
                                   headers.decode('utf-8', 'replace') if headers else '',
                                   payload)
    except Exception as e:
        app_logger.log_exception(e)


@_EVENT_CALLBACK_TYPE
def _on_bridge_event(browser_id, event, data):
    widget = _WIDGETS.get(browser_id)
    if widget is None:
        return
    text = data.decode('utf-8', 'replace') if data else ''
    try:
        widget._handle_bridge_event(int(event), text)
    except Exception as e:
        app_logger.log_exception(e)


@_PAINT_CALLBACK_TYPE
def _on_bridge_paint(browser_id, buffer, width, height):
    widget = _WIDGETS.get(browser_id)
    if widget is None or not buffer or width <= 0 or height <= 0:
        return
    try:
        widget._handle_paint(buffer, int(width), int(height))
    except Exception as e:
        app_logger.log_exception(e)


def _is_gui_thread() -> bool:
    """当前是否在 GUI 线程（CEF 的所有接口都只能在 GUI 线程调用）。"""
    app = QApplication.instance()
    if app is None:
        return True
    return QThread.currentThread() is app.thread()


def _utf8(text: typing.Optional[str]):
    return text.encode('utf-8') if text else None


def system_locale() -> str:
    """系统语言（CEF 需要 zh-CN 这种写法，而 Qt 给的是 zh_CN）。"""
    name = QLocale.system().name() or ''

    if not name:
        name = (os.environ.get('LANG') or os.environ.get('LC_ALL') or '')
        name = name.split('.')[0]
        if not name or name in ('C', 'POSIX'):
            name = 'en-US'

    return name.replace('_', '-')


def _accept_language(locale: str) -> str:
    """给网站用的 Accept-Language：zh-CN -> zh-CN,zh,en。"""
    if not locale:
        return ''
    parts = [locale]
    primary = locale.split('-')[0]
    if primary and primary != locale:
        parts.append(primary)
    if 'en' not in [p.lower() for p in parts]:
        parts.append('en')
    return ','.join(parts)


def _build_extra_args() -> str:
    """
    组装传给 CEF 的额外命令行参数。
    """
    args = os.environ.get('TIEBADESKTOP_CEF_ARGS', '').strip()
    # 让网页的 Accept-Language 跟随系统语言（CEF 的 locale 只管界面语言）
    if '--accept-lang' not in args:
        accept = _accept_language(system_locale())
        if accept:
            args = (args + f' --accept-lang={accept}').strip()
    return args


def _default_user_agent() -> str:
    if IS_WINDOWS:
        return ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36')
    return ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36')


def execute_process(argv=None) -> int:
    """
    CEF 子进程引导（主进程以 --type=xxx 启动时调用）。

    必须在导入 Qt / 创建 QApplication 之前调用（参考 cefpython 的实现）。
    """
    bridge = _CefBridge.instance()
    if not bridge._load_library():
        return -1
    lib = bridge.lib()
    if lib is None:
        return -1
    try:
        lib.cef_bridge_execute_process.restype = ctypes.c_int
        lib.cef_bridge_execute_process.argtypes = [ctypes.c_int, ctypes.c_void_p]
    except Exception:
        pass
    if IS_WINDOWS:
        return int(lib.cef_bridge_execute_process(0, None))
    args = list(argv if argv is not None else sys.argv)
    arr = (ctypes.c_char_p * (len(args) + 1))(*[a.encode('utf-8') for a in args], None)
    return int(lib.cef_bridge_execute_process(len(args), ctypes.cast(arr, ctypes.c_void_p)))


def shutdown():
    """进程退出前释放 CEF（不调用也不影响功能，但退出会更干净）。"""
    _CefBridge.instance().shutdown()


class _QuietFileHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class _LocalPageServer:
    """
    为视频播放页提供本地 http 服务。

    Windows 端 WebView2 用 SetVirtualHostNameToFolderMapping 做虚拟主机映射，
    CEF 没有等价 API，这里起一个只监听 127.0.0.1 的静态文件服务，
    再把虚拟主机 URL 重写过去，保证页面里的绝对路径与 localStorage 正常工作。
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                server = cls()
                if server.start():
                    cls._instance = server
            return cls._instance

    def __init__(self):
        self._httpd = None
        self._thread = None
        self.port = 0

    def start(self) -> bool:
        if not os.path.isdir(JS_PLAYER_DIR):
            app_logger.log_WARN(f'video player dir not found: {JS_PLAYER_DIR}')
            return False
        try:
            handler = functools.partial(_QuietFileHandler, directory=JS_PLAYER_DIR)
            self._httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            self.port = self._httpd.server_address[1]
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
            app_logger.log_INFO(f'local video page server started on port {self.port}')
            return True
        except Exception as e:
            app_logger.log_WARN('failed to start local video page server')
            app_logger.log_exception(e)
            return False

    def rewrite(self, url: str) -> str:
        if not url or self.port == 0:
            return url
        parsed = QUrl(url)
        if parsed.host() != VIRTUAL_HOST:
            return url
        path = parsed.path() or '/video_play_main.html'
        query = parsed.query()
        new_url = f'http://127.0.0.1:{self.port}{path}'
        if query:
            new_url += f'?{query}'
        return new_url


class _CefBridge:
    """CEF 桥接库的单例封装（CEF 每个进程只能初始化一次）。"""

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> '_CefBridge':
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lib = None
        self._initialized = False
        self._next_id = 1
        self._pump_timer = None
        self.last_error = ''

    def _load_library(self) -> bool:
        if self._lib is not None:
            return True

        runtime_dir = cef_runtime_dir()
        lib_path = bridge_path()
        if not os.path.isfile(lib_path):
            self.last_error = f'bridge library not found: {lib_path}'
            return False

        try:
            if IS_WINDOWS:
                # 让 libcef.dll / chrome_elf.dll 等能从 cef 目录被找到
                if hasattr(os, 'add_dll_directory'):
                    os.add_dll_directory(runtime_dir)
            else:
                # Linux 下先按绝对路径把 libcef 载入全局符号表
                ctypes.CDLL(os.path.join(runtime_dir, CEF_LIB_NAME),
                            mode=ctypes.RTLD_GLOBAL)
            self._lib = ctypes.CDLL(lib_path)
        except Exception as e:
            self.last_error = f'load cef bridge failed: {e}'
            app_logger.log_exception(e)
            return False

        self._declare_signatures()
        return True

    def _declare_signatures(self):
        lib = self._lib
        lib.cef_bridge_init.restype = ctypes.c_int
        lib.cef_bridge_init.argtypes = [ctypes.c_char_p] * 8
        lib.cef_bridge_is_initialized.restype = ctypes.c_int
        lib.cef_bridge_set_windowless.restype = None
        lib.cef_bridge_set_windowless.argtypes = [ctypes.c_int]
        lib.cef_bridge_set_event_callback.restype = None
        lib.cef_bridge_set_event_callback.argtypes = [_EVENT_CALLBACK_TYPE]
        lib.cef_bridge_set_paint_callback.restype = None
        lib.cef_bridge_set_paint_callback.argtypes = [_PAINT_CALLBACK_TYPE]
        lib.cef_bridge_set_view_size.restype = None
        lib.cef_bridge_set_view_size.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_set_focus.restype = None
        lib.cef_bridge_set_focus.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_mouse_move.restype = None
        lib.cef_bridge_mouse_move.argtypes = [ctypes.c_int] * 5
        lib.cef_bridge_mouse_click.restype = None
        lib.cef_bridge_mouse_click.argtypes = [ctypes.c_int] * 7
        lib.cef_bridge_mouse_wheel.restype = None
        lib.cef_bridge_mouse_wheel.argtypes = [ctypes.c_int] * 6
        lib.cef_bridge_key.restype = None
        lib.cef_bridge_key.argtypes = [ctypes.c_int] * 7
        lib.cef_bridge_do_work.restype = None
        lib.cef_bridge_shutdown.restype = None
        lib.cef_bridge_version.restype = ctypes.c_char_p

        lib.cef_bridge_create_browser.restype = ctypes.c_int
        lib.cef_bridge_create_browser.argtypes = [
            ctypes.c_int, ctypes.c_ulonglong, ctypes.c_char_p,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_char_p]
        lib.cef_bridge_resize.restype = None
        lib.cef_bridge_resize.argtypes = [ctypes.c_int] + [ctypes.c_int] * 4
        lib.cef_bridge_set_visible.restype = None
        lib.cef_bridge_set_visible.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_load.restype = None
        lib.cef_bridge_load.argtypes = [ctypes.c_int, ctypes.c_char_p]
        lib.cef_bridge_load_string.restype = None
        lib.cef_bridge_load_string.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
        for name in ('cef_bridge_go_back', 'cef_bridge_go_forward', 'cef_bridge_reload',
                     'cef_bridge_stop_load', 'cef_bridge_print',
                     'cef_bridge_clear_cache', 'cef_bridge_clear_cookies'):
            getattr(lib, name).restype = None
            getattr(lib, name).argtypes = [ctypes.c_int]
        lib.cef_bridge_open_devtools.restype = ctypes.c_int
        lib.cef_bridge_open_devtools.argtypes = ([ctypes.c_int, ctypes.c_ulonglong]
                                                 + [ctypes.c_int] * 4)
        lib.cef_bridge_resize_devtools.restype = None
        lib.cef_bridge_resize_devtools.argtypes = [ctypes.c_int] + [ctypes.c_int] * 4
        lib.cef_bridge_close_devtools.restype = None
        lib.cef_bridge_close_devtools.argtypes = [ctypes.c_int]
        lib.cef_bridge_has_devtools.restype = ctypes.c_int
        lib.cef_bridge_has_devtools.argtypes = [ctypes.c_int]
        lib.cef_bridge_set_http_callback.restype = None
        lib.cef_bridge_set_http_callback.argtypes = [_HTTP_CALLBACK_TYPE]
        lib.cef_bridge_set_http_patterns.restype = None
        lib.cef_bridge_set_http_patterns.argtypes = [ctypes.c_int, ctypes.c_char_p]
        lib.cef_bridge_fetch_icon.restype = None
        lib.cef_bridge_fetch_icon.argtypes = [ctypes.c_int, ctypes.c_char_p]
        lib.cef_bridge_download_continue.restype = None
        lib.cef_bridge_download_continue.argtypes = [ctypes.c_int, ctypes.c_char_p]
        lib.cef_bridge_download_cancel.restype = None
        lib.cef_bridge_download_cancel.argtypes = [ctypes.c_int]
        lib.cef_bridge_download_set_paused.restype = None
        lib.cef_bridge_download_set_paused.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_download_cancel_by_id.restype = None
        lib.cef_bridge_download_cancel_by_id.argtypes = [ctypes.c_int]

        lib.cef_bridge_get_cookies.restype = None
        lib.cef_bridge_get_cookies.argtypes = [ctypes.c_int, ctypes.c_char_p]
        for name in ('cef_bridge_can_go_back', 'cef_bridge_can_go_forward',
                     'cef_bridge_is_muted', 'cef_bridge_get_pid'):
            getattr(lib, name).restype = ctypes.c_int
            getattr(lib, name).argtypes = [ctypes.c_int]
        lib.cef_bridge_set_zoom.restype = None
        lib.cef_bridge_set_zoom.argtypes = [ctypes.c_int, ctypes.c_double]
        lib.cef_bridge_get_zoom.restype = ctypes.c_double
        lib.cef_bridge_get_zoom.argtypes = [ctypes.c_int]
        lib.cef_bridge_set_muted.restype = None
        lib.cef_bridge_set_muted.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_execute_js.restype = None
        lib.cef_bridge_execute_js.argtypes = [ctypes.c_int, ctypes.c_char_p]
        lib.cef_bridge_context_menu_command.restype = None
        lib.cef_bridge_context_menu_command.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.cef_bridge_context_menu_cancel.restype = None
        lib.cef_bridge_context_menu_cancel.argtypes = [ctypes.c_int]
        for name in ('cef_bridge_get_url', 'cef_bridge_get_title'):
            getattr(lib, name).restype = ctypes.c_void_p
            getattr(lib, name).argtypes = [ctypes.c_int]
        lib.cef_bridge_free_string.restype = None
        lib.cef_bridge_free_string.argtypes = [ctypes.c_void_p]
        lib.cef_bridge_destroy_browser.restype = None
        lib.cef_bridge_destroy_browser.argtypes = [ctypes.c_int, ctypes.c_int]

    def ensure_initialized(self, profile: WebViewProfile) -> bool:
        # 加载桥接库并初始化 CEF（幂等）
        if self._initialized:
            return True
        if not is_available():
            self.last_error = 'CEF runtime is not available'
            return False
        if not self._load_library():
            return False

        cache_path = profile.data_folder if profile is not None else ''
        try:
            os.makedirs(cache_path, exist_ok=True)
        except Exception:
            pass

        runtime_dir = cef_runtime_dir()
        # 默认把 CEF 日志写文件；但如果用户要求输出到 stderr（排查崩溃用），
        # 就不能再设 log_file，否则 CEF 会把日志重定向到文件、stderr 上什么都看不到。
        log_file = os.path.join(cache_path or runtime_dir, 'cef_debug.log')
        if 'enable-logging=stderr' in _build_extra_args():
            log_file = ''
        user_agent = None
        if profile is not None and profile.user_agent:
            user_agent = profile.user_agent.replace('[default_ua]', _default_user_agent())
        extra_args = _build_extra_args()

        windowless = 1 if profile.enable_osr else 0
        self._lib.cef_bridge_set_windowless(windowless)
        # 必须使用独立的 cef_bridge_helper.exe 作为 CEF 子进程：
        # 若让 CEF 复用主程序（python.exe），子进程会在解析命令行时
        # 因 --type=xxx 直接报 "unknown option" 退出，进而
        # FATAL: GPU process isn't usable. Goodbye. 让整个浏览器进程崩溃。
        ok = self._lib.cef_bridge_init(_utf8(cache_path), _utf8(log_file),
                                       _utf8(runtime_dir),
                                       _utf8(os.path.join(runtime_dir, 'locales')),
                                       _utf8(os.path.join(runtime_dir, HELPER_NAME)),
                                       _utf8(user_agent), _utf8(extra_args),
                                       _utf8(system_locale()))
        if not ok:
            self.last_error = 'cef_bridge_init failed'
            app_logger.log_WARN('cef_bridge_init failed, see cef_debug.log for details')
            return False

        self._lib.cef_bridge_set_event_callback(_on_bridge_event)
        self._lib.cef_bridge_set_paint_callback(_on_bridge_paint)
        self._lib.cef_bridge_set_http_callback(_on_bridge_http)
        try:
            from publics.base_ui_elements.cef_features import cef_tools
            cef_tools.cleanup_stale_markers()
        except Exception as e:
            app_logger.log_exception(e)
        self._initialized = True

        # CEF 使用 external_message_pump，需要我们在 Qt 事件循环里驱动它
        if self._pump_timer is None:
            self._pump_timer = QTimer()
            self._pump_timer.setInterval(4)
            self._pump_timer.timeout.connect(self._pump)
        self._pump_timer.start()

        app_logger.log_INFO(f'CEF initialized, version {self.cef_version()}, cache {cache_path}')
        return True

    def _pump(self):
        if not self._initialized or self._lib is None:
            return
        try:
            self._lib.cef_bridge_do_work()
        except Exception as e:
            app_logger.log_exception(e)

    def shutdown(self):
        if not self._initialized or self._lib is None:
            return
        # 先把所有 webview 销毁（释放 CEF 引用），再关 CEF，
        # 否则 CEF 在退出时会 Check failed: observers_.empty()
        for widget in list(_WIDGETS.values()):
            try:
                widget.destroyWebviewUntilComplete()
            except Exception as e:
                app_logger.log_exception(e)
        try:
            if self._pump_timer is not None:
                self._pump_timer.stop()
            self._lib.cef_bridge_shutdown()
        except Exception as e:
            app_logger.log_exception(e)
        try:
            # 工具窗口是全局的，退出前统一收尾（此时 CEF 已经没有浏览器了）
            from publics.base_ui_elements.cef_features import cef_tools
            cef_tools.shutdown_tools()
        except Exception as e:
            app_logger.log_exception(e)
        self._initialized = False

    def allocate_id(self) -> int:
        browser_id = self._next_id
        self._next_id += 1
        return browser_id

    def cef_version(self) -> str:
        if self._lib is None:
            return ''
        try:
            version = self._lib.cef_bridge_version()
            return version.decode('utf-8', 'replace') if version else ''
        except Exception:
            return ''

    def lib(self):
        return self._lib


# ---------------------------------------------------------------------- Qt 控件

class _CefDevToolsWindow(QWidget):
    """开发者工具窗口。

    这里刻意不使用 CEF 自己的 devtools 弹窗（ShowDevTools + SetAsPopup）：那套窗口在
    部分 Windows 环境下只会显示一片空白（窗口能右键、能点到关闭按钮，但没有任何内容）。
    改由 Qt 提供一个顶层窗口，再把 devtools 浏览器以原生子窗口的方式嵌进去——和主浏览器
    完全相同的渲染路径。

    注意：CEF 只有在承载 devtools 的原生窗口被真正销毁后，才会完成 devtools 浏览器的
    关闭（只调用 CloseDevTools/CloseBrowser 时它会一直存活，最终让 CefShutdown 崩溃）。
    因此这个窗口带 WA_DeleteOnClose，关闭即销毁。
    """

    def __init__(self, view):
        # 以主窗口为父窗口：主窗口销毁时 devtools 窗口会一起销毁，
        # 同时保证 devtools 浏览器不会活得比宿主更久。
        super().__init__(view.window() if view is not None else None, Qt.Window)
        self.__view = view
        self.__browser_open = False
        self.__closing = False
        self.setWindowTitle('CEF DevTools')
        self.resize(1200, 760)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def markClosed(self):
        # devtools 浏览器已经关闭（CEF 主动通知），窗口直接销毁即可
        self.__closing = True
        self.__browser_open = False
        self.hide()
        self.deleteLater()

    def __view_size(self):
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        return max(int(self.width() * dpr), 1), max(int(self.height() * dpr), 1)

    def __open_browser(self):
        try:
            view = self.__view
            lib = _CefBridge.instance().lib()
            if lib is None or view is None or self.__browser_open:
                return
            browser_id = view.browserId()
            if not browser_id:
                return
            width, height = self.__view_size()
            if lib.cef_bridge_has_devtools(browser_id):
                # 上一次的 devtools 还没收尾（窗口刚销毁、CEF 正在关闭它）：先关掉，
                # 否则 ShowDevTools 会复用一个已经失去宿主窗口的实例，导致新窗口空白。
                lib.cef_bridge_close_devtools(browser_id)
            result = lib.cef_bridge_open_devtools(
                browser_id, ctypes.c_ulonglong(int(self.winId())), 0, 0, width, height)
            if result == 0:
                app_logger.log_WARN('open cef devtools failed')
                return
            self.__browser_open = True
            # 复用已经存在的 devtools 浏览器时同步一次尺寸
            lib.cef_bridge_resize_devtools(browser_id, 0, 0, width, height)
        except Exception as e:
            app_logger.log_exception(e)

    def showEvent(self, a0):
        super().showEvent(a0)
        # 等原生窗口稳定之后再让 CEF 把子窗口挂进来
        QTimer.singleShot(0, self.__open_browser)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        try:
            view = self.__view
            lib = _CefBridge.instance().lib()
            if lib is None or view is None or not self.__browser_open:
                return
            browser_id = view.browserId()
            if not browser_id:
                return
            width, height = self.__view_size()
            lib.cef_bridge_resize_devtools(browser_id, 0, 0, width, height)
        except Exception as e:
            app_logger.log_exception(e)

    def closeEvent(self, a0):
        # 这里只做清理并放行：窗口被销毁（WA_DeleteOnClose）时 CEF 会连带把
        # devtools 浏览器关掉并释放，不需要在这里等它（等也等不到）。
        view = self.__view
        self.__view = None
        self.__browser_open = False
        if view is not None:
            view._on_devtools_window_closed(self)


class CefWebView(QWidget):
    """跨平台的 CEF webview 控件，对外接口与 Windows 端 ``webview2.QWebView2View`` 一致。"""

    audioMutedChanged = pyqtSignal(bool)
    windowCloseRequested = pyqtSignal()
    renderInitializationCompleted = pyqtSignal()
    loadStarted = pyqtSignal()
    loadFinished = pyqtSignal(bool)
    urlChanged = pyqtSignal()
    titleChanged = pyqtSignal(str)
    renderProcessTerminated = pyqtSignal(int)
    iconUrlChanged = pyqtSignal(str)
    fullScreenRequested = pyqtSignal(bool)
    iconChanged = pyqtSignal(QIcon)
    jsBridgeReceived = pyqtSignal(str)
    newtabSignal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.__profile = None
        self.__browser_id = 0
        self.__render_completed = False
        self.__load_after_init = ''
        self.__pending_load = ''
        self.__audio_muted = False
        self.__html_fullscreen = False
        self.__current_title = ''
        self.__current_url = ''
        self.__fallback_label = None
        self.__cookie_waiters = {}
        self.__frame = None
        self.__current_icon = None
        self.__current_icon_binary = b''
        self.__current_icon_url = ''
        self.__save_html_path = ''
        self.__save_html_chunks = {}
        self.__tearing_down = False
        self.__close_guard_window = None
        self.__close_guard_timer = QTimer(self)
        self.__close_guard_timer.setSingleShot(True)
        self.__close_guard_timer.timeout.connect(self.__release_close_guard_later)

        self.__devtools_window = None

        self.newtabSignal.connect(self.createWindow)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            if self.__profile.enable_osr:
                # OSR：GetViewRect 用的是逻辑像素（设备无关像素）
                width, height = max(self.width(), 1), max(self.height(), 1)
            else:
                # 窗口化：CEF 子窗体要填满控件的物理像素区域
                width, height = self.__view_size()
            lib.cef_bridge_resize(self.__browser_id, 0, 0, width, height)
        if self.__fallback_label is not None:
            self.__fallback_label.setGeometry(0, 0, max(self.width(), 360), max(self.height(), 140))

    def showEvent(self, a0):
        super().showEvent(a0)
        # 参考 cefpython examples/qt.py：等控件 show 出来之后同步创建浏览器，
        # 此时原生窗口句柄才是最终稳定的
        self.__on_shown()

    def hideEvent(self, a0):
        self.__set_native_visible(False)

    def closeEvent(self, a0):
        a0.ignore()
        self.hide()

    def paintEvent(self, a0):
        if self.__frame is None:
            super().paintEvent(a0)
            return
        painter = QPainter(self)
        painter.drawImage(0, 0, self.__frame)
        painter.end()

    def mouseMoveEvent(self, a0):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            x, y = self.__cef_point(a0.pos())
            lib.cef_bridge_mouse_move(self.__browser_id, x, y, self.__cef_modifiers(a0), 0)

    def mousePressEvent(self, a0):
        self.setFocus()
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            x, y = self.__cef_point(a0.pos())
            lib.cef_bridge_mouse_click(self.__browser_id, x, y, self.__cef_modifiers(a0),
                                       self.__cef_button(a0.button()), 0, 1)

    def mouseReleaseEvent(self, a0):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            x, y = self.__cef_point(a0.pos())
            lib.cef_bridge_mouse_click(self.__browser_id, x, y, self.__cef_modifiers(a0),
                                       self.__cef_button(a0.button()), 1, 1)

    def wheelEvent(self, a0):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            x, y = self.__cef_point(a0.pos())
            delta = a0.angleDelta()
            lib.cef_bridge_mouse_wheel(self.__browser_id, x, y, self.__cef_modifiers(a0),
                                       int(delta.x()), int(delta.y()))

    def keyPressEvent(self, a0):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return
        key = int(a0.nativeVirtualKey()) or 0
        scan = int(a0.nativeScanCode()) or 0
        mods = self.__cef_modifiers(a0)
        if key:
            lib.cef_bridge_key(self.__browser_id, 0, key, scan, mods, 0, 0)  # RAWKEYDOWN
        text = a0.text()
        if len(text) == 1 and text.isprintable():
            lib.cef_bridge_key(self.__browser_id, 3, key, scan, mods, 0, ord(text))  # CHAR

    def keyReleaseEvent(self, a0):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return
        key = int(a0.nativeVirtualKey()) or 0
        scan = int(a0.nativeScanCode()) or 0
        lib.cef_bridge_key(self.__browser_id, 2, key, scan, self.__cef_modifiers(a0), 0, 0)  # KEYUP

    def focusInEvent(self, a0):
        super().focusInEvent(a0)
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_set_focus(self.__browser_id, 1)

    def focusOutEvent(self, a0):
        super().focusOutEvent(a0)
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_set_focus(self.__browser_id, 0)

    # -------------------------------------------------- 初始化
    def setProfile(self, profile: WebViewProfile):
        if self.__profile is None:
            self.__profile = profile

    def profile(self) -> typing.Optional[WebViewProfile]:
        return self.__profile

    def initRender(self):
        if self.__profile is None:
            app_logger.log_WARN('cef webview profile has not been set')
            return
        if self.__render_completed:
            app_logger.log_WARN('cef webview has already been inited')
            return

        try:
            if not is_available():
                raise RuntimeError('CEF runtime is not available')
            bridge = _CefBridge.instance()
            if not bridge.ensure_initialized(self.__profile):
                raise RuntimeError(bridge.last_error or 'CEF initialize failed')
        except Exception as e:
            app_logger.log_WARN('cef webview init failed, fallback to placeholder')
            app_logger.log_exception(e)
            self.__teardown_partial()
            self.__build_fallback()

        # 浏览器窗口必须等控件真正显示（show）之后再创建：
        # 控件如果是在 initRender 之后才被 reparent（例如 ExtWebView 先 initRender、
        # 再被加入 QTabWidget），Qt 会重建它的原生窗口，之前挂在旧句柄上的 CEF 子窗口
        # 会让 Chromium 直接 CHECK 崩溃（STATUS_BREAKPOINT / 0x80000003）。
        if self.isVisible():
            self.__create_browser()

        self.__render_completed = True
        self.renderInitializationCompleted.emit()

    def createWindow(self, newPageUrl: str):
        # 当 handle_newtab_byuser=True 且页面尝试打开新窗口时被调用，可由子类重写
        pass

    def destroyWebview(self):
        self.destroyWebviewUntilComplete()

    @pyqtSlot()
    def destroyWebviewUntilComplete(self):
        """销毁 webview（线程安全：在后台线程里调用会转到 GUI 线程同步执行）。

        CEF 的接口只能在 UI 线程调用，而项目里有些地方（例如登录成功后的
        ``do_login``）是在后台线程里直接调这里的；那样做不仅销毁不彻底
        （CEF 还占着 profile 目录，调用方后续 rename 会失败），宿主窗口的
        关闭守卫也会装错线程，所以统一转回 GUI 线程并等待完成。
        """
        if not _is_gui_thread():
            QMetaObject.invokeMethod(self, 'destroyWebviewUntilComplete',
                                     Qt.BlockingQueuedConnection)
            return
        self.__destroy_webview()

    def isRenderInitOk(self) -> bool:
        return self.__render_completed

    def renderProcessID(self) -> int:
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return -1
        try:
            return int(lib.cef_bridge_get_pid(self.__browser_id))
        except Exception:
            return -1

    def baseWebViewObject(self):
        # 获取底层对象，返回 (browser_id, 桥接库) 二元组
        return self.__browser_id, _CefBridge.instance().lib()

    # -------------------------------------------------- 数据清理
    def clearCacheData(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            try:
                lib.cef_bridge_clear_cache(self.__browser_id)
            except Exception as e:
                app_logger.log_exception(e)

    def clearCookies(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            try:
                lib.cef_bridge_clear_cookies(self.__browser_id)
            except Exception as e:
                app_logger.log_exception(e)

    # -------------------------------------------------- 页面状态
    def icon(self) -> QIcon:
        return self.__current_icon if self.__current_icon is not None else QIcon()

    def iconBinary(self) -> bytes:
        return self.__current_icon_binary or b''

    def iconUrl(self) -> str:
        return self.__current_icon_url

    def title(self) -> str:
        return self.__current_title

    def url(self) -> str:
        return self.__current_url

    def isAudioMuted(self) -> bool:
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            try:
                return bool(lib.cef_bridge_is_muted(self.__browser_id))
            except Exception:
                pass
        return self.__audio_muted

    def setAudioMuted(self, ismuted: bool):
        self.__audio_muted = bool(ismuted)
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            try:
                lib.cef_bridge_set_muted(self.__browser_id, 1 if ismuted else 0)
            except Exception as e:
                app_logger.log_exception(e)
        self.audioMutedChanged.emit(self.__audio_muted)

    def isHtmlInFullScreenState(self) -> bool:
        return self.__html_fullscreen

    # -------------------------------------------------- 导航
    def canBack(self) -> bool:
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return False
        return bool(lib.cef_bridge_can_go_back(self.__browser_id))

    def canForward(self) -> bool:
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return False
        return bool(lib.cef_bridge_can_go_forward(self.__browser_id))

    def back(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_go_back(self.__browser_id)

    def forward(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_go_forward(self.__browser_id)

    def reload(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_reload(self.__browser_id)

    def load(self, url: str):
        if not self.__browser_id:
            # 浏览器还没创建（控件尚未显示），先排队等 showEvent 之后加载
            self.__pending_load = url
            return
        if not self.isVisible():
            self.__pending_load = url
            return
        self.__do_load(url)

    def openChromiumTaskmgrWindow(self):
        # 任务管理器是全局窗口（cef_tools 统一持有），不随标签页销毁
        from publics.base_ui_elements.cef_features import cef_tools
        cef_tools.show_task_manager()

    def openDefaultDownloadDialog(self):
        # 下载气泡同样是全局窗口，anchor 只用来自上角定位
        from publics.base_ui_elements.cef_features import cef_tools
        cef_tools.show_download_panel(self)

    def openPrintDialog(self):
        lib = _CefBridge.instance().lib()
        if lib is not None and self.__browser_id:
            lib.cef_bridge_print(self.__browser_id)

    def openSaveHtmlDialog(self):
        if not self.__browser_id:
            app_logger.log_WARN('cef webview has not inited')
            return
        title = ''.join(ch for ch in (self.title() or 'page') if ch not in '\\/:*?"<>|').strip()
        suggested = os.path.join(os.path.expanduser('~'), (title or 'page') + '.html')
        path, _ = QFileDialog.getSaveFileName(self, '另存为网页', suggested,
                                              'HTML 文件 (*.html *.htm)')
        if not path:
            return
        self.__save_html_path = path
        self.__save_html_chunks = {}
        # 用 JS 把 DOM 序列化出来，分块经 console 桥传回（避免单条消息过大）
        script = (
                "(function(){try{"
                "var h='<!DOCTYPE html>\\n'+document.documentElement.outerHTML;"
                "for(var i=0;i<h.length;i+=" + str(_SAVE_HTML_CHUNK) + "){"
                                                                       "console.log('__TIEBA_BRIDGE__'+JSON.stringify("
                                                                       "{type:'saveHtml',i:i,total:h.length,d:h.substr(i," + str(
            _SAVE_HTML_CHUNK) + ")}));}"
                                "}catch(e){console.log('__TIEBA_BRIDGE__'+JSON.stringify("
                                "{type:'saveHtml',error:String(e)}));}})();")
        self.runJavaScriptAsync(script)

    def loadAfterRender(self, url: str):
        self.__load_after_init = url

    def setHtml(self, html: str = '<html></html>'):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            app_logger.log_WARN('cef webview has not inited')
            return
        lib.cef_bridge_load_string(self.__browser_id, _utf8(html), _utf8('about:blank'))

    def zoomFactor(self) -> float:
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return 1.0
        return math.pow(1.2, lib.cef_bridge_get_zoom(self.__browser_id))

    def setZoomFactor(self, f: float):
        profile = self.__profile
        if profile is not None and not profile.enable_zoom_factor:
            return
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id or f <= 0:
            return
        lib.cef_bridge_set_zoom(self.__browser_id, math.log(f) / math.log(1.2))

    def runJavaScriptAsync(self, js_code: str):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            raise Warning('cef webview has not inited')
        lib.cef_bridge_execute_js(self.__browser_id, _utf8(js_code))

    def openDevtoolsWindow(self):
        if not self.__browser_id:
            app_logger.log_WARN('cef webview has not inited')
            return
        window = self.__devtools_window
        if window is None:
            window = _CefDevToolsWindow(self)
            self.__devtools_window = window
        window.show()
        window.raise_()
        window.activateWindow()

    def browserId(self) -> int:
        return self.__browser_id

    def __do_load(self, url: str):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return
        try:
            lib.cef_bridge_load(self.__browser_id, _utf8(self.__rewrite_url(url)))
        except Exception as e:
            app_logger.log_exception(e)

    def __start_pending_load(self):
        if not self.__pending_load:
            return
        if not self.isVisible() or not self.__browser_id:
            return
        url = self.__pending_load
        self.__pending_load = ''
        self.__do_load(url)

    @staticmethod
    def __rewrite_url(url: str) -> str:
        # 把视频播放页的虚拟主机 URL 重写为本地 http 服务地址
        if not url or VIRTUAL_HOST not in url:
            return url
        server = _LocalPageServer.instance()
        if server is None or server.port == 0:
            return url
        return server.rewrite(url)

    def _on_devtools_window_closed(self, window):
        # 由 _CefDevToolsWindow 在自身关闭时回调，避免留下悬空引用
        if self.__devtools_window is window:
            self.__devtools_window = None

    def __close_devtools_window(self):
        window = self.__devtools_window
        self.__devtools_window = None
        if window is None:
            return
        # 关闭并立刻处理 DeferredDelete，让承载 devtools 的原生窗口同步销毁，
        # 这样 CEF 才有机会在 CefShutdown 之前完成 devtools 的清理。
        try:
            window.close()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        except Exception as e:
            app_logger.log_exception(e)

    # -------------------------------------------------- HTTP 请求 / 响应
    def __intercept_patterns(self) -> str:
        profile = self.__profile
        if profile is None or not profile.http_rewriter:
            return ''
        patterns = []
        for key in profile.http_rewriter.keys():
            key = (key or '').strip()
            if not key:
                continue
            if key == '*':
                return '*'
            cleaned = key.replace('*', '')
            if cleaned and cleaned not in patterns:
                patterns.append(cleaned)
        return '|'.join(patterns)

    def __match_rewriter(self, url: str):
        profile = self.__profile
        if profile is None or not profile.http_rewriter:
            return None
        for pattern, handler in profile.http_rewriter.items():
            if pattern == '*' or pattern.replace('*', '') in url:
                return handler
        return None

    def _handle_bridge_http(self, kind: int, url: str, method: str, status_code: int,
                            headers_text: str, body: typing.Optional[bytes]):
        """桥接层在 UI 线程回调过来的请求 / 响应（见 cef_bridge.h 的说明）。"""
        rewriter = self.__match_rewriter(url)
        if rewriter is None:
            return
        headers = _parse_headers_text(headers_text)
        if kind == 1:
            rewriter.onRequestCaught(url, method, headers, body or None)
        else:
            rewriter.onResponseCaught(url, status_code, headers, body)

    # -------------------------------------------------- favicon
    def __on_favicon_url(self, url: str):
        self.__current_icon_url = url or ''
        self.iconUrlChanged.emit(self.__current_icon_url)
        if not url or not self.__browser_id:
            return
        lib = _CefBridge.instance().lib()
        if lib is None:
            return
        try:
            lib.cef_bridge_fetch_icon(self.__browser_id, _utf8(url))
        except Exception as e:
            app_logger.log_exception(e)

    def __on_favicon_data(self, data: str):
        if not data:
            return
        try:
            raw = base64.b64decode(data)
        except Exception as e:
            app_logger.log_exception(e)
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw) or pixmap.isNull():
            return
        self.__current_icon_binary = raw
        self.__current_icon = QIcon(pixmap)
        self.iconChanged.emit(self.__current_icon)

    # -------------------------------------------------- OSR 光标
    def __on_cursor_change(self, data: str):
        """把网页内的光标类型同步到 Qt 控件（输入框的 I 形、链接的手形等）。

        OSR 下离屏渲染没有原生窗口，只能由这里设置；窗口化嵌入时 CEF 会给浏览器
        子窗口设置光标，这里再同步一份，保证父窗口（Qt 控件）上的光标也一致。
        """
        try:
            cursor_type = int(data)
        except (TypeError, ValueError):
            return
        shape = _CEF_CURSOR_TO_QT.get(cursor_type, Qt.ArrowCursor)
        current = self.cursor()
        if current is not None and current.shape() == shape:
            return
        self.setCursor(QCursor(shape))

    # -------------------------------------------------- OSR 右键菜单
    def __on_context_menu(self, data: str):
        """OSR：CEF 自带的右键菜单在离屏渲染下算不出正确的屏幕坐标，改由 Qt 弹出。

        桥接层已经把菜单模型序列化过来（见 cef_bridge.cpp 的 SerializeMenuItems），
        这里只负责在鼠标位置弹出菜单，并把选中的命令回传给 CEF 去执行。
        """
        lib = _CefBridge.instance().lib()
        if lib is None:
            return
        try:
            payload = json.loads(data or '{}')
        except Exception as e:
            app_logger.log_exception(e)
            return
        menu_id = int(payload.get('id') or 0)
        if not menu_id:
            return
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        # 菜单坐标是 CEF 的 view 坐标（设备无关像素），先换算回 Qt 的逻辑坐标再取屏幕坐标
        position = self.mapToGlobal(QPoint(int(int(payload.get('x') or 0) / dpr),
                                           int(int(payload.get('y') or 0) / dpr)))
        menu = base_ui.BaseQMenu(self)
        try:
            self.__fill_context_menu(menu, payload.get('items') or [])
            action = menu.exec_(position) if not menu.isEmpty() else None
        except Exception as e:
            app_logger.log_exception(e)
            action = None
        finally:
            menu.deleteLater()
        command_id = action.data() if action is not None else None
        if command_id is None:
            lib.cef_bridge_context_menu_cancel(menu_id)
            return
        lib.cef_bridge_context_menu_command(menu_id, int(command_id))

    def __fill_context_menu(self, menu: QMenu, items: typing.List):
        """按 CEF 的菜单模型（cef_menu_item_type_t）递归构建 Qt 菜单。"""
        groups = {}
        for item in items:
            if not isinstance(item, dict) or not item.get('visible', True):
                continue
            kind = int(item.get('type') or 0)
            if kind == 4:  # MENUITEMTYPE_SEPARATOR
                menu.addSeparator()
                continue
            label = (item.get('label') or '').replace('&', '')
            if kind == 5:  # MENUITEMTYPE_SUBMENU
                submenu = menu.addMenu(label)
                submenu.setEnabled(bool(item.get('enabled', True)))
                self.__fill_context_menu(submenu, item.get('items') or [])
                continue
            action = menu.addAction(label)
            action.setEnabled(bool(item.get('enabled', True)))
            action.setData(int(item.get('id') or 0))
            if kind == 2:  # MENUITEMTYPE_CHECK
                action.setCheckable(True)
                action.setChecked(bool(item.get('checked')))
            elif kind == 3:  # MENUITEMTYPE_RADIO
                action.setCheckable(True)
                action.setChecked(bool(item.get('checked')))
                group_id = int(item.get('group') or 0)
                group = groups.get(group_id)
                if group is None:
                    group = QActionGroup(menu)
                    group.setExclusive(True)
                    groups[group_id] = group
                group.addAction(action)

    # -------------------------------------------------- 渲染进程崩溃
    def __on_render_terminated(self, data: str):
        """渲染进程异常退出：与 WebView2 一样把退出码回传给上层。"""
        status_text, _, code_text = (data or "").partition("|")
        try:
            code = int(code_text)
        except Exception:
            code = -1
        app_logger.log_WARN(f'cef render process terminated: {status_text}')
        self.renderProcessTerminated.emit(code)

    # -------------------------------------------------- 下载
    def __on_download_event(self, data: str):
        try:
            payload = json.loads(data or '{}')
        except Exception as e:
            app_logger.log_exception(e)
            return
        from publics.base_ui_elements.cef_features import cef_tools
        cef_tools.DownloadManager.instance().handle_bridge_event(self.__browser_id, payload, anchor=self)

    # -------------------------------------------------- 另存为网页
    def __handle_internal_bridge_message(self, data: str) -> bool:
        if not data.startswith('{') or 'saveHtml' not in data:
            return False
        try:
            payload = json.loads(data)
        except Exception:
            return False
        if payload.get('type') != 'saveHtml':
            return False
        self.__collect_save_html(payload)
        return True

    def __collect_save_html(self, payload: typing.Dict):
        if payload.get('error'):
            app_logger.log_WARN(f'save html failed: {payload["error"]}')
            self.__save_html_chunks = {}
            self.__save_html_path = ''
            return
        total = int(payload.get('total') or 0)
        self.__save_html_chunks[int(payload.get('i') or 0)] = payload.get('d') or ''
        expected = (total + _SAVE_HTML_CHUNK - 1) // _SAVE_HTML_CHUNK if total else 1
        if len(self.__save_html_chunks) < expected:
            return
        chunks = self.__save_html_chunks
        self.__save_html_chunks = {}
        path = self.__save_html_path
        self.__save_html_path = ''
        if not path:
            return
        html = ''.join(chunks[key] for key in sorted(chunks.keys()))
        try:
            with open(path, 'w', encoding='utf-8', errors='replace') as file:
                file.write(html)
            app_logger.log_INFO(f'save html done: {path} ({len(html)} chars)')
        except Exception as e:
            app_logger.log_exception(e)

    def __destroy_webview(self):
        self.__teardown_partial()
        self.__render_completed = False

    def __create_browser(self) -> bool:
        """控件已有稳定的原生窗口后，再创建 CEF 浏览器。"""
        if self.__browser_id:
            return True

        bridge = _CefBridge.instance()
        lib = bridge.lib()
        if lib is None or lib.cef_bridge_is_initialized() != 1:
            return False

        try:
            windowless = self.profile().enable_osr
            self.setAttribute(Qt.WA_OpaquePaintEvent, True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setMouseTracking(True)

            if windowless:
                # OSR 不创建原生窗口，但 CEF 的默认右键菜单 / 对话框仍然需要一个
                # 有效的原生父窗口句柄，否则会报
                # "Window handle is required for default OSR context menu"
                # 并把菜单取消掉，所以这里把控件自身（必要时创建）的原生窗口交给 CEF。
                self.setAttribute(Qt.WA_NativeWindow, True)
                handle = int(self.winId())
            else:
                # 窗口化嵌入（默认）：需要控件自己的原生窗口句柄。
                # 因此必须等控件 show 出来之后再创建浏览器（见 showEvent）。
                self.setAttribute(Qt.WA_NativeWindow, True)
                handle = int(self.winId())

            self.__browser_id = bridge.allocate_id()
            _WIDGETS[self.__browser_id] = self

            # 告诉桥接层要拦截哪些 URL（模式与下面 __match_rewriter 的匹配规则一致）
            patterns = self.__intercept_patterns()
            if patterns:
                lib.cef_bridge_set_http_patterns(self.__browser_id, _utf8(patterns))

            url = self.__rewrite_url(self.__load_after_init) if self.__load_after_init else 'about:blank'
            width, height = self.__view_size()
            ok = lib.cef_bridge_create_browser(
                self.__browser_id, ctypes.c_ulonglong(handle), _utf8(url),
                0, 0, width, height,
                _utf8(self.__bridge_script()), _utf8(self.__user_agent()))
            if not ok:
                raise RuntimeError('cef_bridge_create_browser failed')
            app_logger.log_INFO(f'cef webview create browser: id={self.__browser_id} '
                                f'{"osr" if windowless else "windowed"} handle={handle} '
                                f'size={width}x{height}')
            return True
        except Exception as e:
            app_logger.log_WARN('cef webview create browser failed')
            app_logger.log_exception(e)
            self.__teardown_partial()
            self.__build_fallback()
            return False

    def __teardown_partial(self):
        browser_id = self.__browser_id
        self.__browser_id = 0
        # 销毁 CEF 浏览器时，Chromium 会往宿主顶层窗口 Post 一个真正的 WM_CLOSE
        # （Qt 会把它转成 spontaneous 的 closeEvent），同时 OnBeforeClose 也会触发一次。
        # 这两件事都属于「我们自己拆浏览器」，所以销毁期间要全部屏蔽掉，
        # 否则登录窗口会被误关、或者被当成「网页请求关闭」而把其它标签页一起关掉。
        self.__tearing_down = True
        self.__install_close_guard()
        # 必须先销毁承载 devtools 的窗口：CEF 只有在原生窗口销毁后才会真正关掉
        # devtools 浏览器，这一步要早于宿主浏览器，否则退出时 CefShutdown 会崩溃。
        self.__close_devtools_window()
        if browser_id:
            _WIDGETS.pop(browser_id, None)
            lib = _CefBridge.instance().lib()
            if lib is not None:
                try:
                    # 桥接层在关闭宿主浏览器时会顺带关掉关联的开发者工具浏览器
                    lib.cef_bridge_destroy_browser(browser_id, 1)
                except Exception:
                    pass
            self.__drain_stray_close()
        self.__tearing_down = False
        if self.__close_guard_window is not None:
            self.__arm_close_guard(_CLOSE_GUARD_MAX_MS)

    def __install_close_guard(self):
        """销毁前先把顶层窗口的关闭事件接管起来（只有 Windows 上 CEF 会这么做）。"""
        if not IS_WINDOWS or self.__close_guard_window is not None:
            return
        window = self.window()
        if window is None:
            return
        self.__close_guard_window = window
        window.installEventFilter(self)
        # 原生消息层也接管：这样连 Qt 的 Close/Hide 都不会产生
        _stray_close_filter.on_user_close = self.__on_user_close_intent
        _stray_close_filter.target_hwnd = int(window.winId())
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(_stray_close_filter)

    def __drain_stray_close(self):
        """把还堆在消息队列里的那个 WM_CLOSE 摘掉，尽量不影响用户自己关窗。"""
        window = self.__close_guard_window
        if not IS_WINDOWS or window is None:
            return
        if _stray_close_filter.user_close_requested():
            # 用户正在关窗，队列里的 WM_CLOSE 可能是他自己的，不能摘
            return
        try:
            user32 = ctypes.windll.user32
            message = _WinMsg()
            hwnd = ctypes.c_void_p(int(window.winId()))
            while user32.PeekMessageW(ctypes.byref(message), hwnd,
                                      _WM_CLOSE, _WM_CLOSE, _PM_REMOVE):
                app_logger.log_INFO('cef webview: beyond WM_CLOSE dropped')
        except Exception as e:
            app_logger.log_exception(e)

    def __arm_close_guard(self, msec: int):
        """延长 / 重新开始关闭守卫的存活时间。"""
        try:
            self.__close_guard_timer.start(msec)
        except Exception as e:
            app_logger.log_exception(e)

    def __release_close_guard_later(self):
        try:
            self.__release_close_guard()
        except RuntimeError:
            # 控件（或宿主窗口）已经被析构
            pass

    def __on_user_close_intent(self):
        """用户在守卫有效期内主动关窗：立刻撤销守卫，不要再拦他的关闭消息。"""
        app_logger.log_INFO('cef webview: user close detected, release close guard')
        self.__release_close_guard()

    def __release_close_guard(self):
        window = self.__close_guard_window
        self.__close_guard_window = None
        _stray_close_filter.target_hwnd = 0
        _stray_close_filter.on_user_close = None
        if window is None:
            return
        try:
            window.removeEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, a0, a1):
        # 销毁 CEF 浏览器期间，顶层窗口会收到一个多余的原生关闭事件。
        # 只有「用户没有要关窗」的那种才拦下来；用户自己的关闭必须放行。
        if (self.__close_guard_window is not None and a0 is self.__close_guard_window
                and a1.type() == QEvent.Close and a1.spontaneous()
                and not _stray_close_filter.user_close_requested()):
            app_logger.log_INFO('cef webview: 已忽略销毁 CEF 窗口时产生的多余关闭事件')
            a1.ignore()
            return True
        return super().eventFilter(a0, a1)

    def __build_fallback(self):
        label = QLabel('Chromium Embedded Framework 不可用', self)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setGeometry(0, 0, max(self.width(), 360), max(self.height(), 140))
        label.show()
        self.__fallback_label = label

    def __user_agent(self) -> typing.Optional[str]:
        if self.__profile is None or not self.__profile.user_agent:
            return None
        return self.__profile.user_agent.replace('[default_ua]', _default_user_agent())

    def __bridge_script(self) -> str:
        # 桥接层会在页面加载完成时注入这段脚本（目前无实际用途）
        return ''

    # -------------------------------------------------- 事件分发
    def _handle_bridge_event(self, event: int, data: str):
        if event == CefEventType.CLOSE:
            # 销毁浏览器时 CEF 也会走一次 OnBeforeClose，这种「自己拆的」不算
            # 网页请求关闭，否则宿主窗口 / 标签页会被误关。
            if not self.__tearing_down:
                self.windowCloseRequested.emit()
        elif event == CefEventType.LOAD_START:
            self.__current_url = data or self.__current_url
            self.loadStarted.emit()
        elif event == CefEventType.LOAD_END:
            self.__current_url = data or self.__current_url
            self.__notify_cookie_rewriter(self.__current_url)
            self.loadFinished.emit(True)
        elif event == CefEventType.LOAD_ERROR:
            app_logger.log_WARN(f'cef webview load failed: {data}')
            self.loadFinished.emit(False)
        elif event == CefEventType.TITLE:
            self.__current_title = data
            self.titleChanged.emit(data)
        elif event == CefEventType.URL:
            self.__current_url = data
            self.urlChanged.emit()
        elif event == CefEventType.FAVICON_URL:
            self.__on_favicon_url(data)
        elif event == CefEventType.FAVICON_DATA:
            self.__on_favicon_data(data)
        elif event == CefEventType.DOWNLOAD:
            self.__on_download_event(data)
        elif event == CefEventType.RENDER_TERMINATED:
            self.__on_render_terminated(data)
        elif event == CefEventType.CURSOR:
            self.__on_cursor_change(data)
        elif event == CefEventType.CONTEXT_MENU:
            # 不要在 CEF 的回调栈里直接弹模态菜单：等回到 Qt 事件循环再弹，
            # 这样 Continue / Cancel 一定发生在 CEF 菜单管理器登记回调之后。
            QTimer.singleShot(0, lambda payload=data: self.__on_context_menu(payload))
        elif event == CefEventType.BRIDGE_MESSAGE:
            # 「另存为网页」等内部消息用同一个通道，先给内部处理，再交给业务层
            if not self.__handle_internal_bridge_message(data):
                self.jsBridgeReceived.emit(data)
        elif event == CefEventType.NEW_TAB:
            if self.__profile is not None and self.__profile.handle_newtab_byuser and data:
                self.newtabSignal.emit(data)
        elif event == CefEventType.FULLSCREEN:
            self.__html_fullscreen = data == '1'
            self.fullScreenRequested.emit(self.__html_fullscreen)
        elif event == CefEventType.COOKIES:
            self.__on_cookies_received(data)
        elif event == CefEventType.DEVTOOLS_CREATED:
            app_logger.log_INFO('cef devtools window created')
        elif event == CefEventType.DEVTOOLS_CLOSED:
            # devtools 浏览器已经关闭（用户关掉窗口，或宿主浏览器被销毁），
            # 这里同步销毁承载它的 Qt 窗口。
            window = self.__devtools_window
            self.__devtools_window = None
            if window is not None:
                window.markClosed()
        elif event == CefEventType.CONSOLE:
            app_logger.log_INFO(f'cef console: {data}')

    def __notify_cookie_rewriter(self, url: str):
        # 页面加载完成后，把该 URL 的 Cookie 交给重写器（登录流程依赖它）
        if self.__profile is None or not self.__profile.http_rewriter or not url:
            return
        rewriter = None
        for pattern, handler in self.__profile.http_rewriter.items():
            if pattern == '*' or pattern.replace('*', '') in url:
                rewriter = handler
                break
        if rewriter is None or not self.__browser_id:
            return
        lib = _CefBridge.instance().lib()
        if lib is None:
            return
        self.__cookie_waiters[self.__browser_id] = (url, rewriter)
        try:
            lib.cef_bridge_get_cookies(self.__browser_id, _utf8(url))
        except Exception as e:
            app_logger.log_exception(e)

    # CEF OSR
    def __set_native_visible(self, visible: bool):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return
        try:
            lib.cef_bridge_set_visible(self.__browser_id, 1 if visible else 0)
        except Exception as e:
            app_logger.log_exception(e)

    def __view_size(self):
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        return max(int(self.width() * dpr), 1), max(int(self.height() * dpr), 1)

    def _handle_paint(self, buffer, width, height):
        """CEF 的 OnPaint 回调（BGRA）→ 合成到不透明底图后触发重绘。

        CEF 送来的是一帧完整的 BGRA，页面没有绘制背景的地方 alpha 为 0。
        如果直接把它 SourceOver 到控件上，这些透明像素不会覆盖上一帧的像素，
        滚动 / 重排以后就会留下错位的鬼影；所以每帧都先用底色清一遍再叠加。
        """
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        transparent = bool(self.__profile is not None and self.__profile.enable_transparent_bg)
        background = QColor(0, 0, 0, 0) if transparent else QColor(255, 255, 255)
        frame = self.__frame
        if frame is None or frame.width() != width or frame.height() != height:
            frame = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
            self.__frame = frame
        data = ctypes.string_at(buffer, width * height * 4)
        image = QImage(data, width, height, width * 4, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(frame)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(0, 0, width, height, background)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawImage(0, 0, image)
        painter.end()
        frame.setDevicePixelRatio(dpr)
        self.update()

    def __on_cookies_received(self, cookies: str):
        url, rewriter = self.__cookie_waiters.pop(self.__browser_id, (None, None))
        if rewriter is None or not cookies:
            return
        try:
            rewriter.onRequestCaught(url or '', 'GET', {'Cookie': cookies}, None)
        except Exception as e:
            app_logger.log_exception(e)

    @staticmethod
    def __cef_modifiers(event) -> int:
        mods = 0
        state = event.modifiers() if hasattr(event, 'modifiers') else Qt.NoModifier
        if state & Qt.ShiftModifier:
            mods |= 1 << 1
        if state & Qt.ControlModifier:
            mods |= 1 << 2
        if state & Qt.AltModifier:
            mods |= 1 << 3
        # OSR 拖拽（拖动滚动条、拖选文本等）需要把「当前按下的鼠标键」一起上报，
        # 否则 Chromium 只当成普通移动，滚动条会「能点不能拖」。
        buttons = event.buttons() if hasattr(event, "buttons") else Qt.NoButton
        if buttons & Qt.LeftButton:
            mods |= 1 << 4
        if buttons & Qt.MiddleButton:
            mods |= 1 << 5
        if buttons & Qt.RightButton:
            mods |= 1 << 6
        return mods

    def __cef_point(self, pos):
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        return int(pos.x() * dpr), int(pos.y() * dpr)

    @staticmethod
    def __cef_button(button) -> int:
        if button == Qt.MiddleButton:
            return 1
        if button == Qt.RightButton:
            return 2
        return 0

    def __on_shown(self):
        if not self.isVisible():
            return
        self.__create_browser()
        self.__set_native_visible(True)
        self.__start_pending_load()


# 兼容别名，需要按平台直接引用时使用
CommonWebView = CefWebView
