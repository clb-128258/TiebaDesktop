"""程序入口点，包含了整个程序最基本的函数和类"""
from publics import webview2, cache_mgr
from publics.baidu_features import tieba_apis
from publics import proxytool
from publics.baidu_features.baidu_passport_login import LoginWebView, QRLoginDialog, SeniorLoginDialog
from publics.winrt_url_share import winrt_share
from publics.funcs import *
from publics.app_logger import init_log
from publics.app_logger import log_exception, log_INFO, log_WARN
from publics.tb_syncer import *
from publics import top_toast_widget, account_mgr

from PyQt5.QtCore import (QLocale, QTranslator, QT_VERSION_STR,
                          QT_VERSION, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QPoint)
from PyQt5.QtGui import QPixmapCache, QFont, QCloseEvent
from PyQt5.QtWidgets import (QMessageBox, QAction, QMainWindow, QApplication,
                             QWidgetAction, QInputDialog, QGraphicsOpacityEffect, QFileDialog,
                             QSystemTrayIcon)

from subwindow.agree_thread_list import AgreedThreadsList
from subwindow.firstpage_recommend import RecommendWindow
from subwindow.follow_forum_list import FollowForumList
from subwindow.interact_list import UserInteractionsList
from subwindow.tieba_search_entry import TiebaSearchWindow
from subwindow.mainwindow_menu import MainPopupMenu
from subwindow import base_ui

from ui import mainwindow, settings

import sys
import os
import requests
import aiotieba
import aiotieba.helper.cache
import asyncio
import gc
import consts
import shutil
import platform
import time
import subprocess
import pathlib

if os.name == 'nt':
    import win32api
    import win32con

datapath = consts.datapath
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
            global datapath
            consts.datapath = udf
            datapath = udf
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


class TrayIcon(QSystemTrayIcon):
    def __init__(self):
        super().__init__()
        self.setIcon(QIcon('ui/tieba_logo_small.png'))

        self.activated.connect(self.handle_click)
        main_window.account_manager.accountSwitched.connect(self.update_tooltip)
        main_window.notice_syncer.noticeCountChanged.connect(self.update_tooltip)

        self.init_menu()
        self.update_tooltip()

    def update_tooltip(self):
        interact_type_index = {UnreadMessageType.AGREE: '点赞',
                               UnreadMessageType.AT: '@',
                               UnreadMessageType.REPLY: '回复'}
        base_text = '贴吧桌面'

        account = main_window.account_manager.current_account
        if account:
            base_text += f'\n当前账号: {account.nickname}'

        interact_syncer = main_window.notice_syncer
        if interact_syncer.get_basic_unread_notice_count() > 0:
            base_text += '\n未读通知: '
            for k, v in interact_type_index.items():
                notice_count = interact_syncer.get_unread_notice_count(k)
                if notice_count > 0:
                    base_text += f'{notice_count} 条{v}, '
            base_text = base_text[0:-2]

        self.setToolTip(base_text)

    def handle_click(self, tpe):
        if tpe != QSystemTrayIcon.ActivationReason.Context:
            main_window.show_active_window()

    def init_menu(self):
        self.menu = base_ui.BaseQMenu()

        open_main_window = QAction('打开主窗口', self)
        open_main_window.triggered.connect(main_window.show_active_window)
        self.menu.addAction(open_main_window)

        switch_forum_page = QAction('打开进吧页面', self)
        switch_forum_page.triggered.connect(self.show_into_forum_page)
        self.menu.addAction(switch_forum_page)

        switch_interact_page = QAction('查看互动消息', self)
        switch_interact_page.triggered.connect(self.show_interact_page)
        self.menu.addAction(switch_interact_page)

        self.menu.addSeparator()

        show_all_windows = QAction('还原离散窗口', self)
        show_all_windows.triggered.connect(self.restore_all_windows)
        self.menu.addAction(show_all_windows)

        minimize_all_windows = QAction('最小化离散窗口', self)
        minimize_all_windows.triggered.connect(self.minimize_all_windows)
        self.menu.addAction(minimize_all_windows)

        close_all_windows = QAction('关闭离散窗口', self)
        close_all_windows.triggered.connect(qt_window_mgr.clear_windows)
        self.menu.addAction(close_all_windows)

        self.menu.addSeparator()

        open_settings_window = QAction('软件设置', self)
        open_settings_window.triggered.connect(main_window.open_settings_window)
        self.menu.addAction(open_settings_window)

        exit_app = QAction('退出软件', self)
        exit_app.triggered.connect(main_window.exit_app)
        self.menu.addAction(exit_app)

        self.setContextMenu(self.menu)

    def restore_all_windows(self):
        for i in qt_window_mgr.distributed_window:
            i.showNormal()

    def minimize_all_windows(self):
        for i in qt_window_mgr.distributed_window:
            i.showMinimized()

    def show_into_forum_page(self):
        main_window.show_active_window()
        main_window.switch_follow_forum_page()

    def show_interact_page(self):
        main_window.show_active_window()
        main_window.switch_interact_page()


