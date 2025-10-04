"""程序入口点，包含了整个程序最基本的函数和类"""
import os
import shutil
import time

import cache_mgr
import proxytool
from core_features import *
from ui import mainwindow

requests.session().trust_env = True
requests.session().verify = False


def excepthook(type, value, traceback):
    """捕获并打印错误"""
    if type != SystemExit:
        aiotieba.logging.get_logger().warning(f"A error in main thread caught: ")
        aiotieba.logging.get_logger().warning(f'{type}: {value}')
        aiotieba.logging.get_logger().warning(f'Error details: ')
        while traceback:
            frame = traceback.tb_frame
            lineno = traceback.tb_lineno
            filename = frame.f_code.co_filename
            name = frame.f_code.co_name
            aiotieba.logging.get_logger().warning(f"Filename: {filename}, Function: {name}, LineNumber: {lineno}")
            traceback = traceback.tb_next


def set_qt_languages():
    """加载qt的语言文件"""
    if QLocale().language() == QLocale.Language.Chinese:
        language_file_list = ["ui/qt_zh_CN.qm", 'ui/qtbase_zh_CN.qm']
        translators = []
        for i in language_file_list:
            translator = QTranslator()
            if translator.load(i):
                app.installTranslator(translator)
                aiotieba.logging.get_logger().info(f'Qt language file {i} loaded')
                translators.append(translator)
        return translators


def check_webview2():
    """检查用户的电脑是否安装了webview2"""
    aiotieba.logging.get_logger().info(f'Checking webview2')

    if not webview2.isWebView2Installed():
        msgbox = QMessageBox()
        msgbox.warning(None, '运行警告',
                       '你的电脑上似乎还未安装 WebView2 运行时。本程序的部分功能（如登录等）将不可用。',
                       QMessageBox.Ok)


def handle_command_events():
    """处理命令行参数，与命令行参数有关的代码均在此执行"""
    cmds = sys.argv
    dont_run_gui = False
    aiotieba.logging.get_logger().info('Handling command args')

    def get_current_user():
        user_data = {'bduss': '', 'stoken': ''}
        real_user_data = load_json_secret(f'{datapath}/user_bduss')
        if real_user_data['current_bduss'] and real_user_data['login_list']:  # 有选账号且有已登录用户
            # 找到这个用户
            for i in real_user_data['login_list']:
                if i['bduss'] == real_user_data['current_bduss']:
                    user_data = i
                    break
        return user_data['bduss'], user_data['stoken']

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
                    err_msg += f'\n成长等级签到：{r1.err.msg}'
                if not r2:
                    err_msg += f'\n成长等级分享任务：{r2.err.msg}'
            msgbox(err_msg)

    async def sign_all():
        bduss, stoken = get_current_user()
        if not bduss:
            msgbox('请先登录账号再签到。')
            return
        signed_count = 0

        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            bars = request_mgr.run_get_api('/mo/q/newmoindex', bduss)['data']['like_forum']
            bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

            for forum in bars:
                if forum["is_sign"] != 1:
                    fid = forum['forum_id']
                    r = await client.sign_forum(fid)
                    if r:
                        signed_count += 1  # 签到成功了加一
                    await asyncio.sleep(0.3)  # 休眠0.3秒，防止贴吧服务器抽风
                else:
                    # 已签到的直接跳过
                    signed_count += 1
        msgbox(f'签到完成，已签到 {signed_count} 个吧，{len(bars) - signed_count} 个吧签到失败。')

    async def switch_account():
        uid = -1
        for i in cmds:
            if i.startswith('--userid='):
                uid = int(i.split('=')[1])
        if uid < 0:
            msgbox('请指定正确的用户 ID。')
        else:
            real_user_data = load_json_secret(f'{datapath}/user_bduss')
            for i in real_user_data['login_list']:
                if i['uid'] == uid:
                    real_user_data['current_bduss'] = i['bduss']
                    save_json_secret(real_user_data, f'{datapath}/user_bduss')
                    msgbox(f'已将账号切换到 {uid}。')
                    return
            msgbox(f'未在本地找到 {uid} 的登录信息。')

    def start_async(func):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func)

    if '--set-current-account' in cmds:
        dont_run_gui = True
        aiotieba.logging.get_logger().info('--set-current-account started')
        start_async(switch_account())
    else:
        if '--sign-all-forums' in cmds:
            dont_run_gui = True
            aiotieba.logging.get_logger().info('--sign-all-forums started')
            start_async(sign_all())
        if '--sign-grows' in cmds:
            dont_run_gui = True
            aiotieba.logging.get_logger().info('--sign-grows started')
            start_async(sign_grow())
    if dont_run_gui:
        sys.exit(0)


