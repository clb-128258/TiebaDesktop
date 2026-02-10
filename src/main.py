"""程序入口点，包含了整个程序最基本的函数和类"""
import typing

from core_features import *


def excepthook(type, value, traceback):
    """捕获并打印错误"""
    if type != SystemExit:
        log_exception(value)
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
                app_logger.log_INFO(f'Qt language file {i} loaded')
                translators.append(translator)
        return translators


def check_webview2():
    """检查用户的电脑是否安装了webview2"""
    app_logger.log_INFO(f'Checking webview2')

    webview2.loadLibs()
    if not webview2.isWebView2Installed():
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
            app_logger.log_INFO(f'UserDataPath is reset by --reset-udf.')
        else:
            logging.log_INFO(f'{udf} is not a valid folder, please create it first.')
        app_logger.log_INFO(f'Now UserDataPath is {consts.datapath}.')


def handle_command_events():
    """处理命令行参数，与命令行参数有关的代码均在此执行"""
    cmds = sys.argv
    dont_run_gui = False
    app_logger.log_INFO('Handling command args')

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
                    err_msg += f'\n成长等级签到：{r1.err}'
                if not r2:
                    err_msg += f'\n成长等级分享任务：{r2.err}'
            msgbox(err_msg)

    async def sign_all():
        bduss, stoken = get_current_user()
        if not bduss:
            msgbox('请先登录账号再签到。')
            return
        signed_count = 0

        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            await client.sign_forums()  # 先一键签到

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
        app_logger.log_INFO('--set-current-account started')
        start_async(switch_account())
    else:
        if '--sign-all-forums' in cmds:
            dont_run_gui = True
            app_logger.log_INFO('--sign-all-forums started')
            start_async(sign_all())
        if '--sign-grows' in cmds:
            dont_run_gui = True
            app_logger.log_INFO('--sign-grows started')
            start_async(sign_grow())
    if dont_run_gui:
        sys.exit(0)


