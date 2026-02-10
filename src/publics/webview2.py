"""webview2模块，实现了webview2与pyqt的绑定"""
# 先引入跨平台库
import os
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import pyqtSignal
from publics import app_logger
import typing

# 判断一下是不是windows
if os.name == 'nt':
    import clr
    from win32gui import SetParent, MoveWindow
else:
    app_logger.log_WARN('Your system is not Windows, so WebView2 can not work at this time')

isload = False


def loadLibs():
    """
    加载 WebView2 相关的依赖文件。
    仅在 Windows 系统上运行。

    Raises:
        RuntimeError: 如果未找到 WebView2 运行时文件。
    """
    global isload
    if not isload and os.name == 'nt':
        isload = True
        self_path = os.getcwd() + '\\binres'
        if not os.path.exists(self_path):
            raise RuntimeError(f"Error: WebView2 runtime not found at {self_path}.  Make sure the path is correct.")

        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Threading")
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.Core.dll"))
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.WinForms.dll"))

        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState, CoreWebView2HostResourceAccessKind, \
            CoreWebView2BrowsingDataKinds, CoreWebView2WebResourceContext, CoreWebView2FaviconImageFormat, \
            CoreWebView2Environment
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

        from System import Uri, Object, Action
        from System import Byte, Array
        from System.Threading import Thread, ApartmentState, ThreadStart, SendOrPostCallback
        from System.Threading.Tasks import Task
        from System.IO import MemoryStream, Stream
        from System.Drawing import Color, Point, Size
        from System.Windows.Forms import (
            AnchorStyles, DockStyle,
            Application as FormsApplication,
        )

        globals()['CoreWebView2PermissionState'] = CoreWebView2PermissionState
        globals()['CoreWebView2HostResourceAccessKind'] = CoreWebView2HostResourceAccessKind
        globals()['CoreWebView2BrowsingDataKinds'] = CoreWebView2BrowsingDataKinds
        globals()['CoreWebView2WebResourceContext'] = CoreWebView2WebResourceContext
        globals()['WebView2'] = WebView2
        globals()['CoreWebView2CreationProperties'] = CoreWebView2CreationProperties
        globals()['Uri'] = Uri
        globals()['Byte'] = Byte
        globals()['Array'] = Array
        globals()['Object'] = Object
        globals()['Action'] = Action
        globals()['Thread'] = Thread
        globals()['ApartmentState'] = ApartmentState
        globals()['ThreadStart'] = ThreadStart
        globals()['SendOrPostCallback'] = SendOrPostCallback
        globals()['Task'] = Task
        globals()['Color'] = Color
        globals()['Point'] = Point
        globals()['Size'] = Size
        globals()['AnchorStyles'] = AnchorStyles
        globals()['DockStyle'] = DockStyle
        globals()['FormsApplication'] = FormsApplication
        globals()['MemoryStream'] = MemoryStream
        globals()['Stream'] = Stream
        globals()['CoreWebView2FaviconImageFormat'] = CoreWebView2FaviconImageFormat
        globals()['CoreWebView2Environment'] = CoreWebView2Environment

        app_logger.log_INFO('WebView2 library has been loaded')


def getWebView2Version():
    """
    获取用户电脑上已安装 WebView2 的版本。

    Returns:
        str: WebView2 的版本号。如果系统不是 Windows 或获取失败，返回空字符串。
    """
    if os.name == 'nt':
        return WebView2VersionScaner.get_ver_CoreWebView2Environment()
    else:
        app_logger.log_WARN('Your system is not Windows, so WebView2 can not work at this time')
        return ''


def isWebView2Installed():
    """
    检查用户电脑上是否已安装 WebView2。

    Returns:
        bool: 如果已安装 WebView2，返回 True；否则返回 False。
    """
    if os.name == 'nt':
        return bool(WebView2VersionScaner.get_ver_CoreWebView2Environment())
    else:
        logging.log_WARN('Your system is not Windows, so WebView2 can not work at this time')
        return True


class CSharpConverter:
    """
    用于处理 C# 功能的工具类。
    """

    @classmethod
    def waitCSharpAsyncFunction(cls, task, callback: typing.Callable):
        """
        异步等待 C# 协程 task 执行完毕，并在完成执行时以 callback(result) 的形式调用回调函数。

        Args:
            task: C# 异步任务。
            callback (Callable): 回调函数，接收 task 的结果。
        """

        def wait_thread():
            task.Wait()
            callback(task.Result)

        thread = Thread(ThreadStart(wait_thread))
        thread.ApartmentState = ApartmentState.STA
        thread.Start()


