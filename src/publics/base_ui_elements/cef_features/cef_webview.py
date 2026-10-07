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
import typing

from PyQt5.QtCore import pyqtSignal, Qt, QUrl, QTimer, QEvent
from PyQt5.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QFileDialog, QApplication

from publics import app_logger

IS_WINDOWS = os.name == 'nt'

BRIDGE_LIB_NAME = 'cef_bridge.dll' if IS_WINDOWS else 'libcef_bridge.so'
CEF_LIB_NAME = 'libcef.dll' if IS_WINDOWS else 'libcef.so'
HELPER_NAME = 'cef_bridge_helper.exe' if IS_WINDOWS else 'cef_bridge_helper'

# 视频播放页使用的本地虚拟主机名（与 Windows 端 WebView2 保持一致）
VIRTUAL_HOST = 'clb.tiebadesktop.localpage.jsplayer'
JS_PLAYER_DIR = os.path.join(os.getcwd(), 'ui', 'js_player')


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



# ---------------------------------------------------------------------- 运行时位置

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


# ---------------------------------------------------------------------- 本地页面服务

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


# ---------------------------------------------------------------------- 配置与接口

class HttpDataRewriter:
    """可用于捕获或重写 webview 中发起的 http 请求（与 Windows 端接口保持一致）。"""

    @classmethod
    def parseCookieToDict(cls, cookieString: str):
        cookies_dic = {}
        try:
            for i in cookieString.split('; '):
                cookies_dic[i.split('=')[0]] = i.split('=')[1]
        except Exception as e:
            app_logger.log_exception(e)
        return cookies_dic

    @classmethod
    def packCookieToString(cls, cookieDict: typing.Dict[str, str]):
        cookies = []
        for k, v in cookieDict.items():
            cookies.append(f'{k}={v}')
        return '; '.join(cookies)

    def onRequestCaught(self, url: str, method: str, header: typing.Dict[str, str],
                        content: typing.Optional[bytes]):
        # 捕捉到 http 请求时调用；header 里包含真实请求头（Cookie / Referer 等）。
        # 注意：CEF 的资源回调发生在 IO 线程，桥接层切回 UI 线程后才回调到这里，
        # 所以返回值不会用来重写请求（只做观察），需要重写请在业务层另行处理。
        return url, method, header, content

    def onResponseCaught(self, url: str, statusCode: int, header: typing.Dict[str, str],
                         content: typing.Optional[bytes]):
        # 捕捉到 http 响应时调用（含状态码、响应头与响应体；响应体最大 4MB）。
        # 与 Windows 端一致：返回值不会用来重写响应。
        return statusCode, header, content


class WebViewProfile:
    """CefWebView 使用的配置类，字段与 Windows 端 ``webview2.WebViewProfile`` 保持一致。"""

    def __init__(self,
                 data_folder: str = os.getenv("TEMP", '../..') + "/TiebaDesktopWebViewCache",
                 private_mode=False,
                 user_agent: str = None,
                 enable_error_page: bool = True,
                 enable_zoom_factor: bool = True,
                 handle_newtab_byuser: bool = False,
                 enable_context_menu: bool = True,
                 enable_keyboard_keys: bool = True,
                 proxy_addr: str = "",
                 enable_gpu_boost: bool = True,
                 enable_link_hover_text: bool = True,
                 ignore_all_render_argvs: bool = False,
                 disable_web_safe: bool = False,
                 font_family: list = None,
                 http_rewriter: dict = None,
                 enable_transparent_bg: bool = False,
                 enable_osr: bool = False,
                 ):
        self.data_folder = data_folder
        self.private_mode = private_mode
        self.user_agent = user_agent
        self.enable_error_page = enable_error_page
        self.enable_zoom_factor = enable_zoom_factor
        self.handle_newtab_byuser = handle_newtab_byuser
        self.enable_context_menu = enable_context_menu
        self.enable_keyboard_keys = enable_keyboard_keys
        self.proxy_addr = proxy_addr
        self.enable_gpu_boost = enable_gpu_boost
        self.enable_link_hover_text = enable_link_hover_text
        self.ignore_all_render_argvs = ignore_all_render_argvs
        self.disable_web_safe = disable_web_safe
        self.font_family = font_family
        self.http_rewriter = http_rewriter
        self.enable_transparent_bg = enable_transparent_bg
        self.enable_osr = enable_osr

    def clone(self):
        return WebViewProfile(data_folder=self.data_folder,
                              private_mode=self.private_mode,
                              user_agent=self.user_agent,
                              enable_error_page=self.enable_error_page,
                              enable_zoom_factor=self.enable_zoom_factor,
                              handle_newtab_byuser=self.handle_newtab_byuser,
                              enable_context_menu=self.enable_context_menu,
                              enable_keyboard_keys=self.enable_keyboard_keys,
                              proxy_addr=self.proxy_addr,
                              enable_gpu_boost=self.enable_gpu_boost,
                              enable_link_hover_text=self.enable_link_hover_text,
                              ignore_all_render_argvs=self.ignore_all_render_argvs,
                              disable_web_safe=self.disable_web_safe,
                              font_family=self.font_family,
                              http_rewriter=self.http_rewriter,
                              enable_transparent_bg=self.enable_transparent_bg,
                              enable_osr=self.enable_osr)


# ---------------------------------------------------------------------- 桥接层封装


# 「另存为网页」分块传输的块大小（字符数）
_SAVE_HTML_CHUNK = 40000

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


def _utf8(text: typing.Optional[str]):
    return text.encode('utf-8') if text else None


