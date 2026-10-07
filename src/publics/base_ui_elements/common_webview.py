"""
跨平台 WebView 的统一封装层。

本模块是程序中使用 webview 的唯一入口：业务代码统一使用本模块暴露的
``CommonWebView`` / ``WebViewProfile`` / ``HttpDataRewriter`` / ``loadLibs`` /
``isWebViewInstalled``，由本模块根据运行平台与可用性把调用转发到具体实现：

- Windows：优先使用系统自带的 WebView2（``windows_features/webview2.py``），
  当系统没有安装 WebView2 运行时，则改用 CEF（``cef_features/cef_webview.py``）
- Linux：使用 CEF

可用启动参数 ``--force-webview`` 强制指定后端：``webview2`` / ``cef`` / ``auto``（默认）。
CEF 是可选依赖：没有集成 CEF 运行时（binres/cef 与 binres/cef_bridge）时
``isWebViewInstalled()`` 返回 False，程序会照常启动并自动降级。
"""
import os
import sys

from publics import app_logger


def _load_webview2():
    from publics.base_ui_elements.windows_features import webview2
    return webview2


def _load_cef():
    from publics.base_ui_elements.cef_features import cef_webview
    return cef_webview


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


_platform_webview, PLATFORM = _select_backend()

# 组件类型与配置类统一对外暴露
CommonWebView = getattr(_platform_webview, 'CommonWebView', None)
if CommonWebView is None:
    CommonWebView = _platform_webview.QWebView2View
WebViewProfile = _platform_webview.WebViewProfile
HttpDataRewriter = _platform_webview.HttpDataRewriter


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