class WebView2VersionScaner:
    """
        用于扫描 WebView2 版本的工具类。
        """

    @classmethod
    def get_ver_CoreWebView2Environment(cls):
        """
        获取用户电脑上已安装的 WebView2 环境版本。

        Returns:
            str: WebView2 的版本号。如果获取失败，返回空字符串。
        """
        try:
            return str(CoreWebView2Environment.GetAvailableBrowserVersionString())
        except Exception as e:
            app_logger.log_WARN('call CoreWebView2Environment.GetAvailableBrowserVersionString() failed')
            app_logger.log_exception(e)
            return ''


class HttpDataRewriter:
    """可用于重写webview中发起的http请求"""

    @classmethod
    def parseCookieToDict(cls, cookieString: str):
        """将header中的cookie字段解析为字典"""
        cookies_dic = {}
        for i in cookieString.split('; '):
            cookies_dic[i.split('=')[0]] = i.split('=')[1]

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
            在重写该方法时，请注意返回 [statusCode, header, content] 三个字段，webview内部会使用这些返回值重写响应
        """
        return statusCode, header, content


class WebViewProfile:
    """
    QWebView2View 使用的配置类。

    该类封装了在创建和初始化 WebView2（嵌入到 Qt 窗口中的 WinForms WebView2 控件）时
    会用到的各类运行时设置与 feature 开关。

    Args:
        data_folder (str): WebView2 用户数据目录（用于存放缓存、Cookie 等）。默认为环境变量 TEMP 下的 TiebaDesktopWebviewCache。注意：本构造函数不会自动创建该目录，调用方应确保目录存在或可写。
        private_mode (bool): 是否启用浏览器的无痕模式（InPrivate）。默认 False。
        user_agent (str|None): 自定义 user-agent 字符串。如果包含占位符 '[default_ua]'，在初始化时会替换为默认 UA 的实际值。
        enable_error_page (bool): 是否启用 WebView2 的内置错误页面。默认 True。
        enable_zoom_factor (bool): 是否允许缩放控件（是否启用缩放功能）。默认 True。
        handle_newtab_byuser (bool): 如果为 True，则当页面尝试打开新窗口时，库会通过信号将新窗口 URL 交给调用方处理（通过 newtabSignal）。
        enable_context_menu (bool): 是否启用默认的上下文菜单（右键菜单）。默认 True。
        enable_keyboard_keys (bool): 是否启用浏览器加速键（例如 F5/刷新、F12/开发者工具等）。默认 True。
        proxy_addr (str): 代理服务器地址，格式为 `addr:port`。默认为空字符串（不使用代理）。
        enable_gpu_boost (bool): 是否启用 GPU 硬件加速。
        enable_link_hover_text (bool): 是否显示状态栏的链接悬停文本（IsStatusBarEnabled）。默认 True。
        ignore_all_render_argvs (bool): 如果为 True，会忽略对 proxy/gpu/disable-web-security 等自动拼接的渲染参数。
        disable_web_safe (bool): 是否禁用 Web 安全策略。谨慎使用，仅用于受信任环境或调试。
        font_family (list[str]|None): 注入页面的字体优先级列表，会把这些字体通过 CSS 注入到每个页面以覆盖默认字体。
        http_rewriter (dict[str, HttpDataRewriter]|None): HTTP 请求/响应重写器映射。键为匹配模式，值为继承或实现了 HttpDataRewriter 接口的对象，用于对请求或响应进行处理。

    Behavior:
        - 这些字段仅作配置使用；具体在 WebView2 初始化过程中由 `QWebView2View` 读取并应用。
        - `http_rewriter` 的匹配逻辑：代码会遍历映射中的键，当 `k.replace('*','')` 在请求 URL 中被包含时，会选择该重写器。
        - `user_agent` 中的 '[default_ua]' 占位符会被替换为 CoreWebView2.Settings.UserAgent 的默认值（当 WebView 初始化时）。
    """

    def __init__(self,
                 data_folder: str = os.getenv("TEMP", '.') + "/TiebaDesktopWebviewCache",
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
                 font_family: list[str] = None,
                 http_rewriter: dict[str, HttpDataRewriter] = None,
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
                              font_family=self.font_family,
                              http_rewriter=self.http_rewriter)


class QWebView2View(QWidget):
    """
    可在 PyQt5 应用中嵌入的 WebView2 组件（仅限 Windows）。

    该组件封装了 Microsoft Edge WebView2（基于 Chromium），通过 .NET 的
    WinForms WebView2 控件嵌入到 Qt 窗口中。它提供了与原生 Qt WebEngine
    类似的 API，但底层使用的是系统安装的 Edge WebView2 运行时。

    **注意**：
        - 仅支持 Windows 平台（os.name == 'nt'）。
        - 必须先调用 :meth:`setProfile` 设置配置，再调用 :meth:`initRender` 初始化。
        - 所有 WebView 操作必须在其初始化完成后进行（监听 ``renderInitializationCompleted`` 信号）。

    **信号说明**：
        - ``audioMutedChanged(bool)``: 静音状态变化。
        - ``windowCloseRequested()``: 页面请求关闭窗口（如 window.close()）。
        - ``renderInitializationCompleted()``: WebView2 渲染器初始化完成。
        - ``loadStarted()``: 页面开始加载。
        - ``loadFinished(bool)``: 页面加载完成，参数表示是否成功。
        - ``urlChanged()``: 当前 URL 发生变化。
        - ``titleChanged(str)``: 页面标题变化。
        - ``renderProcessTerminated(int)``: 渲染进程崩溃，参数为退出码。
        - ``iconUrlChanged(str)``: 页面 favicon URL 变化。
        - ``fullScreenRequested(bool)``: 页面请求全屏（HTML 全屏 API）。
        - ``iconChanged(QIcon)``: 页面图标已更新为 QIcon。
        - ``jsBridgeReceived(str)``: 收到来自页面的 WebMessage（通过 postMessage）。
        - ``newtabSignal(str)``: 当 handle_newtab_byuser=True 时，新窗口请求被拦截并发出此信号。
    """

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
        """初始化 QWebView2View 实例（不创建底层 WebView2 控件）。"""
        super().__init__()
        self.__render_completed = False
        self.__webview = None
        self.__webview_core = None
        self.__current_icon = None
        self.__current_icon_binary = None
        self.__load_after_init = ''
        self.__profile = None
        self.__render_completed = False

        self.__set_background()
        self.newtabSignal.connect(self.createWindow)

    def resizeEvent(self, a0):
        """重写 QWidget.resizeEvent，确保 WebView2 控件随窗口大小调整。"""
        if self.__render_completed and self.__webview is not None:
            def _resize():
                hwnd = self.__webview.Handle.ToInt32()
                MoveWindow(hwnd, 0, 0, self.width(), self.height(), True)

            self.__run_on_ui_thread(_resize)

    def closeEvent(self, a0):
        """
        重写 QWidget.closeEvent。

        默认行为是隐藏而非销毁 WebView，以避免频繁创建/销毁带来的性能开销和资源冲突。
        如需彻底释放资源，请显式调用 :meth:`destroyWebview`。
        """
        a0.ignore()
        self.hide()

    def createWindow(self, newPageUrl: str):
        """
        当 ``handle_newtab_byuser=True`` 且页面尝试打开新窗口时被调用。

        子类可重写此方法以自定义新窗口行为（例如在新标签页或新窗口中打开）。

        Args:
            newPageUrl (str): 请求打开的新页面 URL。
        """
        pass

    def baseWebViewObject(self):
        """
        获取底层 .NET WebView2 对象（用于高级控制）。

        Returns:
            tuple: (WinForms.WebView2, CoreWebView2) 实例。

        Notes:
            - 请勿直接在 Qt 主线程外操作返回的对象，否则可能导致跨线程异常。
            - 详细 API 参见：https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2
        """
        return self.__webview, self.__webview_core

    def destroyWebview(self):
        """
        异步销毁 WebView2 实例（非阻塞）。

        调用后，WebView 控件将被释放，但函数立即返回。
        若需等待销毁完成，请使用 :meth:`destroyWebviewUntilComplete`。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Dispose(True)
                return ''

            self.__run_on_ui_thread(_load)

    def destroyWebviewUntilComplete(self):
        """
        同步销毁 WebView2 实例（阻塞直到完成）。

        适用于需要确保资源完全释放后再执行后续操作的场景。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Dispose(True)
                return ''

            self.__get_value_ui_thread(_load)

    def clearCacheData(self):
        """
        清除磁盘缓存、下载历史和浏览历史。

        注意：不会清除 Cookie、本地存储或自动填充数据。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                datakinds = (
                        CoreWebView2BrowsingDataKinds.DiskCache |
                        CoreWebView2BrowsingDataKinds.DownloadHistory |
                        CoreWebView2BrowsingDataKinds.BrowsingHistory
                )
                self.__webview.CoreWebView2.Profile.ClearBrowsingDataAsync(datakinds)

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def clearCookies(self):
        """
        清除 Cookie、自动填充、密码保存及所有 DOM 存储（如 localStorage）。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                datakinds = (
                        CoreWebView2BrowsingDataKinds.Cookies |
                        CoreWebView2BrowsingDataKinds.GeneralAutofill |
                        CoreWebView2BrowsingDataKinds.PasswordAutosave |
                        CoreWebView2BrowsingDataKinds.AllDomStorage
                )
                self.__webview.CoreWebView2.Profile.ClearBrowsingDataAsync(datakinds)

            self.__get_value_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def setProfile(self, profile: WebViewProfile):
        """
        设置 WebView2 的运行配置。

        必须在调用 :meth:`initRender` 前设置，且只能设置一次。

        Args:
            profile (WebViewProfile): 配置对象。
        """
        if self.__profile is None:
            self.__profile = profile

    def profile(self) -> WebViewProfile:
        """
        获取当前使用的 WebViewProfile 配置。

        Returns:
            WebViewProfile: 当前配置实例。
        """
        return self.__profile

    def renderProcessID(self) -> int:
        """
        获取 WebView2 渲染进程的 PID。

        Returns:
            int: 进程 ID；若未初始化则返回 -1。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.BrowserProcessId)
        else:
            return -1

    def isRenderInitOk(self) -> bool:
        """
        检查 WebView2 是否已完成初始化。

        Returns:
            bool: True 表示已就绪，可安全调用其他方法。
        """
        return self.__render_completed

    def iconBinary(self) -> bytes:
        """
        获取当前页面图标的原始字节数据（PNG 格式）。

        Returns:
            bytes: 图标二进制数据；若无图标或未初始化则返回空字节串。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__current_icon_binary if self.__current_icon_binary else b''
        return b''

    def icon(self) -> QIcon:
        """
        获取当前页面图标的 QIcon 对象。

        Returns:
            QIcon: 图标对象；若无图标或未初始化则返回空 QIcon。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__current_icon if self.__current_icon is not None else QIcon()
        return QIcon()

    def iconUrl(self) -> str:
        """
        获取当前页面图标的 URL。

        Returns:
            str: 图标 URL 字符串；若无则返回空字符串。
        """
        if self.__render_completed and self.__webview is not None:
            return str(self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.FaviconUri))
        return ''

    def isAudioMuted(self) -> bool:
        """
        检查当前页面是否处于静音状态。

        Returns:
            bool: True 表示已静音。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.IsMuted)
        return False

    def setAudioMuted(self, ismuted: bool):
        """
        设置页面静音状态。

        Args:
            ismuted (bool): True 为静音，False 为取消静音。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.IsMuted = ismuted

            self.__run_on_ui_thread(_load)
        else:
            logging.log_WARN('WebView has not inited')

    def isHtmlInFullScreenState(self) -> bool:
        """
        检查页面是否通过 HTML Fullscreen API 进入全屏模式。

        注意：这与 Qt 窗口的全屏状态无关。

        Returns:
            bool: True 表示页面处于 HTML 全屏状态。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.ContainsFullScreenElement)
        return False

    def title(self) -> str:
        """
        获取当前页面的标题。

        Returns:
            str: 页面标题。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.DocumentTitle)
        return ''

    def forward(self):
        """前进到历史记录中的下一页（如果可能）。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.GoForward()

            self.__run_on_ui_thread(_load)
        else:
            logging.log_WARN('WebView has not inited')

    def back(self):
        """后退到历史记录中的上一页（如果可能）。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.GoBack()

            self.__run_on_ui_thread(_load)
        else:
            logging.log_WARN('WebView has not inited')

    def reload(self):
        """重新加载当前页面。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Reload()

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def url(self) -> str:
        """
        获取当前页面的 URL。

        Returns:
            str: 完整的 URL 字符串。
        """
        if self.__render_completed and self.__webview is not None:
            return str(self.__webview.Source)
        return ''

    def setHtml(self, html: str = '<html></html>'):
        """
        直接渲染指定的 HTML 字符串（不发起网络请求）。

        Args:
            html (str): 要渲染的 HTML 内容。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.NavigateToString(html)

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def zoomFactor(self) -> float:
        """
        获取当前页面的缩放比例。

        Returns:
            float: 缩放因子（1.0 表示 100%）。
        """
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.ZoomFactor)
        return 1.0

    def setZoomFactor(self, f: float):
        """
        设置页面缩放比例。

        Args:
            f (float): 缩放因子（例如 1.5 表示 150%）。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.ZoomFactor = f

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def load(self, url: str):
        """
        加载指定的 URL（需在 WebView 初始化完成后调用）。

        Args:
            url (str): 要加载的网页地址。
        """

        def _load():
            if self.__webview is not None:
                self.__webview.Source = Uri(url)

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def loadAfterRender(self, url: str):
        """
        设置在 WebView 初始化完成后自动加载的 URL。

        适用于在调用 :meth:`initRender` 前就确定初始页面的场景。

        Args:
            url (str): 初始化完成后要加载的 URL。
        """
        self.__load_after_init = url

    def openDevtoolsWindow(self):
        """打开独立的开发者工具窗口。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenDevToolsWindow()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def openChromiumTaskmgrWindow(self):
        """打开基于 Chromium 的任务管理器窗口（显示内存/CPU 占用）。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenTaskManagerWindow()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def openDefaultDownloadDialog(self):
        """显示默认的下载悬浮窗。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenDefaultDownloadDialog()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def openPrintDialog(self):
        """打开网页打印对话框。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.ShowPrintUI()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            logging.log_WARN('WebView has not inited')

    def openSaveHtmlDialog(self):
        """打开“另存为”对话框以保存当前页面。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.ShowSaveAsUIAsync()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def initRender(self):
        """
        初始化 WebView2 渲染器。

        必须在设置 Profile 后调用。初始化完成后会发出 ``renderInitializationCompleted`` 信号。
        """
        if os.name == 'nt':
            if self.__profile is not None and not self.__render_completed:
                self.__run()
            else:
                app_logger.log_WARN('Your system is not Windows, so WebView2 can not work at this time')

    def __set_background(self):
        self.setStyleSheet("QWidget{background-color: white;}")

    def __run(self):
        try:
            args = ''
            if not self.__profile.ignore_all_render_argvs:
                if self.__profile.proxy_addr:
                    args += f"--proxy-server=\"{self.__profile.proxy_addr}\" "
                if not self.__profile.enable_gpu_boost:
                    args += "--disable-gpu "
                if self.__profile.disable_web_safe:
                    args += '--disable-web-security '

            FormsApplication.EnableVisualStyles()  # 确保启用视觉样式
            self.__webview = WebView2()
            webview = self.__webview
            webview_properties = CoreWebView2CreationProperties()
            webview_properties.UserDataFolder = self.__profile.data_folder
            webview_properties.IsInPrivateModeEnabled = self.__profile.private_mode
            webview_properties.AdditionalBrowserArguments = args
            webview.CreationProperties = webview_properties
            webview.DefaultBackgroundColor = Color.Transparent
            webview.Dock = DockStyle.Fill  # 设置停靠属性

            webview.CoreWebView2InitializationCompleted += self.__on_webview_ready

            webview.EnsureCoreWebView2Async(None)  # 初始化WebView
        except Exception as e:
            app_logger.log_WARN('WebView2 start init failed')
            app_logger.log_exception(e)

    def __get_value_ui_thread(self, func):
        vs = []
        if self.__webview is not None and self.__webview.IsHandleCreated:
            def get_v(_):
                rtv = func()
                vs.append(rtv)

            self.__webview.Invoke(SendOrPostCallback(get_v), '')
            return vs[0]

    def __run_on_ui_thread(self, func):
        """在 WinForms UI 线程上执行给定的函数。"""

        if self.__webview is not None:
            if self.__webview.IsHandleCreated:
                self.__webview.BeginInvoke(SendOrPostCallback(lambda _: func()), '')

    def __wait_task_give_callback(self, task, callback):
        CSharpConverter.waitCSharpAsyncFunction(task, callback)

    def __set_parent(self):
        if self.__webview is not None:
            def _set_parent():
                hwnd = self.__webview.Handle.ToInt32()
                SetParent(hwnd, int(self.winId()))
                MoveWindow(hwnd, 0, 0, self.width(), self.height(), True)

            _set_parent()

    def __remake_qicon(self):
        def on_stream_copied(memoryStream):
            iconBytes = bytes(memoryStream.ToArray())  # 复制完后，转为python的字节数据
            pixmap = QPixmap()
            pixmap.loadFromData(iconBytes)
            if not pixmap.isNull():  # 图像不为空，加载成功
                self.__current_icon = QIcon(pixmap)
                self.__current_icon_binary = iconBytes
                self.iconChanged.emit(self.__current_icon)

        def on_icon_got(faviconStream):
            memoryStream = MemoryStream()
            task = faviconStream.CopyToAsync(memoryStream)  # 异步复制到内存缓冲区
            self.__wait_task_give_callback(task, lambda r: on_stream_copied(memoryStream))

        task = self.__webview_core.GetFaviconAsync(CoreWebView2FaviconImageFormat.Png)  # 异步获取icon流
        self.__wait_task_give_callback(task, on_icon_got)

    def __on_fullscreen_requested(self, _, args):
        self.fullScreenRequested.emit(self.isHtmlInFullScreenState())

    def __on_icon_changed(self, _, args):
        self.__remake_qicon()
        self.iconUrlChanged.emit(self.iconUrl())

    def __on_audio_mute_changed(self, _, args):
        self.audioMutedChanged.emit(self.isAudioMuted())

    def __on_new_window_open(self, _, args):
        if not self.profile().handle_newtab_byuser:
            args.Handled = False
        else:
            args.Handled = True
            self.newtabSignal.emit(args.Uri)

    def __on_window_close(self, _, args):
        self.windowCloseRequested.emit()

    def __on_render_crash(self, _, args):
        self.renderProcessTerminated.emit(args.ExitCode)
        app_logger.log_WARN(f'WebView2 render crashed with exit code {args.ExitCode}')

    def __on_url_change(self, _, args):
        self.urlChanged.emit()

    def __on_navigation_start(self, _, args):
        self.loadStarted.emit()

    def __on_navigation_completed(self, _, args):
        self.loadFinished.emit(args.IsSuccess)

    def __title_change_event(self, _, args):
        self.titleChanged.emit(self.title())

    def __on_request_got(self, _, args):
        try:
            url = str(args.Request.Uri)
            handler = None
            if not self.profile().http_rewriter:
                return
            for k, v in self.profile().http_rewriter.items():
                if k.replace('*', '') in url or k == '*':  # 匹配url
                    handler = v
                    break
            if not handler:
                return

            # request adapter
            if args.Request:
                method = str(args.Request.Method)
                header_dict = {}
                header_iterator = args.Request.Headers.GetIterator()
                while header_iterator.HasCurrentHeader:
                    header_dict[str(header_iterator.Current.Key)] = str(header_iterator.Current.Value)
                    header_iterator.MoveNext()
                if not args.Request.Content:
                    content = None
                else:
                    memoryStream = MemoryStream()
                    args.Request.Content.CopyTo(memoryStream)
                    content = bytes(memoryStream.ToArray())
            else:
                method, header_dict, content = '', {}, None
            url, method, header, content = handler.onRequestCaught(url, method, header_dict, content)

            args.Request.Uri = url
            args.Request.Method = method
            for k, v in header.items():
                args.Request.Headers.SetHeader(k, v)
            if content:
                new_stream = Stream()
                new_stream.Write(Array[Byte](content), 0, len(content))
                args.Request.Content = new_stream

            # response adapter
            if args.Response:
                statusCode = int(args.Response.StatusCode)
                header_dict = {}
                header_iterator = args.Response.Headers.GetIterator()
                while header_iterator.HasCurrentHeader:
                    header_dict[str(header_iterator.Current.Key)] = str(header_iterator.Current.Value)
                    header_iterator.MoveNext()
                if not args.Response.Content:
                    content = None
                else:
                    memoryStream = MemoryStream()
                    args.Response.Content.CopyTo(memoryStream)
                    content = bytes(memoryStream.ToArray())
            else:
                statusCode, header_dict, content = -1, {}, None

            statusCode, header, content = handler.onResponseCaught(url, statusCode, header_dict, content)

            header_str = '\n'.join(list(f'{k}: {v}' for k, v in header.items()))
            new_stream = MemoryStream()
            if content:
                new_stream.Write(Array[Byte](content), 0, len(content))
            response = self.__webview.CoreWebView2.Environment.CreateWebResourceResponse(new_stream, statusCode, "",
                                                                                         header_str)
            args.Response = response
        except Exception as e:
            app_logger.log_WARN(f'WebView2 Http Catcher failed')
            app_logger.log_exception(e)

    def __on_js_msg_received(self, _, args):
        message = args.TryGetWebMessageAsString()
        self.jsBridgeReceived.emit(message)

    def __set_font_family(self):
        # 注入 CSS
        font_list_string = ', '.join(list(f'\"{font}\"' for font in self.profile().font_family))
        font_css = f'''
                html, body, *, p, div, span, li, a, input, button {{
                    font-family: {font_list_string} !important;
                }}
                '''
        inject_script = f"""
                (function() {{
                    // 方法1: adoptedStyleSheets (高优先级)
                    try {{
                        const sheet = new CSSStyleSheet();
                        sheet.replaceSync(`{font_css}`);
                        document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
                        return;
                    }} catch (e) {{}}

                    // 方法2: <style> 标签
                    const style = document.createElement('style');
                    style.textContent = `{font_css}`;
                    document.documentElement.appendChild(style);
                }})();
                """

        # 执行注入
        self.__webview_core.AddScriptToExecuteOnDocumentCreatedAsync(inject_script)

    def __on_webview_ready(self, webview_instance, args):
        if not args.IsSuccess:
            app_logger.log_WARN('WebView2 initialization failed')
            logging.log_WARN(str(args.InitializationException))
            return

        self.__set_parent()

        configuration = self.__profile
        core = webview_instance.CoreWebView2
        self.__webview_core = core

        if self.profile().http_rewriter:
            for k, v in self.profile().http_rewriter.items():
                core.AddWebResourceRequestedFilter(k, CoreWebView2WebResourceContext.All)

        core.NavigationStarting += self.__on_navigation_start
        core.NavigationCompleted += self.__on_navigation_completed
        core.SourceChanged += self.__on_url_change
        core.DocumentTitleChanged += self.__title_change_event
        core.ProcessFailed += self.__on_render_crash
        core.WindowCloseRequested += self.__on_window_close
        core.NewWindowRequested += self.__on_new_window_open
        core.IsMutedChanged += self.__on_audio_mute_changed
        core.FaviconChanged += self.__on_icon_changed
        core.ContainsFullScreenElementChanged += self.__on_fullscreen_requested
        core.WebResourceRequested += self.__on_request_got
        core.WebMessageReceived += self.__on_js_msg_received

        settings = core.Settings
        settings.AreBrowserAcceleratorKeysEnabled = configuration.enable_keyboard_keys
        settings.AreDefaultScriptDialogsEnabled = True
        settings.AreDefaultContextMenusEnabled = configuration.enable_context_menu
        settings.AreDevToolsEnabled = True
        settings.IsBuiltInErrorPageEnabled = configuration.enable_error_page
        settings.IsScriptEnabled = True
        settings.IsWebMessageEnabled = True
        settings.IsStatusBarEnabled = configuration.enable_link_hover_text
        settings.IsSwipeNavigationEnabled = False
        settings.IsZoomControlEnabled = configuration.enable_zoom_factor

        if self.profile().font_family:
            self.__set_font_family()

        ua = configuration.user_agent
        if ua:
            settings.UserAgent = ua.replace('[default_ua]', settings.UserAgent)

        # set virtual host path
        local_path = os.getcwd() + '\\ui\\js_player'
        core.SetVirtualHostNameToFolderMapping("clb.tiebadesktop.localpage.jsplayer",
                                               local_path,
                                               CoreWebView2HostResourceAccessKind.Allow)

        self.__render_completed = True
        self.renderInitializationCompleted.emit()
        if self.__load_after_init:
            self.load(self.__load_after_init)
