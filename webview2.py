"""webview2模块，实现了webview2与pyqt的绑定"""
# 先引入跨平台库
import os
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import pyqtSignal
import requests
from platform import machine

# 判断一下是不是windows
if os.name == 'nt':
    import winreg
    import clr
    from win32gui import SetParent, MoveWindow
else:
    print('Warning: Your system is not Windows, so WebView2 can not work at this time')

isload = False
CoreWebView2PermissionState = CoreWebView2HostResourceAccessKind = CoreWebView2BrowsingDataKinds = CoreWebView2WebResourceContext = WebView2 = CoreWebView2CreationProperties = Uri = Object = Action = Thread = ApartmentState = ThreadStart = SendOrPostCallback = Task = Color = Point = Size = AnchorStyles = DockStyle = FormsApplication = None


def loadLibs():
    """加载webview2相关的依赖文件"""
    global isload
    if not isload and os.name == 'nt':
        global CoreWebView2PermissionState, CoreWebView2HostResourceAccessKind, CoreWebView2BrowsingDataKinds, CoreWebView2WebResourceContext, WebView2, CoreWebView2CreationProperties, Uri, Object, Action, Thread, ApartmentState, ThreadStart, SendOrPostCallback, Task, Color, Point, Size, AnchorStyles, DockStyle, FormsApplication
        isload = True
        self_path = os.getcwd() + '\\dlls'
        if not os.path.exists(self_path):
            raise RuntimeError(f"Error: WebView2 runtime not found at {self_path}.  Make sure the path is correct.")

        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Threading")
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.Core.dll"))
        clr.AddReference(os.path.join(self_path, "Microsoft.Web.WebView2.WinForms.dll"))

        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState, CoreWebView2HostResourceAccessKind, \
            CoreWebView2BrowsingDataKinds, CoreWebView2WebResourceContext
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties
        from System import Uri, Object, Action
        from System.Threading import Thread, ApartmentState, ThreadStart, SendOrPostCallback
        from System.Threading.Tasks import Task
        from System.Drawing import Color, Point, Size
        from System.Windows.Forms import (
            AnchorStyles, DockStyle,
            Application as FormsApplication,
        )


def _is_new_version(current_version: str, new_version: str) -> bool:
    new_range = new_version.split('.')
    cur_range = current_version.split('.')
    for index, _ in enumerate(new_range):
        if len(cur_range) > index:
            return int(new_range[index]) >= int(cur_range[index])

    return False


def edge_build(key_type, key, description=''):
    try:
        windows_key = None
        if machine() == 'x86' or key_type == 'HKEY_CURRENT_USER':
            path = rf'Microsoft\EdgeUpdate\Clients\{key}'
        else:
            path = rf'WOW6432Node\Microsoft\EdgeUpdate\Clients\{key}'

        with winreg.OpenKey(getattr(winreg, key_type), rf'SOFTWARE\{path}') as windows_key:
            build, _ = winreg.QueryValueEx(windows_key, 'pv')
            return str(build)

    except Exception:
        pass

    return '0'


def _get_ver():
    net_key = None
    try:
        net_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
        )
        version, _ = winreg.QueryValueEx(net_key, 'Release')

        if version < 394802:  # .NET 4.6.2
            return ''

        build_versions = [
            {
                'key': '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
                'description': 'Microsoft Edge WebView2 Runtime',
            },  # runtime
            {
                'key': '{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}',
                'description': 'Microsoft Edge WebView2 Beta',
            },  # beta
            {
                'key': '{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}',
                'description': 'Microsoft Edge WebView2 Developer',
            },  # dev
            {
                'key': '{65C35B14-6C1D-4122-AC46-7148CC9D6497}',
                'description': 'Microsoft Edge WebView2 Canary',
            },  # canary
        ]

        for item in build_versions:
            for key_type in ('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE'):
                build = edge_build(key_type, item['key'], item['description'])
                if build != "0":
                    return build

    finally:
        if net_key:
            winreg.CloseKey(net_key)

    return ''


def _is_chromium():
    net_key = None
    try:
        net_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
        )
        version, _ = winreg.QueryValueEx(net_key, 'Release')

        if version < 394802:  # .NET 4.6.2
            return ''

        build_versions = [
            {
                'key': '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
                'description': 'Microsoft Edge WebView2 Runtime',
            },  # runtime
            {
                'key': '{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}',
                'description': 'Microsoft Edge WebView2 Beta',
            },  # beta
            {
                'key': '{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}',
                'description': 'Microsoft Edge WebView2 Developer',
            },  # dev
            {
                'key': '{65C35B14-6C1D-4122-AC46-7148CC9D6497}',
                'description': 'Microsoft Edge WebView2 Canary',
            },  # canary
        ]

        for item in build_versions:
            for key_type in ('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE'):
                build = edge_build(key_type, item['key'], item['description'])
                if _is_new_version('86.0.622.0', build):  # Webview2 86.0.622.0
                    return True

    finally:
        if net_key:
            winreg.CloseKey(net_key)

    return False