def _build_extra_args() -> str:
    """
    组装传给 CEF 的额外命令行参数。
    """
    args = os.environ.get('TIEBADESKTOP_CEF_ARGS', '').strip()
    return args


def _default_user_agent() -> str:
    if IS_WINDOWS:
        return ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36')
    return ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/109.0.5414.120 Safari/537.36')


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
        lib.cef_bridge_init.argtypes = [ctypes.c_char_p] * 7
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
                                       _utf8(user_agent), _utf8(extra_args))
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
        self.__frozen_enabled = False
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
        self.__taskmgr_window = None

        self.__devtools_window = None

        self.newtabSignal.connect(self.createWindow)

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
                # OSR：不创建原生窗口，父窗口句柄传 0
                handle = 0
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

    def __build_fallback(self):
        label = QLabel('当前环境无法使用 CEF 内核的内置浏览器。\n'
                       '请确认 binres/cef_bridge 与 binres/cef 下的 CEF 运行时是否完整。', self)
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
        # 桥接层会在页面加载完成时注入这段脚本（目前只用于注入字体）
        font_family = self.__profile.font_family if self.__profile is not None else None
        if not font_family:
            return ''
        font_list = ', '.join(f'"{font}"' for font in font_family)
        return ("(function(){try{var style=document.createElement('style');"
                "style.textContent='html,body,*{font-family:" + font_list + " !important;}';"
                                                                            "document.documentElement.appendChild(style);}catch(e){}})();")

    # -------------------------------------------------- 事件分发
    def _handle_bridge_event(self, event: int, data: str):
        if event == CefEventType.CLOSE:
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

    def __on_cookies_received(self, cookies: str):
        url, rewriter = self.__cookie_waiters.pop(self.__browser_id, (None, None))
        if rewriter is None or not cookies:
            return
        try:
            rewriter.onRequestCaught(url or '', 'GET', {'Cookie': cookies}, None)
        except Exception as e:
            app_logger.log_exception(e)

    # -------------------------------------------------- 生命周期
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

    def __on_shown(self):
        if not self.isVisible():
            return
        self.__create_browser()
        self.__set_native_visible(True)
        self.__start_pending_load()

    def hideEvent(self, a0):
        super().hideEvent(a0)
        self.__set_native_visible(False)

    def closeEvent(self, a0):
        a0.ignore()
        self.hide()

    def __set_native_visible(self, visible: bool):
        lib = _CefBridge.instance().lib()
        if lib is None or not self.__browser_id:
            return
        try:
            lib.cef_bridge_set_visible(self.__browser_id, 1 if visible else 0)
        except Exception as e:
            app_logger.log_exception(e)

    # -------------------------------------------------- OSR 画面与输入
    def __view_size(self):
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        return max(int(self.width() * dpr), 1), max(int(self.height() * dpr), 1)

    def _handle_paint(self, buffer, width, height):
        """CEF 的 OnPaint 回调（BGRA、物理像素）→ QImage 并触发重绘。"""
        data = ctypes.string_at(buffer, width * height * 4)
        image = QImage(data, width, height, width * 4, QImage.Format_ARGB32_Premultiplied)
        self.__frame = image.copy()  # 必须拷贝：回调返回后 buffer 失效
        try:
            dpr = float(self.devicePixelRatioF()) or 1.0
        except Exception:
            dpr = 1.0
        self.__frame.setDevicePixelRatio(dpr)
        self.update()

    def paintEvent(self, a0):
        if self.__frame is None:
            super().paintEvent(a0)
            return
        painter = QPainter(self)
        painter.drawImage(0, 0, self.__frame)
        painter.end()

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

    def createWindow(self, newPageUrl: str):
        # 当 handle_newtab_byuser=True 且页面尝试打开新窗口时被调用，可由子类重写
        pass

    def destroyWebview(self):
        self.__destroy_webview()

    def destroyWebviewUntilComplete(self):
        self.__destroy_webview()

    def __destroy_webview(self):
        self.__teardown_partial()
        self.__render_completed = False

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

    # -------------------------------------------------- 冻结模式
    def isFrozenModeEnabled(self) -> bool:
        return self.__frozen_enabled

    def setFrozenModeEnabled(self, enable: bool):
        # 冻结模式下隐藏 CEF 视图，减少后台标签页的资源占用
        if self.__frozen_enabled == enable:
            return
        self.__frozen_enabled = enable
        self.__set_native_visible(not enable)

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

    # -------------------------------------------------- 工具窗口
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
    def openChromiumTaskmgrWindow(self):
        # CEF 没有自带任务管理器，这里用 Qt 自己实现一个（列出所有 CEF 子进程）
        from publics.base_ui_elements.cef_features import cef_tools
        if self.__taskmgr_window is None:
            self.__taskmgr_window = cef_tools.CefTaskManagerWindow()
        self.__taskmgr_window.show()
        self.__taskmgr_window.raise_()
        self.__taskmgr_window.activateWindow()
        self.__taskmgr_window.refresh()

    def openDefaultDownloadDialog(self):
        from publics.base_ui_elements.cef_features import cef_tools
        cef_tools.DownloadManager.instance().show_panel(self)
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
            "{type:'saveHtml',i:i,total:h.length,d:h.substr(i," + str(_SAVE_HTML_CHUNK) + ")}));}"
            "}catch(e){console.log('__TIEBA_BRIDGE__'+JSON.stringify("
            "{type:'saveHtml',error:String(e)}));}})();")
        self.runJavaScriptAsync(script)


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
        super().closeEvent(a0)


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


# 兼容别名，需要按平台直接引用时使用
QWebView2View = CefWebView
CommonWebView = CefWebView