class SettingsWindow(QDialog, settings.Ui_Dialog):
    """设置窗口"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label_6.setPixmap(QPixmap('ui/tieba_logo_small.png'))
        self.label_8.setText(f'版本 {consts.APP_VERSION_STR}')
        self.get_log_size()
        self.get_pic_size()
        self.get_logon_accounts()
        self.load_local_config()

        self.init_login_button_menu()
        self.listWidget.currentRowChanged.connect(self.stackedWidget.setCurrentIndex)
        self.pushButton_3.clicked.connect(lambda: open_url_in_browser(f'{datapath}/logs'))
        self.pushButton_4.clicked.connect(self.clear_logs)
        self.pushButton.clicked.connect(self.clear_account_list)
        self.pushButton_5.clicked.connect(self.save_local_config)
        self.pushButton_8.clicked.connect(self.clear_pics)

    def init_login_button_menu(self):
        menu = QMenu()

        webview_login = QAction('网页登录 (推荐)', self)
        webview_login.triggered.connect(self.add_account)
        menu.addAction(webview_login)

        bduss_directly_login = QAction('高级登录', self)
        bduss_directly_login.triggered.connect(self.add_account_senior)
        menu.addAction(bduss_directly_login)

        self.pushButton_2.setMenu(menu)

    def save_local_config(self):
        profile_mgr.local_config['thread_view_settings']['hide_video'] = self.checkBox.isChecked()
        profile_mgr.local_config['thread_view_settings']['hide_ip'] = self.checkBox_2.isChecked()
        profile_mgr.local_config['thread_view_settings']['tb_emoticon_size'] = 0 if self.radioButton.isChecked() else 1
        profile_mgr.local_config['thread_view_settings']['default_sort'] = self.comboBox.currentIndex()
        profile_mgr.local_config['forum_view_settings']['default_sort'] = self.comboBox_2.currentIndex()
        profile_mgr.local_config['thread_view_settings']['enable_lz_only'] = self.checkBox_3.isChecked()
        profile_mgr.save_local_config()
        QMessageBox.information(self, '提示', '设置保存成功。', QMessageBox.Ok)

    def add_account(self):
        d = LoginWebView()
        d.resize(1065, 680)
        d.exec()
        self.get_logon_accounts()

    def add_account_senior(self):
        d = SeniorLoginDialog()
        d.exec()
        self.get_logon_accounts()

    def clear_account_list(self):
        if QMessageBox.warning(self, '警告', '确认要清空本地的所有登录信息吗？这会导致所有用户退出登录。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            # 写入登录信息
            account_list = load_json_secret(f'{datapath}/user_bduss')
            account_list['current_bduss'] = ''
            account_list['login_list'] = []
            save_json_secret(account_list, f'{datapath}/user_bduss')
            shutil.rmtree(f'{datapath}/webview_data')
            os.mkdir(f'{datapath}/webview_data')
            mainw.refresh_all_datas()  # 更新主页面信息
            self.get_logon_accounts()
            QMessageBox.information(self, '提示', '登录信息清空成功。', QMessageBox.Ok)

    def switch_account(self, bduss="", name=""):
        if not bduss:
            bduss = self.listWidget_2.currentItem().bduss
        if not name:
            name = self.listWidget_2.itemWidget(self.listWidget_2.currentItem()).label_2.text()
        if bduss != self.current_a:
            if QMessageBox.information(self, '提示',
                                       f'确认要切换到账号 {name} 吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                # 写入登录信息
                account_list = load_json_secret(f'{datapath}/user_bduss')
                account_list['current_bduss'] = bduss
                save_json_secret(account_list, f'{datapath}/user_bduss')
                mainw.refresh_all_datas()  # 更新主页面信息
                self.get_logon_accounts()
                QMessageBox.information(self, '提示', '账号切换成功。', QMessageBox.Ok)

    def delete_account(self, bduss="", name=""):
        if not bduss:
            bduss = self.listWidget_2.currentItem().bduss
        if not name:
            name = self.listWidget_2.itemWidget(self.listWidget_2.currentItem()).label_2.text()
        if QMessageBox.information(self, '提示',
                                   f'确认要删除账号 {name} 的登录信息吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            account_list = load_json_secret(f'{datapath}/user_bduss')
            for i in tuple(account_list['login_list']):
                if i['bduss'] == bduss:
                    shutil.rmtree(f'{datapath}/webview_data/{i["uid"]}')
                    account_list['login_list'].remove(i)  # 删掉登录信息
                    break
            if account_list['current_bduss'] == bduss:
                # 如果要删除的账号是当前登录的，取消登录状态
                account_list['current_bduss'] = ''
            save_json_secret(account_list, f'{datapath}/user_bduss')
            mainw.refresh_all_datas()  # 更新主页面信息
            self.get_logon_accounts()
            QMessageBox.information(self, '提示', '账号信息删除成功。', QMessageBox.Ok)

    def load_local_config(self):
        self.checkBox.setChecked(profile_mgr.local_config['thread_view_settings']['hide_video'])
        self.checkBox_2.setChecked(profile_mgr.local_config['thread_view_settings']['hide_ip'])
        (self.radioButton if profile_mgr.local_config['thread_view_settings'][
                                 'tb_emoticon_size'] == 0 else self.radioButton_2).setChecked(True)
        self.comboBox.setCurrentIndex(profile_mgr.local_config['thread_view_settings']['default_sort'])
        self.comboBox_2.setCurrentIndex(profile_mgr.local_config['forum_view_settings']['default_sort'])
        self.checkBox_3.setChecked(profile_mgr.local_config['thread_view_settings']['enable_lz_only'])

    def get_logon_accounts(self):
        # 清空数据
        self.listWidget_2.clear()
        QPixmapCache.clear()
        gc.collect()

        # 加载列表
        account_list = load_json_secret(f'{datapath}/user_bduss')
        self.current_a = account_list['current_bduss']
        for i in account_list['login_list']:
            item = ExtListWidgetItem(i['bduss'], i['stoken'])
            item.user_portrait_id = i['portrait']
            widget = UserItem(i['bduss'], i['stoken'])
            widget.switchRequested.connect(lambda d: self.switch_account(d[0], d[1]))
            widget.deleteRequested.connect(lambda d: self.delete_account(d[0], d[1]))
            widget.doubleClicked.connect(self.switch_account)
            widget.user_portrait_id = i['portrait']
            widget.setdatas(i['portrait'], i['name'], i.get('uid', -1), True,
                            is_current_user=self.current_a == i['bduss'])
            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)

    def get_log_size(self):
        lc = 0  # 文件个数
        lsc = 0  # 文件总大小
        for i in os.listdir(f'{datapath}/logs'):
            lc += 1
            lsc += os.stat(f'{datapath}/logs/{i}').st_size
        self.label_3.setText(
            f'日志文件可用于诊断程序问题。\n你的电脑上共有 {lc} 份日志文件，总计大小 {filesize_tostr(lsc)}。\n你可以查看它们，或是全部删除。')

    def get_pic_size(self):
        lsc = 0  # 文件总大小
        for i in os.listdir(f'{datapath}/image_caches'):
            lsc += os.stat(f'{datapath}/image_caches/{i}').st_size
        self.label_12.setText(
            f'包括缓存到本地的帖子图片、用户头像图片等。\n总计已占用大小 {filesize_tostr(lsc)}。')

    def clear_logs(self):
        if QMessageBox.warning(self, '警告', '确认要清理日志文件吗？',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for i in os.listdir(f'{datapath}/logs'):
                try:
                    os.remove(f'{datapath}/logs/{i}')
                except PermissionError:
                    continue
            QMessageBox.information(self, '提示', '文件清理成功。', QMessageBox.Ok)
            self.get_log_size()

    def clear_pics(self):
        if QMessageBox.warning(self, '警告', '确认要清理图片缓存吗？',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for i in os.listdir(f'{datapath}/image_caches'):
                try:
                    os.remove(f'{datapath}/image_caches/{i}')
                except PermissionError:
                    continue
            cache_mgr.portrait_cache_dict = {}
            cache_mgr.save_portrait_pf()
            QMessageBox.information(self, '提示', '图片缓存清理成功。', QMessageBox.Ok)
            self.get_pic_size()


class SeniorLoginDialog(QDialog, login_by_bduss.Ui_Dialog):
    """高级登录对话框"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton_2.clicked.connect(self.close)
        self.pushButton.clicked.connect(self.save_account_info)

    def save_account_info(self):
        async def get_self_info(bduss, stoken):
            try:
                async with aiotieba.Client(bduss, stoken, proxy=True) as client:
                    user_info = await client.get_self_info()
                    return user_info.portrait, user_info.nick_name_new, user_info.user_id
            except:
                return '', '', 0

        bduss = self.lineEdit.text()
        stoken = self.lineEdit_2.text()
        if bduss and stoken:
            # 获取用户信息
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            portrait, name, uid = asyncio.run(get_self_info(bduss, stoken))

            if not (portrait and name and uid):
                QMessageBox.critical(self, '登录失败',
                                     '无法通过你提供的 BDUSS 和 STOKEN 获取用户信息。你的 BDUSS 或 STOKEN 可能失效了，或者你输入的内容不正确。',
                                     QMessageBox.Ok)
            else:
                pf = load_json_secret(f'{datapath}/user_bduss')

                if not pf['login_list']:  # 在没有账号登上去的情况下，把这个账号设置为当前账号
                    pf['current_bduss'] = bduss
                else:
                    # 找一下有没有旧的登录信息，有就删除
                    for i in tuple(pf['login_list']):
                        if i['portrait'] == portrait:
                            # 如果旧信息是当前账号，把当前账号也更新一次
                            if pf['current_bduss'] == i['bduss']:
                                pf['current_bduss'] = bduss
                            pf['login_list'].remove(i)
                            QMessageBox.information(self, '提示',
                                                    '检测到本地已有该账号的登录信息，已使用本次的登录信息替换了旧的登录信息。',
                                                    QMessageBox.Ok)
                            break
                # 添加新的登录信息
                pf['login_list'].append(
                    {'bduss': bduss, 'stoken': stoken, 'portrait': portrait, 'name': name, 'uid': uid})

                save_json_secret(pf, f'{datapath}/user_bduss')
                mainw.refresh_all_datas()  # 更新主页面信息
                if os.path.isdir(f'{datapath}/webview_data/{self.uid}'):  # 把旧的数据删掉
                    shutil.rmtree(f'{datapath}/webview_data/{self.uid}')
                os.mkdir(f'{datapath}/webview_data/{profile_mgr.current_uid}')

                QMessageBox.information(self, '登录成功', f'账号 {name} 已经登录成功，登录信息已保存至本地。',
                                        QMessageBox.Ok)
                self.close()
        else:
            QMessageBox.critical(self, '填写错误',
                                 '请正确填写 BDUSS 和 STOKEN 后再尝试登录。',
                                 QMessageBox.Ok)


