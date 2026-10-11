"""
跨平台 WebView 的统一封装层。

本模块是程序中使用 webview 的唯一入口：业务代码统一使用本模块暴露的
``CommonWebView`` / ``WebViewProfile`` / ``HttpDataRewriter`` / ``loadLibs`` /
``isWebViewInstalled``，由本模块根据运行平台与可用性把调用转发到具体实现：

- Windows：优先使用系统自带的 WebView2（``windows_features/webview2.py``），
  当系统没有安装 WebView2 运行时，则改用 CEF（``cef_features/cef_webview.py``）
- Linux：使用 CEF

WebView2 至今没有离屏渲染（OSR）能力，开启配置里的 ``enable_osr`` 时 Windows 上会
直接选用 CEF 内核；只有 CEF 运行时缺失时才回退 WebView2（此时 OSR 不生效）。

可用启动参数 ``--force-webview`` 强制指定后端：``webview2`` / ``cef`` / ``auto``（默认）。
CEF 是可选依赖：没有集成 CEF 运行时（binres/cef 与 binres/cef_bridge）时
``isWebViewInstalled()`` 返回 False，程序会照常启动并自动降级。
"""
import os
import sys
import typing

from publics import app_logger


def _prepare_windows_com():
    """
    在接触 .NET / WebView2 之前，先把主线程的 COM 初始化为 STA。

    pythonnet 启动 .NET 运行时时会把当前线程初始化为 MTA，而 WebView2 要求 STA；
    一旦顺序反了，就会在 CoreWebView2Environment.CreateAsync 处报
    RPC_E_CHANGED_MODE (0x80010106)。Qt 自己也会做同样的事（OleInitialize），
    这里提前做一遍，保证后面探测和使用 WebView2 时线程已经是 STA。
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        result = ctypes.windll.ole32.OleInitialize(None)
        if result not in (0, 1):  # S_OK / S_FALSE
            app_logger.log_WARN(f'OleInitialize returned 0x{result & 0xFFFFFFFF:08X}')
    except Exception as e:
        app_logger.log_exception(e)


def _load_webview2():
    from publics.base_ui_elements.windows_features import webview2
    return webview2


def _load_cef():
    from publics.base_ui_elements.cef_features import cef_webview
    return cef_webview


def _select_backend():
    mode = 'auto'
    for i in sys.argv:
        if i.startswith('--force-webview'):
            mode = i.split('=')[-1]
            break

    if os.name == 'nt':
        # 必须早于任何 .NET 调用，否则主线程会被设成 MTA，WebView2 将无法初始化
        _prepare_windows_com()

        if mode == 'webview2':
            return _load_webview2(), 'windows/webview2'
        if mode == 'cef':
            return _load_cef(), 'windows/cef'

        webview2 = None
        try:
            webview2 = _load_webview2()
            webview2.loadLibs()
            if webview2.isWebViewInstalled():
                return webview2, 'windows/webview2'
        except Exception as e:
            app_logger.log_WARN('probe webview2 failed')
            app_logger.log_exception(e)

        try:
            cef = _load_cef()
            if cef.is_available():
                return cef, 'windows/cef'
        except Exception as e:
            app_logger.log_WARN('probe cef failed')
            app_logger.log_exception(e)

        if webview2 is not None:
            return webview2, 'windows/webview2'
        return _load_cef(), 'windows/cef'

    if mode == 'webview2':
        app_logger.log_WARN('webview2 is only available on windows, fallback to cef')
    return _load_cef(), 'linux/cef'


def prefer_x11() -> bool:
    """
    Linux 下 CEF 以子窗口方式嵌入 Qt 需要 X11（xcb）。

    供 main.set_qpa() 在创建 QApplication 之前调用，用于选择合适的平台插件。
    """
    if os.name == 'nt':
        return False
    checker = getattr(_platform_webview, 'x11_embedding_possible', None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception as e:
        app_logger.log_exception(e)
        return False


def shutdown():
    """进程退出前释放 webview 后端（目前只有 CEF 需要）。"""
    shutdown_func = getattr(_platform_webview, 'shutdown', None)
    if shutdown_func is None:
        return
    try:
        shutdown_func()
    except Exception as e:
        app_logger.log_exception(e)


def loadLibs():
    """加载当前后端所需的依赖与运行时文件。"""
    return _platform_webview.loadLibs()


def isWebViewInstalled() -> bool:
    """检查当前后端的 webview 运行时是否可用。"""
    checker = getattr(_platform_webview, 'isWebViewInstalled', None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception as e:
        app_logger.log_WARN('check webview runtime failed')
        app_logger.log_exception(e)
        return False


def getWebViewVersion() -> str:
    """获取当前后端的 webview 运行时版本。"""
    checker = getattr(_platform_webview, 'getWebViewVersion', None)
    if checker is None:
        return ''
    try:
        return checker()
    except Exception as e:
        app_logger.log_WARN('check webview version failed')
        app_logger.log_exception(e)
        return ''


class HttpDataRewriter:
    """可用于捕获或重写webview中发起的http请求"""

    @classmethod
    def parseCookieToDict(cls, cookieString: str):
        """将header中的cookie字段解析为字典"""
        cookies_dic = {}
        try:
            for i in cookieString.split('; '):
                cookies_dic[i.split('=')[0]] = i.split('=')[1]
        except Exception as e:
            app_logger.log_exception(e)

        return cookies_dic

    @classmethod
    def packCookieToString(cls, cookieDict: typing.Dict[str, str]):
        """将cookies字典构造为字符串"""
        cookies = []
        for k, v in cookieDict.items():
            cookies.append(f'{k}={v}')

        return '; '.join(cookies)

    def onRequestCaught(self, url: str, method: str, header: typing.Dict[str, str], content: typing.Optional[bytes]):
        """
        捕捉到http请求时，会调用此方法

        Notes:
            在重写该方法时，请注意返回 [url, method, header, content] 四个字段，webview内部会使用这些返回值重写请求
        """
        return url, method, header, content

    def onResponseCaught(self, url: str, statusCode: int, header: typing.Dict[str, str],
                         content: typing.Optional[bytes]):
        """
        捕捉到http响应时，会调用此方法

        Notes:
            目前还尚未支持http响应数据的重写，返回 [statusCode, header, content] 不会起作用
        """
        return statusCode, header, content


class WebViewProfile:
    """
    浏览器使用的配置类。

    该类封装了在创建和初始化 WebView 时会用到的各类运行时设置与 feature 开关

    Args:
        data_folder (str): WebView 用户数据目录（用于存放缓存、Cookie 等）。默认为环境变量 TEMP 下的 TiebaDesktopWebviewCache。
        private_mode (bool): 是否启用浏览器的无痕模式（InPrivate）。默认 False。
        user_agent (str|None): 自定义 user-agent 字符串。如果包含占位符 '[default_ua]'，在初始化时会替换为默认 UA 的实际值。
        enable_error_page (bool): 是否启用 WebView 的内置错误页面。默认 True。
        enable_zoom_factor (bool): 是否允许缩放控件（是否启用缩放功能）。默认 True。
        handle_newtab_byuser (bool): 如果为 True，则当页面尝试打开新窗口时，库会通过信号将新窗口 URL 交给调用方处理（通过 newtabSignal）。
        enable_context_menu (bool): 是否启用默认的上下文菜单（右键菜单）。默认 True。
        enable_keyboard_keys (bool): 是否启用浏览器加速键（例如 F5/刷新、F12/开发者工具等）。默认 True。
        proxy_addr (str): 代理服务器地址，格式为 `addr:port`。默认为空字符串（不使用代理）。
        enable_gpu_boost (bool): 是否启用 GPU 硬件加速。
        enable_link_hover_text (bool): 是否显示状态栏的链接悬停文本（IsStatusBarEnabled）。默认 True。
        ignore_all_render_argvs (bool): 如果为 True，会忽略对 proxy/gpu/disable-web-security 等自动拼接的渲染参数。
        disable_web_safe (bool): 是否禁用 Web 安全策略。谨慎使用，仅用于受信任环境或调试。
        http_rewriter (dict[str, HttpDataRewriter]|None): HTTP 请求/响应重写器映射
        enable_transparent_bg (bool): 是否启用透明背景。开启后，WebView 的背景将与父 QWidget 的相同。否则将使用纯白色背景。
        enable_osr (bool): 是否启用离屏渲染
    Behavior:
        - `http_rewriter` 的匹配逻辑：代码会遍历映射中的键，当 `k.replace('*','')` 在请求 URL 中被包含时，会选择该重写器。
    """

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
                 http_rewriter: dict[str, HttpDataRewriter] = None,
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
        self.http_rewriter = http_rewriter
        self.enable_transparent_bg = enable_transparent_bg
        self.enable_osr = enable_osr

    def clone(self):
        """
        克隆当前 profile 为一个新的 `WebViewProfile` 实例。

        Returns:
            WebViewProfile: 一个新的 `WebViewProfile` 实例，字段值与当前实例相同。
        """
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
                              http_rewriter=self.http_rewriter,
                              enable_transparent_bg=self.enable_transparent_bg,
                              enable_osr=self.enable_osr)


_platform_webview, PLATFORM = _select_backend()
# 组件类型与配置类统一对外暴露
CommonWebView = _platform_webview.CommonWebView