class SettingsWindow(QDialog, settings.Ui_Dialog):
    """设置窗口"""
    scanFinish = pyqtSignal(dict)
    clearFinish = pyqtSignal(bool)
    scannedDetailData = {}

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label_6.setPixmap(QPixmap('ui/tieba_logo_small.png'))
        self.groupBox_3.hide()
        self.init_top_toaster()
        self.init_load_animation()
        self.set_debug_info()
        self.get_logon_accounts()
        self.load_local_config()

        self.init_login_button_menu()
        self.listWidget.currentRowChanged.connect(self.stackedWidget.setCurrentIndex)
        self.pushButton_3.clicked.connect(lambda: open_url_in_browser(f'{datapath}/logs'))
        self.pushButton.clicked.connect(self.clear_account_list)
        self.pushButton_5.clicked.connect(self.save_local_config)
        self.pushButton_11.clicked.connect(lambda: QMessageBox.aboutQt(self, '关于 Qt'))
        self.pushButton_10.clicked.connect(lambda: open_url_in_browser(datapath))
        self.pushButton_12.clicked.connect(self.scan_use_detail_async)
        self.pushButton_4.clicked.connect(self.clear_caches_async)
        self.pushButton_6.clicked.connect(self.open_proxy_settings)
        self.pushButton_7.clicked.connect(self.select_all_caches)
        self.scanFinish.connect(self._set_use_detail_ui)
        self.clearFinish.connect(self._on_caches_cleared)

        self.clearTypeCb = [self.checkBox_4,
                            self.checkBox_5,
                            self.checkBox_9,
                            self.checkBox_10,
                            self.checkBox_7,
                            self.checkBox_6,
                            self.checkBox_18,
                            self.checkBox_19
                            ]
        for i in self.clearTypeCb:
            i.stateChanged.connect(self.calc_willfree_size)

    def closeEvent(self, a0):
        self.listWidget_2.clear()
        QPixmapCache.clear()
        gc.collect()
        a0.accept()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def init_load_animation(self):
        self.load_animation = LoadingFlashWidget()
        self.load_animation.cover_widget(self.groupBox_3)
        self.load_animation.hide()

    def init_login_button_menu(self):
        menu = QMenu()

        webview_login = QAction('网页登录 (推荐)', self)
        webview_login.triggered.connect(self.add_account)
        menu.addAction(webview_login)

        qr_login = QAction('扫码登录', self)
        qr_login.triggered.connect(self.add_account_qrcode)
        menu.addAction(qr_login)

        bduss_directly_login = QAction('高级登录', self)
        bduss_directly_login.triggered.connect(self.add_account_senior)
        menu.addAction(bduss_directly_login)

        self.pushButton_2.setMenu(menu)

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
            profile_mgr.local_config['other_settings']['show_msgbox_before_close'] = self.checkBox_16.isChecked()

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
            profile_mgr.save_local_config()
        except KeyError:
            profile_mgr.fix_local_config()
            self.save_local_config()
        except Exception as e:
            app_logger.log_exception(e)
            toast = top_toast_widget.ToastMessage('设置保存失败，请重试', icon_type=top_toast_widget.ToastIconType.ERROR)
            self.top_toaster.showToast(toast)
        else:
            toast = top_toast_widget.ToastMessage('设置保存成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.top_toaster.showToast(toast)

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
        self.label_8.setText(f'版本 {consts.APP_VERSION_STR}')
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
        self.get_logon_accounts()

    def add_account_qrcode(self):
        d = QRLoginDialog()
        d.exec()
        self.get_logon_accounts()

    def add_account_senior(self):
        d = SeniorLoginDialog()
        d.exec()
        self.get_logon_accounts()

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
                profile_mgr.post_drafts = {}
                profile_mgr.save_post_drafts()
            if self.checkBox_19.isChecked():
                profile_mgr.view_history = []
                profile_mgr.save_view_history()
            if self.checkBox_7.isChecked():
                webview_obj.clearCacheData()
                time.sleep(4)
            if self.checkBox_6.isChecked():
                webview_obj.clearCookies()
                time.sleep(4)

            webview_obj.destroyWebviewUntilComplete()
        except Exception as e:
            app_logger.log_exception(e)
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
                'history_size': 0}

        lsc_log = scan_tree_total_size(f'{datapath}/logs')  # 日志文件总大小
        lsc_img = scan_tree_total_size(f'{datapath}/image_caches')  # 图片缓存文件总大小
        data['image_cache_size'] = lsc_img
        data['log_size'] = lsc_log

        main_pf_exclude = ['view_history', 'post_drafts']  # 排除特定文件
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
        data['post_draft_num'] = len(profile_mgr.post_drafts)
        data['history_size'] = os.stat(f'{datapath}/view_history').st_size
        data['history_num'] = len(profile_mgr.view_history)

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
            # 写入登录信息
            account_list = load_json_secret(f'{datapath}/user_bduss')
            account_list['current_bduss'] = ''
            account_list['login_list'] = []
            save_json_secret(account_list, f'{datapath}/user_bduss')
            shutil.rmtree(f'{datapath}/webview_data')
            os.mkdir(f'{datapath}/webview_data')
            mainw.refresh_all_datas()  # 更新主页面信息
            self.get_logon_accounts()
            toast = top_toast_widget.ToastMessage('登录信息清空成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.top_toaster.showToast(toast)

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

                toast = top_toast_widget.ToastMessage(f'已切换到账号 {name}',
                                                      icon_type=top_toast_widget.ToastIconType.SUCCESS)
                self.top_toaster.showToast(toast)

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

            toast = top_toast_widget.ToastMessage(f'账号信息删除成功',
                                                  icon_type=top_toast_widget.ToastIconType.SUCCESS)
            self.top_toaster.showToast(toast)

    def load_local_config(self):
        try:
            self.checkBox.setChecked(profile_mgr.local_config['thread_view_settings']['hide_video'])
            self.checkBox_2.setChecked(profile_mgr.local_config['thread_view_settings']['hide_ip'])
            self.checkBox_12.setChecked(profile_mgr.local_config['thread_view_settings']['play_gif'])
            self.checkBox_13.setChecked(profile_mgr.local_config["notify_settings"]["enable_interact_notify"])
            (self.radioButton if profile_mgr.local_config['thread_view_settings'][
                                     'tb_emoticon_size'] == 0 else self.radioButton_2).setChecked(True)
            self.comboBox.setCurrentIndex(profile_mgr.local_config['thread_view_settings']['default_sort'])
            self.comboBox_2.setCurrentIndex(profile_mgr.local_config['forum_view_settings']['default_sort'])
            self.checkBox_3.setChecked(profile_mgr.local_config['thread_view_settings']['enable_lz_only'])
            self.checkBox_16.setChecked(profile_mgr.local_config['other_settings']['show_msgbox_before_close'])
            self.checkBox_17.setChecked(profile_mgr.local_config["notify_settings"]["offline_notify"])

            rdbtn_index = [self.radioButton_3, self.radioButton_4, self.radioButton_5]
            port = profile_mgr.local_config['proxy_settings']['custom_proxy_server']['port']
            rdbtn_index[profile_mgr.local_config['proxy_settings']['proxy_switch']].setChecked(True)
            self.lineEdit.setText(profile_mgr.local_config['proxy_settings']['custom_proxy_server']['ip'])
            self.lineEdit_2.setText(str(port) if port != -1 else '')
            self.checkBox_14.setChecked(profile_mgr.local_config['proxy_settings']['enabled_scheme']['http'])
            self.checkBox_15.setChecked(profile_mgr.local_config['proxy_settings']['enabled_scheme']['https'])
        except KeyError:
            if QMessageBox.critical(self, '本地设置加载失败',
                                    '本地存储的设置文件缺少某些关键字段，设置项无法被加载。\n'
                                    '一些设置项不会被正确显示。\n'
                                    '将设置文件恢复到默认状态可解决该问题，是否要重置为默认设置？\n\n'
                                    '注意：如果你最近更新了本软件，那么本问题是因为旧版本的配置文件没有新版本所需的字段所导致的。'
                                    '此时请点击“否”按钮，并在“通用设置”中保存设置即可使配置文件恢复正常。',
                                    QMessageBox.No | QMessageBox.Yes) == QMessageBox.Yes:
                profile_mgr.fix_local_config()
                self.load_local_config()

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

        account_num = len(account_list['login_list'])
        if not account_num:
            self.listWidget_2.hide()
            self.label.setText('你目前还没有登录任何账号，点击右侧的“添加账号”可立即登录新账号。')
        else:
            self.listWidget_2.show()
            self.label.setText(f'你目前已登录 {account_num} 个账号。')


class QRLoginDialog(QDialog, qr_login.Ui_Dialog):
    """扫码登录对话框"""
    BAIDU_PASSPORT_HOST = 'passport.baidu.com'
    qr_code_loaded = pyqtSignal(dict)
    qr_status_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.toolButton.setIcon(QIcon('ui/refresh.png'))

        self.qr_sign = ''
        self.tangram_guid = ''
        self.is_qr_loading = False
        self.is_window_using = True
        self.is_login_succeed = False
        self.session = requests.Session()
        self.session.trust_env = True

        self.loading_widget = LoadingFlashWidget(caption='二维码加载中...')
        self.loading_widget.cover_widget(self.label_3)
        self.loading_widget.hide()
        self.qr_code_image = qt_image.MultipleImage()
        self.qr_code_image.currentPixmapChanged.connect(self.label_3.setPixmap)
        self.qr_code_image.imageLoadSucceed.connect(lambda: self.on_qrimg_loaded(True))
        self.qr_code_image.imageLoadFailed.connect(lambda: self.on_qrimg_loaded(False))

        self.qr_code_loaded.connect(self.load_qrcode_img)
        self.qr_status_changed.connect(self.on_login_state_changed)
        self.toolButton.clicked.connect(self.get_new_qr_code_async)

        self.start_looper()
        self.get_new_qr_code_async()

    def closeEvent(self, a0):
        def do_close():
            self.is_window_using = False
            self.session.close()
            a0.accept()

        if self.is_login_succeed:
            do_close()
        else:
            if QMessageBox.information(self,
                                       '提示',
                                       '你确实要中止登录流程吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                do_close()
            else:
                a0.ignore()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def parse_response(self, text):
        text = text.replace(f'{self.tangram_guid}(', '')[0:-1]
        if text.endswith(')'):
            text = text[0:-1]
        return text

    def parse_response_qrbdusslogin(self, text):
        final_text = text.replace(f'bd__cbs__iou0dl(', '')[0:-1].replace(' ', '').replace(r'\&', '').replace('\'', '\"')
        return final_text

    def on_login_state_changed(self, data):
        if data['type'] == 1:
            self.label_3.setText('二维码已过期，请重新加载')
        elif data['type'] == 2:
            self.label_3.setText('扫码成功，请在手机上确认')
        elif data['type'] == 3:
            self.label_3.setText('你已取消扫码，二维码已失效，请重新加载')
        elif data['type'] == 4:
            self.label_3.setText('百度服务器要求短信验证，请使用网页登录')
        elif data['type'] == 5:
            QMessageBox.information(self, '登录成功',
                                    f'你已成功登录账号 {data["user"]}。\n可以在 设置-账号管理 中找到你的账号。',
                                    QMessageBox.Ok)
            mainw.refresh_all_datas()  # 更新主页面信息
            self.close()

    def get_bduss_by_token(self, token):
        header = {
            'User-Agent': request_mgr.header['User-Agent'],
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'sec-ch-ua-platform': "\"Windows\"",
            'sec-ch-ua': "\"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
            'sec-ch-ua-mobile': "?0",
            'Sec-Fetch-Site': "same-site",
            'Sec-Fetch-Mode': "no-cors",
            'Sec-Fetch-Dest': "script",
            'Referer': "https://tieba.baidu.com/",
            'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Connection": "keep-alive",
        }

        timestamp = time.time()
        timestamp_second = int(timestamp)
        timestamp_ms = int(timestamp * 1000)
        params = {
            "v": str(timestamp_ms),
            "bduss": token,
            "u": "",
            "loginVersion": "v5",
            "qrcode": "1",
            "tpl": "tb",
            "maskId": "",
            "fileId": "",
            "apiver": "v3",
            "tt": str(timestamp_ms),
            "traceid": "",
            "time": str(timestamp_second),
            "alg": "v3",
            "elapsed": "10",
            "callback": "bd__cbs__iou0dl"
        }

        response = self.session.get(f'{request_mgr.SCHEME_HTTPS}{self.BAIDU_PASSPORT_HOST}/v3/login/main/qrbdusslogin',
                                    headers=header, params=params)
        response.raise_for_status()
        json_text = self.parse_response_qrbdusslogin(response.text)
        jsonify_data = json.loads(json_text)
        response.close()

        return jsonify_data

    def handle_qr_status(self, resp):
        """处理扫码轮询逻辑"""
        if resp['errno'] == 1:
            # 没扫码，不操作
            pass
        elif resp['errno'] == 0:
            channel_v = resp['channel_v']
            channel_v_json = json.loads(channel_v)
            if channel_v_json['status'] == 1:
                # 已经扫码，等待手机确认
                self.qr_status_changed.emit({'type': 2})
            elif channel_v_json['status'] == 2:
                # 用户取消扫码登录
                self.qr_status_changed.emit({'type': 3})
            elif channel_v_json['status'] == 0:
                # 用户点击确定登录，登录成功
                login_token = channel_v_json['v']
                login_data = self.get_bduss_by_token(login_token)
                if int(login_data['data']['session']['needvcode']):
                    # 需要验证码
                    self.qr_status_changed.emit({'type': 4})
                else:
                    # 正常上号
                    bduss = login_data['data']['session']['bduss']
                    stoken = login_data['data']['session']['stoken']
                    result = self.write_user_info(bduss, stoken)
                    if result:
                        self.is_login_succeed = True
                        self.qr_status_changed.emit({'type': 5, 'user': result})
                    else:
                        self.qr_status_changed.emit({'type': 6})
        else:
            raise Exception(f'errno is {resp["errno"]}')

    def query_qr_status(self):
        header = {
            'User-Agent': request_mgr.header['User-Agent'],
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'sec-ch-ua-platform': "\"Windows\"",
            'sec-ch-ua': "\"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
            'sec-ch-ua-mobile': "?0",
            'Sec-Fetch-Site': "same-site",
            'Sec-Fetch-Mode': "no-cors",
            'Sec-Fetch-Dest': "script",
            'Referer': "https://tieba.baidu.com/",
            'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Connection": "keep-alive",
        }

        timestamp = time.time()
        timestamp_ms = int(timestamp * 1000)
        params = {
            "channel_id": self.qr_sign,
            "tpl": "tb",
            "_sdkFrom": "1",
            "callback": self.tangram_guid,
            "apiver": "v3",
            "tt": str(timestamp_ms),
            '_': str(timestamp_ms),
        }

        response = self.session.get(f'{request_mgr.SCHEME_HTTPS}{self.BAIDU_PASSPORT_HOST}/channel/unicast',
                                    headers=header, params=params)
        response.raise_for_status()
        json_text = self.parse_response(response.text)
        jsonify_data = json.loads(json_text)
        response.close()

        return jsonify_data

    def write_user_info(self, bduss, stoken):
        """向本地写入登录信息"""

        async def get_self_info(bduss, stoken):
            try:
                async with aiotieba.Client(bduss, stoken, proxy=True) as client:
                    user_info = await client.get_self_info()
                    return user_info.portrait, user_info.nick_name_new, user_info.user_id
            except:
                return '', '', 0

        try:
            # 获取用户信息
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            portrait, name, uid = asyncio.run(get_self_info(bduss, stoken))

            if (portrait and name and uid):
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
                            break
                # 添加新的登录信息
                pf['login_list'].append(
                    {'bduss': bduss, 'stoken': stoken, 'portrait': portrait, 'name': name,
                     'uid': uid})

                save_json_secret(pf, f'{datapath}/user_bduss')
                if os.path.isdir(f'{datapath}/webview_data/{uid}'):  # 把旧的数据删掉
                    shutil.rmtree(f'{datapath}/webview_data/{uid}')
                os.mkdir(f'{datapath}/webview_data/{uid}')

                return f'{name} (用户 ID: {uid})'
            else:
                raise Exception('user info is null')
        except Exception as e:
            app_logger.log_exception(e)
            return ''

    def start_looper(self):
        self.loop_thread = start_background_thread(self.status_looper)

    def status_looper(self):
        """二维码状态轮询器"""
        loop_count = 0
        current_sign = self.qr_sign

        while self.is_window_using:
            if current_sign != self.qr_sign:
                # 在二维码发生更改时，重新初始化数据
                loop_count = 0
                current_sign = self.qr_sign
                app_logger.log_INFO(f'looping qr code {current_sign}')
            elif self.is_qr_loading or not current_sign:
                # 二维码在加载或没有初始化时不操作
                pass
            else:
                if loop_count >= 20:
                    # 在循环次数到上限时，通知二维码过期，重新初始化数据
                    self.qr_status_changed.emit({'type': 1})
                    loop_count = 0
                    current_sign = ''
                else:
                    # 执行轮询逻辑
                    try:
                        resp = self.query_qr_status()
                        app_logger.log_INFO(f'time of loop qr code {current_sign} ok, json data {resp}')
                        self.handle_qr_status(resp)
                    except Exception as e:
                        logging.log_exception(e)
                    else:
                        loop_count += 1

            time.sleep(1)  # 休眠
        else:
            app_logger.log_INFO(f'qr code loop thread will exit')

    def on_qrimg_loaded(self, success):
        if not success:
            self.label_3.setText('二维码图片加载失败')
        self.loading_widget.hide()
        self.is_qr_loading = False

    def load_qrcode_img(self, data):
        """已获取到token, 开始异步加载二维码图片"""
        if not data['success']:
            self.label_3.setText(data['info'])
            self.loading_widget.hide()
        else:
            self.qr_code_image.destroyImage()
            self.qr_code_image.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                            data['qr_code_url'])
            self.qr_code_image.loadImage()

    def get_new_qr_code_async(self):
        if not self.is_qr_loading:
            self.is_qr_loading = True
            self.loading_widget.show()
            start_background_thread(self.get_new_qr_code)

    def get_new_qr_code(self):
        emit_data = {'success': False, 'info': '', 'qr_code_url': ''}

        try:
            header = copy.deepcopy(request_mgr.header)
            del header['x-requested-with']
            header['Referer'] = 'https://tieba.baidu.com/'

            timestamp = time.time()
            timestamp_second = int(timestamp)
            timestamp_ms = int(timestamp * 1000)
            self.tangram_guid = f'tangram_guid_{timestamp_ms}'
            params = {
                "lp": "pc",
                "qrloginfrom": "pc",
                "apiver": "v3",
                "tt": str(timestamp_ms),
                "tpl": "tb",
                "logPage": f"traceId:pc_loginv5_{timestamp_second},logPage:loginv5",
                "callback": self.tangram_guid
            }

            response = self.session.get(f'{request_mgr.SCHEME_HTTPS}{self.BAIDU_PASSPORT_HOST}/v2/api/getqrcode',
                                        headers=header, params=params)
            response.raise_for_status()
            json_text = self.parse_response(response.text)
            jsonify_data = json.loads(json_text)
            response.close()

            if jsonify_data['errno'] != 0:
                raise ValueError(f'Response status code is {jsonify_data["errno"]}')
            else:
                emit_data['qr_code_url'] = request_mgr.SCHEME_HTTP + jsonify_data['imgurl']
                self.qr_sign = jsonify_data['sign']
        except Exception as e:
            logging.log_exception(e)
            emit_data['success'] = False
            emit_data['info'] = str(e)
            self.is_qr_loading = False
        else:
            emit_data['success'] = True
            emit_data['info'] = '获取成功'
        finally:
            self.qr_code_loaded.emit(emit_data)


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
                if os.path.isdir(f'{datapath}/webview_data/{uid}'):  # 把旧的数据删掉
                    shutil.rmtree(f'{datapath}/webview_data/{uid}')
                os.mkdir(f'{datapath}/webview_data/{uid}')

                QMessageBox.information(self, '登录成功', f'账号 {name} 已经登录成功，登录信息已保存至本地。',
                                        QMessageBox.Ok)
                self.close()
        else:
            QMessageBox.critical(self, '填写错误',
                                 '请正确填写 BDUSS 和 STOKEN 后再尝试登录。',
                                 QMessageBox.Ok)


class LoginWebView(QDialog):
    """登录百度账号的webview，用户在网页执行登陆操作，webview后台抓取bduss等登录信息"""

    class LoginRewriter(QObject, webview2.HttpDataRewriter):
        is_token_got = False
        tokenGot = pyqtSignal(dict)

        def onRequestCaught(self, url: str, method: str, header: typing.Dict[str, str],
                            content: typing.Optional[bytes]):
            if not self.is_token_got:
                tlist = [
                    'BDUSS',
                    'STOKEN']

                cookies_dic = self.parseCookieToDict(header['Cookie'])
                login_cookies = {}
                for k, v in cookies_dic.items():
                    if k in tlist:
                        login_cookies[k] = v

                if len(login_cookies.keys()) == len(tlist):
                    self.is_token_got = True
                    self.tokenGot.emit(login_cookies)

            return url, method, header, content

    islogin = False
    closeSignal = pyqtSignal()
    need_restart = False

    def __init__(self):
        super().__init__()
        self.setStyleSheet('QDialog{background-color:white;}QWidget{font-family: \"微软雅黑\";}')
        self.setWindowTitle('登录百度账号')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.closeSignal.connect(self.close)
        self.init_flash_widget()

        self.webview = webview2.QWebView2View()
        self.http_catcher = self.LoginRewriter()
        self.http_catcher.tokenGot.connect(self.start_login)
        self.webview.setParent(self)
        self.webview.newtabSignal.connect(self.open_in_current_page)
        self.profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/default',
                                               enable_link_hover_text=False,
                                               enable_zoom_factor=False, enable_error_page=False,
                                               enable_context_menu=False, enable_keyboard_keys=False,
                                               handle_newtab_byuser=True,
                                               http_rewriter={'*://tieba.baidu.com/*': self.http_catcher})
        self.webview.setProfile(self.profile)
        self.webview.loadAfterRender('https://passport.baidu.com/v2/?login&u=https%3A%2F%2Ftieba.baidu.com')
        self.webview.initRender()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def closeEvent(self, a0):
        if not self.islogin:
            if QMessageBox.information(self, '提示', '你确实要中止登录流程吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.webview.destroyWebviewUntilComplete()
                a0.accept()
            else:
                a0.ignore()
        else:
            if self.need_restart:
                QMessageBox.information(self, '提示',
                                        '账号已登录成功，为保证本地数据完全加载，你需要重启本软件。点击确定键关闭本软件，软件将在下次重新打开时自动应用你的设置。',
                                        QMessageBox.Ok)
                sys.exit(0)

            self.webview.destroyWebviewUntilComplete()
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

    def open_in_current_page(self, link):
        self.webview.load(link)

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
    user_info_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.init_ui_elements()
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton.setIcon(QIcon('ui/more.png'))
        self.pushButton.setStyleSheet("QPushButton::menu-indicator{image:none;}")
        self.notice_syncer = TiebaMsgSyncer()

        self.pushButton_3.clicked.connect(self.switch_follow_forum_page)
        self.pushButton_4.clicked.connect(self.switch_interact_page)
        self.pushButton_2.clicked.connect(self.refresh_recommand)
        self.pushButton_5.clicked.connect(self.open_search_window)

        self.add_info.connect(self._add_uinfo)
        self.user_info_loaded.connect(self.__refresh_ui_datas)
        self.notice_syncer.noticeCountChanged.connect(self.set_unread_count)
        self.notice_syncer.activeWindow.connect(self.switch_interact_page)

        self.init_profile_menu()
        self.init_pages()
        self.notice_syncer.start_sync()
        self.refresh_all_datas()

    def closeEvent(self, a0):
        def whether_show_question():
            try:
                show_question = profile_mgr.local_config['other_settings']['show_msgbox_before_close']
            except KeyError:
                show_question = True

            return show_question

        def save_not_show_profile():
            try:
                profile_mgr.local_config['other_settings']['show_msgbox_before_close'] = False
                profile_mgr.save_local_config()
            except Exception as e:
                app_logger.log_exception(e)

        def do_exit():
            a0.accept()
            app.closeAllWindows()
            app.quit()

        if whether_show_question():
            windows_num = len(qt_window_mgr.distributed_window)
            show_text = (f'你还有 {windows_num} 个打开的窗口没有被关闭，' if windows_num > 0 else '') + '确认要退出软件吗？'
            msgbox = QMessageBox(QMessageBox.Information,
                                 '提示',
                                 show_text,
                                 parent=self)
            msgbox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            cb = QCheckBox()
            cb.setText('以后不再提示')
            cb.setToolTip('勾选后，以后关闭主窗口时将直接关闭程序，不再提示用户。你随时可以到软件设置中调整此选项。')
            msgbox.setCheckBox(cb)

            if msgbox.exec() == QMessageBox.Yes:
                if cb.isChecked():
                    save_not_show_profile()
                do_exit()
            else:
                a0.ignore()
        else:
            do_exit()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_F5 and self.stackedWidget.currentIndex() == 0:
            self.refresh_recommand()

    def init_ui_elements(self):
        self.toast_widget = top_toast_widget.TopToaster()
        self.toast_widget.setCoverWidget(self)

    def set_unread_count(self):
        if self.notice_syncer.have_basic_unread_notice():
            self.pushButton_4.setStyleSheet('QPushButton{color: red;}')
            self.pushButton_4.setText(
                f'消息 ({self.notice_syncer.get_unread_notice_count(UnreadMessageType.TOTAL_COUNT)})')
        else:
            self.pushButton_4.setStyleSheet('')
            self.pushButton_4.setText('消息')

    def switch_follow_forum_page(self):
        if self.flist.is_first_show:
            self.flist.get_bars_async()
            self.flist.is_first_show = False
        self.stackedWidget.setCurrentIndex(1)

    def switch_interact_page(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        if not self.isActiveWindow():
            self.activateWindow()

        if self.interactionlist.is_first_show:
            self.interactionlist.refresh_list()
            self.interactionlist.is_first_show = False
        self.stackedWidget.setCurrentIndex(2)

    def refresh_recommand(self):
        if self.stackedWidget.currentIndex() == 0:
            # 启动刷新
            self.recommend.get_recommand_async(True)
        else:
            self.stackedWidget.setCurrentIndex(0)
            if self.recommend.is_first_load:
                self.recommend.get_recommand_async()

    def refresh_all_datas(self):
        qt_window_mgr.clear_windows()
        self.recommend.clear()
        QPixmapCache.clear()
        gc.collect()

        self.label_9.clear()
        self.label_10.setText('加载中...')
        self.pushButton.setEnabled(False)
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
            self.refresh_recommand()
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
        d = SettingsWindow()
        d.exec()
        d.deleteLater()

    def init_profile_menu(self):
        menu = QMenu()

        self.user_info_widget = MainPopupMenu(menu)
        self.user_info_widget_action = QWidgetAction(self)
        self.user_info_widget.followForumClicked.connect(self.switch_follow_forum_page)
        self.user_info_widget_action.setDefaultWidget(self.user_info_widget)
        menu.addAction(self.user_info_widget_action)

        self.my_agrees = QAction('我的点赞', self)
        self.my_agrees.triggered.connect(self.open_agreed_window)
        menu.addAction(self.my_agrees)

        self.login = QAction('登录账号', self)
        self.login.triggered.connect(self.login_exec)
        menu.addAction(self.login)

        menu.addSeparator()

        self.setting = QAction('软件设置', self)
        self.setting.triggered.connect(self.open_settings_window)
        menu.addAction(self.setting)

        self.exit_login_ac = QAction('退出登录', self)
        self.exit_login_ac.triggered.connect(self.exit_login)
        menu.addAction(self.exit_login_ac)

        self.exit_whole_app = QAction('退出软件', self)
        self.exit_whole_app.triggered.connect(self.close)
        menu.addAction(self.exit_whole_app)

        self.pushButton.setMenu(menu)

    def set_profile_menu(self):
        if self.user_data['bduss']:
            self.my_agrees.setVisible(True)
            self.exit_login_ac.setVisible(True)
            self.login.setVisible(False)
        else:
            self.my_agrees.setVisible(False)
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
            except Exception as e:
                app_logger.log_WARN('handle_d2id_flag method failed')
                app_logger.log_exception(e)
            else:
                save_json({'uid': ''}, f'{datapath}/d2id_flag')

    def _add_uinfo(self, datas):
        if not datas:
            QMessageBox.critical(self, '错误', '用户信息加载失败！', QMessageBox.Ok)
            self.label_10.setText('[用户加载失败]')
        else:
            if datas[0]:
                self.label_9.setPixmap(datas[0])
            if datas[1]:
                self.label_10.setText(datas[1])

    def init_user_data(self):
        try:
            self.handle_d2id_flag()  # 先处理d2id

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
                profile_mgr.current_uid = 'default'
                profile_mgr.current_stoken = ''
                profile_mgr.current_bduss = ''
                pixmap = QPixmap('ui/default_user_image.png')
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
                pixmap.loadFromData(cache_mgr.get_portrait(self.self_user_portrait))
                pixmap = qt_image.add_cover_for_pixmap(pixmap, 30)
                self.add_info.emit([pixmap, name])
        except Exception as e:
            self.add_info.emit([])
            app_logger.log_exception(e)
        else:
            app_logger.log_INFO(f'switched account {profile_mgr.current_uid}')
            self.user_info_loaded.emit()


if __name__ == "__main__":
    sys.excepthook = excepthook

    reset_udf()
    create_data()
    init_log()
    profile_mgr.init_all_datas()
    proxytool.set_proxy()
    handle_command_events()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    translates = set_qt_languages()
    app_logger.log_INFO('Qt init complete')
    check_webview2()

    app_logger.log_INFO('Initing main window')
    mainw = MainWindow()
    mainw.show()
    logging.log_INFO('Mainwindow showed, into the main loop')

    sys.exit(app.exec())