def WebView2Version():
    """获取用户电脑上已安装webview2的版本"""
    if os.name == 'nt':
        if _is_chromium():
            return _get_ver()
        else:
            return ''
    else:
        print('Warning: Your system is not Windows, so WebView2 can not work at this time')
        return ''


def isWebView2Installed():
    """获取用户电脑上是否已安装webview2"""
    if os.name == 'nt':
        return _is_chromium()
    else:
        print('Warning: Your system is not Windows, so WebView2 can not work at this time')
        return True


class WebViewProfile:
    """QWebView2View中使用的配置类"""

    def __init__(self,
                 data_folder: str = os.getenv("TEMP", '.') + "/Microsoft WebView",
                 private_mode=False,
                 user_agent: str = None,
                 vhost_path: str = None,
                 vhost_name: str = "webview",
                 vhost_cors: bool = True,
                 enable_error_page: bool = True,
                 enable_zoom_factor: bool = True,
                 handle_newtab_byuser: bool = False,
                 enable_context_menu: bool = True,
                 enable_keyboard_keys: bool = True,
                 try_to_stop_thread_when_destroy: bool = False,
                 proxy_addr: str = "",
                 enable_gpu_boost: bool = True,
                 enable_link_hover_text: bool = True,
                 ignore_all_render_argvs: bool = False,
                 disable_web_safe: bool = False
                 ):
        self.data_folder = data_folder
        self.private_mode = private_mode
        self.user_agent = user_agent
        self.vhost_path = vhost_path
        self.vhost_name = vhost_name
        self.vhost_cors = vhost_cors
        self.enable_error_page = enable_error_page
        self.enable_zoom_factor = enable_zoom_factor
        self.handle_newtab_byuser = handle_newtab_byuser
        self.enable_context_menu = enable_context_menu
        self.enable_keyboard_keys = enable_keyboard_keys
        self.try_to_stop_thread_when_destroy = try_to_stop_thread_when_destroy
        self.proxy_addr = proxy_addr
        self.enable_gpu_boost = enable_gpu_boost
        self.enable_link_hover_text = enable_link_hover_text
        self.ignore_all_render_argvs = ignore_all_render_argvs
        self.disable_web_safe = disable_web_safe