class SettingsWindow(base_ui.WindowBaseQDialog, settings.Ui_Dialog):
    """设置窗口"""
    scanFinish = pyqtSignal(dict)
    clearFinish = pyqtSignal(bool)
    scannedDetailData = {}
    brightDarkPolicyFlag = 0  # 用于标记主题颜色是否被修改

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.account_mgr = account_mgr.GlobalAccountContainer.get_current_manager()
        self.account_mgr.accountStateChanged.connect(self.get_logon_accounts)
        self.account_mgr.addAccountFailed.connect(self.on_account_add_failed)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label_6.setPixmap(
            QPixmap('ui/tieba_logo_big_transparent.png').scaled(55, 55, transformMode=Qt.SmoothTransformation))
        self.groupBox_3.hide()

        self.init_top_toaster()
        self.init_load_animation()
        self.init_hover_buttons()

        self.set_debug_info()
        self.get_logon_accounts()
        self.load_local_config()

        self.listWidget.currentRowChanged.connect(self.switch_main_page)
        self.listWidget_3.currentRowChanged.connect(self.scroll_common_settings)

        self.manage_account_button.clicked.connect(self.init_manage_acount_button_menu)
        self.login_button.clicked.connect(self.init_login_button_menu)
        self.pushButton_11.clicked.connect(lambda: QMessageBox.aboutQt(self, '关于 Qt'))
        self.pushButton_12.clicked.connect(self.scan_use_detail_async)
        self.pushButton_4.clicked.connect(self.clear_caches_async)
        self.pushButton_6.clicked.connect(self.open_proxy_settings)
        self.pushButton_7.clicked.connect(self.select_all_caches)
        self.pushButton_5.clicked.connect(self.add_search_engine)
        self.pushButton_8.clicked.connect(self.reset_local_config)

        self.commandLinkButton.clicked.connect(
            lambda: self.open_web_link('https://www.github.com/clb-128258/TiebaDesktop'))
        self.commandLinkButton_2.clicked.connect(
            lambda: self.open_web_link('https://www.github.com/clb-128258/TiebaDesktop?tab=MIT-1-ov-file'))
        self.pushButton_3.clicked.connect(lambda: open_url_in_browser(f'{datapath}/logs'))
        self.pushButton_10.clicked.connect(lambda: open_url_in_browser(datapath))

        self.scanFinish.connect(self._set_use_detail_ui)
        self.clearFinish.connect(self._on_caches_cleared)

        self.clearTypeCb = [self.checkBox_4,
                            self.checkBox_5,
                            self.checkBox_9,
                            self.checkBox_10,
                            self.checkBox_7,
                            self.checkBox_6,
                            self.checkBox_18,
                            self.checkBox_19,
                            self.checkBox_22
                            ]
        for i in self.clearTypeCb:
            i.stateChanged.connect(self.calc_willfree_size)

        self.move_as_config()

    def closeEvent(self, a0):
        self.save_local_config()
        profile_mgr.add_window_rects(type(self),
                                     self.x() + 1, self.y() + 31,
                                     self.width(), self.height(),
                                     False)

        self.account_mgr.accountStateChanged.disconnect(self.get_logon_accounts)
        self.account_mgr.addAccountFailed.disconnect(self.on_account_add_failed)
        self.listWidget_2.clear()
        QPixmapCache.clear()
        gc.collect()
        a0.accept()

    def resizeEvent(self, a0):
        self.login_button.move_button()
        self.manage_account_button.move_button()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def move_as_config(self):
        window_rect = profile_mgr.get_window_rects(type(self))
        if window_rect:
            self.setGeometry(window_rect[0],
                             window_rect[1],
                             window_rect[2],
                             window_rect[3])

    def init_hover_buttons(self):
        self.manage_account_button = base_ui.FloatingButton(self, 1)
        self.manage_account_button.set_button_status(base_ui.NarrowButtonStatus.Settings)
        self.manage_account_button.move_button()

        self.login_button = base_ui.FloatingButton(self, 2)
        self.login_button.set_button_status(base_ui.NarrowButtonStatus.Add)
        self.login_button.move_button()

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def init_load_animation(self):
        self.load_animation = LoadingFlashWidget()
        self.load_animation.cover_widget(self.groupBox_3)
        self.load_animation.hide()

    def init_login_button_menu(self):
        menu = base_ui.BaseQMenu()

        webview_login = QAction('浏览器登录', self)
        webview_login.triggered.connect(self.add_account)
        menu.addAction(webview_login)

        qr_login = QAction('扫码登录', self)
        qr_login.triggered.connect(self.add_account_qrcode)
        menu.addAction(qr_login)

        bduss_directly_login = QAction('高级登录', self)
        bduss_directly_login.triggered.connect(self.add_account_senior)
        menu.addAction(bduss_directly_login)

        bt_pos = self.login_button.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x() - (132 - self.login_button.width()), bt_pos.y() - 100)
        menu.exec_(show_pos)

    def init_manage_acount_button_menu(self):
        menu = base_ui.BaseQMenu()
        menu.setToolTipsVisible(True)

        export_accounts = QAction('导出账号信息', self)
        export_accounts.setToolTip('将所有已登录账号的信息导出到本地文件，便于保存账号信息。\n'
                                   '注意：导出的文件中包括 BDUSS 等登录令牌信息，请妥善保管，否则可能导致你的账号被盗。')
        export_accounts.triggered.connect(self.export_account_info)
        export_accounts.setEnabled(self.account_mgr.has_any_accounts())
        menu.addAction(export_accounts)

        update_accounts_info = QAction('更新所有账号的信息', self)
        update_accounts_info.setToolTip(
            '如果已登录账号的显示昵称与实际的不一致，或者需要清理登录失效的账号，可以选择更新所有账号的信息。')
        update_accounts_info.triggered.connect(self.refresh_all_users_info)
        update_accounts_info.setEnabled(self.account_mgr.has_any_accounts())
        menu.addAction(update_accounts_info)

        clear_all_accounts = QAction('清空账号列表', self)
        clear_all_accounts.triggered.connect(self.clear_account_list)
        clear_all_accounts.setEnabled(self.account_mgr.has_any_accounts())
        menu.addAction(clear_all_accounts)

        bt_pos = self.manage_account_button.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x() - 139, bt_pos.y() - (95 - self.manage_account_button.height()))
        menu.exec_(show_pos)

    def open_web_link(self, url):
        open_url_in_browser(url)
        policy = profile_mgr.local_config['web_browser_settings']['url_open_policy']
        if policy == 0:
            self.close()

    def switch_main_page(self, index):
        self.stackedWidget.setCurrentIndex(index)

        self.login_button.setVisible(index == 0)
        self.manage_account_button.setVisible(index == 0)

    def scroll_common_settings(self, row):
        groupbox_map = [self.groupBox_8, self.groupBox_4,
                        self.groupBox_7, self.groupBox_5,
                        self.groupBox_10, self.groupBox_9]
        self.scrollArea.ensureWidgetVisible(groupbox_map[row])

    def reset_local_config(self):
        if QMessageBox.warning(self,
                               '警告',
                               '确认要重置所有设置吗？重置后，本页的所有选项都将恢复到默认状态。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            profile_mgr.fix_local_config()
            self.load_local_config()
            self.top_toaster.showToast(
                top_toast_widget.ToastMessage('设置重置成功', icon_type=top_toast_widget.ToastIconType.SUCCESS))

    def save_local_config(self):
        try:
            profile_mgr.local_config['thread_view_settings']['hide_video'] = self.checkBox.isChecked()
            profile_mgr.local_config['thread_view_settings']['hide_ip'] = self.checkBox_2.isChecked()
            profile_mgr.local_config['thread_view_settings'][
                'tb_emoticon_size'] = 0 if self.radioButton.isChecked() else 1
            profile_mgr.local_config['thread_view_settings']['default_sort'] = self.comboBox.currentIndex()
            profile_mgr.local_config['forum_view_settings']['default_sort'] = self.comboBox_2.currentIndex()
            profile_mgr.local_config['thread_view_settings']['enable_lz_only'] = self.checkBox_3.isChecked()
            profile_mgr.local_config['web_browser_settings']['url_open_policy'] = self.comboBox_3.currentIndex()
            profile_mgr.local_config['thread_view_settings']['play_gif'] = self.checkBox_12.isChecked()
            profile_mgr.local_config["notify_settings"]["enable_interact_notify"] = self.checkBox_13.isChecked()
            profile_mgr.local_config["notify_settings"]["offline_notify"] = self.checkBox_17.isChecked()
            profile_mgr.local_config["other_settings"]["mw_default_page"] = self.comboBox_4.currentIndex()
            profile_mgr.local_config["webview_settings"]["disable_font_cover"] = self.checkBox_20.isChecked()
            profile_mgr.local_config["webview_settings"]["view_frozen"] = self.checkBox_21.isChecked()
            profile_mgr.local_config["notify_settings"]["enable_clipboard_notify"] = self.checkBox_23.isChecked()
            profile_mgr.local_config["theme_settings"]["bright_dark_policy"] = self.comboBox_6.currentIndex()
            profile_mgr.local_config["thread_view_settings"]["show_statement"] = self.checkBox_24.isChecked()
            profile_mgr.local_config["webview_settings"]["transparent_bg_color"] = self.checkBox_25.isChecked()
            profile_mgr.local_config['sign_settings']['use_widget_sign_flag'] = self.checkBox_26.isChecked()
            profile_mgr.local_config["other_settings"]["disable_ssl_verify"] = self.checkBox_27.isChecked()
            profile_mgr.local_config['other_settings']['animation_switches'][
                'enable_image_fade_in'] = self.checkBox_28.isChecked()
            profile_mgr.local_config['other_settings']['animation_switches'][
                'disable_top_toast_animation'] = self.checkBox_29.isChecked()
            profile_mgr.local_config['other_settings']['animation_switches'][
                'disable_mw_switch_animation'] = self.checkBox_30.isChecked()
            profile_mgr.local_config["other_settings"]["close_main_window_action"] = self.comboBox_7.currentIndex()

            se_name_map = profile_mgr.sep_name_map
            if se_name_map.get(self.comboBox_5.currentText()) in profile_mgr.search_engine_presets.keys():
                profile_mgr.local_config["other_settings"]["context_menu_search_engine"]['preset'] = se_name_map.get(
                    self.comboBox_5.currentText())
                profile_mgr.local_config["other_settings"]["context_menu_search_engine"]['custom_url'] = ''
            else:
                profile_mgr.local_config["other_settings"]["context_menu_search_engine"]['preset'] = ''
                profile_mgr.local_config["other_settings"]["context_menu_search_engine"][
                    'custom_url'] = self.comboBox_5.currentText()

            try:
                rdbtn_check_index = [self.radioButton_3.isChecked(),
                                     self.radioButton_4.isChecked(),
                                     self.radioButton_5.isChecked()]
                proxy_switch = rdbtn_check_index.index(True)
            except ValueError:
                proxy_switch = 0
            port_num = int(self.lineEdit_2.text()) if self.lineEdit_2.text() else -1
            if not 0 <= port_num <= 65535 and self.lineEdit_2.text():
                raise IndexError(f'invalid port number {port_num}')

            profile_mgr.local_config["proxy_settings"]["proxy_switch"] = proxy_switch
            profile_mgr.local_config['proxy_settings']['custom_proxy_server']['ip'] = self.lineEdit.text()
            profile_mgr.local_config['proxy_settings']['custom_proxy_server']['port'] = port_num
            profile_mgr.local_config['proxy_settings']['enabled_scheme']['http'] = self.checkBox_14.isChecked()
            profile_mgr.local_config['proxy_settings']['enabled_scheme']['https'] = self.checkBox_15.isChecked()

            if self.radioButton_6.isChecked():
                profile_mgr.local_config['other_settings']['reset_dpi'] = -1
            else:
                profile_mgr.local_config['other_settings']['reset_dpi'] = self.spinBox.value() / 100

            profile_mgr.save_local_config()
        except KeyError:
            profile_mgr.fix_local_config()
            self.save_local_config()
        except Exception as e:
            log_exception(e)
        else:
            if self.brightDarkPolicyFlag != self.comboBox_6.currentIndex():  # 只在选项改变时执行切换主题
                QTimer.singleShot(300, lambda: qt_window_mgr.refresh_all_windows_theme())  # 延迟执行，防止UI卡顿

    def add_search_engine(self):
        text, click_ok = QInputDialog.getText(self, '添加自定义搜索引擎',
                                              '请在下方输入你要添加的搜索引擎链接，'
                                              '链接中的 [query] 字段代表实际使用时的搜索关键词（包括中括号）。\n'
                                              '请注意输入链接头部的 HTTP/HTTPS 前缀。')
        if click_ok and text:
            if not text.startswith((consts.SCHEME_HTTP, consts.SCHEME_HTTPS)):
                QMessageBox.critical(self, '输入错误', '请输入一个有效的 HTTP/HTTPS 链接。', QMessageBox.Ok)
            else:
                self.comboBox_5.addItem(text)
                self.comboBox_5.setCurrentIndex(self.comboBox_5.count() - 1)

    def open_proxy_settings(self):
        if platform.system() == 'Windows':  # windows 系统
            if int(platform.version().split('.')[-1]) < 10240:  # win10以下系统
                subprocess.call('inetcpl.cpl ,4', shell=True)  # 调用控制面板的老设置
            else:
                # win10 以后系统调用 UWP 设置
                open_url_in_browser('ms-settings:network-proxy')
        else:
            QMessageBox.information(self, '提示', '该功能暂不支持你的系统，请手动调整系统的代理设置。', QMessageBox.Ok)

    def set_debug_info(self):
        self.label_8.setText(f'版本 {consts.APP_VERSION_STR} ({consts.APP_VERSION_NUM})')
        self.label_23.setText(f'Qt 版本：{QT_VERSION_STR} ({QT_VERSION})')
        self.label_22.setText(f'用户数据目录：{consts.datapath}')
        self.label_21.setText(f'内部版本信息：version {consts.APP_VERSION_NUM} '
                              f'with aiotieba {aiotieba.__version__}, TiebaRequestMgr Client Version {request_mgr.TIEBA_CLIENT_VERSION}')
        self.label_20.setText(f'操作系统版本：{platform.system()} {platform.version()}, on {platform.machine()} CPU')
        self.label_16.setText('当前系统时间：' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))

    def add_account(self):
        d = LoginWebView()
        d.resize(1065, 680)
        d.exec()

    def add_account_qrcode(self):
        d = QRLoginDialog()
        d.exec()

    def add_account_senior(self):
        d = SeniorLoginDialog()
        d.exec()

    def select_all_caches(self):
        safetyClearTypeCb = [self.checkBox_4,
                             self.checkBox_5,
                             self.checkBox_9,
                             self.checkBox_10,
                             self.checkBox_7,
                             ]
        for i in safetyClearTypeCb:
            i.setChecked(True)

    def calc_willfree_size(self):
        free_size = 0
        select_num = 0

        for i in self.clearTypeCb:
            if i.isChecked():
                select_num += 1

        if self.checkBox_4.isChecked():
            free_size += self.scannedDetailData["image_cache_size"]
        if self.checkBox_5.isChecked():
            free_size += self.scannedDetailData["log_size"]
        if self.checkBox_9.isChecked():
            free_size += self.scannedDetailData["default_webview_size"]
        if self.checkBox_10.isChecked():
            free_size += self.scannedDetailData["fidcache_size"]
        if self.checkBox_7.isChecked():
            free_size += self.scannedDetailData["current_webview_cache_size"]
        if self.checkBox_6.isChecked():
            free_size += self.scannedDetailData["current_webview_cookie_size"]
        if self.checkBox_18.isChecked():
            free_size += self.scannedDetailData["post_draft_size"]
        if self.checkBox_19.isChecked():
            free_size += self.scannedDetailData["history_size"]
        if self.checkBox_22.isChecked():
            free_size += self.scannedDetailData["window_rect_size"]

        self.label_3.setText(f'已选 {select_num} 个条目，大约可清理 {filesize_tostr(free_size)} 空间')

    def _on_caches_cleared(self, isok):
        self.load_animation.hide()
        self.pushButton_12.setEnabled(True)

        toast = top_toast_widget.ToastMessage()
        if isok:
            toast.title = '数据清理成功'
            toast.icon_type = top_toast_widget.ToastIconType.SUCCESS

            self.groupBox_3.hide()
            self.label_26.setText('点击左侧按钮以分析本地数据存储情况')
        else:
            toast.title = '抱歉，数据清理失败，请重试'
            toast.icon_type = top_toast_widget.ToastIconType.SUCCESS
        self.top_toaster.showToast(toast)

    def clear_caches_async(self):
        if QMessageBox.warning(self, '清理数据',
                               '确认要清理这些数据吗？本操作需要一定时间，请耐心等待，清理数据时请不要关闭本窗口。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.pushButton_12.setEnabled(False)
            self.load_animation.set_caption(caption='正在清理数据，请稍等...')
            self.load_animation.show()
            webview = webview2.QWebView2View()
            webview.setProfile(
                webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}'))
            webview.initRender()

            start_background_thread(self.clear_caches, args=(webview,))

    def clear_caches(self, webview_obj: webview2.QWebView2View):
        def clear_folder(path):
            if not os.path.isdir(path):
                return

            for i in os.listdir(path):
                try:
                    item_path = f'{path}/{i}'
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except PermissionError:
                    continue

        try:
            while not webview_obj.isRenderInitOk():
                time.sleep(1)

            if self.checkBox_4.isChecked():
                clear_folder(f'{datapath}/image_caches')
            if self.checkBox_5.isChecked():
                clear_folder(f'{datapath}/logs')
            if self.checkBox_9.isChecked():
                clear_folder(f'{datapath}/webview_data/default')
            if self.checkBox_10.isChecked():
                aiotieba.helper.cache._fname2fid.clear()
                aiotieba.helper.cache._fid2fname.clear()
                aiotieba.helper.cache.save_caches()
                aiotieba.helper.cache.clear_repeat_items()
            if self.checkBox_18.isChecked():
                profile_mgr.post_drafts.clear()
                profile_mgr.save_post_drafts()
            if self.checkBox_19.isChecked():
                profile_mgr.view_history = []
                profile_mgr.save_view_history()
            if self.checkBox_22.isChecked():
                profile_mgr.window_rects.clear()
                profile_mgr.save_window_rects()
            if self.checkBox_7.isChecked():
                webview_obj.clearCacheData()
                time.sleep(4)
            if self.checkBox_6.isChecked():
                webview_obj.clearCookies()
                time.sleep(4)

            webview_obj.destroyWebviewUntilComplete()
        except Exception as e:
            log_exception(e)
            self.clearFinish.emit(False)
        else:
            self.clearFinish.emit(True)

    def _set_use_detail_ui(self, data):
        self.scannedDetailData = data

        self.checkBox_18.setText(f'回贴草稿 ({data["post_draft_num"]} 条)')
        self.checkBox_4.setText(f'图像缓存 ({filesize_tostr(data["image_cache_size"])})')
        self.checkBox_5.setText(f'日志文件 ({filesize_tostr(data["log_size"])})')
        self.checkBox_9.setText(f'游客网页数据 ({filesize_tostr(data["default_webview_size"])})')
        self.checkBox_10.setText(f'吧信息缓存 ({data["fidcache_num"]} 条)')
        self.checkBox_8.setText(f'主要配置文件 ({filesize_tostr(data["main_profile_size"])})')
        self.checkBox_11.setText(f'所有网页数据 ({filesize_tostr(data["total_webview_size"])})')
        self.checkBox_7.setText(f'网页缓存 ({filesize_tostr(data["current_webview_cache_size"])})')
        self.checkBox_6.setText(f'网页 Cookies ({filesize_tostr(data["current_webview_cookie_size"])})')
        self.checkBox_19.setText(f'浏览记录 ({data["history_num"]} 条)')
        self.checkBox_22.setText(f'窗口大小位置 ({data["window_rect_num"]} 条)')

        for i in self.clearTypeCb:
            i.setChecked(False)
        self.pushButton_12.setEnabled(True)
        self.label_26.setText(f'分析完成，贴吧桌面已存储了 {filesize_tostr(data["total_data_size"])} 的用户数据。')
        self.load_animation.hide()

    def scan_use_detail_async(self):
        self.pushButton_12.setEnabled(False)
        self.label_26.setText('正在分析本地数据存储情况，请稍等...')
        self.groupBox_3.show()
        self.load_animation.set_caption(caption='正在分析存储情况...')
        self.load_animation.show()

        start_background_thread(self.scan_use_detail)

    def scan_use_detail(self):
        def scan_tree_total_size(path):
            tsize = 0
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for name in files:
                        path = os.path.join(root, name)
                        tsize += os.stat(path).st_size

            return tsize

        data = {'total_data_size': 0,
                'image_cache_size': 0,
                'log_size': 0,
                'default_webview_size': 0,
                'fidcache_num': 0,
                'main_profile_size': 0,
                'total_webview_size': 0,
                'current_webview_cache_size': 0,
                'current_webview_cookie_size': 0,
                'fidcache_size': 0,
                'post_draft_num': 0,
                'post_draft_size': 0,
                'history_num': 0,
                'history_size': 0,
                'window_rect_num': 0,
                'window_rect_size': 0}

        lsc_log = scan_tree_total_size(f'{datapath}/logs')  # 日志文件总大小
        lsc_img = scan_tree_total_size(f'{datapath}/image_caches')  # 图片缓存文件总大小
        data['image_cache_size'] = lsc_img
        data['log_size'] = lsc_log

        main_pf_exclude = ['view_history', 'post_drafts', 'window_rects.json']  # 排除特定文件
        for i in os.listdir(datapath):
            if os.path.isfile(f'{datapath}/{i}') and i not in main_pf_exclude:
                data['main_profile_size'] += os.stat(f'{datapath}/{i}').st_size

        data['default_webview_size'] = scan_tree_total_size(f'{datapath}/webview_data/default')
        data['current_webview_cache_size'] = scan_tree_total_size(
            f'{datapath}/webview_data/{profile_mgr.current_uid}/EBWebView/Default/Cache')
        data['current_webview_cookie_size'] = scan_tree_total_size(
            f'{datapath}/webview_data/{profile_mgr.current_uid}/EBWebView/Default/Network')
        data['total_webview_size'] = scan_tree_total_size(f'{datapath}/webview_data')
        data['fidcache_num'] = len(aiotieba.helper.cache._fname2fid.keys())
        data['fidcache_size'] = os.stat(f'{datapath}/cache_index/fidfname_index.json').st_size
        data['post_draft_size'] = os.stat(f'{datapath}/post_drafts').st_size
        data['post_draft_num'] = len(profile_mgr.post_drafts.keys())
        data['history_size'] = os.stat(f'{datapath}/view_history').st_size
        data['history_num'] = len(profile_mgr.view_history)
        data['window_rect_num'] = len(profile_mgr.window_rects.keys())
        data['window_rect_size'] = os.stat(f'{datapath}/window_rects.json').st_size

        data['total_data_size'] = (lsc_img +
                                   lsc_log +
                                   data['main_profile_size'] +
                                   data['total_webview_size'] +
                                   data['fidcache_size'] +
                                   data['post_draft_size'] +
                                   data['history_size'])

        self.scanFinish.emit(data)

    def clear_account_list(self):
        if QMessageBox.warning(self, '警告', '确认要清空本地的所有登录信息吗？这会导致所有用户退出登录。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.current_a = None
            self.account_mgr.clear_all_accounts_async()

    def switch_account(self, uid=0):
        if not uid:
            uid = self.listWidget_2.currentItem().user_portrait_id
        user_info = self.account_mgr.get_account_by_uid_portrait(uid)

        if user_info != self.current_a:
            if QMessageBox.information(self, '提示',
                                       f'确认要切换到账号 {user_info.nickname} 吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.account_mgr.switch_to_account_async(user_info.uid)

    def delete_account(self, uid=0):
        if not uid:
            uid = self.listWidget_2.currentItem().user_portrait_id
        user_info = self.account_mgr.get_account_by_uid_portrait(uid)

        if QMessageBox.information(self, '提示',
                                   f'确认要删除账号 {user_info.nickname} 的登录信息吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.account_mgr.delete_account_async(uid)

    def load_local_config(self):
        try:
            self.brightDarkPolicyFlag = profile_mgr.local_config["theme_settings"]["bright_dark_policy"]

            self.checkBox_3.setChecked(profile_mgr.local_config['thread_view_settings']['enable_lz_only'])
            self.checkBox.setChecked(profile_mgr.local_config['thread_view_settings']['hide_video'])
            self.checkBox_2.setChecked(profile_mgr.local_config['thread_view_settings']['hide_ip'])
            self.checkBox_12.setChecked(profile_mgr.local_config['thread_view_settings']['play_gif'])
            self.checkBox_24.setChecked(profile_mgr.local_config["thread_view_settings"]["show_statement"])
            self.comboBox.setCurrentIndex(profile_mgr.local_config['thread_view_settings']['default_sort'])
            (self.radioButton if profile_mgr.local_config['thread_view_settings'][
                                     'tb_emoticon_size'] == 0 else self.radioButton_2).setChecked(True)

            self.checkBox_13.setChecked(profile_mgr.local_config["notify_settings"]["enable_interact_notify"])
            self.checkBox_17.setChecked(profile_mgr.local_config["notify_settings"]["offline_notify"])
            self.checkBox_23.setChecked(profile_mgr.local_config["notify_settings"]["enable_clipboard_notify"])

            self.comboBox_2.setCurrentIndex(profile_mgr.local_config['forum_view_settings']['default_sort'])

            self.checkBox_28.setChecked(
                profile_mgr.local_config['other_settings']['animation_switches']['enable_image_fade_in'])
            self.comboBox_4.setCurrentIndex(profile_mgr.local_config["other_settings"]["mw_default_page"])
            self.comboBox_6.setCurrentIndex(self.brightDarkPolicyFlag)
            self.comboBox_7.setCurrentIndex(profile_mgr.local_config["other_settings"]["close_main_window_action"])

            self.checkBox_29.setChecked(
                profile_mgr.local_config['other_settings']['animation_switches']['disable_top_toast_animation'])
            self.checkBox_20.setChecked(profile_mgr.local_config["webview_settings"]["disable_font_cover"])
            self.checkBox_21.setChecked(profile_mgr.local_config["webview_settings"]["view_frozen"])
            self.checkBox_25.setChecked(profile_mgr.local_config["webview_settings"]["transparent_bg_color"])
            self.checkBox_27.setChecked(profile_mgr.local_config["other_settings"]["disable_ssl_verify"])
            self.comboBox_3.setCurrentIndex(profile_mgr.local_config['web_browser_settings']['url_open_policy'])
            self.checkBox_30.setChecked(
                profile_mgr.local_config['other_settings']['animation_switches']['disable_mw_switch_animation'])

            self.checkBox_26.setChecked(profile_mgr.local_config['sign_settings']['use_widget_sign_flag'])

            search_engine_settings = profile_mgr.local_config["other_settings"]["context_menu_search_engine"]
            if search_engine_settings['preset']:
                self.comboBox_5.setCurrentText(profile_mgr.sep_name_map_inverted[search_engine_settings['preset']])
            else:
                self.comboBox_5.addItem(search_engine_settings['custom_url'])
                self.comboBox_5.setCurrentIndex(self.comboBox_5.count() - 1)

            rdbtn_index = [self.radioButton_3, self.radioButton_4, self.radioButton_5]
            port = profile_mgr.local_config['proxy_settings']['custom_proxy_server']['port']
            rdbtn_index[profile_mgr.local_config['proxy_settings']['proxy_switch']].setChecked(True)
            self.lineEdit.setText(profile_mgr.local_config['proxy_settings']['custom_proxy_server']['ip'])
            self.lineEdit_2.setText(str(port) if port != -1 else '')
            self.checkBox_14.setChecked(profile_mgr.local_config['proxy_settings']['enabled_scheme']['http'])
            self.checkBox_15.setChecked(profile_mgr.local_config['proxy_settings']['enabled_scheme']['https'])

            if profile_mgr.local_config['other_settings']['reset_dpi'] == -1:
                self.radioButton_6.setChecked(True)
            else:
                self.radioButton_7.setChecked(True)
                self.spinBox.setValue(int(profile_mgr.local_config['other_settings']['reset_dpi'] * 100))
        except KeyError:
            logging.log_WARN('settings profile load failed, use default settings')

    def get_logon_accounts(self):
        # 清空数据
        self.listWidget_2.clear()
        QPixmapCache.clear()
        gc.collect()

        # 加载列表
        self.current_a = self.account_mgr.current_account
        for account in self.account_mgr.account_list:
            # 向下兼容
            i = account.to_json()

            item = ExtListWidgetItem(i['bduss'], i['stoken'])
            item.user_portrait_id = i['uid']
            widget = UserItem(i['bduss'], i['stoken'])
            widget.switchRequested.connect(lambda d: self.switch_account(d[0]))
            widget.deleteRequested.connect(lambda d: self.delete_account(d[0]))
            widget.doubleClicked.connect(self.switch_account)
            widget.user_portrait_id = i['portrait']
            widget.setdatas(i['portrait'], i['name'], i['uid'], True,
                            is_current_user=account.is_current)
            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)

        account_num = len(self.account_mgr.account_list)
        if not account_num:
            self.listWidget_2.hide()
            self.label.show()
            self.label.setText('未登录任何账号\n点击右下角“+”按钮可登录账号')
        else:
            self.listWidget_2.show()
            self.label.hide()

    def export_account_info(self):
        filetype_list = ['JSON 文件 (*.json)', '纯文本文件 (*.txt)']
        path, tpe = QFileDialog.getSaveFileName(self, '导出账号信息', '',
                                                ';;'.join(filetype_list))

        if path and tpe:
            if tpe == filetype_list[0]:
                json_data = {'current_account_uid': self.account_mgr.current_account.uid,
                             "account_list": [i.to_json() for i in self.account_mgr.account_list]}
                save_json(json_data, path, ensure_ascii=False, indent=4)
            elif tpe == filetype_list[1]:
                export_text = f'TiebaDesktop Account Info\n{"-" * 100}'

                for i in self.account_mgr.account_list:
                    account_string = (f'Nickname: {i.nickname}\n'
                                      f'User ID: {i.uid}\n'
                                      f'Portrait: {i.portrait}\n'
                                      f'BDUSS: {i.bduss}\n'
                                      f'STOKEN: {i.stoken}\n'
                                      f'Is Current Account: {"Yes" if i.is_current else "No"}')
                    export_text += '\n\n' + account_string

                with open(path, 'wt', encoding='utf-8') as file:
                    file.write(export_text)

            toast = top_toast_widget.ToastMessage('数据导出成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.top_toaster.showToast(toast)

    def refresh_all_users_info(self):
        self.account_mgr.refresh_all_accounts_info_async()

        toast = top_toast_widget.ToastMessage('已开始在后台刷新数据，登录失效的账号将被清理，请耐心等待',
                                              icon_type=top_toast_widget.ToastIconType.INFORMATION)
        self.top_toaster.showToast(toast)

    def on_account_add_failed(self, err_info):
        toast = top_toast_widget.ToastMessage(f'账号添加失败: {err_info}',
                                              icon_type=top_toast_widget.ToastIconType.ERROR)
        self.top_toaster.showToast(toast)


class MainWindow(QMainWindow, mainwindow.Ui_MainWindow):
    """主窗口，整个程序的入口点"""
    user_data = {'bduss': '', 'stoken': ''}
    self_user_portrait = ''
    is_account_first_load = True
    is_settings_window_using = False

    add_info = pyqtSignal(list)
    user_info_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.init_ui_elements()
        self.set_theme_qss(True)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton.setStyleSheet("QPushButton::menu-indicator{image:none;}")
        self.notice_syncer = TiebaMsgSyncer()
        self.clipboard_syncer = ClipboardSyncer()

        self.pushButton_3.clicked.connect(self.switch_follow_forum_page)
        self.pushButton_4.clicked.connect(self.switch_interact_page)
        self.pushButton_2.clicked.connect(self.switch_recommand_page)
        self.pushButton_5.clicked.connect(self.open_search_window)

        self.account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
        self.add_info.connect(self._add_uinfo)
        self.user_info_loaded.connect(self.__refresh_ui_datas)
        self.notice_syncer.noticeCountChanged.connect(self.set_unread_count)
        self.notice_syncer.activeWindow.connect(self.switch_interact_page)
        self.account_manager.accountSwitched.connect(self.refresh_all_datas)

        self.init_profile_menu()
        self.init_pages()

        default_index = get_dict_value_treely(profile_mgr.local_config,
                                              ['other_settings', 'mw_default_page'],
                                              0)
        self.stackedWidget.setCurrentIndex(default_index)  # 设置初始页面
        self.previous_page_index = default_index  # 初始化前一个页面索引
        self.paint_page_switch_elements()

        self.notice_syncer.start_sync()
        self.free_current_session()
        self.account_manager.load_accounts_list_async()
        self.move_as_config()

    def nativeEvent(self, eventType, message):
        base_ui.handle_native_event(self, qt_window_mgr.refresh_all_windows_theme, eventType, message)
        return super().nativeEvent(eventType, message)

    def closeEvent(self, a0):
        close_action = get_dict_value_treely(profile_mgr.local_config,
                                             ['other_settings', 'close_main_window_action'],
                                             0)
        if close_action == 0:
            a0.ignore()
            self.hide()
        elif close_action == 1:
            windows_num = len(qt_window_mgr.distributed_window)
            show_text = (f'你还有 {windows_num} 个打开的窗口没有被关闭，' if windows_num > 0 else '') + '确认要退出软件吗？'
            msgbox = QMessageBox(QMessageBox.Information,
                                 '提示',
                                 show_text,
                                 parent=self)
            msgbox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

            if msgbox.exec() == QMessageBox.Yes:
                self.exit_app(a0)
            else:
                a0.ignore()
        else:
            self.exit_app(a0)

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_F5 and self.stackedWidget.currentIndex() == 0:
            self.recommend.get_recommand_async(True)

    def move_as_config(self):
        window_rect = profile_mgr.get_window_rects(type(self))
        if window_rect and window_rect[4]:
            self.showMaximized()
        elif window_rect:
            self.setGeometry(window_rect[0],
                             window_rect[1],
                             window_rect[2],
                             window_rect[3])

    def set_theme_qss(self, is_init_setting=False):
        base_ui.set_widget_dark_mode(self)

        color = profile_mgr.get_theme_color_string()
        color_reversed = profile_mgr.get_theme_font_color_string()

        # 设置自己的样式
        base_ui.set_theme_qss_as_cfg(self, f'\nQFrame#frame{{background-color:{color};}}')
        self.frame.setStyleSheet(f'QPushButton{{color:{color_reversed};}}')
        self.pushButton.setIcon(QIcon(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/more.png'))

        # 初始化阶段不对子页面设置，初始化时子页面会自己设置
        if not is_init_setting:
            # 设置子页面的样式
            self.recommend.set_theme_qss()
            self.flist.reset_theme()
            self.interactionlist.reset_theme()
            self.user_info_widget.reset_theme()
            self.popup_menu.reset_theme()

            # 弹出通知
            toast = top_toast_widget.ToastMessage('主题切换成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.toast_widget.showToast(toast)

    def exit_app(self, close_event: QCloseEvent = None):
        profile_mgr.add_window_rects(type(self),
                                     self.x() + 1, self.y() + 31,
                                     self.width(), self.height(),
                                     self.isMaximized())

        if close_event:
            close_event.accept()
        else:
            self.hide()

        tray_icon.hide()
        qt_window_mgr.clear_windows()
        app.closeAllWindows()
        app.quit()

    def init_ui_elements(self):
        self.toast_widget = top_toast_widget.TopToaster()
        self.toast_widget.setCoverWidget(self)

        # 初始化页面切换动画相关的属性
        self.previous_page_index = 0  # 前一个页面的索引
        self.page_switch_animation = None  # 当前正在执行的动画

    def paint_page_switch_elements(self):
        self.set_top_button_style()

        page_switch_animation_enabled = get_dict_value_treely(profile_mgr.local_config,
                                                              ['other_settings', 'animation_switches',
                                                               'disable_mw_switch_animation'],
                                                              False)
        if not page_switch_animation_enabled:
            self.rend_page_switch_animation()

        # 不管怎样，更新前一个页面的索引
        self.previous_page_index = self.stackedWidget.currentIndex()

    def rend_page_switch_animation(self):
        """
        实现页面切换时的视觉渐变效果
        当用户切换页面时，前一个页面淡出，新页面淡入，形成平滑的过渡动画
        """

        # 获取前一个页面和当前页面的索引
        previous_index = self.previous_page_index
        current_index = self.stackedWidget.currentIndex()

        # 如果页面没有实际改变，则不执行动画
        if previous_index == current_index:
            return

        # 停止之前正在执行的动画（如果有）
        if self.page_switch_animation is not None:
            self.page_switch_animation.stop()
            self.page_switch_animation.deleteLater()

        # 获取前一个页面和当前页面的widgets
        previous_widget = self.stackedWidget.widget(previous_index)
        current_widget = self.stackedWidget.widget(current_index)

        if previous_widget is None or current_widget is None:
            self.previous_page_index = current_index
            return

        # 确保当前页面可见，前一个页面也保持可见以便显示动画
        current_widget.setVisible(True)
        previous_widget.setVisible(True)

        # 为前一个页面创建透明度效果
        fade_out_effect = QGraphicsOpacityEffect()
        fade_out_effect.setOpacity(1.0)
        previous_widget.setGraphicsEffect(fade_out_effect)

        # 为当前页面创建透明度效果
        fade_in_effect = QGraphicsOpacityEffect()
        fade_in_effect.setOpacity(0.0)
        current_widget.setGraphicsEffect(fade_in_effect)

        # 创建并行动画组，用于同时执行淡出和淡入效果
        animation_group = QParallelAnimationGroup()

        # 创建前一个页面的淡出动画
        fade_out_animation = QPropertyAnimation(fade_out_effect, b"opacity")
        fade_out_animation.setStartValue(1.0)
        fade_out_animation.setEndValue(0.0)
        fade_out_animation.setDuration(200)
        fade_out_animation.setEasingCurve(QEasingCurve.InOutQuad)

        # 创建当前页面的淡入动画
        fade_in_animation = QPropertyAnimation(fade_in_effect, b"opacity")
        fade_in_animation.setStartValue(0.0)
        fade_in_animation.setEndValue(1.0)
        fade_in_animation.setDuration(200)
        fade_in_animation.setEasingCurve(QEasingCurve.InOutQuad)

        # 将两个动画添加到并行动画组
        animation_group.addAnimation(fade_out_animation)
        animation_group.addAnimation(fade_in_animation)

        # 动画完成后的清理工作
        def on_animation_finished():
            previous_widget.setVisible(False)
            previous_widget.setGraphicsEffect(None)
            current_widget.setGraphicsEffect(None)
            self.page_switch_animation = None

        animation_group.finished.connect(on_animation_finished)

        # 保存当前动画引用并启动动画
        self.page_switch_animation = animation_group
        animation_group.start()

    def set_top_button_style(self):
        button_index = [self.pushButton_2, self.pushButton_3, self.pushButton_4]
        current_button = button_index[self.stackedWidget.currentIndex()]

        current_font = QFont()
        other_font = QFont()

        current_font.setBold(True)
        current_font.setPointSize(15)
        other_font.setBold(False)
        other_font.setPointSize(13)

        current_button.setFont(current_font)

        for btn in button_index:
            if btn == current_button:
                continue
            btn.setFont(other_font)

    def set_unread_count(self):
        if self.notice_syncer.have_basic_unread_notice():
            self.pushButton_4.setStyleSheet('QPushButton{color: red;}')
            self.pushButton_4.setText(
                f'消息 ({self.notice_syncer.get_unread_notice_count(UnreadMessageType.TOTAL_COUNT)})')
        else:
            self.pushButton_4.setStyleSheet('')
            self.pushButton_4.setText('消息')

    def switch_follow_forum_page(self):
        self.stackedWidget.setCurrentIndex(1)
        if self.flist.is_first_show:
            self.flist.get_bars_async()
            self.flist.is_first_show = False

        self.paint_page_switch_elements()

    def show_active_window(self):
        if self.is_settings_window_using:
            return

        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        if not self.isActiveWindow():
            self.activateWindow()

    def switch_interact_page(self):
        self.show_active_window()
        self.stackedWidget.setCurrentIndex(2)

        if self.interactionlist.is_first_show:
            self.interactionlist.refresh_list()
            self.interactionlist.is_first_show = False

        self.paint_page_switch_elements()

    def switch_recommand_page(self):
        self.stackedWidget.setCurrentIndex(0)
        if self.recommend.is_first_load:
            self.recommend.get_recommand_async()

        self.paint_page_switch_elements()

    def free_current_session(self):
        qt_window_mgr.clear_windows()
        QPixmapCache.clear()
        gc.collect()

        self.label_9.clear()
        self.label_10.setText('账号加载中...')
        self.frame.setEnabled(False)

    def refresh_all_datas(self):
        self.free_current_session()

        if self.is_account_first_load:
            self.is_account_first_load = False
        else:
            account = self.account_manager.current_account
            if account:
                toast = top_toast_widget.ToastMessage(f'已切换到账号 {account.nickname}',
                                                      icon_type=top_toast_widget.ToastIconType.SUCCESS)
            else:
                toast = top_toast_widget.ToastMessage(f'已进入游客账号模式',
                                                      icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.toast_widget.showToast(toast)
        start_background_thread(self.init_user_data)

    def __refresh_ui_datas(self):
        # 清理内存
        self.set_profile_menu()
        self.pushButton.setEnabled(True)
        self.recommend.bduss = self.user_data['bduss']
        self.recommend.stoken = self.user_data['stoken']
        self.recommend.is_first_load = True
        self.flist.bduss = self.user_data['bduss']
        self.flist.stoken = self.user_data['stoken']
        self.flist.is_first_show = True
        self.interactionlist.bduss = self.user_data['bduss']
        self.interactionlist.stoken = self.user_data['stoken']
        self.interactionlist.is_first_show = True
        self.notice_syncer.set_account(self.user_data['bduss'], self.user_data['stoken'])

        self.user_info_widget.get_self_info_async()
        self.notice_syncer.run_msg_sync_immedently()
        if self.stackedWidget.currentIndex() == 0:
            self.switch_recommand_page()
        elif self.stackedWidget.currentIndex() == 1:
            self.switch_follow_forum_page()
        elif self.stackedWidget.currentIndex() == 2:
            self.switch_interact_page()

    def open_search_window(self):
        tb_search_window = TiebaSearchWindow(self.user_data['bduss'], self.user_data['stoken'])
        qt_window_mgr.add_window(tb_search_window)

    def open_agreed_window(self):
        user_stared_list = AgreedThreadsList(profile_mgr.current_bduss, profile_mgr.current_stoken)
        qt_window_mgr.add_window(user_stared_list)

    def init_pages(self):
        self.recommend = RecommendWindow(self.user_data['bduss'], self.user_data['stoken'], self)
        self.stackedWidget.addWidget(self.recommend)

        self.flist = FollowForumList(self.user_data['bduss'], self.user_data['stoken'], self)
        self.stackedWidget.addWidget(self.flist)

        self.interactionlist = UserInteractionsList(self.user_data['bduss'], self.user_data['stoken'], self)
        self.stackedWidget.addWidget(self.interactionlist)

        self.stackedWidget.setCurrentIndex(0)

    def open_settings_window(self):
        if self.is_settings_window_using:
            return

        self.is_settings_window_using = True
        d = SettingsWindow()
        d.exec()
        d.deleteLater()
        self.is_settings_window_using = False

    def init_profile_menu(self):
        self.popup_menu = base_ui.BaseQMenu()

        self.user_info_widget = MainPopupMenu(self.popup_menu)
        self.user_info_widget_action = QWidgetAction(self)
        self.user_info_widget.followForumClicked.connect(self.switch_follow_forum_page)
        self.user_info_widget.loginAccountClicked.connect(self.login_exec)
        self.user_info_widget_action.setDefaultWidget(self.user_info_widget)
        self.popup_menu.addAction(self.user_info_widget_action)

        self.my_agrees = QAction('我的点赞', self)
        self.my_agrees.triggered.connect(self.open_agreed_window)
        self.popup_menu.addAction(self.my_agrees)

        self.popup_menu.addSeparator()

        self.setting = QAction('软件设置', self)
        self.setting.triggered.connect(self.open_settings_window)
        self.popup_menu.addAction(self.setting)

        self.exit_login_ac = QAction('退出登录', self)
        self.exit_login_ac.triggered.connect(self.exit_login)
        self.popup_menu.addAction(self.exit_login_ac)

        self.popup_menu.addSeparator()

        self.hide_window = QAction('最小化到托盘', self)
        self.hide_window.triggered.connect(self.hide)
        self.popup_menu.addAction(self.hide_window)

        self.exit_whole_app = QAction('退出软件', self)
        self.exit_whole_app.triggered.connect(self.exit_app)
        self.popup_menu.addAction(self.exit_whole_app)

        self.pushButton.setMenu(self.popup_menu)

    def set_profile_menu(self):
        if self.user_data['bduss']:
            self.my_agrees.setVisible(True)
            self.exit_login_ac.setVisible(True)
        else:
            self.my_agrees.setVisible(False)
            self.exit_login_ac.setVisible(False)

    def exit_login(self):
        if QMessageBox.warning(self, '警告',
                               '确认要退出当前账号吗？\n如果本机没有登录其他账号，那么你将会切换到游客模式下；\n如果你登录了其他账号，那么你将会被切换到下一个账号。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.account_manager.delete_account_async(self.account_manager.current_account.uid)

    def login_exec(self):
        if webview2.isWebView2Installed():
            d = LoginWebView()
            d.resize(1065, 680)
        else:
            d = QRLoginDialog()
        d.exec()

    def handle_d2id_flag(self):
        data = load_json(f'{datapath}/d2id_flag')
        uid = data['uid']
        if uid:
            try:
                if os.path.isdir(f'{datapath}/webview_data/{uid}'):  # 把旧的数据删掉
                    shutil.rmtree(f'{datapath}/webview_data/{uid}')
                os.rename(f'{datapath}/webview_data/default', f'{datapath}/webview_data/{uid}')
                os.mkdir(f'{datapath}/webview_data/default')
            except Exception as e:
                log_WARN('handle_d2id_flag failed')
                log_exception(e)
            else:
                save_json({'uid': ''}, f'{datapath}/d2id_flag')

    def _add_uinfo(self, datas):
        self.frame.setEnabled(True)
        if not datas:
            toast = top_toast_widget.ToastMessage(f'用户信息加载失败，已临时进入游客模式',
                                                  icon_type=top_toast_widget.ToastIconType.ERROR)
            self.toast_widget.showToast(toast)

            self.label_10.setText('[用户信息加载失败]')
        else:
            if datas[0]:
                self.label_9.setPixmap(datas[0])
            if datas[1]:
                self.label_10.setText(datas[1])

    def init_user_data(self):
        try:
            self.handle_d2id_flag()  # 先处理d2id

            self.user_data = self.account_manager.current_account.to_json()

            if not self.user_data['bduss']:
                profile_mgr.current_uid = 'default'
                profile_mgr.current_stoken = ''
                profile_mgr.current_bduss = ''

                pixmap = QPixmap('ui/default_user_image.png')
                pixmap.setDevicePixelRatio(qt_image.get_screen_ratio())
                pixmap = qt_image.add_cover_for_pixmap(pixmap, 30)
                self.add_info.emit([pixmap, '未登录'])
            else:
                # 获取用户信息
                profile_mgr.current_uid = self.user_data['uid']
                profile_mgr.current_bduss = self.user_data['bduss']
                profile_mgr.current_stoken = self.user_data['stoken']
                name = self.user_data['name']
                self.self_user_portrait = self.user_data['portrait']

                pixmap = QPixmap()
                pixmap.setDevicePixelRatio(qt_image.get_screen_ratio())
                pixmap.loadFromData(cache_mgr.get_portrait(self.self_user_portrait))
                pixmap = qt_image.add_cover_for_pixmap(pixmap, 30)
                self.add_info.emit([pixmap, name])
        except Exception as e:
            self.add_info.emit([])
            log_exception(e)
        else:
            log_INFO(f'switched account {profile_mgr.current_uid}')
            self.user_info_loaded.emit()


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
    app.setQuitOnLastWindowClosed(False)
    translates = set_qt_languages()
    log_INFO('Qt init complete')

    # init .net/cpp libraries
    winrt_share.init_library()
    check_webview2()

    # init main window, tray icon
    log_INFO('Initing main window')
    main_window = MainWindow()
    tray_icon = TrayIcon()

    # show ui elements
    tray_icon.show()
    if '--quiet' not in sys.argv:
        main_window.show()

    # main loop
    logging.log_INFO('MainWindow showed, now run into the main loop')
    sys.exit(app.exec())
