"""
程序入口点
"""
from publics.app_logger import init_log
from publics.app_logger import log_exception, log_INFO, log_WARN

from publics.cli_feats import handle_command_events, reset_udf
from publics.base_ui_elements import base_ui
from publics.base_ui_elements.windows_features import webview2
from publics.winrt_url_share import winrt_share

from publics.funcs import *
from publics import proxytool

from PyQt5.QtCore import QLocale, QTranslator, Qt
from PyQt5.QtWidgets import QMessageBox, QApplication

import sys
import os
import requests
import pathlib

from subwindow import main_ui_elements

requests.session().trust_env = True
requests.session().verify = False


def excepthook(type, value, traceback):
    """捕获并打印错误"""
    if type != SystemExit:
        log_WARN('An error in main thread was caught')
        log_exception(value)


def set_qt_languages():
    """加载qt的语言文件"""
    if QLocale().language() == QLocale.Language.Chinese:
        language_file_list = ["ui/qt_zh_CN.qm", 'ui/qtbase_zh_CN.qm']
        translators = []
        for i in language_file_list:
            translator = QTranslator()
            if translator.load(i):
                app.installTranslator(translator)
                log_INFO(f'Qt language file {i} loaded')
                translators.append(translator)
        return translators


def check_webview2():
    """检查用户的电脑是否安装了webview2"""
    log_INFO(f'Checking webview2')

    webview2.loadLibs()
    if not webview2.isWebView2Installed() and os.name == 'nt':
        msgbox = QMessageBox()
        msgbox.warning(None, '运行警告',
                       '你的电脑上似乎还未安装 WebView2 运行时。本程序的部分功能（如登录等）将不可用。',
                       QMessageBox.Ok)


def set_qt_scale_factor():
    """重设 Qt 的缩放因子"""
    factor = get_dict_value_treely(profile_mgr.local_config, ['other_settings', 'reset_dpi'], -1)
    if factor != -1:
        os.environ['QT_SCALE_FACTOR'] = str(factor)


def reset_cwd():
    """把工作目录重设到可执行文件所在目录下"""
    exec_file = pathlib.Path(sys.executable)
    if 'python' in exec_file.name:
        return

    os.chdir(exec_file.parent)


if __name__ == "__main__":
    # set excepthook
    sys.excepthook = excepthook

    # reset cwd
    reset_cwd()

    # init profiles
    reset_udf()
    create_data()
    init_log()
    profile_mgr.init_all_datas()
    proxytool.set_proxy()

    # process command args
    handle_command_events()

    # Qt high dpi support
    set_qt_scale_factor()
    QApplication.setAttribute(Qt.AA_UseOpenGLES)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # init Qt
    app = QApplication(sys.argv)
    main_ui_elements.QApp_instance = app
    app.setQuitOnLastWindowClosed(False)
    translates = set_qt_languages()
    log_INFO('Qt init complete')

    # init .net/cpp libraries
    winrt_share.init_library()
    check_webview2()

    # init theme elements
    base_ui.init_bg_pixmap()

    # init main window, tray icon
    log_INFO('Initing main window')
    main_window = main_ui_elements.MainWindow.create_instance()
    tray_icon = main_ui_elements.TrayIcon.create_instance()

    # show ui elements
    tray_icon.show()
    if '--quiet' not in sys.argv:
        main_window.show()

    # main loop
    logging.log_INFO('MainWindow showed, now run into the main loop')
    exit_code = app.exec()

    # exit program
    logging.log_INFO(f'Qt event loop finished with exit code {exit_code}. Exiting...')
    sys.exit(exit_code)