class QWebView2View(QWidget):
    """可在qt内嵌入的webview2组件"""
    tokenGot = pyqtSignal(dict)
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

    __newtabSignal = pyqtSignal(str)
    __setparentsignal = pyqtSignal()
    __render_completed = False
    __webview = None
    __webview_thread = None
    __webview_core = None
    __current_icon = None
    __load_after_init = ''
    __is_destroy_time = False
    __token_got = False

    def __init__(self):
        super().__init__()
        self.__profile = None
        self.__set_background()
        self.__newtabSignal.connect(self.createWindow)
        self.__setparentsignal.connect(self.__set_parent)

    def resizeEvent(self, a0):
        if self.__render_completed and self.__webview is not None:  # 检查 __webview
            def _resize():
                hwnd = self.__webview.Handle.ToInt32()
                MoveWindow(hwnd, 0, 0, self.width(), self.height(), True)

            self.__run_on_ui_thread(_resize)

    def closeEvent(self, a0):
        a0.ignore()
        self.hide()

    def createWindow(self, newPageUrl: str):
        """在 handle_newtab_byuser 特性启用时，应当在此处重写新页面事件。"""
        pass
        self.load(newPageUrl)

    def destroyWebview(self):
        """销毁 WebView 实例。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Dispose(True)
                return ''

            self.__run_on_ui_thread(_load)
            if self.__profile.try_to_stop_thread_when_destroy:
                self.__is_destroy_time = True

    def destroyWebviewUntilComplete(self):
        """销毁 WebView 实例，并等待销毁操作完成。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Dispose(True)
                return ''

            self.__get_value_ui_thread(_load)
            if self.__profile.try_to_stop_thread_when_destroy:
                self.__is_destroy_time = True

    def clearCacheData(self):
        """清除缓存数据。包括磁盘缓存、下载记录、浏览记录。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                datakinds = (CoreWebView2BrowsingDataKinds.DiskCache
                             | CoreWebView2BrowsingDataKinds.DownloadHistory
                             | CoreWebView2BrowsingDataKinds.BrowsingHistory)
                self.__webview.CoreWebView2.Profile.ClearBrowsingDataAsync(datakinds)

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def clearCookies(self):
        """清除 Cookie、自动填充和 H5 本地存储数据。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                datakinds = (CoreWebView2BrowsingDataKinds.Cookies
                             | CoreWebView2BrowsingDataKinds.GeneralAutofill
                             | CoreWebView2BrowsingDataKinds.PasswordAutosave
                             | CoreWebView2BrowsingDataKinds.AllDomStorage)
                self.__webview.CoreWebView2.Profile.ClearBrowsingDataAsync(datakinds)

            self.__get_value_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def setProfile(self, profile: WebViewProfile):
        """设置配置文件对象。"""
        if self.__profile is None:
            self.__profile = profile

    def profile(self):
        """获取配置文件对象。"""
        return self.__profile

    def renderProcessID(self):
        """获取 Webview 渲染器的进程 ID。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.BrowserProcessId)

    def isRenderInitOk(self):
        """获取 Webview 是否初始化完成。"""
        return self.__render_completed

    def icon(self):
        """以 QIcon 对象的形式获得网页图标。"""
        if self.__render_completed and self.__webview is not None:
            if self.__current_icon is not None:
                return self.__current_icon
            else:
                return QIcon()

    def iconUrl(self):
        """以 URL 字符串的形式获得网页图标。"""
        if self.__render_completed and self.__webview is not None:
            return str(self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.FaviconUri))

    def isAudioMuted(self):
        """获取网页是否被静音。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.IsMuted)

    def setAudioMuted(self, ismuted: bool):
        """设置网页是否被静音。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.CoreWebView2.IsMuted = ismuted

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def isHtmlInFullScreenState(self):
        """获取网页是否处于全屏状态。
        请注意，这是相对整个 HTML 页面来说的，与 Qt 窗口的全屏状态没有关联。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.ContainsFullScreenElement)

    def title(self):
        """获取网页标题。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.CoreWebView2.DocumentTitle)

    def forward(self):
        """使 Webview 执行前进一页的操作。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.GoForward()

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def back(self):
        """使 Webview 执行后退一页的操作。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.GoBack()

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def reload(self):
        """使 Webview 执行刷新页面的操作。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.Reload()

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def url(self):
        """获取当前页面的 URL 字符串。"""
        if self.__render_completed and self.__webview is not None:
            return str(self.__webview.Source)

    def setHtml(self, html: str = '<html></html>'):
        """在 Webview 中直接渲染给定的 HTML 文档。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.NavigateToString(html)

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def zoomFactor(self):
        """获取网页缩放比。"""
        if self.__render_completed and self.__webview is not None:
            return self.__get_value_ui_thread(lambda: self.__webview.ZoomFactor)

    def setZoomFactor(self, f: float):
        """设置网页缩放比。"""
        if self.__render_completed and self.__webview is not None:
            def _load():
                self.__webview.ZoomFactor = f

            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def load(self, url: str):
        """加载一个特定的 URL。"""

        def _load():
            if self.__webview is not None:
                self.__webview.Source = Uri(url)

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def loadAfterRender(self, url: str):
        """设置在初始化完成后，加载一个特定的 URL。"""
        self.__load_after_init = url

    def openDevtoolsWindow(self):
        """打开开发者工具窗口。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenDevToolsWindow()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def openChromiumTaskmgrWindow(self):
        """打开浏览器任务管理器窗口。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenTaskManagerWindow()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def openDefaultDownloadDialog(self):
        """打开默认的下载内容悬浮窗。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.OpenDefaultDownloadDialog()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def openPrintDialog(self):
        """打开打印页面。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.ShowPrintUI()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def openSaveHtmlDialog(self):
        """打开另存网页的对话框。"""

        def _load():
            if self.__webview is not None:
                self.__webview.CoreWebView2.ShowSaveAsUIAsync()

        if self.__render_completed:
            self.__run_on_ui_thread(_load)
        else:
            raise Warning('WebView has not inited')

    def initRender(self):
        """初始化 render。"""
        if os.name == 'nt':
            if self.__profile is not None and not self.__render_completed:
                self.__webview_thread = Thread(ThreadStart(self.__run))
                self.__webview_thread.ApartmentState = ApartmentState.STA
                self.__webview_thread.Start()
        else:
            QMessageBox.critical(self, '当前平台不支持', '你当前使用的系统不是 Windows，不支持执行 WebView2。',
                                 QMessageBox.Ok)
            print('Warning: Your system is not Windows, so WebView2 can not work at this time')

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
            webview.DefaultBackgroundColor = Color.White
            webview.Dock = DockStyle.Fill  # 设置停靠属性

            webview.CoreWebView2InitializationCompleted += self.__on_webview_ready

            webview.EnsureCoreWebView2Async(None)  # 初始化WebView

            # 手动处理 WinForms 的消息循环
            if self.__profile.try_to_stop_thread_when_destroy:
                while 1:
                    FormsApplication.DoEvents()
                    if self.__is_destroy_time:
                        break
            else:
                FormsApplication.Run()  # 自动处理的
        except Exception as e:
            print(f"loop error {e}")
        finally:
            print(f"loop ok")
            return

    def __get_value_ui_thread(self, func):
        vs = []
        if self.__webview is not None:
            if self.__webview.IsHandleCreated:
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

    def __set_parent(self):
        if self.__webview is not None:
            def _set_parent():
                hwnd = self.__webview.Handle.ToInt32()
                SetParent(hwnd, int(self.winId()))
                MoveWindow(hwnd, 0, 0, self.width(), self.height(), True)

            # self.__run_on_ui_thread(_set_parent)
            _set_parent()

    def __remake_qicon(self):
        r = requests.get(self.iconUrl(), headers={'User-Agent': self.__webview.CoreWebView2.Settings.UserAgent})
        r.close()
        if r.status_code != 200:
            raise Warning(f'Get icon binary data failed, status code: {r.status_code}')

        if self.__current_icon is not None:
            del self.__current_icon
        pixmap = QPixmap()
        pixmap.loadFromData(r.content)
        self.__current_icon = QIcon(pixmap)

    def __on_fullscreen_requested(self, _, args):
        self.fullScreenRequested.emit(self.isHtmlInFullScreenState())

    def __on_icon_changed(self, _, args):
        self.__remake_qicon()
        self.iconUrlChanged.emit(self.iconUrl())
        self.iconChanged.emit(self.__current_icon)

    def __on_audio_mute_changed(self, _, args):
        self.audioMutedChanged.emit(self.isAudioMuted())

    def __on_new_window_open(self, _, args):
        if not self.profile().handle_newtab_byuser:
            args.Handled = False
        else:
            args.Handled = True
            self.__newtabSignal.emit(args.Uri)

    def __on_window_close(self, _, args):
        self.windowCloseRequested.emit()

    def __on_render_crash(self, _, args):
        self.renderProcessTerminated.emit(args.ExitCode)
        print(f'WebView2 render crashed,\nCode: {args.ExitCode}\nModule: {args.FailureSourceModulePath}')

    def __on_url_change(self, _, args):
        self.urlChanged.emit()

    def __on_navigation_start(self, _, args):
        self.loadStarted.emit()

    def __on_navigation_completed(self, _, args):
        self.loadFinished.emit(args.IsSuccess)

    def __title_change_event(self, _, args):
        self.titleChanged.emit(self.title())

    def __on_request_got(self, _, args):
        if args.Request.Headers.Contains("Cookie"):
            tlist = [
                'BDUSS',
                'STOKEN']
            cookies_dic = {}
            cookies = args.Request.Headers.GetHeader("Cookie")
            for i in cookies.split('; '):
                cookies_dic[i.split('=')[0]] = i.split('=')[1]

            count = 0
            for i in tuple(cookies_dic.keys()):
                if i in tlist and cookies_dic[i]:
                    count += 1
                else:
                    del cookies_dic[i]

            if count == len(tlist) and not self.__token_got:
                self.__token_got = True
                self.tokenGot.emit(cookies_dic)

    def __on_js_msg_received(self, _, args):
        message = args.TryGetWebMessageAsString()
        print(message)

    def __on_webview_ready(self, webview_instance, args):
        if not args.IsSuccess:
            print(args.InitializationException)
            return

        self.__setparentsignal.emit()

        configuration = self.__profile
        core = webview_instance.CoreWebView2
        self.__webview_core = core
        core.AddWebResourceRequestedFilter("*://tieba.baidu.com/*", CoreWebView2WebResourceContext.All)

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

        ua = configuration.user_agent
        if ua:
            settings.UserAgent = ua.replace('[default_ua]', settings.UserAgent)

        # cookies persist even if UserDataFolder is in memory. We have to delete cookies manually.
        if configuration.private_mode:
            core.CookieManager.DeleteAllCookies()

        self.__render_completed = True
        self.renderInitializationCompleted.emit()
        if self.__load_after_init:
            self.load(self.__load_after_init)
