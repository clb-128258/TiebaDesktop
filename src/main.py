"""
程序入口点
"""

from publics import webview2
from publics.baidu_features import tieba_apis
from publics import proxytool
from publics.winrt_url_share import winrt_share
from publics.funcs import *
from publics.app_logger import init_log
from publics.app_logger import log_exception, log_INFO, log_WARN
from publics import account_mgr

from PyQt5.QtCore import QLocale, QTranslator
from PyQt5.QtWidgets import QMessageBox, QApplication
import sys
import os
import requests
import aiotieba
import aiotieba.helper.cache
import asyncio
import consts
import pathlib

from subwindow import main_ui_elements

if os.name == 'nt':
    import win32api
    import win32con

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


def reset_udf():
    """根据命令行参数重设datapath"""
    cmds = sys.argv
    if '--reset-udf' in cmds:
        udf = ''
        for i in cmds:
            if i.startswith('--udf-path='):
                udf = i.split('=')[1]
        if os.path.isdir(udf):
            consts.datapath = udf
            log_INFO(f'UserDataPath is reset by --reset-udf.')
        else:
            logging.log_INFO(f'{udf} is not a valid folder, please create it first.')
        log_INFO(f'Now UserDataPath is {consts.datapath}.')


def handle_command_events():
    """处理命令行参数，与命令行参数有关的代码均在此执行"""
    cmds = sys.argv
    dont_run_gui = False
    log_INFO('Handling command args')

    def get_current_user():
        account_mgr_obj = account_mgr.GlobalAccountContainer.get_current_manager()
        account_mgr_obj.load_accounts_list()
        return account_mgr_obj.current_account.bduss, account_mgr_obj.current_account.stoken

    def msgbox(text, title='贴吧桌面'):
        if '--quiet' not in cmds and os.name == 'nt':
            win32api.MessageBox(None, text, title, win32con.MB_OK | win32con.MB_ICONINFORMATION)

    async def sign_grow():
        bduss, stoken = get_current_user()
        if not bduss:
            msgbox('请先登录账号再签到。')
            return
        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            r1 = await client.sign_growth()
            r2 = await client.sign_growth_share()

            err_msg = '成长等级签到成功。'
            if not (r1 and r2):
                err_msg = '签到失败，详情如下：'
                if not r1:
                    err_msg += f'\n成长等级签到：{r1.err}'
                if not r2:
                    err_msg += f'\n成长等级分享任务：{r2.err}'
            msgbox(err_msg)

    async def sign_all():
        bduss, stoken = get_current_user()
        signed_count = 0

        if not bduss:
            msgbox('请先登录账号再签到。')
            return

        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            await client.sign_forums()  # 先一键签到

            bars = tieba_apis.newmoindex(bduss)['data']['like_forum']
            bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

            for forum in bars:
                if forum["is_sign"] != 1:
                    fid = forum['forum_id']
                    fname = forum['forum_name']
                    r = tieba_apis.sign_forum(bduss, stoken, fid, fname)['error_code'] == '0'

                    signed_count += (1 if r else 0)
                    await asyncio.sleep(0.3)  # 休眠0.3秒，防止贴吧服务器抽风
                else:
                    # 已签到的直接跳过
                    signed_count += 1
        msgbox(f'签到完成，已签到 {signed_count} 个吧，{len(bars) - signed_count} 个吧签到失败。')

    async def switch_account():
        uid = -1
        for i in cmds:
            if i.startswith('--userid='):
                try:
                    uid = int(i.split('=')[1])
                except:
                    uid = -1

        if uid <= 0:
            msgbox('请指定正确的用户 ID。')
        else:
            account_mgr_obj = account_mgr.GlobalAccountContainer.get_current_manager()
            account_mgr_obj.load_accounts_list()

            for i in account_mgr_obj.account_list:
                if i.uid == uid:
                    account_mgr_obj.switch_to_account(uid)
                    msgbox(f'已将账号切换到 {uid}。')
                    return
            msgbox(f'未在本地找到 {uid} 的登录信息。')

    def start_async(func):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func)

    if '--set-current-account' in cmds:
        dont_run_gui = True
        log_INFO('--set-current-account started')
        start_async(switch_account())
    else:
        if '--sign-all-forums' in cmds:
            dont_run_gui = True
            log_INFO('--sign-all-forums started')
            start_async(sign_all())
        if '--sign-grows' in cmds:
            dont_run_gui = True
            log_INFO('--sign-grows started')
            start_async(sign_grow())
    if dont_run_gui:
        sys.exit(0)


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
