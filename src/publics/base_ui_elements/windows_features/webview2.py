"""
Windows 平台上 WebView2 的实现
"""
# 先引入跨平台库
import os
import typing

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QIcon, QPixmap, QPixmapCache
from PyQt5.QtCore import pyqtSignal, Qt

from publics import app_logger, qt_image
from publics.base_ui_elements.common_webview import WebViewProfile

# 判断一下是不是windows
if os.name == 'nt':
    try:
        import clr
    except Exception as e:
        app_logger.log_WARN('failed to init .net CLR!')
        app_logger.log_exception(e)
        clr = None
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
        self_path = os.getcwd() + '\\binres'
        if not os.path.exists(self_path):
            app_logger.log_WARN(f"WebView2 runtime not found at {self_path}.  Make sure the path is correct.")
            return

        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Threading")
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.Core.dll"))
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.WinForms.dll"))

        from Microsoft.Web.WebView2.Core import (
            CoreWebView2PermissionState,
            CoreWebView2HostResourceAccessKind, \
            CoreWebView2BrowsingDataKinds,
            CoreWebView2WebResourceContext,
            CoreWebView2FaviconImageFormat, \
            CoreWebView2Environment,
            CoreWebView2CapturePreviewImageFormat)
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
        globals()['CoreWebView2CapturePreviewImageFormat'] = CoreWebView2CapturePreviewImageFormat

        isload = True
        app_logger.log_INFO('WebView2 library has been loaded')


def getWebViewVersion():
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