class LoginWebView(QDialog):
    """登录百度账号的webview，用户在网页执行登陆操作，webview后台抓取bduss等登录信息"""
    islogin = False
    closeSignal = pyqtSignal()
    need_restart = False

    def __init__(self):
        super().__init__()
        self.setStyleSheet('QDialog{background-color:white;}QWidget{font-family: \"微软雅黑\";}')
        self.setWindowTitle('登录贴吧账号')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.closeSignal.connect(self.close)
        self.init_flash_widget()

        webview2.loadLibs()
        self.webview = webview2.QWebView2View()
        self.webview.setParent(self)
        self.webview.tokenGot.connect(self.start_login)
        self.profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/default',
                                               enable_link_hover_text=False,
                                               enable_zoom_factor=False, enable_error_page=False,
                                               enable_context_menu=False, enable_keyboard_keys=False,
                                               handle_newtab_byuser=False)
        self.webview.setProfile(self.profile)
        self.webview.loadAfterRender('https://passport.baidu.com/v2/?login&u=https%3A%2F%2Ftieba.baidu.com')
        self.webview.initRender()

    def closeEvent(self, a0):
        if not self.islogin:
            if QMessageBox.information(self, '提示', '你确实要中止登录流程吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.webview.destroyWebview()
                a0.accept()
            else:
                a0.ignore()
        else:
            if self.need_restart:
                QMessageBox.information(self, '提示',
                                        '账号已登录成功，为保证本地数据完全加载，你需要重启本软件。点击确定键关闭本软件，软件将在下次重新打开时自动应用你的设置。',
                                        QMessageBox.Ok)
                sys.exit(0)
            mainw.refresh_all_datas()  # 更新主页面信息
            self.flash_widget.hide()
            a0.accept()

    def resizeEvent(self, a0):
        self.webview.setGeometry(0, 0, self.width(), self.height())
        self.flash_widget.sync_parent_widget_size()

    def init_flash_widget(self):
        self.flash_widget = LoadingFlashWidget(caption='登录成功，即将跳转...')
        self.flash_widget.cover_widget(self, enable_filler=False)
        self.flash_widget.hide()

    def start_login(self, infos):
        self.webview.hide()
        self.flash_widget.show()
        start_background_thread(self.do_login, (infos,))

    def do_login(self, infos):
        async def get_self_info(bduss, stoken):
            try:
                async with aiotieba.Client(bduss, stoken, proxy=True) as client:
                    user_info = await client.get_self_info()
                    return user_info.portrait, user_info.nick_name_new, user_info.user_id
            except:
                return '', '', 0

        self.webview.destroyWebview()  # 先销毁webview
        time.sleep(5)

        # 获取用户信息
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        portrait, name, uid = asyncio.run(get_self_info(infos['BDUSS'], infos['STOKEN']))

        pf = load_json_secret(f'{datapath}/user_bduss')  # 加载配置文件

        if not pf['login_list']:  # 在没有账号登上去的情况下，把这个账号设置为当前账号
            pf['current_bduss'] = infos['BDUSS']
        else:
            # 找一下有没有旧的登录信息，有就删除
            for i in tuple(pf['login_list']):
                if i['portrait'] == portrait:
                    # 如果旧信息是当前账号，把当前账号也更新一次
                    if pf['current_bduss'] == i['bduss']:
                        pf['current_bduss'] = infos['BDUSS']
                    pf['login_list'].remove(i)
                    break
        # 添加新的登录信息
        pf['login_list'].append(
            {'bduss': infos['BDUSS'], 'stoken': infos['STOKEN'], 'portrait': portrait, 'name': name, 'uid': uid})
        save_json_secret(pf, f'{datapath}/user_bduss')  # 保存配置文件

        try:
            if os.path.isdir(f'{datapath}/webview_data/{uid}'):  # 把旧的数据删掉
                shutil.rmtree(f'{datapath}/webview_data/{uid}')
            os.rename(f'{datapath}/webview_data/default', f'{datapath}/webview_data/{uid}')
            os.mkdir(f'{datapath}/webview_data/default')
        except PermissionError:
            self.need_restart = True
            save_json({'uid': str(uid)}, f'{datapath}/d2id_flag')

        self.islogin = True
        self.closeSignal.emit()


class MainWindow(QMainWindow, mainwindow.Ui_MainWindow):
    """主窗口，整个程序的入口点"""
    user_data = {'bduss': '', 'stoken': ''}
    self_user_portrait = ''
    add_info = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton.setIcon(QIcon('ui/more.png'))
        self.pushButton.setStyleSheet("QPushButton::menu-indicator{image:none;}")

        self.pushButton_3.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.pushButton_4.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(2))
        self.pushButton_2.clicked.connect(self.refresh_recommand)
        self.pushButton_5.clicked.connect(self.open_search_window)
        self.add_info.connect(self._add_uinfo)

        self.handle_d2id_flag()
        self.init_profile_menu()
        self.init_pages()
        self.refresh_all_datas()

    def closeEvent(self, a0):
        if QMessageBox.information(self, '提示', '确认要退出软件吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            a0.accept()
            app.closeAllWindows()
            app.quit()
        else:
            a0.ignore()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_F5 and self.stackedWidget.currentIndex() == 0:
            self.refresh_recommand()

    def refresh_recommand(self):
        if self.stackedWidget.currentIndex() == 0:
            if not self.recommend.isloading:
                # 初始化计时器
                self.text_timer = QTimer(self)
                self.text_timer.setSingleShot(True)
                self.text_timer.setInterval(1600)
                self.text_timer.timeout.connect(lambda: self.pushButton_2.setText('推荐'))

                # 清理内存
                self.recommend.clear()
                QPixmapCache.clear()
                gc.collect()

                # 启动刷新
                self.recommend.get_recommand_async()
                self.pushButton_2.setText('刷新中...')
                self.text_timer.start()
        else:
            self.stackedWidget.setCurrentIndex(0)

    def refresh_all_datas(self):
        # 清理内存
        qt_window_mgr.clear_windows()
        self.recommend.clear()
        QPixmapCache.clear()
        gc.collect()

        self.init_user_data()
        self.set_profile_menu()
        self.recommend.bduss = self.user_data['bduss']
        self.recommend.stoken = self.user_data['stoken']
        self.flist.bduss = self.user_data['bduss']
        self.flist.stoken = self.user_data['stoken']
        self.interactionlist.bduss = self.user_data['bduss']
        self.interactionlist.stoken = self.user_data['stoken']
        self.flist.get_bars_async()
        self.recommend.get_recommand_async()
        self.interactionlist.refresh_list()

    def open_user_homepage(self, uid):
        user_home_page = UserHomeWindow(self.user_data['bduss'], self.user_data['stoken'], uid)
        qt_window_mgr.add_window(user_home_page)

    def open_star_window(self):
        user_stared_list = StaredThreadsList(self.user_data['bduss'], self.user_data['stoken'])
        qt_window_mgr.add_window(user_stared_list)

    def open_agreed_window(self):
        user_stared_list = AgreedThreadsList(self.user_data['bduss'], self.user_data['stoken'])
        qt_window_mgr.add_window(user_stared_list)

    def open_search_window(self):
        tb_search_window = TiebaSearchWindow(self.user_data['bduss'], self.user_data['stoken'])
        qt_window_mgr.add_window(tb_search_window)

    def init_pages(self):
        self.recommend = RecommandWindow(self.user_data['bduss'], self.user_data['stoken'])
        self.stackedWidget.addWidget(self.recommend)

        self.flist = FollowForumList(self.user_data['bduss'], self.user_data['stoken'])
        self.stackedWidget.addWidget(self.flist)

        self.interactionlist = UserInteractionsList(self.user_data['bduss'], self.user_data['stoken'])
        self.stackedWidget.addWidget(self.interactionlist)

        self.stackedWidget.setCurrentIndex(0)

    def open_settings_window(self):
        d = SettingsWindow()
        d.exec()

    def init_profile_menu(self):
        menu = QMenu()
        self.my_homepage = QAction('我的个人主页', self)
        self.my_homepage.triggered.connect(lambda: self.open_user_homepage(self.self_user_portrait))
        menu.addAction(self.my_homepage)

        self.my_favourite = QAction('我的收藏', self)
        self.my_favourite.triggered.connect(self.open_star_window)
        menu.addAction(self.my_favourite)

        self.my_agrees = QAction('我的点赞', self)
        self.my_agrees.triggered.connect(self.open_agreed_window)
        menu.addAction(self.my_agrees)

        menu.addSeparator()
        self.login = QAction('添加新账号', self)
        self.login.triggered.connect(self.login_exec)
        menu.addAction(self.login)

        self.exit_login_ac = QAction('退出当前账号', self)
        self.exit_login_ac.triggered.connect(self.exit_login)
        menu.addAction(self.exit_login_ac)

        menu.addSeparator()
        self.setting = QAction('设置', self)
        self.setting.triggered.connect(self.open_settings_window)
        menu.addAction(self.setting)

        self.pushButton.setMenu(menu)

    def set_profile_menu(self):
        if self.user_data['bduss']:
            self.my_homepage.setVisible(True)
            self.my_agrees.setVisible(True)
            self.my_favourite.setVisible(True)
            self.exit_login_ac.setVisible(True)
            self.login.setVisible(False)
        else:
            self.my_homepage.setVisible(False)
            self.my_agrees.setVisible(False)
            self.my_favourite.setVisible(False)
            self.exit_login_ac.setVisible(False)
            self.login.setVisible(True)

    def exit_login(self):
        if QMessageBox.warning(self, '警告',
                               '确认要退出当前账号吗？\n如果本机没有登录其他账号，那么你将会切换到游客模式下；\n如果你登录了其他账号，那么你将会被切换到下一个账号。',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            pf = load_json_secret(f'{datapath}/user_bduss')
            for i in tuple(pf['login_list']):
                if i['bduss'] == pf['current_bduss']:
                    pf['login_list'].remove(i)
                    break
            pf['current_bduss'] = ''

            save_json_secret(pf, f'{datapath}/user_bduss')
            shutil.rmtree(f'{datapath}/webview_data/{profile_mgr.current_uid}')
            self.refresh_all_datas()

    def login_exec(self):
        d = LoginWebView()
        d.resize(1065, 680)
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
            except:
                QMessageBox.critical(self, '错误', '用户数据应用失败！', QMessageBox.Ok)
            else:
                save_json({'uid': ''}, f'{datapath}/d2id_flag')

    def _add_uinfo(self, datas):
        if not datas:
            QMessageBox.critical(self, '错误', '用户信息加载失败！', QMessageBox.Ok)
        else:
            if datas[0]:
                self.label_9.setPixmap(datas[0])
            if datas[1]:
                self.label_10.setText(datas[1])

    def init_user_data_async(self):
        start_background_thread(self.init_user_data)

    def load_user_portrait(self):
        pixmap = QPixmap()
        pixmap.loadFromData(cache_mgr.get_portrait(self.self_user_portrait))
        pixmap = pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.add_info.emit([pixmap, ''])

    def init_user_data(self):
        try:
            # {'bduss': , 'stoken': , 'portrait':,'name': }
            self.user_data = {'bduss': '', 'stoken': ''}
            real_user_data = load_json_secret(f'{datapath}/user_bduss')
            if not real_user_data['current_bduss'] and real_user_data['login_list']:  # 没选账号但是有已登录用户
                # 把当前用户设置成第一个
                self.user_data = real_user_data['login_list'][0]
                real_user_data['current_bduss'] = real_user_data['login_list'][0]['bduss']
                save_json_secret(real_user_data, f'{datapath}/user_bduss')
            elif real_user_data['current_bduss'] and real_user_data['login_list']:  # 有选账号且有已登录用户
                # 找到这个用户
                for i in real_user_data['login_list']:
                    if i['bduss'] == real_user_data['current_bduss']:
                        self.user_data = i
                        break

            if not self.user_data['bduss']:
                pixmap = QPixmap('ui/default_user_image.png')
                pixmap = pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.add_info.emit([pixmap, '未登录'])
            else:
                # 获取用户信息
                profile_mgr.current_uid = self.user_data['uid']
                name = self.user_data['name']
                self.self_user_portrait = self.user_data['portrait']

                start_background_thread(self.load_user_portrait)
                self.add_info.emit([None, name])
        except Exception as e:
            self.add_info.emit([])


if __name__ == "__main__":
    sys.excepthook = excepthook

    create_data()
    init_log()
    proxytool.set_proxy()
    profile_mgr.init_all_datas()
    cache_mgr.init_all_datas()
    handle_command_events()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    translates = set_qt_languages()
    aiotieba.logging.get_logger().info('Qt init complete')
    check_webview2()

    aiotieba.logging.get_logger().info('Initing main window')
    mainw = MainWindow()
    mainw.show()
    aiotieba.logging.get_logger().info('Mainwindow showed, into the main loop')

    sys.exit(app.exec())