def isWebViewInstalled():
    """
    检查用户电脑上是否已安装 WebView2。

    Returns:
        bool: 如果已安装 WebView2，返回 True；否则返回 False。
    """
    if os.name == 'nt':
        return bool(WebView2VersionScaner.get_ver_CoreWebView2Environment())
    else:
        app_logger.log_WARN('Your system is not Windows, so WebView2 can not work at this time')
        return False


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
            try:
                task.Wait()
                callback(task.Result)
            except Exception as e:
                app_logger.log_WARN('waitCSharpAsyncFunction thread failed')
                app_logger.log_exception(e)

        thread = Thread(ThreadStart(wait_thread))
        thread.ApartmentState = ApartmentState.STA
        thread.Start()

    @classmethod
    def createCSharpThread(cls, target: typing.Callable):
        """
        创建一个 C# 线程。

        Args:
            target (typing.Callable): 线程内运行的函数
        """

        thread = Thread(ThreadStart(target))
        thread.ApartmentState = ApartmentState.STA
        return thread


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
        self.__webview = None
        self.__webview_core = None
        self.__current_icon = None
        self.__current_icon_binary = None
        self.__load_after_init = ''
        self.__profile = None
        self.__render_completed = False
        self.__is_frozen_enabling = False
        self.__has_first_load = False

        self.newtabSignal.connect(self.createWindow)

    def resizeEvent(self, a0):
        """重写 QWidget.resizeEvent，确保 WebView2 控件随窗口大小调整。"""
        if self.__render_completed and self.__webview is not None:
            hwnd = self.__webview.Handle.ToInt32()

            real_width = int(self.width() * self.devicePixelRatioF())
            real_height = int(self.height() * self.devicePixelRatioF())
            MoveWindow(hwnd, 0, 0, real_width, real_height, True)

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

    def runJavaScriptAsync(self, js_code: str):
        """
        异步在浏览器内执行 JavaScript 代码

        Args:
            js_code (str): 要执行的 JS 代码
        """
        if self.__render_completed and self.__webview is not None:
            def _run():
                task = self.__webview.CoreWebView2.ExecuteScriptWithResultAsync(js_code)

            self.__run_on_ui_thread(_run)
        else:
            raise Warning('WebView has not inited')

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
            app_logger.log_WARN('WebView has not inited')

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

    def canForward(self) -> bool:
        """获取是否可以前进一页。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.CanGoForward)
        return False

    def canBack(self) -> bool:
        """获取是否可以后退一页。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.CanGoBack)
        return False

    def forward(self):
        """前进到历史记录中的下一页（如果可能）。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.GoForward()

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def back(self):
        """后退到历史记录中的上一页（如果可能）。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.GoBack()

            self.__run_on_ui_thread(_load)
        else:
            app_logger.log_WARN('WebView has not inited')

    def reload(self):
        """重新加载当前页面。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.Reload()

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
            return str(self.__webview.CoreWebView2.Source)
        return ''

    def setHtml(self, html: str = '<html></html>'):
        """
        直接渲染指定的 HTML 字符串（不发起网络请求）。

        Args:
            html (str): 要渲染的 HTML 内容。
        """
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.NavigateToString(html)

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
            app_logger.log_WARN('WebView has not inited')

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
        if self.__profile is not None and self.__profile.enable_osr:
            # WebView2 没有离屏渲染能力（官方仍未提供 OSR API），这里只做提示，
            # 实际渲染仍然是原生子窗口；需要 OSR 请使用 CEF 内核。
            app_logger.log_WARN('WebView2 does not support off-screen rendering (OSR); '
                                'the enable_osr setting is ignored by this backend')
        if os.name == 'nt':
            if self.__profile is not None and not self.__render_completed:
                self.__run()
            else:
                app_logger.log_WARN('Your system is not Windows, so WebView2 can not work at this time')

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
            webview.DefaultBackgroundColor = Color.Transparent if self.profile().enable_transparent_bg else Color.White
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

                real_width = int(self.width() * self.devicePixelRatioF())
                real_height = int(self.height() * self.devicePixelRatioF())
                MoveWindow(hwnd, 0, 0, real_width, real_height, True)

            _set_parent()

    def __remake_qicon(self):
        def on_stream_copied(memoryStream):
            iconBytes = bytes(memoryStream.ToArray())  # 复制完后，转为python的字节数据

            # 处理 QPixmap
            screen_rate = qt_image.get_screen_ratio()
            pixmap = QPixmap()
            pixmap.setDevicePixelRatio(screen_rate)
            pixmap.loadFromData(iconBytes)
            pixmap = pixmap.scaled(int(pixmap.width() * screen_rate),
                                   int(pixmap.height() * screen_rate),
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)

            if not pixmap.isNull():  # 图像不为空，加载成功
                self.__current_icon = QIcon(pixmap)
                self.__current_icon_binary = iconBytes
                self.iconChanged.emit(self.__current_icon)

            # 释放资源
            memoryStream.Dispose()
            memoryStream.Close()

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
            self.newtabSignal.emit(args.Uri)
            args.Handled = True

    def __on_window_close(self, _, args):
        self.windowCloseRequested.emit()

    def __on_render_crash(self, _, args):
        self.renderProcessTerminated.emit(args.ExitCode)
        app_logger.log_WARN(f'WebView2 render crashed with exit code {args.ExitCode}')

    def __on_url_change(self, _, args):
        self.urlChanged.emit()

    def __on_navigation_start(self, _, args):
        if not self.__has_first_load:
            self.__has_first_load = True
        self.loadStarted.emit()

    def __on_navigation_completed(self, _, args):
        self.loadFinished.emit(args.IsSuccess)

    def __title_change_event(self, _, args):
        self.titleChanged.emit(self.title())

    def __on_response_got(self, _, args):
        def on_content_loaded(url, statusCode, header_dict, content_cstream):
            memoryStream = MemoryStream()
            content_cstream.CopyTo(memoryStream)
            content = bytes(memoryStream.ToArray())

            # 读出字节数据后，释放资源
            memoryStream.Dispose()
            memoryStream.Close()

            handler.onResponseCaught(url, statusCode, header_dict, content)  # call custom method

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

            # response adapter
            if args.Response:
                statusCode = int(args.Response.StatusCode)
                header_dict = {}
                header_iterator = args.Response.Headers.GetIterator()
                while header_iterator.HasCurrentHeader:
                    header_dict[str(header_iterator.Current.Key)] = str(header_iterator.Current.Value)
                    header_iterator.MoveNext()

                task = args.Response.GetContentAsync()
                CSharpConverter.waitCSharpAsyncFunction(task,
                                                        lambda result: on_content_loaded(url, statusCode, header_dict,
                                                                                         result))
        except Exception as e:
            app_logger.log_WARN(f'WebView2 Http Catcher failed')
            app_logger.log_exception(e)

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

                    # 读出字节数据后，释放资源
                    memoryStream.Dispose()
                    memoryStream.Close()

                url, method, header, content = handler.onRequestCaught(url, method, header_dict,
                                                                       content)  # call custom method

                args.Request.Uri = url
                args.Request.Method = method
                for k, v in header.items():
                    args.Request.Headers.SetHeader(k, v)
                if content:
                    new_stream = MemoryStream()
                    new_stream.Write(Array[Byte](content), 0, len(content))
                    args.Request.Content = new_stream

        except Exception as e:
            app_logger.log_WARN(f'WebView2 Http Catcher failed')
            app_logger.log_exception(e)

    def __on_js_msg_received(self, _, args):
        message = args.TryGetWebMessageAsString()
        self.jsBridgeReceived.emit(message)


    def __on_webview_ready(self, webview_instance, args):
        if not args.IsSuccess:
            app_logger.log_WARN('WebView2 initialization failed')
            app_logger.log_WARN(str(args.InitializationException))
            return

        configuration = self.__profile
        core = webview_instance.CoreWebView2
        self.__webview_core = core

        self.__set_parent()

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
        core.WebResourceResponseReceived += self.__on_response_got

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


# 供外部包装层调用
CommonWebView = QWebView2View
