"""核心模块，实现了程序内大部分功能，本程序的主要函数和类均封装在此处"""
from PyQt5.QtWidgets import QWidget, QDialog, QMessageBox, QListWidgetItem, \
    QListWidget, QApplication, QMainWindow, QMenu, QAction, QLabel, QFileDialog, QTreeWidgetItem, QTableWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QLocale, QTranslator, QPoint, QEvent, QMimeData, QUrl, QSize, \
    QByteArray, QObject
from PyQt5.QtGui import QPixmap, QIcon, QPixmapCache, QCursor, QDrag, QImage, QTransform, QMovie
from ui import follow_ba, ba_item, tie_preview, ba_head, sign, tie_detail_view, comment_view, reply_comments, \
    thread_video_item, forum_detail, user_home_page, image_viewer, reply_at_me_page, star_list, settings, user_item, \
    login_by_bduss, forum_search, loading_amt, user_blacklist_setter, thread_voice_item, agreed_item, tb_browser

import sys
import platform
import os
import json
import aes
import threading
import requests
import webview2
import request_mgr
import aiotieba
import asyncio
import gc
from bs4 import BeautifulSoup
import time
import subprocess
import pyperclip
import profile_mgr
import cache_mgr
import shutil
import audio_stream_player
import queue
import yarl

# 引入protobuf
from proto.GetUserBlackInfo import GetUserBlackInfoReqIdl_pb2, GetUserBlackInfoResIdl_pb2

if os.name == 'nt':
    import win32api
    import win32con
import consts
import pathlib
import qt_window_mgr

datapath = consts.datapath
requests.session().trust_env = True
requests.session().verify = False


def init_log():
    """初始化日志系统"""
    if consts.enable_log_file:
        aiotieba.logging.enable_filelog(aiotieba.logging.logging.INFO, pathlib.Path(f'{datapath}/logs'))
    aiotieba.logging.get_logger().info(
        f'TiebaDesktop started, App version {consts.APP_VERSION_STR} ({consts.APP_VERSION_NUM}), System {platform.system()} {platform.version()}')


def cut_string(text: str, length: int, moretext: str = '...'):
    """裁剪字符串，当长度超过 length 时自动裁断并加上后缀 moretext"""
    if len(text) <= length:
        return text
    else:
        return text[0:length] + moretext


def load_json(filename):
    """加载json文件"""
    with open(filename, 'rt') as file:
        items = json.loads(file.read())
    return items


def save_json(jsondata, filename):
    """保存json文件"""
    with open(filename, 'wt') as file:
        file.write(json.dumps(jsondata))


def save_json_secret(jsondata, filename):
    """加密保存本地的json文件"""
    with open(filename, 'wt') as file:
        file.write(aes.encode(json.dumps(jsondata), consts.encrypt_key))


def load_json_secret(filename):
    """加载本地加密存储的json文件"""
    with open(filename, 'rt') as file:
        items = file.read()
    return json.loads(aes.decode(items, consts.encrypt_key))


def create_data():
    """识别用户的电脑上是否存在用户数据，如不存在则创建"""
    aiotieba.logging.get_logger().info('Creating user data')
    global datapath
    expect_folder = [datapath, f'{datapath}/webview_data', f'{datapath}/logs', f'{datapath}/image_caches',
                     f'{datapath}/cache_index', f'{datapath}/webview_data/default']  # 欲创建的文件夹
    expect_secret_json = {f'{datapath}/user_bduss': {'current_bduss': '', 'login_list': []}}  # 欲创建的加密json文件
    expect_json = {f'{datapath}/config.json': {
        'thread_view_settings': {'hide_video': False, 'hide_ip': False, 'tb_emoticon_size': 1, 'default_sort': 0,
                                 'enable_lz_only': False},
        'forum_view_settings': {'default_sort': 0},
        'web_browser_settings': {'url_open_policy': 0}},
        f'{datapath}/cache_index/fidfname_index.json': {},
        f'{datapath}/d2id_flag': {'uid': ''}}  # 欲创建的json文件

    for i in expect_folder:
        if not os.path.isdir(i):
            os.mkdir(i)
    for k, v in expect_secret_json.items():
        if not os.path.isfile(k):
            save_json_secret(v, k)
    for k, v in expect_json.items():
        if not os.path.isfile(k):
            save_json(v, k)


def start_background_thread(func, args=()):
    """异步执行函数（新开一个线程，在子线程内执行函数），并返回线程对象"""
    thread = threading.Thread(target=func, daemon=True, args=args)
    thread.start()
    return thread


def format_second(seconds):
    """把整形秒数转换成易读的字符串"""
    if int(seconds / 60) < 10:
        minute = '0' + str(int(seconds / 60))
    else:
        minute = str(int(seconds / 60))
    if int(seconds % 60) < 10:
        second = '0' + str(int(seconds % 60))
    else:
        second = str(int(seconds % 60))
    return minute + ':' + second


def make_thread_content(threadContents, previewPlainText=False):
    """把贴子正文内容碎片转换成 Qt 可以解析的 HTML 代码，或者是纯文本"""
    if previewPlainText:
        _text = ''
    else:
        _text = '<p>'

    for i in threadContents:
        if type(i) == aiotieba.get_posts._classdef.FragText:
            will_add_text = i.text
            if not previewPlainText:
                will_add_text = will_add_text.replace('\n', '<br>')  # 在html格式下，把原本的换行符号转换为br标签
            _text += will_add_text

        elif type(i) == aiotieba.get_posts._classdef.FragEmoji and previewPlainText:
            _text += f'[{i.desc}]'
        elif type(i) == aiotieba.get_posts._classdef.FragEmoji and not previewPlainText:
            path = f'{os.getcwd()}/ui/emoticons/{i.id}.png'
            iconsize = 17 if profile_mgr.local_config['thread_view_settings']['tb_emoticon_size'] == 0 else 30
            if os.path.isfile(path):
                _text += f'<img src=\"file:///{path}\" width="{iconsize}" height="{iconsize}">'
            else:
                _text += f'[{i.desc}]'

        elif type(i) == aiotieba.get_posts._classdef.FragVoice and previewPlainText:
            _text += f'[语音，时长 {format_second(i.duration)}]'
        elif type(i) == aiotieba.get_posts._classdef.FragVideo and previewPlainText:
            _text += f'[这是一条视频贴，时长 {format_second(i.duration)}，{i.view_num} 次浏览，进贴即可查看]'

        elif type(i) == aiotieba.get_posts._classdef.FragAt and not previewPlainText:
            _text += f' <a href=\"user://{i.user_id}\">{i.text}</a> '
        elif type(i) == aiotieba.get_posts._classdef.FragAt and previewPlainText:
            _text += f' {i.text} '

        elif type(i) == aiotieba.get_posts._classdef.FragLink and not previewPlainText:
            if str(i.url).startswith(('https://tieba.baidu.com/p/', 'http://tieba.baidu.com/p/')):
                t = ' <a href=\"tieba_thread://{0}\">{1}</a> '.format(str(i.url).split('?')[0].split('/')[-1], i.title)
            else:
                t = ' <a href=\"{0}\">{1}</a> '.format(i.url, i.title)
            _text += t
        elif type(i) == aiotieba.get_posts._classdef.FragLink and previewPlainText:
            t = ' [链接]{0} '.format(i.title)
            _text += t

    if not previewPlainText:
        _text += '</p>'
    if _text == '<p></p>':
        _text = ''
    return _text


def http_downloader(path, src):
    """
    http 协议文件下载器，支持简单的单线程下载并保存数据

    Args:
        path (str): 文件在本地的保存路径
        src (str): 源文件url
    """
    aiotieba.logging.get_logger().info(f'start download {src} to local file {path}.')
    resp = requests.get(src, headers=request_mgr.header, stream=True)
    if resp.status_code == 200:
        aiotieba.logging.get_logger().info(f'server returned status code 200, start to write data.')
        f = open(path + '.crdownload', 'wb')
        for i in resp.iter_content(chunk_size=128 * 1024):
            f.write(i)
        f.close()
        os.rename(path + '.crdownload', path)  # 改回最终文件格式
        aiotieba.logging.get_logger().info(f'file write finish, download OK.')
    else:
        aiotieba.logging.get_logger().info(f'can not download file because http {resp.status_code} error.')


def filesize_tostr(size: int):
    """将文件字节大小转换为易读的字符串"""
    if size < 0:
        return '未知大小'
    elif size < 1024:
        return f'{size} 字节'
    elif 1024 ** 2 > size >= 1024:
        return f'{round(size / 1024, 2)} KB'
    elif 1024 ** 3 > size >= 1024 ** 2:
        return f'{round(size / 1024 ** 2, 2)} MB'
    elif 1024 ** 4 > size >= 1024 ** 3:
        return f'{round(size / 1024 ** 3, 2)} GB'
    else:
        return f'{round(size / 1024 ** 4, 2)} TB'


def open_url_in_browser(url, always_os_browser=False):
    """在浏览器内打开网页"""

    def open_in_system():
        shell = ''
        # 针对不同系统进行识别
        if os.name == 'nt':
            shell = f'start \"\" \"{url}\"'
        elif os.name == 'posix':
            shell = f'xdg-open {url}'
        start_background_thread(lambda sh: subprocess.call(sh, shell=True), (shell,))

    def open_in_webview():
        browser = TiebaWebBrowser()
        qt_window_mgr.add_window(browser)
        browser.add_new_page(url)

    url_list = (
        'http://tieba.baidu.com',
        'https://tieba.baidu.com',
        'http://tiebac.baidu.com',
        'https://tiebac.baidu.com',
        'http://c.tieba.baidu.com',
        'https://c.tieba.baidu.com')
    is_http = url.startswith((request_mgr.SCHEME_HTTP, request_mgr.SCHEME_HTTPS))
    is_tieba_link = url.startswith(url_list)

    if always_os_browser or not is_http:  # 手动指定强制使用系统浏览器，或是非http协议时
        open_in_system()  # 在系统内打开
    else:
        policy = profile_mgr.local_config['web_browser_settings']['url_open_policy']
        if policy == 0:  # 策略为始终在内置浏览器打开
            open_in_webview()
        elif policy == 1 and is_tieba_link:  # 策略为只打开贴吧链接，且当前链接为贴吧链接
            open_in_webview()
        elif policy == 1 and not is_tieba_link:  # 策略为只打开贴吧链接，但当前链接不是贴吧链接
            open_in_system()
        elif policy == 2:  # 策略为不使用内置浏览器
            open_in_system()


def timestamp_to_string(ts: int):
    """把时间戳转换为字符串"""
    # 判断时间是否是最近的
    current_time = time.time()
    time_separation = abs(current_time - ts)
    if time_separation < 60:  # 一分钟以内
        timestr = f'{round(time_separation)} 秒前'
    elif time_separation < 3600:  # 一小时以内
        timestr = f'{round(time_separation / 60)} 分钟前'
    elif time_separation < 86400:  # 一天以内
        timestr = f'{round(time_separation / 3600)} 小时前'
    elif time_separation < 604800:  # 一星期以内
        timeArray = time.localtime(ts)
        nodate_timestr = time.strftime("%H:%M:%S", timeArray)
        timestr = f'{round(time_separation / 86400)} 天前的 {nodate_timestr}'
    elif ts >= current_time - (current_time % 31536000):  # 今年以内
        timeArray = time.localtime(ts)
        timestr = time.strftime("%m-%d %H:%M:%S", timeArray)
    else:  # 更早的
        timeArray = time.localtime(ts)
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)

    return timestr


class UnreadMessageType:
    """未读消息数类型"""
    BOOKMARK = "bookmark"  # 收藏
    TOTAL_COUNT = "count"  # 总通知数量
    NEW_FANS = "fans"  # 新粉丝
    REPLY = "replyme"  # 回复我的
    AT = "atme"  # @我的
    AGREE = "agree"  # 点赞我的
    OFFICIAL_SYSTEM_NOTIFICATION = "pletter"  # 系统通知（例如贴子被系统删）


class TiebaMsgSyncer(QObject):
    """
    贴吧用户状态同步器

    Args:
        bduss (str): 该用户的bduss
        stoken (str): 该用户的stoken
    """

    unread_msg_counts: dict = {}
    noticeCountChanged = pyqtSignal()
    is_running = False

    def __init__(self, bduss: str = "", stoken: str = ""):
        super().__init__()
        self.set_account(bduss, stoken)
        self.event_queue = queue.Queue()

    def set_account(self, bduss: str, stoken: str):
        """重新设置账户"""
        self.bduss = bduss
        self.stoken = stoken

    def start_sync(self):
        """开始状态同步"""
        if not self.is_running:
            self.sync_thread = start_background_thread(self.unread_notice_sync_thread)

    def stop_sync(self):
        """停止状态同步"""
        if self.is_running:
            self.event_queue.put('stop')

    def have_basic_unread_notice(self):
        """当前是否存在未读的点赞、回复、@通知"""
        return self.get_unread_notice_count(UnreadMessageType.AGREE) + self.get_unread_notice_count(
            UnreadMessageType.AT) + self.get_unread_notice_count(UnreadMessageType.REPLY) != 0

    def have_unread_notice(self):
        """当前是否存在未读通知"""
        return self.get_unread_notice_count(UnreadMessageType.TOTAL_COUNT) != 0

    def get_unread_notice_count(self, msg_type):
        """获取某个类型的未读通知数"""
        return self.unread_msg_counts.get(msg_type, 0)

    def unread_notice_sync_thread(self):
        """未读通知数同步线程"""
        self.is_running = True
        aiotieba.logging.get_logger().info('notice syncer started')
        while True:
            if not self.event_queue.empty():
                e = self.event_queue.get()
                if e == 'stop':
                    break
            else:
                try:
                    if self.bduss and self.stoken:
                        self.load_unread_notice_from_api()
                    else:
                        time.sleep(5)
                        continue
                except Exception as e:
                    print('load_unread_notice_from_api error:')
                    print(e)
                else:
                    self.noticeCountChanged.emit()
                finally:
                    time.sleep(5)
        self.is_running = False
        aiotieba.logging.get_logger().info('notice syncer stopped')

    def load_unread_notice_from_api(self):
        """从接口重新加载未读通知数"""
        payloads = {
            "BDUSS": self.bduss,
            "_client_type": "2",
            "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
            "stoken": self.stoken,
        }
        resp = request_mgr.run_post_api('/c/s/msg', request_mgr.calc_sign(payloads), use_mobile_header=True,
                                        host_type=2)
        self.unread_msg_counts = resp['message']
        if self.unread_msg_counts:
            self.unread_msg_counts['count'] = 0
            for k, v in tuple(self.unread_msg_counts.items()):
                if k != 'count':
                    self.unread_msg_counts['count'] += v


class LoadingFlashWidget(QWidget, loading_amt.Ui_loadFlashForm):
    """覆盖在其它widget上层的加载动画组件"""

    def __init__(self, show_caption=True, caption=''):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 始终置顶
        self.setAttribute(Qt.WA_TranslucentBackground, False)  # 背景不透明
        self.setStyleSheet('QFrame#frame{background-color: rgb(255, 255, 255); color: rgb(255, 255, 255);}')  # 白色背景
        self.set_caption(show_caption, caption)

        self.init_load_flash()

    def set_caption(self, show_caption=True, caption=''):
        if show_caption:
            self.label_17.show()
            if caption:
                self.label_17.setText(caption)
            else:
                self.label_17.setText('数据正在赶来的路上...')
        else:
            self.label_17.hide()

    def init_load_flash(self):
        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(120, 120))
        self.show_movie.frameChanged.connect(lambda: self.label_18.setPixmap(self.show_movie.currentPixmap()))

    def eventFilter(self, source, event):
        if event.type() == QEvent.Resize and source is self.parent():  # 父组件调整大小
            self.sync_parent_widget_size()
        return super(LoadingFlashWidget, self).eventFilter(source, event)  # 照常处理事件

    def closeEvent(self, a0):
        self.show_movie.stop()
        a0.accept()

    def hideEvent(self, a0):
        self.show_movie.stop()
        a0.accept()

    def showEvent(self, a0):
        self.show_movie.start()
        a0.accept()

    def sync_parent_widget_size(self):
        self.resize(self.parent().size())

    def cover_widget(self, widget, enable_filler=True):
        self.setParent(widget)
        if enable_filler:
            widget.installEventFilter(self)

        self.raise_()
        self.sync_parent_widget_size()


class ExtListWidgetItem(QListWidgetItem):
    """可以标识用户id的QListWidgetItem，用于在列表内添加用户并找出item对应的用户id"""
    user_portrait_id = ''

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken

    def set_show_datas(self, uicon, name):
        self.setIcon(QIcon(uicon))
        self.setText(name)


class ExtTreeWidgetItem(QTreeWidgetItem):
    """可以标识用户id的QTreeWidgetItem，用于在列表内添加用户并找出item对应的用户id"""
    user_portrait_id = ''

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken


class UserItem(QWidget, user_item.Ui_Form):
    """嵌入在列表内的用户组件"""
    user_portrait_id = ''
    show_homepage_by_click = False
    switchRequested = pyqtSignal(tuple)
    deleteRequested = pyqtSignal(tuple)
    doubleClicked = pyqtSignal()
    setPortrait = pyqtSignal(QPixmap)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.setPortrait.connect(self.label.setPixmap)
        self.label_3.setToolTip(
            '请注意，贴吧 ID 与用户 ID 不同，贴吧 ID 显示在贴吧 APP 的个人主页上，用户 ID 则主要供 APP 内部使用。')

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.doubleClicked.emit()
        if self.show_homepage_by_click:
            self.open_user_homepage(self.user_portrait_id)

    def open_user_homepage(self, uid):
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def get_portrait(self, p):
        pixmap = QPixmap()
        pixmap.loadFromData(cache_mgr.get_portrait(p))
        pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPortrait.emit(pixmap)

    def setdatas(self, uicon, uname, uid=-1, show_switch=False, is_current_user=False, is_tieba_uid=False):
        if uicon:
            if isinstance(uicon, QPixmap):
                self.label.setPixmap(uicon)
            elif isinstance(uicon, str):
                if uicon.startswith('tb.'):
                    start_background_thread(self.get_portrait, (uicon,))
        else:
            self.label.hide()
        self.label_2.setText(uname)
        if uid != -1:
            self.label_3.setText(f'{"贴吧 ID" if is_tieba_uid else "用户 ID"}: {uid}')
            self.toolButton.clicked.connect(lambda: pyperclip.copy(uid))
        else:
            self.label_3.hide()
        if not show_switch:
            self.pushButton.hide()
            self.pushButton_2.hide()
        else:
            if is_current_user:
                self.pushButton.setEnabled(False)
                self.pushButton.setText('当前账号')
            self.pushButton.clicked.connect(lambda: self.switchRequested.emit((self.bduss, uname)))
            self.pushButton_2.clicked.connect(lambda: self.deleteRequested.emit((self.bduss, uname)))


class SingleUserBlacklistWindow(QWidget, user_blacklist_setter.Ui_Form):
    """拉黑设置窗口"""
    get_black_status_ok_signal = pyqtSignal(dict)
    set_black_status_ok_signal = pyqtSignal(dict)

    def __init__(self, bduss, stoken, user_id_portrait):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.user_id_portrait = user_id_portrait

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_loading_flash()

        self.get_black_status_ok_signal.connect(self.get_black_status_ok_slot)
        self.set_black_status_ok_signal.connect(self.set_black_status_ok_slot)
        self.pushButton_2.clicked.connect(self.close)
        self.pushButton.clicked.connect(self.set_black_status_async)
        self.pushButton_3.clicked.connect(self.open_user_homepage)

        self.get_black_status_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_loading_flash(self):
        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self)

    def open_user_homepage(self):
        user_home_page = UserHomeWindow(self.bduss, self.stoken, self.user_id_portrait)
        qt_window_mgr.add_window(user_home_page)

    def set_black_status_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
            self.close()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)
            self.loading_widget.hide()

    def set_black_status_async(self):
        self.loading_widget.set_caption(True, '正在应用拉黑设置，请稍等...')
        self.loading_widget.show()
        start_background_thread(self.set_black_status)

    def set_black_status(self):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    flag = aiotieba.enums.BlacklistType.NULL
                    if self.checkBox.isChecked():
                        flag |= aiotieba.enums.BlacklistType.INTERACT
                    if self.checkBox_3.isChecked():
                        flag |= aiotieba.enums.BlacklistType.CHAT
                    if self.checkBox_2.isChecked():
                        flag |= aiotieba.enums.BlacklistType.FOLLOW

                    r = await client.set_blacklist(self.user_id_portrait, flag)
                    if r:
                        turn_data['success'] = True
                        turn_data['title'] = '拉黑成功'
                        turn_data['text'] = '已成功对此用户设置拉黑。'
                    else:
                        turn_data['success'] = False
                        turn_data['title'] = '拉黑失败'
                        turn_data['text'] = str(r.err)
            except Exception as e:
                print(type(e))
                print(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.set_black_status_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def get_black_status_ok_slot(self, data):
        if data['success']:
            self.label.setPixmap(data['head'])
            self.label_2.setText(data['name'])
            self.checkBox.setChecked(data['black_state'][0])
            self.checkBox_2.setChecked(data['black_state'][2])
            self.checkBox_3.setChecked(data['black_state'][1])
            self.loading_widget.hide()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)
            self.close()

    def get_black_status_async(self):
        self.loading_widget.show()
        start_background_thread(self.get_black_status)

    def get_black_status(self):
        async def doaction():
            # 互动、私信、关注
            turn_data = {'success': True, 'head': None, 'name': '', 'black_state': [False, False, False]}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    user_info = await client.get_user_info(self.user_id_portrait,
                                                           aiotieba.enums.ReqUInfo.USER_ID | aiotieba.enums.ReqUInfo.NICK_NAME | aiotieba.enums.ReqUInfo.PORTRAIT)
                    if user_info.err:
                        turn_data['success'] = False
                        turn_data['title'] = '获取用户信息失败'
                        turn_data['text'] = f'{user_info.err}'
                    elif profile_mgr.current_uid == user_info.user_id:
                        turn_data['success'] = False
                        turn_data['title'] = '错误'
                        turn_data['text'] = '你不能拉黑自己。'
                    else:
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(user_info.portrait))
                        user_head_pixmap = user_head_pixmap.scaled(40, 40, Qt.KeepAspectRatio,
                                                                   Qt.SmoothTransformation)
                        turn_data['head'] = user_head_pixmap
                        turn_data['name'] = user_info.nick_name_new

                        payload = GetUserBlackInfoReqIdl_pb2.GetUserBlackInfoReqIdl()

                        payload.data.common._client_type = 2
                        payload.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
                        payload.data.common.BDUSS = self.bduss
                        payload.data.common.stoken = self.stoken

                        payload.data.black_uid = user_info.user_id

                        response = request_mgr.run_protobuf_api('/c/u/user/getUserBlackInfo',
                                                                payloads=payload.SerializeToString(),
                                                                cmd_id=309698,
                                                                bduss=self.bduss, stoken=self.stoken,
                                                                host_type=2)
                        final_response = GetUserBlackInfoResIdl_pb2.GetUserBlackInfoResIdl()
                        final_response.ParseFromString(response)

                        if final_response.error.errorno == 0:
                            turn_data['black_state'][0] = bool(int(final_response.data.perm_list.interact))
                            turn_data['black_state'][1] = bool(int(final_response.data.perm_list.chat))
                            turn_data['black_state'][2] = bool(int(final_response.data.perm_list.follow))
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '获取拉黑状态失败'
                            turn_data[
                                'text'] = f'{final_response.error.errmsg} (错误代码 {final_response.error.errorno})'

            except Exception as e:
                print(type(e))
                print(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.get_black_status_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()


class NetworkImageViewer(QWidget, image_viewer.Ui_Form):
    """图片查看器窗口，支持旋转缩放图片，以及保存"""
    updateImage = pyqtSignal(QPixmap)
    finishDownload = pyqtSignal(bool)
    closed = pyqtSignal()
    start_pos = None
    round_angle = 0
    isDraging = False
    originalImage = None
    downloadOk = False
    isResizing = False

    def __init__(self, src):
        super().__init__()
        self.setupUi(self)
        self.src = src

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label.setText('图片加载中...')
        self.init_menu()
        self.scrollArea.viewport().installEventFilter(self)  # 重写事件过滤器

        self.updateImage.connect(self._resizeslot)
        self.spinBox.valueChanged.connect(self.resize_image)
        self.finishDownload.connect(self.update_download_state)

        self.load_image()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Wheel and source is self.scrollArea.viewport():
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.wheelEvent(event)  # 手动执行缩放事件
                return True  # 让qt忽略事件
        return super(NetworkImageViewer, self).eventFilter(source, event)  # 否则照常处理事件

    def closeEvent(self, e):
        self.closed.emit()
        e.accept()

    def mousePressEvent(self, a0):
        self.start_pos = a0.pos()

    def mouseMoveEvent(self, a0):
        if a0.buttons() and Qt.MouseButton.LeftButton and self.downloadOk:
            distance = (a0.pos() - self.start_pos).manhattanLength()
            temp_name = '{0}/{1}'.format(os.getenv('temp'), 'view_pic.jpg')
            if distance >= QApplication.startDragDistance():
                self.isDraging = True
                self.reset_title()
                if not self.originalImage.isNull():
                    self.originalImage.save(temp_name)
                mime_data = QMimeData()
                url = QUrl()
                url.setUrl("file:///" + temp_name)
                mime_data.setUrls((url,))

                drag = QDrag(self)
                drag.setMimeData(mime_data)
                drag.setHotSpot(a0.pos())
                drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction | Qt.DropAction.LinkAction,
                          Qt.DropAction.CopyAction)
                self.isDraging = False
                self.reset_title()

    def destroyEvent(self):
        try:
            self.show_movie.stop()
            del self.originalImage
            self.destroy()
            self.deleteLater()
            gc.collect()
        except:
            pass

    def init_menu(self):
        menu = QMenu(self)

        transform_left = QAction('顺时针旋转 90 度', self)
        transform_left.triggered.connect(self.transform_image_left)
        menu.addAction(transform_left)
        transform_right = QAction('逆时针旋转 90 度', self)
        transform_right.triggered.connect(self.transform_image_right)
        menu.addAction(transform_right)
        reset_pixmap = QAction('复原图片', self)
        reset_pixmap.triggered.connect(self.reset_image)
        menu.addAction(reset_pixmap)

        self.pushButton_2.setMenu(menu)

        share_menu = QMenu(self)

        copyto = QAction('复制', self)
        copyto.triggered.connect(lambda: QApplication.clipboard().setPixmap(QPixmap.fromImage(self.originalImage)))
        share_menu.addAction(copyto)

        save = QAction('保存', self)
        save.triggered.connect(self.save_file)
        share_menu.addAction(save)

        self.pushButton_4.setMenu(share_menu)

    def transform_image_left(self):
        self.round_angle += 90
        self.resize_image()

    def transform_image_right(self):
        self.round_angle += -90
        self.resize_image()

    def reset_image(self):
        self.round_angle = 0
        self.spinBox.setValue(100)
        self.resize_image()

    def reset_title(self):
        append_text = ''
        if self.isDraging:
            append_text += '[拖拽图片到外部] '
        if self.spinBox.value() != 100:
            append_text += f'[缩放 {self.spinBox.value()} %] '
        if self.round_angle != 0:
            if self.round_angle < 0:
                append_text += f'[逆时针旋转 {abs(self.round_angle)}°] '
            elif self.round_angle > 0:
                append_text += f'[顺时针旋转 {self.round_angle}°] '
        if append_text:
            self.setWindowTitle(f'{append_text} - 图片查看器')
        else:
            self.setWindowTitle('图片查看器')

    def _resizeslot(self, pixmap):
        self.label.setPixmap(pixmap)
        self.scrollAreaWidgetContents.setMinimumSize(pixmap.width(), pixmap.height())
        self.reset_title()

    def _resizedo(self, ruler):
        self.isResizing = True
        if self.originalImage is None:
            image = QImage()
            self.originalImage = image

            success_flag = False
            try:
                response = requests.get(self.src, headers=request_mgr.header)
                if response.content:
                    if self.originalImage.loadFromData(response.content):
                        success_flag = True
            except Exception as e:
                print(type(e))
                print(e)
            finally:
                self.finishDownload.emit(success_flag)

        result_image = self.originalImage
        if not result_image.isNull():
            if self.round_angle != 0:
                result_image = result_image.transformed(QTransform().rotate(self.round_angle))
            if ruler != 1:
                nw = int(self.originalImage.width() * ruler)
                nh = int(self.originalImage.height() * ruler)
                if int(self.round_angle / 90) % 2 != 0:
                    # 交换图片长宽值以实现正确缩放
                    _ = nh
                    nh = nw
                    nw = _
                result_image = result_image.scaled(nw, nh, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
            self.updateImage.emit(QPixmap.fromImage(result_image))
        self.isResizing = False

    def resize_image(self):
        if not self.isResizing:
            if abs(self.round_angle) == 360:
                self.round_angle = 0
            thread = threading.Thread(target=self._resizedo, args=(self.spinBox.value() / 100,), daemon=True)
            thread.start()

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and self.downloadOk:
            if event.angleDelta().y() > 0:
                value = 10
            else:
                value = -10
            self.spinBox.setValue(self.spinBox.value() + value)

    def save_file(self):
        path, tpe = QFileDialog.getSaveFileName(self, '保存图片', '',
                                                'JPG 图片文件 (*.jpg;*.jpeg)')
        if path:
            try:
                if not self.originalImage.isNull():
                    self.originalImage.save(path)
            except Exception as e:
                QMessageBox.critical(self, '文件保存失败', str(e), QMessageBox.StandardButton.Ok)
            else:
                QMessageBox.information(self, '提示', '文件保存成功。', QMessageBox.StandardButton.Ok)

    def update_download_state(self, f):
        self.show_movie.stop()
        if not f:
            self.label.setText('图片加载失败，请重新打开图片窗口以重新加载。')
        else:
            self.downloadOk = True
            self.pushButton_4.setEnabled(True)
            self.pushButton_2.setEnabled(True)
            self.spinBox.setEnabled(True)

    def load_image(self):
        self.setWindowTitle(f'[加载中...] - 图片查看器')

        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(100, 100))
        self.show_movie.frameChanged.connect(lambda: self.label.setPixmap(self.show_movie.currentPixmap()))

        self.resize_image()
        self.show_movie.start()


class ThreadPictureLabel(QLabel):
    """嵌入在列表的贴子图片"""
    set_picture_signal = pyqtSignal(QPixmap)
    opic_view = None

    def __init__(self, width, height, src, view_src):
        super().__init__()
        self.src_addr = src
        self.width_n = width
        self.height_n = height
        self.preview_src = view_src

        self.setToolTip('图片正在加载...')
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.set_picture_signal.connect(self.set_picture)
        self.customContextMenuRequested.connect(self.init_picture_contextmenu)
        self.setFixedSize(self.width_n + 20, self.height_n + 35)

        self.load_picture_async()

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.show_big_picture()

    def set_picture(self, pixmap):
        self.setPixmap(pixmap)
        self.setToolTip('贴子图片')

    def load_picture_async(self):
        start_background_thread(self.load_picture)

    def load_picture(self):
        pixmap = QPixmap()
        response = requests.get(self.preview_src, headers=request_mgr.header)
        if response.content:
            pixmap.loadFromData(response.content)
            if pixmap.width() != self.width_n + 20 or pixmap.height() != self.height_n + 35:
                pixmap = pixmap.scaled(self.width_n + 20, self.height_n + 35, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation)
        self.set_picture_signal.emit(pixmap)

    def init_picture_contextmenu(self):
        menu = QMenu()

        show_o = QAction('显示大图', self)
        show_o.triggered.connect(self.show_big_picture)
        menu.addAction(show_o)

        save = QAction('保存图片', self)
        save.triggered.connect(self.save_picture)
        menu.addAction(save)

        copy_src = QAction('复制图片链接', self)
        copy_src.triggered.connect(lambda: pyperclip.copy(self.src_addr))
        menu.addAction(copy_src)

        menu.exec(QCursor.pos())

    def show_big_picture(self):
        def close_memory_clear():
            self.opic_view.destroyEvent()
            del self.opic_view
            gc.collect()
            self.opic_view = None

        if self.opic_view:
            self.opic_view.raise_()
            if self.opic_view.isMinimized():
                self.opic_view.showNormal()
            if not self.opic_view.isActiveWindow():
                self.opic_view.activateWindow()
        else:
            self.opic_view = NetworkImageViewer(self.src_addr)
            self.opic_view.closed.connect(close_memory_clear)
            self.opic_view.show()

    def save_picture(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择图片保存位置', '', 'JPEG 图片 (*.jpg;*.jpeg)')
        if path:
            start_background_thread(http_downloader, (path, self.src_addr))


class TiebaWebBrowser(QWidget, tb_browser.Ui_Form):
    """贴吧页面内置浏览器"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.toolButton.setIcon(QIcon('ui/back.png'))
        self.toolButton_2.setIcon(QIcon('ui/forward.png'))
        self.toolButton_3.setIcon(QIcon('ui/refresh.png'))
        self.toolButton_5.setIcon(QIcon('ui/os_browser.png'))
        self.default_profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}',
                                                       enable_link_hover_text=False,
                                                       enable_zoom_factor=True, enable_error_page=True,
                                                       enable_context_menu=True, enable_keyboard_keys=True,
                                                       handle_newtab_byuser=True)

        self.tabWidget.tabCloseRequested.connect(self.remove_widget)
        self.tabWidget.currentChanged.connect(self.on_tab_changed)
        self.lineEdit.returnPressed.connect(self.load_new_page)
        self.toolButton.clicked.connect(self.button_back)
        self.toolButton_2.clicked.connect(self.button_forward)
        self.toolButton_3.clicked.connect(self.button_refresh)
        self.toolButton_5.clicked.connect(self.button_os_browser)
        self.toolButton_4.clicked.connect(self.init_more_menu)

    def closeEvent(self, a0):
        a0.accept()
        while self.tabWidget.count() != 0:
            self.remove_widget(0)
        qt_window_mgr.del_window(self)

    def keyPressEvent(self, a0):
        if a0.modifiers() == Qt.ControlModifier and a0.key() == Qt.Key_W:
            self.remove_widget(self.tabWidget.currentIndex())

    def open_in_tieba(self, url):
        def open_ba_detail(fname):
            async def get_fid():
                try:
                    async with aiotieba.Client(proxy=True) as client:
                        fid = await client.get_fid(fname)
                        return fid
                except:
                    return 0

            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            fid = asyncio.run(get_fid())

            forum_window = ForumShowWindow(profile_mgr.current_bduss, profile_mgr.current_stoken, int(fid))
            qt_window_mgr.add_window(forum_window)
            forum_window.load_info_async()
            forum_window.get_threads_async()

        def open_thread(tid):
            third_party_thread = ThreadDetailView(profile_mgr.current_bduss, profile_mgr.current_stoken, int(tid))
            qt_window_mgr.add_window(third_party_thread)

        def open_user_homepage(uid):
            user_home_page = UserHomeWindow(profile_mgr.current_bduss, profile_mgr.current_stoken, uid)
            qt_window_mgr.add_window(user_home_page)

        if url.startswith('user://'):
            user_sign = url.replace('user://', '')
            # 判断是不是portrait
            if not user_sign.startswith('tb.'):
                open_user_homepage(int(user_sign))
            else:
                open_user_homepage(user_sign)
        elif url.startswith('tieba_thread://'):
            open_thread(url.replace('tieba_thread://', ''))
        elif url.startswith('tieba_forum_namely://'):
            open_ba_detail(url.replace('tieba_forum_namely://', ''))
        else:
            print(url, 'is not a tieba link')

    def parse_weburl_to_tburl(self):
        tb_url = ''
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            if widget.isRenderInitOk():
                url = widget.url()
                tb_thread_urls = ('http://tieba.baidu.com/p/', 'https://tieba.baidu.com/p/',)
                tb_forum_urls = ('http://tieba.baidu.com/f', 'https://tieba.baidu.com/f',)
                tb_homepage_urls = ('http://tieba.baidu.com/home/main/?id=', 'https://tieba.baidu.com/home/main/?id=',)
                if url.startswith(tb_thread_urls):
                    thread_id = url.split('?')[0].split('/')[-1]
                    tb_url = f'tieba_thread://{thread_id}'
                elif url.startswith(tb_forum_urls):
                    forum_name = yarl.URL(url).query['kw']
                    tb_url = f'tieba_forum_namely://{forum_name}'
                elif url.startswith(tb_homepage_urls):
                    portrait = yarl.URL(url).query['id']
                    tb_url = f'user://{portrait}'

        return tb_url

    def init_more_menu(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            if widget.isRenderInitOk():
                menu = QMenu()

                jump_url = self.parse_weburl_to_tburl()
                jump_to_tbd = QAction('在贴吧桌面中打开此页面', self)
                jump_to_tbd.triggered.connect(lambda: self.open_in_tieba(jump_url))
                menu.addAction(jump_to_tbd)
                if not jump_url:
                    jump_to_tbd.setVisible(False)

                menu.addSeparator()

                current_zoom = QAction(f'当前网页缩放 {int(widget.zoomFactor() * 100)}%', self)
                current_zoom.setEnabled(False)
                menu.addAction(current_zoom)

                zoom_bigger = QAction('增加 10% 缩放', self)
                zoom_bigger.triggered.connect(lambda: widget.setZoomFactor(widget.zoomFactor() + 0.1))
                menu.addAction(zoom_bigger)

                zoom_smaller = QAction('减小 10% 缩放', self)
                zoom_smaller.triggered.connect(lambda: widget.setZoomFactor(widget.zoomFactor() - 0.1))
                menu.addAction(zoom_smaller)

                menu.addSeparator()

                print_page = QAction('打印网页', self)
                print_page.triggered.connect(widget.openPrintDialog)
                menu.addAction(print_page)

                downloads = QAction('下载记录', self)
                downloads.triggered.connect(widget.openDefaultDownloadDialog)
                menu.addAction(downloads)

                taskmgr = QAction('任务管理器', self)
                taskmgr.triggered.connect(widget.openChromiumTaskmgrWindow)
                menu.addAction(taskmgr)

                devtools = QAction('开发者工具', self)
                devtools.triggered.connect(widget.openDevtoolsWindow)
                menu.addAction(devtools)

                bt_pos = self.toolButton_4.mapToGlobal(QPoint(0, 0))
                menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.toolButton_4.height()))

    def button_back(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.back()

    def button_forward(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.forward()

    def button_refresh(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.reload()

    def button_os_browser(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            open_url_in_browser(widget.url(), True)

    def load_new_page(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            url = self.lineEdit.text()
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            widget.load(url)

    def on_tab_changed(self):
        self.reset_url_text()
        self.reset_main_title()

    def reset_main_title(self):
        widget = self.tabWidget.currentWidget()
        if widget:
            self.setWindowIcon(widget.windowIcon())
            self.setWindowTitle(cut_string(widget.windowTitle(), 20) + ' - 贴吧桌面')

    def reset_url_text(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            self.lineEdit.setText(widget.url())

    def handle_fullscreen(self, is_fullscreen):
        if is_fullscreen:
            self.showFullScreen()
            self.frame.hide()
            self.tabWidget.tabBar().hide()
        else:
            self.showNormal()
            self.frame.show()
            self.tabWidget.tabBar().show()

    def add_new_page(self, url):
        def stop_ani():
            webview.show_movie.stop()
            webview.setWindowIcon(webview.icon())
            webview.setWindowTitle(webview.title())

        webview2.loadLibs()

        webview = webview2.QWebView2View()
        webview.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        webview.setWindowTitle('正在加载...')

        webview.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        webview.show_movie.setScaledSize(QSize(50, 50))
        webview.show_movie.frameChanged.connect(
            lambda: webview.setWindowIcon(QIcon(webview.show_movie.currentPixmap())))

        webview.titleChanged.connect(webview.setWindowTitle)
        webview.iconChanged.connect(webview.setWindowIcon)
        webview.fullScreenRequested.connect(self.handle_fullscreen)
        webview.windowCloseRequested.connect(lambda: self.remove_widget(self.tabWidget.indexOf(webview)))
        webview.newtabSignal.connect(self.add_new_page)
        webview.loadStarted.connect(webview.show_movie.start)
        webview.loadStarted.connect(lambda: webview.setWindowTitle('正在加载...'))
        webview.loadFinished.connect(stop_ani)
        webview.urlChanged.connect(self.reset_url_text)
        webview.setProfile(self.default_profile)
        webview.loadAfterRender(url)

        self.add_new_widget(webview)
        webview.initRender()

    def add_new_widget(self, widget: QWidget):
        self.tabWidget.addTab(widget, widget.windowIcon(), widget.windowTitle())
        widget.windowIconChanged.connect(lambda icon: self.tabWidget.setTabIcon(self.tabWidget.indexOf(widget), icon))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabText(self.tabWidget.indexOf(widget), cut_string(title, 20)))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabToolTip(self.tabWidget.indexOf(widget), title))
        widget.windowIconChanged.connect(self.reset_main_title)
        widget.windowTitleChanged.connect(self.reset_main_title)

        self.tabWidget.setCurrentWidget(widget)

    def remove_widget(self, index: int):
        widget = self.tabWidget.widget(index)
        self.tabWidget.removeTab(index)
        if isinstance(widget, webview2.QWebView2View):
            widget.destroyWebview()
            widget.show_movie.stop()
        widget.deleteLater()
        del widget

        if self.tabWidget.count() == 0:
            self.close()


class AgreedThreadsList(QDialog, star_list.Ui_Dialog):
    """点赞的贴子列表，和最新版贴吧一样，可查看点赞过的贴子\n
    由于和收藏列表一样都是贴子列表，所以直接继承star_list.Ui_Dialog来写"""
    add_thread = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.page = 1
        self.isloading = False

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowTitle('点赞列表')
        self.label.setText('这里可以查看你点过赞的贴子。')
        self.resize(720, 520)

        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_list_info)
        self.listWidget.verticalScrollBar().setSingleStep(25)

        self.add_thread.connect(self.add_agreed_threads_ui)
        self.pushButton.clicked.connect(self.refresh_agreed_threads)

        self.get_agreed_threads_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def scroll_load_list_info(self):
        if self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value():
            self.get_agreed_threads_async()

    def add_agreed_threads_ui(self, infos):
        item = QListWidgetItem()

        if infos['type'] == 0:
            widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)

            widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], infos['text'],
                             infos['forum_head_pixmap'],
                             infos['forum_name'])
            widget.set_thread_values(infos['thread_data']['vn'], infos['thread_data']['ag'],
                                     infos['thread_data']['rpy'], infos['thread_data']['rpt'], infos['timestamp'])
            widget.set_picture(infos['picture'])
            widget.adjustSize()
        else:
            widget = ReplyItem(self.bduss, self.stoken)
            timestr = timestamp_to_string(infos['timestamp'])
            widget.portrait = infos['portrait']
            widget.thread_id = infos['thread_id']
            widget.post_id = infos['post_id']
            widget.allow_home_page = True
            widget.subcomment_show_thread_button = True
            widget.set_reply_text(
                '<a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下的回复：'.format(
                    fname=infos['forum_name'], tname=infos['title'], tid=infos['thread_id'],
                    fid=infos['forum_id']))
            widget.setdatas(infos['user_portrait_pixmap'], infos['user_name'], False, infos['text'],
                            infos['picture'], -1, timestr, '', -2, -1, -1, False)

        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def refresh_agreed_threads(self):
        if not self.isloading:
            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()
            self.page = 1

        self.get_agreed_threads_async()

    def get_agreed_threads_async(self):
        if not self.isloading and self.page != -1:
            start_background_thread(self.get_agreed_threads)

    def get_agreed_threads(self):
        async def run_func():
            try:
                self.isloading = True
                aiotieba.logging.get_logger().info(f'loading userAgreedThreadsList page {self.page}')
                payload = {
                    'BDUSS': self.bduss,
                    'stoken': self.stoken,
                    'tab_id': "0",
                    'pn': str(self.page),
                    'rn': "20",
                }
                resp = request_mgr.run_post_api(f'/c/u/feed/userAgree', payloads=payload, bduss=self.bduss,
                                                stoken=self.stoken, use_mobile_header=True)

                for thread in resp['data']["thread_list"]:
                    # 贴子类型0为主题，1为回复
                    data = {'type': 1 if thread.get('top_agree_post') else 0,
                            'user_name': thread['author']['name_show'],
                            'user_portrait_pixmap': None,
                            'forum_head_pixmap': None,
                            'thread_id': thread['tid'],
                            'post_id': 0,
                            'forum_id': thread['forum_info']['id'],
                            'forum_name': thread['forum_info']['name'],
                            'title': thread["title"],
                            'text': cut_string(thread['abstract'][0]['text'], 50),
                            'picture': [],
                            'timestamp': thread['create_time'],
                            'thread_data': {'vn': thread["view_num"], 'ag': thread["agree_num"],
                                            'rpy': thread["reply_num"], 'rpt': thread["share_num"]},
                            'portrait': thread["author"]["portrait"].split('?')[0]}

                    # 获取回复贴数据
                    if postinfo := thread.get('top_agree_post'):
                        data['post_id'] = postinfo['id']
                        data['timestamp'] = postinfo["time"]
                        data['thread_data']['ag'] = postinfo["agree"]['agree_num']
                        data['user_name'] = postinfo['author']['name_show']
                        data['portrait'] = postinfo["author"]["portrait"].split('?')[0]
                        text = ''
                        for i in postinfo['content']:
                            if i['type'] == 0:  # 是文本
                                text += i['text']
                            elif i['type'] == 3:  # 是图片
                                data['picture'].append(
                                    {'width': int(i['bsize'].split(',')[0]), 'height': int(i['bsize'].split(',')[1]),
                                     'src': i['origin_src'], 'view_src': i['src']})
                        data['text'] = cut_string(text, 50)

                    # 获取吧头像
                    forum_head_pixmap = QPixmap()
                    url = thread["forum_info"]["avatar"]
                    response = requests.get(
                        url,
                        headers=request_mgr.header)
                    if response.content:
                        forum_head_pixmap.loadFromData(response.content)
                        forum_head_pixmap = forum_head_pixmap.scaled(15, 15, Qt.KeepAspectRatio,
                                                                     Qt.SmoothTransformation)
                        data['forum_head_pixmap'] = forum_head_pixmap

                    # 获取用户头像
                    portrait = data['portrait']
                    user_head_pixmap = QPixmap()
                    user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                    user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    data['user_portrait_pixmap'] = user_head_pixmap

                    # 获取主题贴图片
                    if thread.get("media") and data['type'] == 0:
                        for m in thread['media']:
                            if m["type"] == 3:  # 是图片
                                pixmap = QPixmap()
                                url = m["small_pic"]
                                response = requests.get(url, headers=request_mgr.header)
                                if response.content:
                                    pixmap.loadFromData(response.content)
                                    pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                           Qt.SmoothTransformation)
                                    data['picture'].append(pixmap)

                    self.add_thread.emit(data)
            except Exception as e:
                print(type(e))
                print(e)
            else:
                aiotieba.logging.get_logger().info(
                    f'load userAgreedThreadsList page {self.page} successful')
                if not resp['data']['has_more']:
                    self.page = -1
                else:
                    self.page += 1
            finally:
                self.isloading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()


class StaredThreadsList(QDialog, star_list.Ui_Dialog):
    """收藏的贴子列表，可查看已收藏的贴子"""
    add_thread = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.page = 1
        self.isloading = False

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))

        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_list_info)
        self.listWidget.verticalScrollBar().setSingleStep(25)

        self.add_thread.connect(self.add_star_threads_ui)
        self.pushButton.clicked.connect(self.refresh_star_threads)

        self.get_star_threads_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def scroll_load_list_info(self):
        if self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value():
            self.get_star_threads_async()

    def add_star_threads_ui(self, infos):
        item = QListWidgetItem()
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)

        widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], '', None,
                         infos['forum_name'])
        if infos['picture']:
            widget.set_picture([infos['picture']])
        else:
            widget.set_picture([])
        if infos['is_del']:
            widget.label_11.show()
            widget.label_11.setStyleSheet('QLabel{color: red;}')
            widget.label_11.setText('该贴已被作者删除')

        widget.label.hide()
        widget.adjustSize()
        item.setSizeHint(widget.size())

        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def refresh_star_threads(self):
        if not self.isloading:
            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()
            self.page = 1

        self.get_star_threads_async()

    def get_star_threads_async(self):
        if not self.isloading and self.page != -1:
            start_background_thread(self.get_star_threads)

    def get_star_threads(self):
        async def run_func():
            try:
                self.isloading = True
                aiotieba.logging.get_logger().info(
                    f'loading userThreadStoreList page {self.page}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    resp = request_mgr.run_get_api(f'/mg/o/threadstore?pn={self.page}&rn=10&eqid=&refer=',
                                                   bduss=self.bduss, stoken=self.stoken)
                    for thread in resp['data']['store_thread']:
                        data = {'user_name': thread['author']['show_nickname'], 'user_portrait_pixmap': None,
                                'thread_id': thread['tid'], 'forum_id': await client.get_fid(thread['forum_name']),
                                'forum_name': thread['forum_name'], 'title': thread["title"], 'picture': None,
                                'is_del': bool(thread['is_deleted'])}

                        portrait = thread["author"]["portrait"].split('?')[0]
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        data['user_portrait_pixmap'] = user_head_pixmap

                        if thread.get("media"):
                            pixmap = QPixmap()
                            url = thread['media'][0]["cover_img"]
                            response = requests.get(url, headers=request_mgr.header)
                            if response.content:
                                pixmap.loadFromData(response.content)
                                data['picture'] = pixmap

                        self.add_thread.emit(data)
            except Exception as e:
                print(type(e))
                print(e)
            else:
                aiotieba.logging.get_logger().info(
                    f'load userThreadStoreList page {self.page} successful')
                if not resp['data']['has_more']:
                    self.page = -1
                else:
                    self.page += 1
            finally:
                self.isloading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()


class UserInteractionsList(QWidget, reply_at_me_page.Ui_Form):
    """点赞、回复和@当前用户的列表"""
    add_post_data = pyqtSignal(dict)
    reply_page = 1
    at_page = 1
    agree_page = 1
    is_reply_loading = False
    is_at_loading = False
    is_agree_loading = False
    latest_agree_id = 0
    is_first_show = True

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.label.hide()
        listwidgets = [self.listWidget_3, self.listWidget_2, self.listWidget]
        for lw in listwidgets:
            lw.verticalScrollBar().setSingleStep(25)
            lw.setStyleSheet('QListWidget{outline:0px;}'
                             'QListWidget::item:hover {color:white; background-color:white;}'
                             'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('reply'))
        self.listWidget_2.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('at'))
        self.listWidget_3.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('agree'))
        self.pushButton.clicked.connect(self.refresh_list)

        self.add_post_data.connect(self.set_inter_data_ui)

    def refresh_list(self):
        if not self.is_at_loading and not self.is_reply_loading:
            self.listWidget.clear()
            self.listWidget_2.clear()
            self.listWidget_3.clear()
            QPixmapCache.clear()
            gc.collect()
            self.reply_page = 1
            self.at_page = 1
            self.agree_page = 1
            self.latest_agree_id = 0

        self.load_inter_data_async('all')

    def scroll_load_list_info(self, type_):
        flag_reply = (
                type_ == "reply" and not self.is_reply_loading and self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value() and not self.reply_page == -1)
        flag_at = (
                type_ == "at" and not self.is_at_loading and self.listWidget_2.verticalScrollBar().maximum() == self.listWidget_2.verticalScrollBar().value() and not self.at_page == -1)
        flag_agree = (
                type_ == "agree" and not self.is_agree_loading and self.listWidget_3.verticalScrollBar().maximum() == self.listWidget_3.verticalScrollBar().value() and not self.agree_page == -1)
        if flag_reply or flag_at or flag_agree:
            start_background_thread(self.load_inter_data, (type_,))

    def set_inter_data_ui(self, data):
        item = QListWidgetItem()
        if data['type'] != 'agree':
            widget = ReplyItem(self.bduss, self.stoken)

            widget.is_comment = data['is_subfloor']
            widget.portrait = data['portrait']
            widget.thread_id = data['thread_id']
            widget.post_id = data['post_id']
            widget.subcomment_show_thread_button = True
            widget.set_reply_text(
                '{sub_floor}在 <a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下{ptype}了你：'.format(
                    fname=data['forum_name'], tname=data['thread_title'], tid=data['thread_id'],
                    fid=data['forum_id'], sub_floor='[楼中楼] ' if data['is_subfloor'] else '[回复贴] ',
                    ptype='回复' if data['type'] == 'reply' else '@'))
            widget.setdatas(data['user_portrait_pixmap'], data['user_name'], False, data['content'],
                            [], -1, data['post_time_str'], '', -2, -1, -1, False)
        else:
            widget = AgreedThreadItem(self.bduss, self.stoken)

            widget.is_post = False
            widget.portrait = data['portrait']
            widget.thread_id = data['thread_id']
            widget.post_id = data['post_id']
            widget.setdatas(data['user_portrait_pixmap'], data['user_name'], data['content'],
                            data['pic_link'], data['post_time_str'],
                            '在 <a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 内为你发布的以下内容点了赞：'.format(
                                fname=data['forum_name'], tname=data['thread_title'], tid=data['thread_id'],
                                fid=data['forum_id']))
        item.setSizeHint(widget.size())

        if data['type'] == 'reply':
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif data['type'] == 'at':
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
        elif data['type'] == 'agree':
            self.listWidget_3.addItem(item)
            self.listWidget_3.setItemWidget(item, widget)

    def load_inter_data_async(self, type_):
        if self.bduss:
            self.label.hide()
            self.tabWidget.show()
            if (type_ == "reply" and not self.is_reply_loading) or (type_ == "at" and not self.is_at_loading) or (
                    type_ == "agree" and not self.is_agree_loading):
                start_background_thread(self.load_inter_data, (type_,))
            elif type_ == "all" and not self.is_reply_loading and not self.is_at_loading and not self.is_agree_loading:
                start_background_thread(self.load_inter_data, ('reply',))
                start_background_thread(self.load_inter_data, ('at',))
                start_background_thread(self.load_inter_data, ('agree',))
        else:
            self.label.show()
            self.tabWidget.hide()

    def load_inter_data(self, type_):
        async def run_func():
            try:
                aiotieba.logging.get_logger().info(
                    f'loading userInteractionsList {type_}, page (reply {self.reply_page} at {self.at_page} agree {self.agree_page})')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if type_ == "reply":
                        self.is_reply_loading = True
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': '2',
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'pn': str(self.reply_page),
                            'stoken': self.stoken,
                        }
                        datas = request_mgr.run_post_api('/c/u/feed/replyme', payloads=request_mgr.calc_sign(payload),
                                                         use_mobile_header=True, host_type=2)

                        for thread in datas['reply_list']:
                            # 用户头像
                            portrait = thread["replyer"]["portrait"].split("?")[0]
                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            # 用户昵称
                            nick_name = thread["replyer"]["name_show"]

                            # 获取吧id
                            forum_id = await client.get_fid(thread["fname"])

                            # 获取贴子标题
                            thread_title = thread['title']

                            # 发布时间字符串
                            timestr = timestamp_to_string(int(thread['time']))

                            # 是楼中楼获取对应的pid
                            if bool(int(thread['is_floor'])):
                                pid = int(thread['quote_pid'])
                            else:
                                pid = int(thread["post_id"])

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': int(thread["thread_id"]),
                                    'real_post_id': int(thread["post_id"]),
                                    'post_id': pid,
                                    'is_subfloor': bool(int(thread['is_floor'])),
                                    'forum_id': forum_id,
                                    'forum_name': thread["fname"],
                                    'thread_title': thread_title,
                                    'content': thread["content"],
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'portrait': portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.add_post_data.emit(data)
                    elif type_ == "at":
                        self.is_at_loading = True
                        datas = await client.get_ats(self.at_page)

                        for thread in datas.objs:
                            # 用户头像
                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(thread.user.portrait))
                            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            # 用户昵称
                            nick_name = thread.user.nick_name_new

                            # 获取吧id
                            forum_id = thread.fid

                            # 获取贴子标题
                            thread_title = thread.thread_title if thread.thread_title else "无法获取贴子标题，可能已被删除"

                            # 发布时间字符串
                            timestr = timestamp_to_string(thread.create_time)

                            # 是楼中楼获取对应的pid
                            if thread.is_comment:
                                thread_info = await client.get_comments(thread.tid, thread.pid, pn=1, is_comment=True)
                                pid = thread_info.post.pid
                            else:
                                pid = thread.pid

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': thread.tid,
                                    'real_post_id': thread.pid,
                                    'post_id': pid,
                                    'is_subfloor': thread.is_comment,
                                    'forum_id': forum_id,
                                    'forum_name': thread.fname,
                                    'thread_title': thread_title,
                                    'content': thread.text,
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'portrait': thread.user.portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.add_post_data.emit(data)
                    elif type_ == "agree":
                        self.is_agree_loading = True
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': '2',
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'id': str(self.latest_agree_id),
                            'rn': '20',
                            'stoken': self.stoken,
                        }
                        if not self.latest_agree_id:
                            del payload['id']
                        datas = request_mgr.run_post_api('/c/u/feed/agreeme', payloads=request_mgr.calc_sign(payload),
                                                         use_mobile_header=True, host_type=2)

                        for thread in datas['agree_list']:
                            # 更新点赞id
                            self.latest_agree_id = int(thread['id'])

                            # 用户头像
                            portrait = thread["agreeer"]["portrait"].split("?")[0]
                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            # 用户昵称
                            nick_name = thread["agreeer"]["name_show"]

                            # 获取吧id
                            forum_id = thread["thread_info"]['fid']

                            # 获取贴子标题
                            thread_title = thread['thread_info']['title']

                            # 发布时间字符串
                            timestr = timestamp_to_string(int(thread['op_time']))

                            # 被点赞的内容
                            content = f'主题贴：{thread_title}'
                            if int(thread['type']) != 3:
                                content += '\n  - '
                                content += f"{thread['post_info']['author']['name_show']} 发表的回复：{thread['post_info']['content'][0]['text']}"

                            # 贴子图片链接
                            pic_link = ''
                            if pic_list := thread['thread_info'].get('media'):
                                for p in pic_list:
                                    if int(p['type']) == 3:
                                        pic_link = p['small_pic']
                                        break

                            # 是楼中楼获取对应的pid
                            if int(thread['type']) == 2:
                                pid = int(thread['post_info']['id'])
                            else:
                                pid = int(thread["post_id"])

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': int(thread["thread_id"]),
                                    'post_id': pid,
                                    'item_type': int(thread['type']),  # 1回复 2楼中楼 3主题
                                    'forum_id': forum_id,
                                    'forum_name': thread['thread_info']["fname"],
                                    'thread_title': thread_title,
                                    'content': content,
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'portrait': portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr,
                                    'pic_link': pic_link}
                            self.add_post_data.emit(data)
            except Exception as e:
                print(type(e))
                print(e)
            else:
                if type_ == "reply":
                    if bool(int(datas["page"]["has_more"])):
                        self.reply_page += 1
                    else:
                        self.reply_page = -1
                    self.is_reply_loading = False
                elif type_ == "at":
                    if datas.has_more:
                        self.at_page += 1
                    else:
                        self.at_page = -1
                    self.is_at_loading = False
                elif type_ == "agree":
                    if bool(int(datas["has_more"])):
                        self.agree_page += 1
                    else:
                        self.agree_page = -1
                    self.is_agree_loading = False
                aiotieba.logging.get_logger().info(
                    f'load userInteractionsList {type_}, page (reply {self.reply_page} at {self.at_page} agree {self.agree_page}) successful')

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()


class UserHomeWindow(QWidget, user_home_page.Ui_Form):
    """用户个人主页窗口"""
    set_head_info_signal = pyqtSignal(dict)
    set_list_info_signal = pyqtSignal(tuple)
    action_ok_signal = pyqtSignal(dict)

    nick_name = ''
    real_user_id = -1

    def __init__(self, bduss, stoken, user_id_portrait):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.user_id_portrait = user_id_portrait

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label_11.setPixmap(QPixmap('ui/user_ban.png').scaled(15, 15, transformMode=Qt.SmoothTransformation))
        self.label_7.setPixmap(QPixmap('ui/tb_dashen.png').scaled(15, 15, transformMode=Qt.SmoothTransformation))
        self.init_user_action_menu()

        # 隐藏组件
        self.frame_8.hide()
        self.frame_2.hide()
        self.frame_3.hide()
        self.frame_5.hide()
        self.frame_4.hide()

        self.page = {'thread': {'loading': False, 'page': 1},
                     'reply': {'loading': False, 'page': 1},
                     'follow_forum': {'loading': False, 'page': 1},
                     'follow': {'loading': False, 'page': 1},
                     'fans': {'loading': False, 'page': 1}}
        self.listwidgets = {'follow_forum': self.listWidget, 'reply': self.listWidget_2, 'follow': self.listWidget_3,
                            'thread': self.listWidget_4, 'fans': self.listWidget_5}
        for v in self.listwidgets.values():
            v.verticalScrollBar().setSingleStep(20)

        # 必须手动链接所有信号，在上面的循环里进行会有奇怪的bug
        self.listWidget.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('follow_forum'))
        self.listWidget_2.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('reply'))
        self.listWidget_3.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('follow'))
        self.listWidget_4.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('thread'))
        self.listWidget_5.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('fans'))

        self.listWidget_4.setStyleSheet('QListWidget{outline:0px;}'
                                        'QListWidget::item:hover {color:white; background-color:white;}'
                                        'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget_2.setStyleSheet('QListWidget{outline:0px;}'
                                        'QListWidget::item:hover {color:white; background-color:white;}'
                                        'QListWidget::item:selected {color:white; background-color:white;}')

        # 隐藏ip属地
        if profile_mgr.local_config['thread_view_settings']['hide_ip']:
            self.label_5.hide()

        self.action_ok_signal.connect(self.action_ok_slot)
        self.set_head_info_signal.connect(self.set_head_info_ui)
        self.set_list_info_signal.connect(self.set_list_info_ui)
        self.listWidget_3.itemDoubleClicked.connect(self.open_user_homepage)
        self.listWidget_5.itemDoubleClicked.connect(self.open_user_homepage)

        self.init_load_flash()
        self.get_head_info_async()

    def closeEvent(self, a0):
        self.flash_shower.hide()
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)
        self.flash_shower.show()

    def init_user_action_menu(self):
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        follow = QAction('关注', self)
        follow.triggered.connect(lambda: self.do_action_async('follow'))
        menu.addAction(follow)

        unfollow = QAction('取消关注', self)
        unfollow.triggered.connect(lambda: self.do_action_async('unfollow'))
        menu.addAction(unfollow)

        menu.addSeparator()

        blacklist = QAction('拉黑', self)
        blacklist.setToolTip('禁止该用户与你互动（转评赞等），以及禁止该用户关注你和给你发私信。')
        blacklist.triggered.connect(self.open_user_blacklister)
        menu.addAction(blacklist)

        old_mute = QAction('禁言', self)
        old_mute.triggered.connect(lambda: self.do_action_async('mute'))
        old_mute.setToolTip('禁止该用户回复你的贴子。\nPS：该功能存在于旧版本贴吧中，已被新版本的拉黑功能取代，不推荐使用。')
        menu.addAction(old_mute)

        cancel_old_mute = QAction('取消禁言', self)
        cancel_old_mute.triggered.connect(lambda: self.do_action_async('unmute'))
        menu.addAction(cancel_old_mute)

        self.pushButton.setMenu(menu)

    def open_user_homepage(self, item):
        if isinstance(item, ExtListWidgetItem):
            user_home_page = UserHomeWindow(self.bduss, self.stoken, item.user_portrait_id)
            qt_window_mgr.add_window(user_home_page)

    def open_user_blacklister(self):
        blacklister = SingleUserBlacklistWindow(self.bduss, self.stoken, self.user_id_portrait)
        qt_window_mgr.add_window(blacklister)

    def action_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'unfollow':
            if QMessageBox.warning(self, '取关用户', f'确定要取消关注用户 {self.nick_name} 吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        elif action_type == 'mute':
            if QMessageBox.warning(self, '禁言用户', f'禁言后，该用户将无法回复你。确定要禁言用户 {self.nick_name} 吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                aiotieba.logging.get_logger().info(f'do user {self.user_id_portrait} action type {action_type}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'follow':
                        r = await client.follow_user(self.user_id_portrait)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '关注成功'
                            turn_data['text'] = f'已成功关注该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unfollow':
                        r = await client.unfollow_user(self.user_id_portrait)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消关注成功'
                            turn_data['text'] = f'已成功取消关注该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'mute':
                        r = await client.add_blacklist_old(self.real_user_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '禁言成功'
                            turn_data['text'] = f'已成功禁言该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '禁言失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unmute':
                        r = await client.del_blacklist_old(self.real_user_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消禁言成功'
                            turn_data['text'] = f'已成功取消禁言该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消禁言失败'
                            turn_data['text'] = f'{r.err}'
            except Exception as e:
                print(type(e))
                print(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.action_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def set_head_info_ui(self, data):
        if data['error']:
            QMessageBox.critical(self, '用户信息加载失败', data['error'], QMessageBox.Ok)
            self.close()
        else:
            self.setWindowTitle(data['name'] + ' - 个人主页')
            self.setWindowIcon(QIcon(data['portrait_pixmap']))

            self.label.setPixmap(data['portrait_pixmap'])
            self.label_2.setText(data['name'])
            self.label_2.setToolTip('用户名：' + data['bd_user_name'])
            self.label_9.setText('Lv.' + str(data['level']))
            self.label_8.setText('获赞数 ' + str(data['agree_c']))
            self.label_3.setText('贴吧 ID：' + str(data['tieba_id']))
            self.label_4.setText('吧龄 {age} 年'.format(age=data['account_age']))
            self.label_5.setText('IP 属地：' + data['ip'])
            self.label_14.setText('发贴数 ' + str(data['post_c']))
            self.tabWidget.setTabText(2, '关注的吧 ({c})'.format(c=data['follow_forum_count']))
            self.tabWidget.setTabText(3, '关注的人 ({c})'.format(c=data['follow']))
            self.tabWidget.setTabText(4, '粉丝列表 ({c})'.format(c=data['fans']))

            if not data['desp']:
                self.frame_6.hide()
            else:
                self.label_6.setText(cut_string(data['desp'], 50))

            sex_icon_path = ''
            sex_icon_desp = ''
            if data['sex'] == 1:
                sex_icon_path = 'ui/sex_male.png'
                sex_icon_desp = '男性'
            elif data['sex'] == 2:
                sex_icon_path = 'ui/sex_female.png'
                sex_icon_desp = '女性'
            if sex_icon_path:
                self.label_13.setToolTip(sex_icon_desp)
                self.label_13.setPixmap(QPixmap(sex_icon_path).scaled(20, 20, transformMode=Qt.SmoothTransformation))
            else:
                self.label_13.hide()

            have_flag_showed = False
            if data['is_banned']:
                self.frame_3.show()
                have_flag_showed = True
            if data['is_dashen']:
                self.frame_2.show()
                have_flag_showed = True
            if data['thread_reply_permission'] != 1:
                self.frame_5.show()
                have_flag_showed = True
                if data['thread_reply_permission'] == 5:
                    self.label_16.setText('由于隐私设置，只有粉丝可以评论该用户的贴子。')
                elif data['thread_reply_permission'] == 6:
                    self.label_16.setText('由于隐私设置，只有该用户关注的人可以评论该用户的贴子。')
            if data['follow_forums_show_permission'] != 1:
                self.frame_4.show()
                have_flag_showed = True
                if data['follow_forums_show_permission'] == 2:
                    self.label_15.setText('该用户设置关注吧列表仅好友可见。')
                elif data['follow_forums_show_permission'] == 3:
                    self.label_15.setText('该用户隐藏了关注吧列表。')
            if have_flag_showed:
                self.frame_8.hide()

            # 隐藏动画，显示内容
            self.frame.show()
            self.tabWidget.show()
            self.frame_8.show()
            self.flash_shower.hide()

            # 查看当前用户主页或未登录时不显示操作按钮
            if profile_mgr.current_uid == self.real_user_id or not self.bduss:
                self.pushButton.hide()

            # 主信息加载完之后再加载
            for i in self.page.keys():
                self.get_list_info_async(i)

    def get_head_info_async(self):
        start_background_thread(self.get_head_info)

    def get_head_info(self):
        async def run_func():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    # 初始化数据
                    data = {'error': '',
                            'name': '',
                            'sex': 0,
                            'level': 0,
                            'portrait_pixmap': None,
                            'agree_c': 0,
                            'tieba_id': 0,
                            'post_c': 0,
                            'account_age': 0.0,
                            'ip': '',
                            'follow_forum_count': 0,
                            'follow': 0,
                            'fans': 0,
                            'is_dashen': False,
                            'is_banned': False,
                            'thread_reply_permission': 0,
                            'follow_forums_show_permission': 0,
                            'desp': '',
                            'bd_user_name': ''}

                    if self.user_id_portrait in ('00000000', 0):
                        data['error'] = '无法加载匿名用户的个人主页信息。'
                    else:
                        # 获取用户信息
                        user_info = await client.get_user_info(self.user_id_portrait, aiotieba.ReqUInfo.ALL)

                        # 判断是否出错
                        if user_info.err:
                            data['error'] = str(user_info.err)
                        else:
                            self.real_user_id = user_info.user_id
                            self.nick_name = data['name'] = user_info.nick_name_new
                            data['sex'] = user_info.gender
                            data['level'] = user_info.glevel
                            data['agree_c'] = user_info.agree_num
                            data['tieba_id'] = user_info.tieba_uid
                            data['account_age'] = user_info.age
                            data['ip'] = user_info.ip
                            data['follow_forum_count'] = user_info.forum_num
                            data['follow'] = user_info.follow_num
                            data['fans'] = user_info.fan_num
                            data['is_dashen'] = bool(user_info.is_god)
                            data['is_banned'] = bool(user_info.is_blocked)
                            data['thread_reply_permission'] = user_info.priv_reply
                            data['follow_forums_show_permission'] = user_info.priv_like
                            data['desp'] = user_info.sign
                            data['post_c'] = user_info.post_num
                            data['bd_user_name'] = user_info.user_name

                            pixmap = QPixmap()
                            pixmap.loadFromData(cache_mgr.get_portrait(user_info.portrait))
                            pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)
                            data['portrait_pixmap'] = pixmap

                    self.set_head_info_signal.emit(data)

            except Exception as e:
                print(type(e))
                print(e)
                self.set_head_info_signal.emit({'error': '程序内部出错，请重试。'})

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()

    def scroll_load_list_info(self, tpe):
        if (tpe in self.listwidgets.keys() and
                self.listwidgets[tpe].verticalScrollBar().value() == self.listwidgets[
                    tpe].verticalScrollBar().maximum() and
                not self.page.get(tpe).get('loading')):
            self.get_list_info_async(tpe)

    def set_list_info_ui(self, data):
        datas = data[1]
        if data[0] == 'thread':
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)
            widget.set_thread_values(datas['view_count'], datas['agree_count'], datas['reply_count'],
                                     datas['repost_count'], datas['post_time'])
            widget.set_infos(datas['user_portrait_pixmap'], datas['user_name'], datas['title'], datas['content'],
                             None, datas['forum_name'])
            widget.set_picture(datas['view_pixmap'])
            widget.label.hide()
            widget.adjustSize()
            item.setSizeHint(widget.size())
            self.listWidget_4.addItem(item)
            self.listWidget_4.setItemWidget(item, widget)
        elif data[0] == 'reply':
            item = QListWidgetItem()
            widget = ReplyItem(self.bduss, self.stoken)

            widget.portrait = datas['portrait']
            widget.thread_id = datas['thread_id']
            widget.post_id = datas['post_id']
            widget.allow_home_page = False
            widget.subcomment_show_thread_button = True
            forum_link_html = '<a href=\"tieba_forum://{fid}\">{fname}吧</a>'.format(fname=datas['forum_name'],
                                                                                     fid=datas['forum_id'])
            forum_link_html = forum_link_html if datas['forum_name'] else '贴吧动态'
            widget.set_reply_text(
                '{sub_floor}在 {forum_link} 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下回复：'.format(
                    tname=datas['thread_title'],
                    tid=datas['thread_id'],
                    sub_floor='[楼中楼] ' if datas['is_subfloor'] else '[回复贴] ',
                    forum_link=forum_link_html))
            widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], False, datas['content'],
                            [], -1, datas['post_time_str'], '', -2, -1, -1, False)

            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
        elif data[0] == 'follow_forum':
            item = QListWidgetItem()
            widget = ForumItem(datas['forum_id'], True, self.bduss, self.stoken, datas['forum_name'])
            widget.pushButton_2.hide()
            widget.set_info(datas['forum_pixmap'], datas['forum_name'] + '吧',
                            '{cfollow_info}[等级 {level}，经验值 {exp}] {desp}'.format(
                                cfollow_info='[共同关注] ' if datas['is_common_follow'] else '',
                                level=datas['level'], exp=datas['exp'],
                                desp=datas['forum_desp']))
            widget.set_level_color(datas['level'])
            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif data[0] in ('follow', 'fans'):
            item = ExtListWidgetItem(self.bduss, self.stoken)
            item.user_portrait_id = datas['user_id']
            item.set_show_datas(datas['user_pixmap'], datas['user_name'])
            if data[0] == 'follow':
                self.listWidget_3.addItem(item)
            else:
                self.listWidget_5.addItem(item)

    def get_list_info_async(self, type_):
        if not self.page[type_]['loading'] and self.page[type_]['page'] != -1:
            start_background_thread(self.get_list_info, (type_,))

    def get_list_info(self, type_):
        async def run_func():
            self.page[type_]['loading'] = True
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if type_ == 'thread':
                        # 获取用户头像
                        user_head_pixmap = QPixmap()
                        thread_datas = await client.get_user_threads(self.user_id_portrait, self.page[type_]['page'])
                        for thread in thread_datas.objs:
                            # 初始化数据
                            if user_head_pixmap.isNull():  # 头像为空
                                user_head_pixmap.loadFromData(cache_mgr.get_portrait(thread.user.portrait))
                                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                           Qt.SmoothTransformation)
                            data = {'thread_id': thread.tid, 'forum_id': thread.fid, 'title': thread.title,
                                    'content': cut_string(make_thread_content(thread.contents.objs, True), 50),
                                    'author_portrait': thread.user.portrait, 'user_name': thread.user.nick_name_new,
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'forum_name': thread.fname if thread.fname else "贴吧动态",
                                    'view_pixmap': [], 'view_count': thread.view_num, 'agree_count': thread.agree,
                                    'reply_count': thread.reply_num, 'repost_count': thread.share_num,
                                    'post_time': thread.create_time}

                            # 找出所有预览图
                            preview_pixmap = []
                            for pic in thread.contents.imgs:
                                pic_hash = pic.hash
                                pixmap = QPixmap()
                                pixmap.loadFromData(cache_mgr.get_bd_hash_img(pic_hash))
                                pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                       Qt.SmoothTransformation)
                                preview_pixmap.append(pixmap)
                            data['view_pixmap'] = preview_pixmap

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'reply':
                        # 获取新版昵称
                        nick_name = self.nick_name

                        # 初始化数据
                        user_head_pixmap = QPixmap()
                        post_list = []

                        post_datas = await client.get_user_posts(self.user_id_portrait, self.page[type_]['page'])
                        for t in post_datas.objs:
                            for st in t:
                                post_list.append(st)
                        post_list.sort(key=lambda k: k.create_time, reverse=True)  # 按发贴时间排序

                        for thread in post_list:
                            # 初始化数据
                            if user_head_pixmap.isNull():  # 头像为空
                                user_head_pixmap.loadFromData(cache_mgr.get_portrait(thread.user.portrait))
                                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                           Qt.SmoothTransformation)

                            # 获取吧名称
                            if thread.fid != 0:
                                forum_name = await client.get_fname(thread.fid)
                            else:
                                forum_name = ''

                            # 获取贴子标题
                            thread_info = await client.get_posts(thread.tid, pn=1, rn=0, comment_rn=0)
                            thread_title = thread_info.thread.title if thread_info.thread.title else "无法获取贴子标题，可能已被删除"

                            # 发布时间字符串
                            timestr = timestamp_to_string(thread.create_time)

                            # 是楼中楼获取对应的pid
                            if thread.is_comment:
                                thread_info = await client.get_comments(thread.tid, thread.pid, pn=1, is_comment=True)
                                pid = thread_info.post.pid
                            else:
                                pid = thread.pid

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'thread_id': thread.tid,
                                    'real_post_id': thread.pid,
                                    'post_id': pid,
                                    'is_subfloor': thread.is_comment,
                                    'forum_id': thread.fid,
                                    'forum_name': forum_name,
                                    'thread_title': thread_title,
                                    'content': cut_string(make_thread_content(thread.contents.objs, True), 50),
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'portrait': thread.user.portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'follow_forum':
                        forum_list = await client.get_follow_forums(self.user_id_portrait, self.page[type_]['page'])
                        for f in forum_list.objs:
                            pixmap = QPixmap()
                            if f.avatar:
                                response = requests.get(f.avatar, headers=request_mgr.header)
                                if response.content:
                                    pixmap.loadFromData(response.content)
                                    pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                            data = {'forum_name': f.fname,
                                    'forum_id': f.fid,
                                    'forum_pixmap': pixmap,
                                    'forum_desp': f.slogan,
                                    'level': f.level,
                                    'exp': f.exp,
                                    'is_common_follow': f.is_common_follow}

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'follow':
                        follow_list = await client.get_follows(self.user_id_portrait, pn=self.page[type_]['page'])
                        for user in follow_list:
                            name = user.nick_name_new
                            if user.forum_admin_info:
                                name += f' ({user.forum_admin_info})'

                            data = {'user_name': name,
                                    'user_pixmap': None,
                                    'user_id': user.user_id}

                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(user.portrait))
                            user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            data['user_pixmap'] = user_head_pixmap

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'fans':
                        fan_list = await client.get_fans(self.user_id_portrait, pn=self.page[type_]['page'])
                        for user in fan_list:
                            data = {'user_name': user.nick_name_new,
                                    'user_pixmap': None,
                                    'user_id': user.user_id}

                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(user.portrait))
                            user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)
                            data['user_pixmap'] = user_head_pixmap

                            self.set_list_info_signal.emit((type_, data))
            except Exception as e:
                print(type(e))
                print(e)
            else:
                self.page[type_]['page'] += 1
            finally:
                self.page[type_]['loading'] = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()


class ForumDetailWindow(QDialog, forum_detail.Ui_Dialog):
    """吧详细信息窗口，可显示吧详细信息、吧务信息、等级排行榜"""
    set_main_info_signal = pyqtSignal(dict)
    action_ok_signal = pyqtSignal(dict)

    forum_bg_link = ''
    forum_name = ''
    forum_atavar_link = ''
    is_followed = False

    def __init__(self, bduss, stoken, forum_id):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.forum_id = forum_id

        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.tableWidget.setEditTriggers(QListWidget.NoEditTriggers)
        self.tableWidget.verticalHeader().setVisible(False)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_load_flash()

        self.set_main_info_signal.connect(self.ui_set_main_info)
        self.action_ok_signal.connect(self.action_ok_slot)
        self.pushButton_5.clicked.connect(self.close)
        self.treeWidget.itemDoubleClicked[QTreeWidgetItem, int].connect(self.open_user_homepage)
        self.pushButton_4.clicked.connect(self.save_bg_image)
        self.pushButton_6.clicked.connect(lambda: pyperclip.copy(self.forum_bg_link))
        self.pushButton_7.clicked.connect(lambda: self.show_big_picture(self.forum_atavar_link))
        self.pushButton.clicked.connect(lambda: self.do_action_async('unfollow' if self.is_followed else 'follow'))
        self.pushButton_2.clicked.connect(lambda: self.do_action_async('sign'))
        self.pushButton_8.clicked.connect(self.refresh_main_data)

        self.loading_widget.show()
        self.get_main_info_async()

    def closeEvent(self, a0):
        self.loading_widget.hide()
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self)

    def refresh_main_data(self):
        self.loading_widget.set_caption(True, '正在重新加载数据...')
        self.loading_widget.show()
        self.get_main_info_async()

    def save_bg_image(self):
        if self.forum_bg_link:
            path, tpe = QFileDialog.getSaveFileName(self, '保存图片', '',
                                                    'JPG 图片文件 (*.jpg;*.jpeg)')
            if path:
                start_background_thread(http_downloader, (path, self.forum_bg_link))

    def open_user_homepage(self, item, column):
        if isinstance(item, ExtTreeWidgetItem):
            user_home_page = UserHomeWindow(self.bduss, self.stoken, item.user_portrait_id)
            qt_window_mgr.add_window(user_home_page)

    def show_big_picture(self, link):
        opic_view = NetworkImageViewer(link)
        opic_view.closed.connect(lambda: qt_window_mgr.del_window(opic_view))
        qt_window_mgr.add_window(opic_view)

    def action_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
            self.refresh_main_data()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'unfollow':
            if QMessageBox.warning(self, '取关贴吧', f'确定不再关注 {self.forum_name}吧？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False

        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                aiotieba.logging.get_logger().info(f'do forum {self.forum_id} action type {action_type}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'follow':
                        r = await client.follow_forum(self.forum_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '关注成功'
                            turn_data['text'] = f'已成功关注 {self.forum_name}吧。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unfollow':
                        r = await client.unfollow_forum(self.forum_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消关注成功'
                            turn_data['text'] = f'已成功取消关注 {self.forum_name}吧。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'sign':
                        tsb_resp = request_mgr.run_post_api('/c/s/login', request_mgr.calc_sign(
                            {'_client_version': request_mgr.TIEBA_CLIENT_VERSION, 'bdusstoken': self.bduss}),
                                                            use_mobile_header=True,
                                                            host_type=2)
                        tbs = tsb_resp["anti"]["tbs"]

                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'fid': self.forum_id,
                            'kw': self.forum_name,
                            'stoken': self.stoken,
                            'tbs': tbs,
                        }
                        r = request_mgr.run_post_api('/c/c/forum/sign',
                                                     payloads=request_mgr.calc_sign(payload),
                                                     bduss=self.bduss, stoken=self.stoken,
                                                     use_mobile_header=True,
                                                     host_type=2)
                        if r['error_code'] == '0':
                            user_sign_rank = r['user_info']['user_sign_rank']
                            sign_bonus_point = r['user_info']['sign_bonus_point']

                            turn_data['success'] = True
                            turn_data['title'] = '签到成功'
                            turn_data[
                                'text'] = f'{self.forum_name}吧 已签到成功。\n本次签到经验 +{sign_bonus_point}，你是今天本吧第 {user_sign_rank} 个签到的用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '签到失败'
                            turn_data['text'] = f'{r["error_msg"]} (错误代码 {r["error_code"]})'
            except Exception as e:
                print(type(e))
                print(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.action_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def ui_set_main_info(self, datas):
        if not datas['err_info']:
            self.loading_widget.hide()
            self.forum_name = datas['forum_name']
            self.label_2.setText(datas['forum_name'] + '吧')
            self.label.setPixmap(datas['forum_pixmap'])
            self.label_5.setText(datas['forum_desp'] + '\n' + datas['forum_desp_ex'])
            self.label_11.setText(f'吧 ID：{self.forum_id}')
            self.label_3.setText('关注数：' + str(datas['follow_c']))
            self.label_4.setText('贴子数：' + str(datas['thread_c']))
            self.label_12.setText('吧分类：' + datas['forum_volume'])
            self.label_13.setText('主题贴数：{0}'.format(str(datas['main_thread_c'])))
            self.textBrowser.setHtml(datas['forum_rule_html'])
            self.label_15.setText(f'<html><body>'
                                  f'<p>很抱歉，出于加载时的性能问题，该功能已被停用。<br/>该页面将在将来的版本中删除。<br>'
                                  f'你可以到 <a href="https://tieba.baidu.com/f/like/furank?kw={self.forum_name}&ie=utf-8">牛人排行榜</a> '
                                  f'中查看{self.forum_name}吧的等级排行榜。</p>'
                                  f'</body></html>')

            if self.bduss:
                self.is_followed = datas['follow_info']['isfollow']
                if datas['follow_info']['isfollow']:
                    self.pushButton.setText('取消关注')
                else:
                    self.pushButton.setText('关注')
                self.label_6.setText(f'你已经关注了本吧。' if datas['follow_info'][
                    'isfollow'] else f'你还没有关注{self.forum_name}吧，不妨考虑一下？')

                if datas['follow_info']['isfollow']:
                    ts = time.time() - datas["follow_info"]["follow_day"] * 86400
                    timeArray = time.localtime(ts)
                    follow_date_str = time.strftime("(大约是在 %Y年%m月%d日 那天关注的)", timeArray)
                else:
                    follow_date_str = ''
                self.label_7.setText('等级：' + str(datas['follow_info']['level']))
                self.label_8.setText('等级头衔：' + datas['follow_info']['level_flag'])
                self.label_25.setText(
                    f'关注天数：{datas["follow_info"]["follow_day"]} 天 {follow_date_str}')
                self.label_26.setText(f'总发贴数：{datas["follow_info"]["total_thread_num"]}')
                self.label_27.setText(f'今日发贴回贴数：{datas["follow_info"]["today_post_num"]}')

                if datas['follow_info']['isSign']:
                    self.pushButton_2.setEnabled(False)
                    self.pushButton_2.setText('已签到')
                self.label_9.setText(
                    f'{datas["follow_info"]["exp"]} / {datas["follow_info"]["next_exp"]}，距离下一等级还差 {datas["follow_info"]["next_exp"] - datas["follow_info"]["exp"]} 经验值')
                self.progressBar.setRange(0, datas["follow_info"]["next_exp"])
                self.progressBar.setValue(datas["follow_info"]["exp"])

                self.label_10.setText(f'共计签到天数：{datas["follow_info"]["total_sign_count"]}')
                self.label_17.setText(f'连签天数：{datas["follow_info"]["continuous_sign_count"]}')
                self.label_18.setText(f'漏签天数：{datas["follow_info"]["forget_sign_count"]}')
                self.label_28.setText(f'今日签到名次：第 {datas["follow_info"]["today_sign_rank"]} 个签到')
            else:
                self.pushButton.hide()
                self.label_6.setText('你还没有登录，登录后即可查看自己的信息。')
                self.groupBox.hide()

            if datas['bg_pic_info']['pixmap']:
                self.label_14.setPixmap(datas['bg_pic_info']['pixmap'])
            else:
                self.label_14.setText('本吧没有背景图片。')

            for i in datas['friend_forum_list']:
                item = QListWidgetItem()
                widget = ForumItem(i['forum_id'], True, self.bduss, self.stoken, i['forum_name'])
                widget.set_info(i['headpix'], i['forum_name'], '')
                widget.pushButton_2.hide()
                widget.adjustSize()
                item.setSizeHint(widget.size())

                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, widget)

            bawu_types = {}
            for i in datas['bawu_info']:
                if not bawu_types.get(i['type']):
                    item = QTreeWidgetItem()
                    item.setText(0, i['type'])
                    self.treeWidget.addTopLevelItem(item)
                    bawu_types[i['type']] = item

                item = ExtTreeWidgetItem(self.bduss, self.stoken)
                item.user_portrait_id = i['portrait']
                item.setIcon(0, QIcon(i['portrait_pixmap']))
                item.setText(0, i['name'])
                item.setText(1, str(i['level']))
                item.setText(2, i['type'])
                bawu_types[i['type']].addChild(item)

            count = 0
            for i in datas['forum_level_value_index']:
                self.tableWidget.insertRow(count)
                self.tableWidget.setItem(count, 0, QTableWidgetItem(str(count + 1)))
                self.tableWidget.setItem(count, 1, QTableWidgetItem(i['name']))
                self.tableWidget.setItem(count, 2, QTableWidgetItem(str(i['score'])))
                count += 1
            self.tableWidget.setHorizontalHeaderLabels(('等级', '头衔', '所需经验值'))

        else:
            QMessageBox.critical(self, '吧信息加载异常', datas['err_info'], QMessageBox.Ok)
            self.close()

    def get_main_info_async(self):
        self.treeWidget.clear()
        self.listWidget.clear()
        self.tableWidget.clear()
        self.tableWidget.setRowCount(0)
        start_background_thread(self.get_main_info)

    def get_main_info(self):
        async def dosign():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    # 初始化数据
                    data = {'forum_name': '', 'has_bawu': False, 'bawu_info': [], 'forum_pixmap': None,
                            'forum_desp': '', 'thread_c': 0, 'follow_c': 0, 'main_thread_c': 0,
                            'follow_info': {'isfollow': False, 'level': 0, 'exp': 0, 'level_flag': '', 'isSign': False,
                                            'next_exp': 0, 'total_sign_count': 0, 'continuous_sign_count': 0,
                                            'forget_sign_count': 0, 'follow_day': 0, 'today_sign_rank': 0,
                                            'total_thread_num': 0, 'today_post_num': 0},
                            'forum_volume': '', 'err_info': '', 'friend_forum_list': [],
                            'bg_pic_info': {'url': '', 'pixmap': None}, 'forum_desp_ex': '', 'forum_rule_html': '',
                            'forum_level_value_index': []}

                    async def get_forum_desp_ex():
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'forum_id': str(self.forum_id),
                            'is_newfrs': '1',
                            'stoken': self.stoken,
                        }
                        ex_forum_info = request_mgr.run_post_api('/c/f/forum/getforumdetail',
                                                                 request_mgr.calc_sign(payload), bduss=self.bduss,
                                                                 stoken=self.stoken, use_mobile_header=True,
                                                                 host_type=2)
                        if forum_content := ex_forum_info["forum_info"].get("content"):
                            data['forum_desp_ex'] = forum_content[0]['text']

                        data['follow_info']['isfollow'] = bool(int(ex_forum_info['forum_info']['is_like']))
                        data['follow_info']['exp'] = int(ex_forum_info['forum_info']["cur_score"])
                        data['follow_info']['level'] = int(ex_forum_info['forum_info']["level_id"])
                        data['follow_info']['level_flag'] = ex_forum_info['forum_info']["level_name"]
                        data['follow_info']['next_exp'] = int(ex_forum_info['forum_info']["levelup_score"])
                        self.forum_atavar_link = ex_forum_info['forum_info']["avatar_origin"]

                    async def get_forum_rule():
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'forum_id': str(self.forum_id),
                            'stoken': self.stoken,
                        }
                        ex_rule = request_mgr.run_post_api('/c/f/forum/forumRuleDetail',
                                                           request_mgr.calc_sign(payload), bduss=self.bduss,
                                                           stoken=self.stoken, use_mobile_header=True,
                                                           host_type=2)
                        html_code = '<html>'
                        if ex_rule['forum_rule_id']:
                            html_code += f'<h2>{ex_rule["title"]}</h2>'
                            html_code += f'<h3>{ex_rule["forum"]["forum_name"]}吧吧务于 {ex_rule["publish_time"]} 修订</h3>'
                            html_code += f'<h4>前言</h4><p>{ex_rule["preface"]}</p>'
                            r_count = 0  # 前缀下标

                            for rule in ex_rule.get('rules', []):  # 纯自定义吧规
                                title = rule['title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'

                                for single_sub_rule_item in rule['content']:
                                    if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                        content = single_sub_rule_item['text']
                                        if content != '\n':
                                            sub_html_code += f'<p>{content}</p>'
                                    elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                        sub_html_code += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'

                                html_code += sub_html_code

                            for rule in ex_rule.get('default_rules', []):  # 默认吧规内容
                                title = ex_rule['forum_rule_conf']['first_level_index_list'][r_count] + rule[
                                    'title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'
                                sub_prefix_count = 0  # 前缀下标
                                for sub_rule in rule['content_list']:  # 子条目
                                    pfix = ex_rule['forum_rule_conf']['second_level_index_list'][
                                        sub_prefix_count]  # 数字前缀
                                    content = ''  # 正文内容
                                    for single_sub_rule_item in sub_rule['content']:
                                        if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                            content += single_sub_rule_item['text']
                                        elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                            content += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'
                                    sub_html_code += f'<p>{pfix}{content}</p>'
                                    sub_prefix_count += 1
                                html_code += sub_html_code
                                r_count += 1

                            for rule in ex_rule.get('new_rules', []):  # 混合的自定义吧规
                                title = ex_rule['forum_rule_conf']['first_level_index_list'][r_count] + rule[
                                    'title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'
                                sub_prefix_count = 0  # 前缀下标
                                for sub_rule in rule['content_list']:  # 子条目
                                    pfix = ex_rule['forum_rule_conf']['second_level_index_list'][
                                        sub_prefix_count]  # 数字前缀
                                    content = ''  # 正文内容
                                    for single_sub_rule_item in sub_rule['content']:
                                        if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                            content += single_sub_rule_item['text']
                                        elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                            content += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'
                                    sub_html_code += f'<p>{pfix}{content}</p>'
                                    sub_prefix_count += 1
                                html_code += sub_html_code
                                r_count += 1

                            html_code += '</html>'
                            data['forum_rule_html'] = html_code
                        else:
                            data['forum_rule_html'] = '<html><h2>很抱歉，本吧吧主并没有在此设置吧规。</h2></html>'

                    async def get_sign_info():
                        if self.bduss:
                            # 在登录情况下，获取签到信息
                            payload = {
                                'BDUSS': self.bduss,
                                '_client_type': "2",
                                '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                                'forum_ids': str(self.forum_id),
                                'from': "frs",
                                'stoken': self.stoken,
                            }
                            resp_sign_info = request_mgr.run_post_api('/c/f/forum/getUserSign',
                                                                      request_mgr.calc_sign(payload), bduss=self.bduss,
                                                                      stoken=self.stoken, use_mobile_header=True,
                                                                      host_type=2)

                            # 整理签到信息
                            data['follow_info']['isSign'] = bool(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["is_sign_in"])
                            data['follow_info']['total_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["cout_total_sign_num"])
                            data['follow_info']['continuous_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["cont_sign_num"])
                            data['follow_info']['forget_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["miss_sign_num"])

                    async def get_user_forum_level_info():
                        if self.bduss:
                            # 在登录情况下，获取新版我在本吧信息
                            params = {
                                "_client_type": "2",
                                "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                                "BDUSS": self.bduss,
                                "stoken": self.stoken,
                                "forum_id": str(self.forum_id),
                                "subapp_type": "hybrid"
                            }
                            resp_mytb_info = request_mgr.run_get_api('/c/f/forum/getUserForumLevelInfo',
                                                                     bduss=self.bduss,
                                                                     stoken=self.stoken, use_mobile_header=True,
                                                                     host_type=1, params=params)

                            # 整理我在本吧信息
                            data['follow_info']['follow_day'] = int(
                                resp_mytb_info["data"]['user_forum_info']["follow_days"])
                            data['follow_info']['today_sign_rank'] = int(
                                resp_mytb_info["data"]['user_forum_info']["day_sign_no"])
                            data['follow_info']['total_thread_num'] = int(
                                resp_mytb_info["data"]['user_forum_info']["thread_num"])
                            data['follow_info']['today_post_num'] = int(
                                resp_mytb_info["data"]['user_forum_info']["day_post_num"])
                            data['forum_level_value_index'] = resp_mytb_info["data"]['level_info']["list"]

                    async def get_forum_bg():
                        # 获取吧背景图片
                        self.forum_bg_link = url = forum_info.background_image_url
                        data['bg_pic_info']['url'] = url
                        if url:
                            forum_bg_pixmap = QPixmap()
                            response = requests.get(url, headers=request_mgr.header)
                            if response.content:
                                forum_bg_pixmap.loadFromData(response.content)
                                data['bg_pic_info']['pixmap'] = forum_bg_pixmap

                    async def get_forums_heads():
                        # 获取友情吧信息
                        if forum_info.friend_forums:
                            for i in forum_info.friend_forums:
                                single_ff_info = {'forum_name': i.fname, 'forum_id': i.fid, 'headpix': None}
                                pixmap = QPixmap()
                                response = requests.get(i.small_avatar, headers=request_mgr.header)
                                if response.content:
                                    pixmap.loadFromData(response.content)
                                    pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                           Qt.SmoothTransformation)
                                    single_ff_info['headpix'] = pixmap
                                data['friend_forum_list'].append(single_ff_info)

                    async def get_self_forum_head():
                        # 获取吧头像
                        forum_pixmap = QPixmap()
                        response = requests.get(forum_info.small_avatar, headers=request_mgr.header)
                        if response.content:
                            forum_pixmap.loadFromData(response.content)
                            forum_pixmap = forum_pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            data['forum_pixmap'] = forum_pixmap

                    async def get_bawu_infos():
                        # 有吧务获取吧务信息
                        if forum_info.has_bawu:
                            bawu_info = await client.get_bawu_info(self.forum_id)
                            bawu_iter_index = {'大吧主': bawu_info.admin,
                                               '小吧主': bawu_info.manager,
                                               '语音小编': bawu_info.voice_editor,
                                               '图片小编': bawu_info.image_editor,
                                               '视频小编': bawu_info.video_editor,
                                               '广播小编': bawu_info.broadcast_editor,
                                               '吧刊主编': bawu_info.journal_chief_editor,
                                               '吧刊小编': bawu_info.journal_editor,
                                               '职业吧主': bawu_info.profess_admin,
                                               '第四吧主': bawu_info.fourth_admin}

                            for k, v in bawu_iter_index.items():
                                for bawu in v:
                                    pixmap = QPixmap()
                                    pixmap.loadFromData(cache_mgr.get_portrait(bawu.portrait))
                                    pixmap = pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                                    data['bawu_info'].append(
                                        {'name': bawu.nick_name_new, 'level': bawu.level, 'type': k,
                                         'portrait': bawu.portrait, 'portrait_pixmap': pixmap})

                    # 获取吧信息
                    forum_info = await client.get_forum(self.forum_id)

                    if forum_info.err:
                        if isinstance(forum_info.err, aiotieba.exception.TiebaServerError):
                            data['err_info'] = f'{forum_info.err.msg} (错误代码 {forum_info.err.code})'
                        else:
                            data['err_info'] = str(forum_info.err)
                    else:
                        # 整理吧信息
                        data['forum_name'] = forum_info.fname
                        data['has_bawu'] = forum_info.has_bawu
                        data['forum_desp'] = forum_info.slogan
                        data['thread_c'] = forum_info.post_num
                        data['follow_c'] = forum_info.member_num
                        data['main_thread_c'] = forum_info.thread_num
                        data['forum_volume'] = f'{forum_info.category} - {forum_info.subcategory}'

                        await asyncio.gather(get_forum_rule(),
                                             get_forum_desp_ex(),
                                             get_sign_info(),
                                             get_forum_bg(),
                                             get_forums_heads(),
                                             get_bawu_infos(),
                                             get_self_forum_head(),
                                             get_user_forum_level_info(),
                                             return_exceptions=True)

                    self.set_main_info_signal.emit(data)
            except Exception as e:
                print(type(e))
                print(e)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()


class ThreadVideoItem(QWidget, thread_video_item.Ui_Form):
    """嵌入在列表的视频贴入口组件"""
    source_link = ''
    length = 0
    view_num = 0
    webview = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.webview_show_html = profile_mgr.video_webview_show_html
        self.pushButton_3.hide()

        self.pushButton.clicked.connect(self.save_video)
        self.pushButton_2.clicked.connect(self.play_video)
        self.pushButton_3.clicked.connect(self.destroy_webview)

    def handle_webview_fullscreen(self):
        if self.webview.isHtmlInFullScreenState():
            self.webview.showFullScreen()
        else:
            self.webview.showNormal()

    def destroy_webview(self):
        self.webview.close()
        self.pushButton_3.hide()
        self.webview.destroyWebview()
        self.webview = None

    def play_video(self):
        if self.webview:
            self.webview.show()
            self.webview.raise_()
            if self.webview.isMinimized():
                self.webview.showNormal()
            if not self.webview.isActiveWindow():
                self.webview.activateWindow()
        else:
            webview2.loadLibs()
            self.webview = webview2.QWebView2View()

            self.webview.resize(920, 530)
            self.webview.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
            self.webview.setWindowTitle('WebView 视频播放器')

            self.webview.titleChanged.connect(self.webview.setWindowTitle)
            self.webview.fullScreenRequested.connect(self.handle_webview_fullscreen)
            self.webview.windowCloseRequested.connect(self.destroy_webview)
            self.webview.renderInitializationCompleted.connect(self.pushButton_3.show)
            self.webview.renderInitializationCompleted.connect(lambda: self.webview.setHtml(self.webview_show_html))

            profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}',
                                              enable_link_hover_text=False,
                                              enable_zoom_factor=False, enable_error_page=True,
                                              enable_context_menu=True, enable_keyboard_keys=True,
                                              handle_newtab_byuser=False, disable_web_safe=True)
            self.webview.setProfile(profile)

            self.webview.initRender()
            self.webview.show()

    def save_video(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择视频保存位置', '', '视频文件 (*.mp4)')
        if path:
            right_link = self.source_link.replace('tb-video.bdstatic.com', 'bos.nj.bpc.baidu.com')
            start_background_thread(http_downloader, (path, right_link))

    def setdatas(self, src, len_, views):
        self.source_link = src
        self.length = len_
        self.view_num = views
        right_link = self.source_link.replace('tb-video.bdstatic.com', 'bos.nj.bpc.baidu.com')
        self.webview_show_html = self.webview_show_html.replace('[vurl]', right_link)

        self.label_3.setText(f'时长 {format_second(len_)}，浏览量 {views}')


class ThreadVoiceItem(QWidget, thread_voice_item.Ui_Form):
    """嵌入在列表的语音贴播放组件"""
    source_link = ''
    length = 0
    play_engine = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.play_engine = audio_stream_player.HttpMp3Player()
        self.label.setPixmap(QPixmap('ui/voice_icon.png').scaled(20, 20, transformMode=Qt.SmoothTransformation))
        self.pushButton_2.hide()

        self.play_engine.playEvent.connect(self.handle_events)
        self.pushButton.clicked.connect(self.start_pause_audio)
        self.pushButton_2.clicked.connect(self.play_engine.stop_play)

        self.destroyed.connect(self.play_engine.stop_play)

    def start_pause_audio(self):
        if not self.play_engine.is_audio_playing():
            self.play_engine.start_play()
        elif not self.play_engine.is_audio_pause():
            self.play_engine.pause_play()
        elif self.play_engine.is_audio_pause():
            self.play_engine.unpause_play()

    def handle_events(self, type_):
        if type_ == audio_stream_player.EventType.PLAY:
            self.pushButton.setText('暂停')
            self.pushButton_2.show()
        elif type_ == audio_stream_player.EventType.PAUSE:
            self.pushButton.setText('继续播放')
        elif type_ == audio_stream_player.EventType.UNPAUSE:
            self.pushButton.setText('暂停')
        elif type_ == audio_stream_player.EventType.STOP:
            self.pushButton.setText('播放')
            self.pushButton_2.hide()

    def setdatas(self, src, len_):
        self.source_link = src
        self.play_engine.mp3_url = src
        self.length = len_
        self.label_3.setText(f'这是一条语音 [时长 {format_second(len_)}]')


class ReplySubComments(QDialog, reply_comments.Ui_Dialog):
    """楼中楼窗口，可查看楼中楼内的回复"""
    isLoading = False
    page = 1
    add_comment = pyqtSignal(dict)
    set_floor_info = pyqtSignal(tuple)

    def __init__(self, bduss, stoken, thread_id, post_id, floor, comment_count, show_thread_button=False):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = thread_id
        self.post_id = post_id
        self.floor_num = floor
        self.comment_count = comment_count

        self.setWindowFlags(Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')

        self.add_comment.connect(self.ui_add_comment)
        self.set_floor_info.connect(self.ui_set_floor_info)
        self.pushButton_2.clicked.connect(self.refresh_comments)
        self.pushButton.clicked.connect(self.open_thread_detail)
        self.listWidget.verticalScrollBar().valueChanged.connect(self.load_from_scroll)
        if not show_thread_button:
            self.pushButton.hide()
        if self.floor_num == -1 and self.comment_count == -2:
            self.label.setText('楼中楼回复')
        else:
            self.label.setText(f'第 {self.floor_num} 楼的回复，共 {self.comment_count} 条')

        self.load_comments_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def open_thread_detail(self):
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id))
        qt_window_mgr.add_window(thread_window)

    def refresh_comments(self):
        if not self.isLoading:
            # 清理内存
            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()

            self.page = 1
            self.load_comments_async()

    def load_from_scroll(self):
        if self.listWidget.verticalScrollBar().value() == self.listWidget.verticalScrollBar().maximum():
            self.load_comments_async()

    def ui_set_floor_info(self, datas):
        if datas[0] == -1:
            QMessageBox.critical(self, '楼中楼加载失败', datas[1], QMessageBox.Ok)
        else:
            self.label.setText(f'第 {datas[0]} 楼的回复，共 {datas[1]} 条')

    def ui_add_comment(self, datas):
        widget = ReplyItem(self.bduss, self.stoken)
        widget.portrait = datas['portrait']
        widget.thread_id = datas['thread_id']
        widget.post_id = datas['post_id']
        if not datas['is_floor']:
            widget.is_comment = True
            if datas['replyobj']:
                widget.set_reply_text(
                    '回复用户 <a href=\"user://{uid}\">{u}</a>: '.format(uid=datas['reply_uid'], u=datas['replyobj']))
            widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], datas['is_author'], datas['content'], [],
                            -1,
                            datas['create_time_str'], '', -1,
                            datas['agree_count'], datas['ulevel'], datas['is_bawu'], voice_info=datas['voice_info'])
        else:
            widget.is_comment = False
            widget.set_reply_text(f'当前楼层信息')
            widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], False, datas['content'],
                            datas['pictures'],
                            datas['floor'],
                            datas['create_time_str'], '', -1, -1, datas['ulevel'], datas['is_bawu'],
                            voice_info=datas['voice_info'])

        item = QListWidgetItem()
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def load_comments_async(self):
        if not self.isLoading and self.page != -1:
            start_background_thread(self.load_comments)

    def load_comments(self):
        async def dosign():
            self.isLoading = True
            try:
                aiotieba.logging.get_logger().info(
                    f'loading sub-replies (thread_id {self.thread_id} post_id {self.post_id} page {self.page})')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    comments = await client.get_comments(self.thread_id, self.post_id, self.page)
                    if comments.err:
                        raise Exception(comments.err)
                    if self.floor_num == -1 and self.comment_count == -2:
                        self.set_floor_info.emit((comments.post.floor, comments.page.total_count))
                    aiotieba.logging.get_logger().info(
                        f'itering sub-replies (thread_id {self.thread_id} post_id {self.post_id} floor {comments.post.floor} page {self.page})')

                    if self.page == 1:
                        # 获取当前楼层信息
                        floor_thread = comments.post
                        content = make_thread_content(floor_thread.contents.objs)
                        portrait = floor_thread.user.portrait
                        user_name = floor_thread.user.nick_name_new
                        time_str = timestamp_to_string(floor_thread.create_time)
                        user_level = floor_thread.user.level
                        is_bawu = floor_thread.user.is_bawu
                        thread_id = floor_thread.tid
                        post_id = floor_thread.pid
                        floor = floor_thread.floor
                        reply_num = comments.page.total_count

                        voice_info = {'have_voice': False, 'src': '', 'length': 0}
                        if floor_thread.contents.voice:
                            voice_info['have_voice'] = True
                            voice_info[
                                'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={floor_thread.contents.voice.md5}&play_from=pb_voice_play'
                            voice_info['length'] = floor_thread.contents.voice.duration

                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                        preview_pixmap = []
                        for j in floor_thread.contents.imgs:
                            # width, height, src, view_src
                            src = j.origin_src
                            view_src = j.src
                            height = j.show_height
                            width = j.show_width
                            preview_pixmap.append(
                                {'width': width, 'height': height, 'src': src, 'view_src': view_src})

                        tdata = {'is_floor': True, 'content': content, 'portrait': portrait, 'user_name': user_name,
                                 'user_portrait_pixmap': user_head_pixmap,
                                 'create_time_str': time_str, 'ulevel': user_level, 'is_bawu': is_bawu,
                                 'thread_id': thread_id, 'post_id': post_id, 'voice_info': voice_info,
                                 'pictures': preview_pixmap, 'floor': floor, 'reply_num': reply_num}

                        self.add_comment.emit(tdata)

                    for t in comments.objs:
                        content = make_thread_content(t.contents.objs)
                        portrait = t.user.portrait
                        user_name = t.user.nick_name_new
                        agree_num = t.agree
                        time_str = timestamp_to_string(t.create_time)
                        user_level = t.user.level
                        is_author = t.is_thread_author
                        is_bawu = t.user.is_bawu
                        thread_id = t.tid
                        post_id = t.pid
                        be_replied_user = ''
                        replyer_uid = 0
                        if t.reply_to_id != 0:
                            uinfo = await client.get_user_info(t.reply_to_id, aiotieba.ReqUInfo.NICK_NAME)
                            be_replied_user = uinfo.nick_name_new
                            replyer_uid = t.reply_to_id

                        voice_info = {'have_voice': False, 'src': '', 'length': 0}
                        if t.contents.voice:
                            voice_info['have_voice'] = True
                            voice_info[
                                'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={t.contents.voice.md5}&play_from=pb_voice_play'
                            voice_info['length'] = t.contents.voice.duration

                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                        tdata = {'is_floor': False, 'content': content, 'portrait': portrait, 'user_name': user_name,
                                 'user_portrait_pixmap': user_head_pixmap,
                                 'agree_count': agree_num,
                                 'create_time_str': time_str, 'is_author': is_author, 'ulevel': user_level,
                                 'replyobj': be_replied_user, 'reply_uid': replyer_uid, 'is_bawu': is_bawu,
                                 'thread_id': thread_id, 'post_id': post_id, 'voice_info': voice_info}

                        self.add_comment.emit(tdata)
            except Exception as e:
                print(type(e))
                print(e)
                self.set_floor_info.emit((-1, str(e)))
            else:
                if comments.has_more:
                    self.page += 1
                else:
                    self.page = -1
                aiotieba.logging.get_logger().info(
                    f'load sub-replies (thread_id {self.thread_id} post_id {self.post_id}) finished and page changed to {self.page}')
            finally:
                self.isLoading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()


class AgreedThreadItem(QWidget, agreed_item.Ui_Form):
    """互动列表中被点赞的内容"""
    portrait = ''
    thread_id = -1
    post_id = -1
    is_post = False
    setPicture = pyqtSignal(QPixmap)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.label_10.setContextMenuPolicy(Qt.NoContextMenu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_10.linkActivated.connect(self.handle_link_event)
        self.pushButton.clicked.connect(self.show_subcomment_window)
        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器
        self.setPicture.connect(self.label_2.setPixmap)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease and source in (
                self.label_3, self.label_4):
            self.open_user_homepage(self.portrait)
        return super(AgreedThreadItem, self).eventFilter(source, event)  # 照常处理事件

    def show_subcomment_window(self):
        if self.is_post:
            fwindow = ReplySubComments(self.bduss, self.stoken, self.thread_id, self.post_id, -1, -1,
                                       show_thread_button=True)
        else:
            fwindow = ThreadDetailView(self.bduss, self.stoken, self.thread_id)
        qt_window_mgr.add_window(fwindow)

    def open_ba_detail(self, fid):
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(fid))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def open_thread(self, tid):
        third_party_thread = ThreadDetailView(self.bduss, self.stoken, int(tid))
        qt_window_mgr.add_window(third_party_thread)

    def open_user_homepage(self, uid):
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def handle_link_event(self, url):
        if url.startswith('user://'):
            user_sign = url.replace('user://', '')
            # 判断是不是portrait
            if not user_sign.startswith('tb.'):
                self.open_user_homepage(int(user_sign))
            else:
                self.open_user_homepage(user_sign)
        elif url.startswith('tieba_thread://'):
            self.open_thread(url.replace('tieba_thread://', ''))
        elif url.startswith('tieba_forum://'):
            self.open_ba_detail(url.replace('tieba_forum://', ''))
        else:
            open_url_in_browser(url)

    def load_picture(self, url):
        resp = requests.get(url, headers=request_mgr.header)
        if resp.content:
            pixmap = QPixmap()
            pixmap.loadFromData(resp.content)
            pixmap = pixmap.scaled(100, 100, transformMode=Qt.SmoothTransformation, aspectRatioMode=Qt.KeepAspectRatio)
            self.setPicture.emit(pixmap)

    def setdatas(self, uicon: QPixmap, uname: str, text: str, pixmap_link: str, timestr: str, toptext: str):
        self.label_4.setPixmap(uicon)
        self.label_3.setText(uname)
        self.label.setText(timestr)
        self.label_6.setText(text)
        self.label_10.setText(toptext)
        if pixmap_link:
            self.label_2.setFixedHeight(100)
            start_background_thread(self.load_picture, (pixmap_link,))
        else:
            self.label_2.hide()

        self.adjustSize()


class ReplyItem(QWidget, comment_view.Ui_Form):
    """嵌入在列表里的回复贴内容"""
    height_count = 0
    portrait = ''
    c_count = -1
    floor = -1
    thread_id = -1
    post_id = -1
    flash_timer_count = 0
    replyWindow = None
    allow_home_page = True
    subcomment_show_thread_button = False
    agree_num = 0
    is_comment = False
    agree_thread_signal = pyqtSignal(str)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.label_13.hide()
        self.label_10.hide()
        self.listWidget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.label_10.setContextMenuPolicy(Qt.NoContextMenu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_10.linkActivated.connect(self.handle_link_event)
        self.pushButton.clicked.connect(self.show_subcomment_window)
        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器
        self.pushButton_3.clicked.connect(self.agree_thread_async)
        self.agree_thread_signal.connect(self.agree_thread_ok_action)

        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(200)
        self.flash_timer.timeout.connect(self.handle_flash_timer_event)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease and source in (
                self.label_3, self.label_4) and self.allow_home_page:
            self.open_user_homepage(self.portrait)
        return super(ReplyItem, self).eventFilter(source, event)  # 照常处理事件

    def mouseDoubleClickEvent(self, a0):
        if not self.flash_timer_count:
            self.flash_timer_count = 1
            self.flash_timer.start()
            self.label_6.setStyleSheet('QWidget{background-color: rgb(71, 71, 255);}')

    def agree_thread_ok_action(self, isok):
        self.pushButton_3.setText(str(self.agree_num) + ' 个赞')
        if isok == '[ALREADY_AGREE]':
            if QMessageBox.information(self, '已经点过赞了', '你已经点过赞了，是否要取消点赞？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.agree_thread_async(True)
        else:
            QMessageBox.information(self, '点赞操作完成', isok)

    def agree_thread_async(self, is_cancel=False):
        start_background_thread(self.agree_thread, (is_cancel,))

    def agree_thread(self, iscancel=False):
        aiotieba.logging.get_logger().info(f'agree reply/comment {self.post_id} in thread {self.thread_id}')
        try:
            if not self.bduss:
                self.agree_thread_signal.emit('你还没有登录，登录后即可为这条回复点赞。')
            elif self.portrait == '00000000':
                self.agree_thread_signal.emit('不能给匿名用户点赞。')
            else:
                account = aiotieba.Account()  # 实例化account以便计算一些数据
                # 拿tbs
                tsb_resp = request_mgr.run_post_api('/c/s/login', request_mgr.calc_sign(
                    {'_client_version': request_mgr.TIEBA_CLIENT_VERSION, 'bdusstoken': self.bduss}),
                                                    use_mobile_header=True, host_type=2)
                tbs = tsb_resp["anti"]["tbs"]

                if iscancel:
                    payload = {
                        'BDUSS': self.bduss,
                        '_client_type': "2",
                        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                        'agree_type': "5",  # 2点赞 5取消点赞
                        'cuid': account.cuid_galaxy2,
                        'obj_type': 2 if self.is_comment else 1,  # 1回复贴 2楼中楼 3主题贴
                        'op_type': "1",  # 0点赞 1取消点赞
                        'post_id': str(self.post_id),
                        'stoken': self.stoken,
                        'tbs': tbs,
                        'thread_id': str(self.thread_id),
                    }

                    response = request_mgr.run_post_api('/c/c/agree/opAgree', payloads=request_mgr.calc_sign(payload),
                                                        use_mobile_header=True, bduss=self.bduss, stoken=self.stoken,
                                                        host_type=2)
                    if int(response['error_code']) == 0:
                        self.agree_num -= 1
                        self.agree_thread_signal.emit('取消点赞成功。')
                    else:
                        self.agree_thread_signal.emit(response['error_msg'])
                else:
                    payload = {
                        'BDUSS': self.bduss,
                        '_client_type': "2",
                        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                        'agree_type': "2",  # 2点赞 5取消点赞
                        'cuid': account.cuid_galaxy2,
                        'obj_type': 2 if self.is_comment else 1,  # 1回复贴 2楼中楼 3主题贴
                        'op_type': "0",  # 0点赞 1取消点赞
                        'post_id': str(self.post_id),
                        'stoken': self.stoken,
                        'tbs': tbs,
                        'thread_id': str(self.thread_id),
                    }

                    response = request_mgr.run_post_api('/c/c/agree/opAgree', payloads=request_mgr.calc_sign(payload),
                                                        use_mobile_header=True, bduss=self.bduss, stoken=self.stoken,
                                                        host_type=2)
                    if int(response['error_code']) == 0:
                        self.agree_num += 1
                        is_expa2 = bool(int(response["data"]["agree"]["is_first_agree"]))
                        self.agree_thread_signal.emit(f'{"点赞成功，本吧首赞经验 +2" if is_expa2 else "点赞成功"}。')
                    elif int(response['error_code']) == 3280001:
                        self.agree_thread_signal.emit('[ALREADY_AGREE]')
                    else:
                        self.agree_thread_signal.emit(response['error_msg'])

        except Exception as e:
            print(type(e))
            print(e)
            self.agree_thread_signal.emit('程序内部出错，请重试')

    def handle_flash_timer_event(self):
        if self.flash_timer_count == 6:
            self.flash_timer.stop()
            self.flash_timer_count = -1
        elif self.flash_timer_count % 2 == 1:
            self.label_6.setStyleSheet('')
        else:
            self.label_6.setStyleSheet('QWidget{background-color: rgb(71, 71, 255);}')
        self.flash_timer_count += 1

    def show_subcomment_window(self):
        if self.c_count != 0:
            if not self.replyWindow:
                self.replyWindow = ReplySubComments(self.bduss, self.stoken, self.thread_id, self.post_id, self.floor,
                                                    self.c_count, show_thread_button=self.subcomment_show_thread_button)
            self.replyWindow.show()
            self.replyWindow.raise_()
            if self.replyWindow.isMinimized():
                self.replyWindow.showNormal()
            if not self.replyWindow.isActiveWindow():
                self.replyWindow.activateWindow()
        else:
            QMessageBox.information(self, '暂无回复', f'第 {self.floor} 楼还没有任何回复。', QMessageBox.Ok)

    def update_listwidget_size(self, h):
        # 动态更新内容列表大小
        self.height_count += h
        self.listWidget.setFixedHeight(self.height_count)

    def open_ba_detail(self, fid):
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(fid))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def open_thread(self, tid):
        third_party_thread = ThreadDetailView(self.bduss, self.stoken, int(tid))
        qt_window_mgr.add_window(third_party_thread)

    def open_user_homepage(self, uid):
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def handle_link_event(self, url):
        if url.startswith('user://'):
            user_sign = url.replace('user://', '')
            # 判断是不是portrait
            if not user_sign.startswith('tb.'):
                self.open_user_homepage(int(user_sign))
            else:
                self.open_user_homepage(user_sign)
        elif url.startswith('tieba_thread://'):
            self.open_thread(url.replace('tieba_thread://', ''))
        elif url.startswith('tieba_forum://'):
            self.open_ba_detail(url.replace('tieba_forum://', ''))
        else:
            open_url_in_browser(url)

    def set_grow_level(self, level):
        self.label_13.show()
        self.label_13.setText('Lv.' + str(level))

    def set_reply_text(self, t):
        self.label_10.show()
        self.label_10.setText(t)

    def setdatas(self, uicon: QPixmap, uname: str, islz: bool, text: str, pixmaps: list, floor: int, timestr: str,
                 ip: str, reply_count: int, agree_count: int, level: int, isbawu: bool, voice_info=None):
        if voice_info is None:
            voice_info = {'have_voice': False}

        self.label_4.setPixmap(uicon)
        self.label_3.setText(uname)

        text_ = ''
        is_high_agree = floor == 0
        if floor != -1 and floor:
            self.floor = floor
            text_ += f'第 {"高赞回答楼" if is_high_agree else floor} 楼 | '
        if timestr:
            text_ += f'{timestr} | '
        if ip and not profile_mgr.local_config['thread_view_settings']['hide_ip']:
            text_ += f'IP 属地 {ip} | '
        self.label.setText(text_[:-3])

        if reply_count == -1:
            self.pushButton.hide()
        else:
            self.c_count = reply_count
            if reply_count == -2:
                self.pushButton.setText('查看楼中楼')
            else:
                self.pushButton.setText(f'查看楼中楼 ({reply_count})')
        if agree_count != -1:
            self.agree_num = agree_count
            self.pushButton_3.setText(f'{agree_count} 个赞')
        else:
            self.pushButton_3.hide()
        if not text:
            self.label_6.hide()
        else:
            self.label_6.setText(text)
        if islz:
            self.label_8.show()
        else:
            self.label_8.hide()
        if isbawu:
            self.label_11.show()
        else:
            self.label_11.hide()

        if level == -1:
            self.label_9.hide()
        else:
            self.label_9.setText(f'Lv.{level}')
            qss = ''
            if 0 <= level <= 3:  # 绿牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 211, 171);}'
            elif 4 <= level <= 9:  # 蓝牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 161, 255);}'
            elif 10 <= level <= 15:  # 黄牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(253, 194, 53);}'
            elif level >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48);}'

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss

        if not pixmaps and not voice_info['have_voice']:
            self.listWidget.hide()
        else:
            for i in pixmaps:
                label = ThreadPictureLabel(i['width'], i['height'], i['src'], i['view_src'])

                item = QListWidgetItem()
                item.setSizeHint(label.size())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, label)

                self.update_listwidget_size(i['height'] + 35)

            if voice_info['have_voice']:
                voice_widget = ThreadVoiceItem()
                voice_widget.setdatas(voice_info['src'], voice_info['length'])
                item = QListWidgetItem()
                item.setSizeHint(voice_widget.size())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, voice_widget)
                self.update_listwidget_size(voice_widget.height())

        self.adjustSize()


class ThreadDetailView(QWidget, tie_detail_view.Ui_Form):
    """主题贴详情窗口，可以浏览主题贴详细内容和回复"""
    first_floor_pid = -1
    forum_id = -1
    user_id = -1
    height_count = 0
    height_count_replies = 0
    width_count_replies = 0
    reply_page = 1
    agree_num = 0
    is_getting_replys = False
    head_data_signal = pyqtSignal(dict)
    add_reply = pyqtSignal(dict)
    show_reply_end_text = pyqtSignal(int)
    store_thread_signal = pyqtSignal(str)
    agree_thread_signal = pyqtSignal(str)
    add_post_signal = pyqtSignal(str)

    def __init__(self, bduss, stoken, tid, is_treasure=False, is_top=False):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = tid
        self.is_treasure = is_treasure
        self.is_top = is_top

        self.label_2.hide()
        self.label_8.hide()
        self.label_11.hide()
        self.label_12.hide()
        self.label_13.hide()
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget_4.setStyleSheet('QListWidget{outline:0px;}'
                                        'QListWidget::item:hover {color:white; background-color:white;}'
                                        'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget_4.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget_4.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.label_2.setContextMenuPolicy(Qt.NoContextMenu)
        self.comboBox.setCurrentIndex(profile_mgr.local_config['thread_view_settings']['default_sort'])
        self.checkBox.setChecked(profile_mgr.local_config['thread_view_settings']['enable_lz_only'])
        self.init_load_flash()

        self.pushButton.clicked.connect(self.init_more_menu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.head_data_signal.connect(self.update_ui_head_info)
        self.pushButton_2.clicked.connect(self.open_ba_detail)
        self.add_reply.connect(self.add_reply_ui)
        self.show_reply_end_text.connect(self.show_end_reply_ui)
        self.store_thread_signal.connect(self.store_thread_ok_action)
        self.agree_thread_signal.connect(self.agree_thread_ok_action)
        self.add_post_signal.connect(self.add_post_ok_action)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.load_sub_threads_from_scroll)
        self.comboBox.currentIndexChanged.connect(self.load_sub_threads_refreshly)
        self.checkBox.stateChanged.connect(self.load_sub_threads_refreshly)
        self.label_2.linkActivated.connect(self.end_label_link_event)
        self.pushButton_4.clicked.connect(self.agree_thread_async)
        self.pushButton_3.clicked.connect(self.add_post_async)
        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器

        self.flash_shower.show()
        self.get_thread_head_info_async()
        self.get_sub_thread_async()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease and source in (
                self.label_3, self.label_4):
            self.open_user_homepage(self.user_id)
        return super(ThreadDetailView, self).eventFilter(source, event)  # 照常处理事件

    def closeEvent(self, a0):
        self.flash_shower.hide()
        a0.accept()
        if self.listWidget.count() == 1:
            widget = self.listWidget.itemWidget(self.listWidget.item(0))
            if isinstance(widget, ThreadVideoItem):
                if widget.webview:
                    widget.destroy_webview()

        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)

    def end_label_link_event(self, url):
        if url == 'reload_replies':
            self.load_sub_threads_refreshly()

    def init_more_menu(self):
        url = f'https://tieba.baidu.com/p/{self.thread_id}'

        menu = QMenu()

        copy_id = QAction('复制贴子 ID', self)
        copy_id.triggered.connect(lambda: pyperclip.copy(str(self.thread_id)))
        menu.addAction(copy_id)

        copy_link = QAction('复制贴子链接', self)
        copy_link.triggered.connect(lambda: pyperclip.copy(url))
        menu.addAction(copy_link)

        open_link = QAction('在浏览器中打开贴子', self)
        open_link.triggered.connect(lambda: open_url_in_browser(url))
        menu.addAction(open_link)

        menu.addSeparator()

        store_thread = QAction('收藏', self)
        store_thread.triggered.connect(self.store_thread_async)
        menu.addAction(store_thread)

        cancel_store_thread = QAction('取消收藏', self)
        cancel_store_thread.triggered.connect(lambda: self.store_thread_async(True))
        menu.addAction(cancel_store_thread)

        if not self.bduss:  # 在未登录时不显示收藏按钮
            store_thread.setVisible(False)
            cancel_store_thread.setVisible(False)

        bt_pos = self.pushButton.mapToGlobal(QPoint(0, 0))
        menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.pushButton.height()))

    def open_thread(self, tid):
        third_party_thread = ThreadDetailView(self.bduss, self.stoken, int(tid))
        qt_window_mgr.add_window(third_party_thread)

    def open_user_homepage(self, uid):
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def handle_link_event(self, url):
        if url.startswith('user://'):
            user_sign = url.replace('user://', '')
            # 判断是不是portrait
            if not user_sign.startswith('tb.'):
                self.open_user_homepage(int(user_sign))
            else:
                self.open_user_homepage(user_sign)
        elif url.startswith('tieba_thread://'):
            self.open_thread(url.replace('tieba_thread://', ''))
        else:
            open_url_in_browser(url)

    def add_post_ok_action(self, isok):
        if not isok:
            self.lineEdit.setText('')
            self.comboBox.setCurrentIndex(1)
            QMessageBox.information(self, '回贴成功', '回复贴发送成功。')
        else:
            QMessageBox.information(self, '回贴失败', isok)

    def add_post_async(self):
        if not self.lineEdit.text():
            QMessageBox.information(self, '提示', '请输入内容后再回贴。')
        elif not self.bduss:
            QMessageBox.information(self, '提示', '目前处于游客状态，请登录后再回贴。')
        else:
            show_string = ('回复功能目前还处于测试阶段。\n'
                           '使用本软件回贴可能会遇到发贴失败等情况，甚至可能导致你的账号被永久全吧封禁。\n'
                           '目前我们不建议使用此方法进行回贴，我们建议你使用官方网页版进行回贴。\n确认要继续吗？')
            msgbox = QMessageBox(QMessageBox.Warning, '回贴风险提示', show_string, parent=self)
            msgbox.setStandardButtons(QMessageBox.Help | QMessageBox.Yes | QMessageBox.No)
            msgbox.button(QMessageBox.Help).setText("去网页发贴")
            msgbox.button(QMessageBox.Yes).setText("无视风险，继续发贴")
            msgbox.button(QMessageBox.No).setText("取消发贴")
            r = msgbox.exec()
            flag = r == QMessageBox.Yes
            if r == QMessageBox.Help:
                url = f'https://tieba.baidu.com/p/{self.thread_id}'
                open_url_in_browser(url)

            if flag:
                start_background_thread(self.add_post)

    def add_post(self):
        async def dopost():
            try:
                aiotieba.logging.get_logger().info(f'post thread {self.thread_id}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    result = await client.add_post(self.forum_id, self.thread_id, self.lineEdit.text())
                    if result:
                        self.add_post_signal.emit('')
                    else:
                        self.add_post_signal.emit(str(result.err))
            except Exception as e:
                print(type(e))
                print(e)
                self.add_post_signal.emit('程序内部出错，请重试')

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dopost())

        start_async()

    def agree_thread_ok_action(self, isok):
        self.pushButton_4.setText(str(self.agree_num) + ' 个赞')
        if isok == '[ALREADY_AGREE]':
            if QMessageBox.information(self, '已经点过赞了', '你已经点过赞了，是否要取消点赞？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.agree_thread_async(True)
        else:
            QMessageBox.information(self, '点赞操作完成', isok)

    def agree_thread_async(self, is_cancel=False):
        start_background_thread(self.agree_thread, (is_cancel,))

    def agree_thread(self, iscancel=False):
        aiotieba.logging.get_logger().info(f'agree thread {self.thread_id}')
        try:
            if not self.bduss:
                self.agree_thread_signal.emit('你还没有登录，登录后即可为贴子点赞。')
            elif self.user_id == 0:
                self.agree_thread_signal.emit('不能给匿名用户点赞。')
            else:
                account = aiotieba.Account()  # 实例化account以便计算一些数据
                # 拿tbs
                tsb_resp = request_mgr.run_post_api('/c/s/login', request_mgr.calc_sign(
                    {'_client_version': request_mgr.TIEBA_CLIENT_VERSION, 'bdusstoken': self.bduss}),
                                                    use_mobile_header=True, host_type=2)
                tbs = tsb_resp["anti"]["tbs"]

                if iscancel:
                    payload = {
                        'BDUSS': self.bduss,
                        '_client_type': "2",
                        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                        'agree_type': "5",  # 2点赞 5取消点赞
                        'cuid': account.cuid_galaxy2,
                        'forum_id': str(self.forum_id),
                        'obj_type': "3",  # 1回复贴 2楼中楼 3主题贴
                        'op_type': "1",  # 0点赞 1取消点赞
                        'post_id': str(self.first_floor_pid),
                        'stoken': self.stoken,
                        'tbs': tbs,
                        'thread_id': str(self.thread_id),
                    }

                    response = request_mgr.run_post_api('/c/c/agree/opAgree', payloads=request_mgr.calc_sign(payload),
                                                        use_mobile_header=True, bduss=self.bduss, stoken=self.stoken,
                                                        host_type=2)
                    if int(response['error_code']) == 0:
                        self.agree_num -= 1
                        self.agree_thread_signal.emit('取消点赞成功。')
                    else:
                        self.agree_thread_signal.emit(response['error_msg'])
                else:
                    payload = {
                        'BDUSS': self.bduss,
                        '_client_type': "2",
                        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                        'agree_type': "2",  # 2点赞 5取消点赞
                        'cuid': account.cuid_galaxy2,
                        'forum_id': str(self.forum_id),
                        'obj_type': "3",  # 1回复贴 2楼中楼 3主题贴
                        'op_type': "0",  # 0点赞 1取消点赞
                        'post_id': str(self.first_floor_pid),
                        'stoken': self.stoken,
                        'tbs': tbs,
                        'thread_id': str(self.thread_id),
                    }

                    response = request_mgr.run_post_api('/c/c/agree/opAgree', payloads=request_mgr.calc_sign(payload),
                                                        use_mobile_header=True, bduss=self.bduss, stoken=self.stoken,
                                                        host_type=2)
                    if int(response['error_code']) == 0:
                        self.agree_num += 1
                        is_expa2 = bool(int(response["data"].get("agree", {"is_first_agree": False})["is_first_agree"]))
                        self.agree_thread_signal.emit(f'{"点赞成功，本吧首赞经验 +2" if is_expa2 else "点赞成功"}。')
                    elif int(response['error_code']) == 3280001:
                        self.agree_thread_signal.emit('[ALREADY_AGREE]')
                    else:
                        self.agree_thread_signal.emit(response['error_msg'])

        except Exception as e:
            print(type(e))
            print(e)
            self.agree_thread_signal.emit('程序内部出错，请重试')

    def store_thread_ok_action(self, isok):
        QMessageBox.information(self, '操作完成', isok)

    def store_thread_async(self, is_cancel=False):
        item = self.listWidget_4.currentItem()
        if not item:
            # 没有回贴就使用第一楼的pid
            pid = self.first_floor_pid
            floor = 1
        else:
            reply_widget = self.listWidget_4.itemWidget(item)
            pid = reply_widget.post_id
            floor = reply_widget.floor
        start_background_thread(self.store_thread, (pid, is_cancel, floor))

    def store_thread(self, current_post_id: int, is_cancel=False, floor=-1):
        async def dosign():
            aiotieba.logging.get_logger().info(f'store thread {self.thread_id}')
            try:
                if not is_cancel:
                    # 客户端收藏接口
                    data = "[{\"tid\":\"[tid]\",\"pid\":\"[pid]\",\"status\":1}]"
                    data = data.replace('[tid]', str(self.thread_id))
                    data = data.replace('[pid]', str(current_post_id))
                    payload = {
                        'BDUSS': self.bduss,
                        '_client_type': "2",
                        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                        'data': data,
                        'stoken': self.stoken,
                    }
                    result = request_mgr.run_post_api('/c/c/post/addstore', request_mgr.calc_sign(payload),
                                                      bduss=self.bduss,
                                                      stoken=self.stoken, use_mobile_header=True, host_type=2)
                    if result['error_code'] == '0':
                        self.store_thread_signal.emit(f'贴子已成功收藏到第 {floor} 楼，你可以在 ⌈我的收藏⌋ 中查看贴子。')
                    else:
                        self.store_thread_signal.emit(result['error_msg'])
                else:
                    # wap版取消收藏接口
                    payload = {
                        '_client_type': "2",
                        '_client_version': "12.64.0",
                        'subapp_type': "newwise",
                        'tid': str(self.thread_id),
                        'pid': str(current_post_id)
                    }
                    result = request_mgr.run_post_api('/mo/q/post_rmstore', request_mgr.calc_sign(payload),
                                                      bduss=self.bduss,
                                                      stoken=self.stoken, use_mobile_header=True)
                    if result['no'] == 0:
                        self.store_thread_signal.emit('贴子已成功取消收藏。')
                    else:
                        self.store_thread_signal.emit(result['error'])
            except Exception as e:
                print(type(e))
                print(e)
                self.store_thread_signal.emit('程序内部出错，请重试')

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def load_sub_threads_refreshly(self):
        if not self.is_getting_replys:
            # 清理内存
            self.listWidget_4.clear()
            QPixmapCache.clear()
            gc.collect()

            # 初始化值
            if self.comboBox.currentIndex() == 1:
                self.reply_page = -2
            else:
                self.reply_page = 1
            self.height_count_replies = 0
            self.width_count_replies = 0

            # 启动刷新
            self.get_sub_thread_async()

    def load_sub_threads_from_scroll(self):
        if self.scrollArea.verticalScrollBar().value() == self.scrollArea.verticalScrollBar().maximum():
            self.get_sub_thread_async()

    def open_ba_detail(self):
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def update_listwidget_size(self, h):
        self.height_count += h
        self.listWidget.setFixedHeight(self.height_count)

    def show_end_reply_ui(self, v):
        self.label_2.show()
        if self.listWidget_4.count() == 0:
            self.listWidget_4.setMinimumHeight(0)
        if v == 0:
            self.label_2.setText('你已经到达了贴子的尽头')
        elif v == 1:
            self.label_2.setText('还没有人回贴，别让楼主寂寞太久')
        elif v == 2:
            self.label_2.setText('服务器开小差了，请试试 <a href="reload_replies">重新加载</a>')

    def add_reply_ui(self, datas):
        # tdata = {'content': content, 'portrait': portrait, 'user_name': user_name,
        #          'user_portrait_pixmap': user_head_pixmap, 'view_pixmap': preview_pixmap,
        #          'agree_count': agree_num,
        #          'create_time_str': time_str, 'user_ip': user_ip, 'is_author': is_author,
        #          'floor': floor, 'reply_num': reply_num}
        item = QListWidgetItem()
        widget = ReplyItem(self.bduss, self.stoken)
        widget.portrait = datas['portrait']
        widget.is_comment = False
        widget.thread_id = self.thread_id
        widget.post_id = datas['post_id']
        widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], datas['is_author'], datas['content'],
                        datas['view_pixmap'],
                        datas['floor'], datas['create_time_str'], datas['user_ip'], datas['reply_num'],
                        datas['agree_count'], datas['ulevel'], datas['is_bawu'], voice_info=datas['voice_info'])
        widget.set_grow_level(datas['grow_level'])
        item.setSizeHint(widget.size())
        self.listWidget_4.addItem(item)
        self.listWidget_4.setItemWidget(item, widget)

        self.height_count_replies += widget.height()
        self.listWidget_4.setMinimumHeight(self.height_count_replies)

        if widget.width() > self.width_count_replies:
            self.width_count_replies = widget.width()
            self.listWidget_4.setMinimumWidth(self.width_count_replies)

    def get_sub_thread_async(self):
        if not self.is_getting_replys and self.reply_page != -1:
            self.label_2.hide()
            self.listWidget_4.show()
            start_background_thread(self.get_sub_thread)

    def get_sub_thread(self):
        async def dosign():
            aiotieba.logging.get_logger().info(f'loading thread {self.thread_id} replies list page {self.reply_page}')
            self.is_getting_replys = True
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    sort_type = aiotieba.PostSortType.ASC if self.comboBox.currentIndex() == 0 else (
                        aiotieba.PostSortType.DESC if self.comboBox.currentIndex() == 1 else aiotieba.PostSortType.HOT)
                    if self.reply_page == -2:
                        # 倒序查看时要从总页数开始
                        page_thread_info = await client.get_posts(self.thread_id, pn=1, sort=sort_type,
                                                                  only_thread_author=self.checkBox.isChecked(),
                                                                  comment_rn=0)
                        if page_thread_info.err:
                            raise Exception(page_thread_info.err)
                        self.reply_page = page_thread_info.page.total_page

                    thread_info = await client.get_posts(self.thread_id, pn=self.reply_page, sort=sort_type,
                                                         only_thread_author=self.checkBox.isChecked(), comment_rn=0)
                    if thread_info.err:
                        raise Exception(thread_info.err)
                    if thread_info.thread.reply_num == 1:
                        self.reply_page = -1
                        self.show_reply_end_text.emit(1)
                    else:
                        aiotieba.logging.get_logger().info(
                            f'itering thread {self.thread_id} replies list page {self.reply_page}')
                        for t in thread_info.objs:
                            if t.floor == 1:  # 跳过第一楼
                                continue

                            content = make_thread_content(t.contents.objs)
                            floor = t.floor
                            reply_num = t.reply_num
                            portrait = t.user.portrait
                            user_name = t.user.nick_name_new
                            agree_num = t.agree
                            time_str = timestamp_to_string(t.create_time)
                            user_ip = t.user.ip
                            user_level = t.user.level
                            user_ip = user_ip if user_ip else '未知'
                            is_author = t.is_thread_author
                            post_id = t.pid
                            is_bawu = t.user.is_bawu
                            grow_level = t.user.glevel

                            voice_info = {'have_voice': False, 'src': '', 'length': 0}
                            if t.contents.voice:
                                voice_info['have_voice'] = True
                                voice_info[
                                    'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={t.contents.voice.md5}&play_from=pb_voice_play'
                                voice_info['length'] = t.contents.voice.duration

                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                            user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            preview_pixmap = []
                            for j in t.contents.imgs:
                                # width, height, src, view_src
                                src = j.origin_src
                                view_src = j.src
                                height = j.show_height
                                width = j.show_width
                                preview_pixmap.append(
                                    {'width': width, 'height': height, 'src': src, 'view_src': view_src})

                            tdata = {'content': content, 'portrait': portrait, 'user_name': user_name,
                                     'user_portrait_pixmap': user_head_pixmap, 'view_pixmap': preview_pixmap,
                                     'agree_count': agree_num,
                                     'create_time_str': time_str, 'user_ip': user_ip, 'is_author': is_author,
                                     'floor': floor, 'reply_num': reply_num, 'ulevel': user_level, 'post_id': post_id,
                                     'is_bawu': is_bawu, 'grow_level': grow_level, 'voice_info': voice_info}

                            self.add_reply.emit(tdata)

                        aiotieba.logging.get_logger().info(
                            f'load thread {self.thread_id} replies list page {self.reply_page} ok')

                        if sort_type == aiotieba.PostSortType.DESC:  # 在倒序查看时要递减页数
                            self.reply_page -= 1
                        else:
                            self.reply_page += 1
                        if not thread_info.page.has_more:
                            self.reply_page = -1
                            self.show_reply_end_text.emit(0)

            except Exception as e:
                print(type(e))
                print(e)
                if not isinstance(e, RuntimeError):
                    self.show_reply_end_text.emit(2)
            finally:
                self.is_getting_replys = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def update_ui_head_info(self, datas):
        if datas['err_info']:
            QMessageBox.critical(self, '贴子加载失败', datas['err_info'], QMessageBox.Ok)
            self.close()
        else:
            self.flash_shower.hide()
            if self.forum_id != 0:
                self.setWindowTitle(datas['title'] + ' - ' + datas['forum_name'] + '吧')
                self.pushButton_2.setText(datas['forum_name'] + '吧')
                self.pushButton_2.setIcon(QIcon(datas['forum_pixmap']))
            else:
                self.setWindowTitle(datas['title'] + ' - 贴吧动态')
                self.pushButton_2.hide()
            self.pushButton_4.setText(str(datas['agree_count']) + ' 个赞')
            self.label_4.setPixmap(datas['user_portrait_pixmap'])
            self.label_3.setText(datas['user_name'])
            if profile_mgr.local_config['thread_view_settings']['hide_ip']:
                self.label.setText(datas['create_time_str'])
            else:
                self.label.setText('{time} | IP 属地 {ip}'.format(time=datas['create_time_str'], ip=datas['user_ip']))
            self.label_5.setText(datas['title'])
            self.label_6.setText(datas['content'])
            self.label_10.setText('Lv.' + str(datas['user_grow_level']))
            self.label_7.setText('共 {n} 条回复'.format(n=str(datas['post_num'])))
            if datas['is_forum_manager']:
                self.label_11.show()
            if not datas['title']:
                self.label_5.hide()
            if not datas['content']:
                self.label_6.hide()

            if datas['is_help']:
                self.label_8.show()
            else:
                self.horizontalLayout_2.removeWidget(self.label_8)
            if self.is_treasure:
                self.label_13.show()
            else:
                self.horizontalLayout_2.removeWidget(self.label_13)
            if self.is_top:
                self.label_12.show()
            else:
                self.horizontalLayout_2.removeWidget(self.label_12)
            if not self.label_8.isVisible() and not self.label_12.isVisible() and not self.label_13.isVisible():
                self.gridLayout.setHorizontalSpacing(0)

            self.label_9.setText('Lv.{0}'.format(datas['uf_level']))
            qss = ''
            if 0 <= datas['uf_level'] <= 3:  # 绿牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 211, 171);}'
            elif 4 <= datas['uf_level'] <= 9:  # 蓝牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 161, 255);}'
            elif 10 <= datas['uf_level'] <= 15:  # 黄牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(253, 194, 53);}'
            elif datas['uf_level'] >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48);}'

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss

            if not datas['view_pixmap'] and not datas['video_info']['have_video'] and not datas['voice_info'][
                'have_voice'] and not datas['repost_info']['have_repost']:
                self.listWidget.hide()
            else:
                if datas['video_info']['have_video']:
                    video_widget = ThreadVideoItem()
                    video_widget.setdatas(datas['video_info']['src'], datas['video_info']['length'],
                                          datas['video_info']['view'])
                    item = QListWidgetItem()
                    item.setSizeHint(video_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, video_widget)
                    self.update_listwidget_size(video_widget.height() + 5)

                if datas['voice_info']['have_voice']:
                    voice_widget = ThreadVoiceItem()
                    voice_widget.setdatas(datas['voice_info']['src'], datas['voice_info']['length'])
                    item = QListWidgetItem()
                    item.setSizeHint(voice_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, voice_widget)
                    self.update_listwidget_size(voice_widget.height())

                for i in datas['view_pixmap']:
                    label = ThreadPictureLabel(i['width'], i['height'], i['src'], i['view_src'])

                    item = QListWidgetItem()
                    item.setSizeHint(label.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, label)

                    self.update_listwidget_size(i['height'] + 35)

                if datas['repost_info']['have_repost']:
                    repost_widget = ThreadView(self.bduss, datas['repost_info']['thread_id'],
                                               datas['repost_info']['forum_id'], self.stoken)
                    repost_widget.set_infos(datas['repost_info']['author_portrait_pixmap'],
                                            datas['repost_info']['author_name'], datas['repost_info']['title'],
                                            datas['repost_info']['content'], None, datas['repost_info']['forum_name'])
                    repost_widget.set_picture([])
                    repost_widget.label_11.show()
                    repost_widget.label_11.setText('这是被转发的贴子。')
                    repost_widget.adjustSize()

                    item = QListWidgetItem()
                    item.setSizeHint(repost_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, repost_widget)
                    self.update_listwidget_size(repost_widget.height())

    def get_thread_head_info_async(self):
        start_background_thread(self.get_thread_head_info)

    def get_thread_head_info(self):
        async def dosign():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    aiotieba.logging.get_logger().info(f'loading thread {self.thread_id} main info')
                    thread_info = await client.get_posts(self.thread_id)
                    if thread_info.err:
                        if isinstance(thread_info.err,
                                      (aiotieba.exception.TiebaServerError, aiotieba.exception.HTTPStatusError)):
                            self.head_data_signal.emit(
                                {'err_info': f'{thread_info.err.msg} (错误代码 {thread_info.err.code})'})
                        else:
                            self.head_data_signal.emit(
                                {'err_info': str(thread_info.err)})
                    else:
                        self.forum_id = forum_id = thread_info.forum.fid

                        if self.forum_id != 0:
                            forum_info = await client.get_forum_detail(self.forum_id)
                            forum_name = forum_info.fname
                            forum_pic_url = forum_info.small_avatar
                        else:
                            forum_name = ''
                            forum_pic_url = ''

                        preview_pixmap = []
                        self.user_id = thread_info.thread.user.user_id
                        self.first_floor_pid = thread_info.thread.pid
                        title = thread_info.thread.title
                        content = make_thread_content(thread_info.thread.contents.objs)
                        portrait = thread_info.thread.user.portrait
                        user_name = thread_info.thread.user.nick_name_new
                        self.agree_num = agree_num = thread_info.thread.agree
                        time_str = timestamp_to_string(thread_info.thread.create_time)
                        _user_ip = thread_info.thread.user.ip
                        user_ip = _user_ip if _user_ip else '未知'
                        is_help = thread_info.thread.is_help
                        user_forum_level = thread_info.thread.user.level
                        user_grow_level = thread_info.thread.user.glevel
                        is_forum_manager = bool(thread_info.thread.user.is_bawu)
                        post_num = thread_info.thread.reply_num - 1

                        video_info = {'have_video': False, 'src': '', 'length': 0, 'view': 0}
                        if thread_info.thread.contents.video:
                            video_info['have_video'] = True
                            video_info['src'] = thread_info.thread.contents.video.src
                            video_info['length'] = thread_info.thread.contents.video.duration
                            video_info['view'] = thread_info.thread.contents.video.view_num

                        voice_info = {'have_voice': False, 'src': '', 'length': 0}
                        if thread_info.thread.contents.voice:
                            voice_info['have_voice'] = True
                            voice_info[
                                'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={thread_info.thread.contents.voice.md5}&play_from=pb_voice_play'
                            voice_info['length'] = thread_info.thread.contents.voice.duration

                        repost_info = {'have_repost': thread_info.thread.is_share, 'author_portrait_pixmap': None,
                                       'author_name': '', 'title': '', 'content': '', 'thread_id': -1, 'forum_id': -1,
                                       'forum_name': ''}
                        if thread_info.thread.is_share:
                            repost_user_info = await client.get_user_info(thread_info.thread.share_origin.author_id,
                                                                          aiotieba.enums.ReqUInfo.PORTRAIT | aiotieba.enums.ReqUInfo.NICK_NAME)

                            repost_user_head_pixmap = QPixmap()
                            repost_user_head_pixmap.loadFromData(cache_mgr.get_portrait(repost_user_info.portrait))
                            repost_user_head_pixmap = repost_user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                                     Qt.SmoothTransformation)
                            repost_info['author_portrait_pixmap'] = repost_user_head_pixmap
                            repost_info['author_name'] = repost_user_info.nick_name_new

                            repost_info['title'] = thread_info.thread.share_origin.title
                            repost_info['content'] = cut_string(
                                make_thread_content(thread_info.thread.share_origin.contents, True), 150)
                            repost_info['thread_id'] = thread_info.thread.share_origin.tid
                            repost_info['forum_id'] = thread_info.thread.share_origin.fid
                            repost_info['forum_name'] = thread_info.thread.share_origin.fname

                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                        forum_pixmap = QPixmap()
                        if forum_pic_url:
                            response = requests.get(forum_pic_url, headers=request_mgr.header)
                            if response.content:
                                forum_pixmap.loadFromData(response.content)
                                forum_pixmap = forum_pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                        for j in thread_info.thread.contents.imgs:
                            # width, height, src, view_src
                            src = j.origin_src
                            view_src = j.src
                            height = j.show_height
                            width = j.show_width
                            preview_pixmap.append({'width': width, 'height': height, 'src': src, 'view_src': view_src})

                        tdata = {'forum_id': forum_id,  # 吧id
                                 'title': title,  # 标题
                                 'content': content,  # 正内容
                                 'author_portrait': portrait,  # 作者portrait
                                 'user_name': user_name,  # 作者昵称
                                 'user_portrait_pixmap': user_head_pixmap,  # 作者头像QPixmap
                                 'forum_name': forum_name,  # 吧名称
                                 'forum_pixmap': forum_pixmap,  # 吧头像QPixmap
                                 'view_pixmap': preview_pixmap,  # 主题内图片列表
                                 'agree_count': agree_num,  # 点赞数
                                 'create_time_str': time_str,  # 发布时间字符串
                                 'user_ip': user_ip,  # 作者ip属地
                                 'is_help': is_help,  # 是否为求助贴
                                 'uf_level': user_forum_level,  # 吧等级
                                 'err_info': '',  # 错误信息
                                 'video_info': video_info,  # 视频贴信息
                                 'voice_info': voice_info,  # 语音内容信息
                                 'user_grow_level': user_grow_level,  # 用户成长等级
                                 'is_forum_manager': is_forum_manager,  # 是否为吧务
                                 'post_num': post_num,  # 回贴数
                                 'repost_info': repost_info}  # 转发贴信息

                        aiotieba.logging.get_logger().info(
                            f'load thread {self.thread_id} main info ok, send to qt side')
                        self.head_data_signal.emit(tdata)
            except Exception as e:
                print(type(e))
                print(e)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()


class ForumItem(QWidget, ba_item.Ui_Form):
    """列表内嵌入的吧组件"""
    signok = pyqtSignal(tuple)

    def __init__(self, fid, issign, bduss, stoken, fname):
        super().__init__()
        self.setupUi(self)
        self.forum_id = fid
        self.is_sign = issign
        self.bduss = bduss
        self.stoken = stoken
        self.forum_name = fname

        self.signok.connect(self.update_sign_ui)
        self.pushButton.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.sign_async)

        if issign:
            self.pushButton_2.setEnabled(False)
            self.pushButton_2.setText('已签到')

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.open_ba_detail()

    def update_sign_ui(self, isok):
        if isok[0]:
            QMessageBox.information(self, isok[1], isok[2])
            self.pushButton_2.setEnabled(False)
            self.pushButton_2.setText('已签到')
        else:
            QMessageBox.critical(self, isok[1], isok[2])
            self.pushButton_2.setEnabled(True)

    def sign_async(self):
        if not self.is_sign:
            self.pushButton_2.setEnabled(False)
            start_background_thread(self.sign)

    def sign(self):
        async def dosign():
            turn_data = [False, '签到完成', '']

            tsb_resp = request_mgr.run_post_api('/c/s/login', request_mgr.calc_sign(
                {'_client_version': request_mgr.TIEBA_CLIENT_VERSION, 'bdusstoken': self.bduss}),
                                                use_mobile_header=True,
                                                host_type=2)
            tbs = tsb_resp["anti"]["tbs"]

            payload = {
                'BDUSS': self.bduss,
                '_client_type': "2",
                '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                'fid': self.forum_id,
                'kw': self.forum_name,
                'stoken': self.stoken,
                'tbs': tbs,
            }
            r = request_mgr.run_post_api('/c/c/forum/sign',
                                         payloads=request_mgr.calc_sign(payload),
                                         bduss=self.bduss, stoken=self.stoken,
                                         use_mobile_header=True,
                                         host_type=2)
            if r['error_code'] == '0':
                user_sign_rank = r['user_info']['user_sign_rank']
                sign_bonus_point = r['user_info']['sign_bonus_point']

                turn_data[0] = True
                turn_data[1] = '签到成功'
                turn_data[
                    2] = f'{self.forum_name}吧 已签到成功。\n本次签到经验 +{sign_bonus_point}，你是今天本吧第 {user_sign_rank} 个签到的用户。'
            elif r['error_code'] == '160002':
                turn_data[0] = True
                turn_data[1] = '已经签到过了'
                turn_data[2] = f'你已签到过 {self.forum_name}吧，无需再签到。'
            else:
                turn_data[0] = False
                turn_data[1] = '签到失败'
                turn_data[2] = f'{r["error_msg"]} (错误代码 {r["error_code"]})'

            self.signok.emit(tuple(turn_data))

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def open_ba_detail(self):
        forum_window = ForumShowWindow(self.bduss, self.stoken, self.forum_id)
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_info(self, headpixmap, name, desp):
        self.label.setPixmap(headpixmap)
        self.label_2.setText(name)
        self.label_3.setText(desp)

    def set_level_color(self, level):
        qss = 'QLabel{color: [color];font-weight: [is_high_level];}'
        if level >= 10:  # 10级以上粗体显示
            qss = qss.replace('[is_high_level]', 'bold')
        else:
            qss = qss.replace('[is_high_level]', 'normal')
        if 1 <= level <= 3:  # 绿牌
            qss = qss.replace('[color]', 'rgb(101, 211, 171)')
        elif 4 <= level <= 9:  # 蓝牌
            qss = qss.replace('[color]', 'rgb(101, 161, 255)')
        elif 10 <= level <= 15:  # 黄牌
            qss = qss.replace('[color]', 'rgb(253, 194, 53)')
        elif level >= 16:  # 橙牌老东西
            qss = qss.replace('[color]', 'rgb(247, 126, 48)')

        self.label_3.setStyleSheet(qss)  # 为不同等级设置qss


class SignAllDialog(QDialog, sign.Ui_Dialog):
    """一键签到窗口，可以实现全吧和成长等级签到"""
    update_label_count = pyqtSignal(str)
    sign_grow_ok = pyqtSignal(str)
    is_signing_forums = False
    is_signing_grows = False

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.lineEdit.setText(f'\"{sys.executable}\" --sign-all-forums --sign-grows')

        self.update_label_count.connect(lambda text: self.label_3.setText(text))
        self.sign_grow_ok.connect(self.show_grow_sign_msg)
        self.pushButton_2.clicked.connect(self.sign_grow_async)
        self.pushButton_3.clicked.connect(self.sign_all_forum_async)
        self.pushButton.clicked.connect(self.sign_all)

        self.bduss = bduss
        self.stoken = stoken

    def sign_all(self):
        self.sign_grow_async()
        self.sign_all_forum_async()

    def show_grow_sign_msg(self, result):
        if not result:
            QMessageBox.information(self, '签到成功', '成长等级签到成功。')
        else:
            QMessageBox.critical(self, '签到失败', result)

        self.pushButton_2.setEnabled(True)

    def sign_grow_async(self):
        if not self.is_signing_grows:
            self.pushButton_2.setEnabled(False)
            start_background_thread(self.sign_grow)

    def sign_grow(self):
        async def dosign():
            self.is_signing_grows = True
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                r1 = await client.sign_growth()
                r2 = await client.sign_growth_share()

                if r1 and r2:
                    self.sign_grow_ok.emit('')
                else:
                    err_msg = ''
                    if not r1:
                        head = ''
                        if err_msg:
                            head = '\n'
                        err_msg += f'{head}成长等级签到：{r1.err.msg}'
                    if not r2:
                        head = ''
                        if err_msg:
                            head = '\n'
                        err_msg += f'{head}成长等级分享任务：{r2.err.msg}'

                    self.sign_grow_ok.emit(err_msg)

            self.is_signing_grows = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def sign_all_forum_async(self):
        if not self.is_signing_forums:
            self.update_label_count.emit('正在开始签到...')
            start_background_thread(self.sign_all_forum)

    def sign_all_forum(self):
        async def dosign():
            self.is_signing_forums = True
            signed_count = 0
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    bars = request_mgr.run_get_api('/mo/q/newmoindex', self.bduss)['data']['like_forum']
                    bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

                    for forum in bars:
                        if forum["is_sign"] != 1:
                            forum_name = forum['forum_name']
                            self.update_label_count.emit(
                                f'正在签到 {forum_name}吧\n已签到 {signed_count + 1} / 总吧数 {len(bars)}')

                            fid = forum['forum_id']
                            r = await client.sign_forum(fid)
                            if r:
                                signed_count += 1  # 签到成功了加一
                            elif r.err.code == 160002:
                                signed_count += 1  # 之前签到过了也加一
                            await asyncio.sleep(0.3)  # 休眠0.3秒，防止贴吧服务器抽风
                        else:
                            # 已签到的直接跳过
                            signed_count += 1

                self.update_label_count.emit(
                    f'签到完成，已签到 {signed_count} 个吧，{len(bars) - signed_count} 个吧签到失败。')

            except Exception as e:
                self.update_label_count.emit('签到时发生异常错误，请再试一次。')
                print(type(e))
                print(e)
            finally:
                if os.name == 'nt':
                    win32api.MessageBeep(win32con.MB_ICONASTERISK)
                self.is_signing_forums = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()


class FollowForumList(QWidget, follow_ba.Ui_Form):
    """关注吧列表组件"""
    add_ba = pyqtSignal(list)
    ba_add_ok = pyqtSignal()

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.add_ba.connect(self.add_bar)
        self.ba_add_ok.connect(lambda: self.pushButton_2.setEnabled(True))
        self.pushButton_2.clicked.connect(self.get_bars_async)
        self.pushButton.clicked.connect(self.show_onekey_sign)
        self.listWidget.verticalScrollBar().setSingleStep(25)

    def keyPressEvent(self, a0):
        a0.accept()
        if a0.key() == Qt.Key.Key_F5:
            self.get_bars_async()

    def show_onekey_sign(self):
        if self.bduss and self.stoken:
            d = SignAllDialog(self.bduss, self.stoken)
            d.exec()
        else:
            QMessageBox.information(self, '提示', '请先登录账号后再进行签到。', QMessageBox.Ok)

    def add_bar(self, data):
        item = QListWidgetItem()
        widget = ForumItem(data[3], data[4], self.bduss, self.stoken, data[1])
        widget.set_info(data[0], data[1] + '吧', data[2])
        widget.set_level_color(data[5])
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def get_bars_async(self):
        if self.bduss:
            self.label_2.hide()
            self.listWidget.show()
            self.pushButton_2.setEnabled(False)

            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()

            start_background_thread(self.get_bars)
        else:
            self.listWidget.hide()
            self.label_2.show()

    def get_bars(self):
        async def func():
            try:
                aiotieba.logging.get_logger().info('loading userself follow forum list')

                payload = {
                    'BDUSS': self.bduss,
                    'stoken': self.stoken,
                    'sort_type': "3",
                    'call_from': "1",
                }
                bars = request_mgr.run_post_api('/c/f/forum/forumGuide', payloads=payload, bduss=self.bduss,
                                                stoken=self.stoken, use_mobile_header=True)['like_forum']
                for forum in bars:
                    name = forum['forum_name']
                    pixmap = QPixmap()
                    response = requests.get(forum['avatar'], headers=request_mgr.header)
                    if response.content:
                        pixmap.loadFromData(response.content)
                        pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                    level_str = forum['level_name']
                    level_value = forum['level_id']
                    ba_info_str = f'[Lv.{level_value}] {level_str}'
                    self.add_ba.emit([pixmap, name, ba_info_str, forum['forum_id'], forum['is_sign'] == 1, level_value])
            finally:
                self.ba_add_ok.emit()
                aiotieba.logging.get_logger().info('load userself follow forum list complete')

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func())


class ThreadView(QWidget, tie_preview.Ui_Form):
    """贴子在列表内的预览小组件"""
    is_treasure = False
    is_top = False

    def __init__(self, bduss, tid, fid, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = tid
        self.forum_id = fid

        self.label_11.hide()
        self.pushButton_3.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.open_thread_detail)

    def open_thread_detail(self):
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), self.is_treasure,
                                         self.is_top)
        qt_window_mgr.add_window(thread_window)

    def open_ba_detail(self):
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_thread_values(self, view, agree, reply, repost, send_time=0):
        text = f'{view} 次浏览，{agree} 人点赞，{reply} 条回复，{repost} 次转发'
        if send_time > 0:
            timestr = '发布于 ' + timestamp_to_string(send_time)
            text += '\n' + timestr
        self.label_11.show()
        self.label_11.setText(text)

    def set_infos(self, uicon, uname, title, text, baicon, baname):
        self.label_4.setPixmap(uicon)
        self.label_3.setText(uname)
        self.label_5.setText(title)
        self.label_6.setText(text)
        self.label_2.setText(baname + '吧')

        if baicon:
            self.label.setPixmap(baicon)
        else:
            self.label.hide()

        if not text:
            self.label_6.hide()
        if not title:
            self.label_5.hide()

    def set_picture(self, piclist):
        labels = [self.label_7, self.label_8, self.label_9]
        self.label_7.clear()
        self.label_8.clear()
        self.label_9.clear()
        if len(piclist) == 0:
            self.gridLayout.removeWidget(self.frame_2)
        else:
            try:
                for i in range(len(piclist)):
                    labels[i].setPixmap(piclist[i])
            except IndexError:
                return


class RecommandWindow(QListWidget):
    """首页推荐列表组件"""
    isloading = False
    offset = 0
    add_tie = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken
        self.setStyleSheet('QListWidget{outline:0px;}'
                           'QListWidget::item:hover {color:white; background-color:white;}'
                           'QListWidget::item:selected {color:white; background-color:white;}')
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSizeAdjustPolicy(QListWidget.SizeAdjustPolicy.AdjustToContents)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.verticalScrollBar().setSingleStep(20)
        self.add_tie.connect(self.add_thread)
        self.verticalScrollBar().valueChanged.connect(self.load_more)

    def load_more(self):
        if not self.isloading and self.verticalScrollBar().value() >= self.verticalScrollBar().maximum() - self.verticalScrollBar().maximum() / 5:
            self.get_recommand_async()

    def add_thread(self, infos):
        # {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
        # 'content': content, 'author_portrait': portrait, 'user_name': user_name,
        # 'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
        # 'forum_pixmap': forum_pixmap, 'view_pixmap': []}
        item = QListWidgetItem()
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
        widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], infos['content'],
                         infos['forum_pixmap'], infos['forum_name'])
        widget.set_picture(infos['view_pixmap'])
        widget.adjustSize()
        item.setSizeHint(widget.size())
        self.addItem(item)
        self.setItemWidget(item, widget)

    def get_recommand_async(self):
        if self.bduss:  # 登录了使用新接口
            start_background_thread(self.get_recommand_v2)
        else:
            start_background_thread(self.get_recommand_v1)

    def get_recommand_v1(self):
        """贴吧电脑网页版的推荐接口，不登录也能获取"""

        async def get_detail(element):
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                title = element.find_all(class_='title feed-item-link')[0].text  # 找出标题
                content = element.find_all(class_='n_txt')[0].text[0:-1]  # 找出正文
                portrait = \
                    element.find_all(class_='post_author')[0]['href'].split('/home/main?id=')[1].split(
                        '&fr=index')[
                        0]  # 找出portrait，方便获取用户数据
                thread_id = element['data-thread-id']  # 贴子id
                forum_id = element['fid']  # 吧id

                # 找出所有预览图
                preview_pixmap = []
                picture_elements = element.find_all(class_="m_pic")  # 找出所有图片
                for i in picture_elements:
                    pic_addr = i['original']
                    response = requests.get(pic_addr, headers=request_mgr.header)
                    if response.content:
                        pixmap = QPixmap()
                        pixmap.loadFromData(response.content)
                        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation)
                        preview_pixmap.append(pixmap)

                # 进一步获取用户信息
                userinfo = await client.get_user_info(portrait)
                user_name = userinfo.nick_name_new
                user_head_pixmap = QPixmap()
                user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                # 进一步获取吧信息
                forum = await client.get_forum_detail(int(forum_id))
                forum_name = forum.fname
                forum_pixmap = QPixmap()
                response = requests.get(forum.origin_avatar, headers=request_mgr.header)
                if response.content:
                    forum_pixmap.loadFromData(response.content)
                    forum_pixmap = forum_pixmap.scaled(15, 15, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                tdata = {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
                         'content': content, 'author_portrait': portrait, 'user_name': user_name,
                         'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
                         'forum_pixmap': forum_pixmap, 'view_pixmap': preview_pixmap}
                self.add_tie.emit(tdata)

        def start_async(element):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(get_detail(element))

        def func():
            global datapath
            self.isloading = True
            try:
                # 贴吧电脑网页版的推荐接口，不登录也能获取
                # 在登录情况下，需要传一组特定的cookie才能使推荐个性化（不只是bduss和stoken），否则是默认推荐
                aiotieba.logging.get_logger().info('loading recommands from api /f/index/feedlist')
                response = request_mgr.run_get_api(f'/f/index/feedlist?tag_id=like&offset={self.offset}')
                html = response['data']['html']

                # 统一贴子列表内的class类型
                for i in range(1, 11):
                    html = html.replace(f'clearfix j_feed_li  {i}', 'clearfix j_feed_li')

                # 解析网页
                soup = BeautifulSoup(html, "html.parser")
                elements = soup.find_all(class_="clearfix j_feed_li")  # 找出所有贴子

                for element in elements:
                    start_background_thread(start_async, (element,))
            except Exception as e:
                print(type(e))
                print(e)
            else:
                self.offset += 20
            finally:
                self.isloading = False
                aiotieba.logging.get_logger().info('loading recommands from api /f/index/feedlist finished')

        func()

    def get_recommand_v2(self):
        """手机网页版贴吧的首页推荐接口"""

        async def get_detail(element):
            # 视频贴过滤检测
            if profile_mgr.local_config['thread_view_settings']['hide_video'] and element.get('video_info'):
                return

            title = element['title']  # 找出标题
            content = ''  # 贴子正文
            if element['abstract']:
                for i in element['abstract']:
                    if i['type'] == 0:
                        content += i['text']
            if element.get('video_info'):
                content = '[这是一条视频贴，时长 {vlen}，{view_num} 次浏览，进贴即可查看]'.format(
                    vlen=format_second(element['video_info']['video_duration']),
                    view_num=element['video_info']['play_count'])
            portrait = element['author']['portrait'].split('?')[0]
            thread_id = element['tid']  # 贴子id
            forum_id = element['forum']['forum_id']  # 吧id

            # 找出所有预览图
            preview_pixmap = []
            picture_elements = element['media']  # 找出所有媒体
            if picture_elements:
                for i in picture_elements:
                    if i['type'] == 3:  # 类型是图片
                        pic_addr = i['big_pic']
                        response = requests.get(pic_addr, headers=request_mgr.header)
                        if response.content:
                            pixmap = QPixmap()
                            pixmap.loadFromData(response.content)
                            pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)
                            preview_pixmap.append(pixmap)

            # 进一步获取用户信息
            user_name = element['author'].get('user_nickname_v2',
                                              element['author']['display_name'])  # 优先获取新版昵称，如果没有则使用旧版昵称或者用户名
            user_head_pixmap = QPixmap()
            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 进一步获取吧信息
            forum_name = element['forum']['forum_name']
            forum_pixmap = QPixmap()
            response = requests.get(element['forum']['forum_avatar'], headers=request_mgr.header)
            if response.content:
                forum_pixmap.loadFromData(response.content)
                forum_pixmap = forum_pixmap.scaled(15, 15, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            tdata = {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
                     'content': content, 'author_portrait': portrait, 'user_name': user_name,
                     'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
                     'forum_pixmap': forum_pixmap, 'view_pixmap': preview_pixmap}
            self.add_tie.emit(tdata)

        def start_async(element):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(get_detail(element))

        def func():
            global datapath
            self.isloading = True
            try:
                # 手机网页版贴吧的首页推荐接口
                # 该接口在未登录的情况下会获取不到数据，并报未知错误 (110003)
                # 在登录情况下，有bduss和stoken就可以实现个性化推荐
                # 该接口包含的信息较为全面，很多信息无需再另起请求，因此该方法获取贴子数据会比旧版的快
                # 该接口返回的视频贴较多，疑似是贴吧后端刻意为之
                aiotieba.logging.get_logger().info('loading recommands from api /mg/o/getRecommPage')
                response = request_mgr.run_get_api('/mg/o/getRecommPage?load_type=1&eqid=&refer=tieba.baidu.com'
                                                   '&page_thread_count=10',
                                                   bduss=self.bduss, stoken=self.stoken)
                if response['errno'] == 110003:
                    start_background_thread(self.get_recommand_v1)
                else:
                    tlist = response['data']['thread_list']
                    for element in tlist:
                        start_background_thread(start_async, (element,))
                    aiotieba.logging.get_logger().info('loading recommands from api /mg/o/getRecommPage finished')
            except Exception as e:
                print(type(e))
                print(e)
            finally:
                self.isloading = False

        func()


class TiebaSearchWindow(QDialog, forum_search.Ui_Dialog):
    """贴吧搜索窗口"""
    add_result = pyqtSignal(dict)

    def __init__(self, bduss, stoken, forum_name=''):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))

        self.bduss = bduss
        self.stoken = stoken
        self.page = {'thread': {'loading': False, 'page': 1},
                     'forum': {'loading': False, 'page': 1},
                     'user': {'loading': False, 'page': 1},
                     'thread_single_forum': {'loading': False, 'page': 1},
                     'reply_single_forum': {'loading': False, 'page': 1}}
        self.listwidgets = [self.listWidget, self.listWidget_2, self.listWidget_3, self.listWidget_4, self.listWidget_5]

        for i in self.listwidgets:
            i.verticalScrollBar().setSingleStep(20)

        contain_thread_listwidgets = [self.listWidget_2, self.listWidget_4, self.listWidget_5]
        for i in contain_thread_listwidgets:
            i.setStyleSheet('QListWidget{outline:0px;}'
                            'QListWidget::item:hover {color:white; background-color:white;}'
                            'QListWidget::item:selected {color:white; background-color:white;}')

        self.listWidget_2.verticalScrollBar().valueChanged.connect(
            lambda: self.scroll_load_more('thread', self.listWidget_2))
        self.listWidget_4.verticalScrollBar().valueChanged.connect(
            lambda: self.scroll_load_more('thread_single_forum', self.listWidget_4))
        self.listWidget_5.verticalScrollBar().valueChanged.connect(
            lambda: self.scroll_load_more('reply_single_forum', self.listWidget_5))

        if forum_name:
            self.lineEdit_2.setText(forum_name)
            self.comboBox.setCurrentIndex(1)
        self.handle_search_type_switch(self.comboBox.currentIndex())

        self.add_result.connect(self._ui_add_search_result)
        self.comboBox.currentIndexChanged.connect(self.handle_search_type_switch)
        self.pushButton.clicked.connect(self.start_search)

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def scroll_load_more(self, type, listw: QListWidget):
        if listw.verticalScrollBar().value() == listw.verticalScrollBar().maximum():
            if type in ('thread', 'forum', 'user'):
                self.search_global_async(type)
            elif type in ('thread_single_forum', 'reply_single_forum'):
                self.search_forum_async(type)

    def handle_search_type_switch(self, index):
        if not self.clear_list_all():
            QMessageBox.information(self, '提示', '列表还在加载中，请稍后再尝试切换搜索范围。', QMessageBox.Ok)
            self.comboBox.blockSignals(True)  # 暂时阻塞信号
            self.comboBox.setCurrentIndex(0 if index == 1 else 1)
            self.comboBox.blockSignals(False)  # 解除阻塞信号
        else:
            if index == 0:
                self.tabWidget.removeTab(self.tabWidget.indexOf(self.tab_4))
                self.tabWidget.removeTab(self.tabWidget.indexOf(self.tab_5))
                self.tabWidget.addTab(self.tab, '贴吧')
                self.tabWidget.addTab(self.tab_2, '贴子')
                self.tabWidget.addTab(self.tab_3, '用户')

                self.lineEdit_2.hide()
            else:
                self.tabWidget.removeTab(self.tabWidget.indexOf(self.tab))
                self.tabWidget.removeTab(self.tabWidget.indexOf(self.tab_2))
                self.tabWidget.removeTab(self.tabWidget.indexOf(self.tab_3))
                self.tabWidget.addTab(self.tab_4, '主题贴')
                self.tabWidget.addTab(self.tab_5, '回复贴')

                self.lineEdit_2.show()

    def clear_list_all(self):
        flag = True
        for v in self.page.values():
            if v['loading']:
                flag = False
                break
        if flag:
            for i in self.listwidgets:
                i.clear()
            QPixmapCache.clear()
            gc.collect()
            self.page = {'thread': {'loading': False, 'page': 1},
                         'forum': {'loading': False, 'page': 1},
                         'user': {'loading': False, 'page': 1},
                         'thread_single_forum': {'loading': False, 'page': 1},
                         'reply_single_forum': {'loading': False, 'page': 1}}
        return flag

    def _ui_add_search_result(self, datas):
        if datas['type'] == 'thread':
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)

            widget.set_infos(datas['user_portrait_pixmap'], datas['user_name'], datas['title'], datas['text'],
                             datas['forum_head_pixmap'],
                             datas['forum_name'])
            widget.set_picture(datas['picture'])
            widget.adjustSize()

            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
        elif datas['type'] == 'forum':
            item = QListWidgetItem()
            widget = ForumItem(datas['forum_id'], True, self.bduss, self.stoken, datas['forum_name'])
            widget.set_info(datas['forum_head_pixmap'], datas['forum_name'] + '吧', datas['desp'])
            widget.pushButton_2.hide()
            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif datas['type'] == 'user':
            item = QListWidgetItem()
            widget = UserItem(self.bduss, self.stoken)
            widget.user_portrait_id = datas['portrait']
            widget.show_homepage_by_click = True
            widget.setdatas(datas['portrait'], datas['name'], datas['tieba_id'], is_tieba_uid=True)
            item.setSizeHint(widget.size())
            self.listWidget_3.addItem(item)
            self.listWidget_3.setItemWidget(item, widget)
        elif datas['type'] == 'thread_single_forum':
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)

            widget.set_infos(datas['user_portrait_pixmap'], datas['user_name'], datas['title'], datas['text'],
                             datas['forum_head_pixmap'],
                             datas['forum_name'])
            widget.set_picture(datas['picture'])
            widget.adjustSize()

            item.setSizeHint(widget.size())
            self.listWidget_4.addItem(item)
            self.listWidget_4.setItemWidget(item, widget)
        elif datas['type'] == 'reply_single_forum':
            item = QListWidgetItem()
            widget = ReplyItem(self.bduss, self.stoken)

            widget.portrait = datas['portrait']
            widget.thread_id = datas['thread_id']
            widget.post_id = datas['post_id']
            widget.allow_home_page = True
            widget.subcomment_show_thread_button = True
            widget.set_reply_text(
                '<a href=\"tieba_thread://{tid}\">{title}</a>'.format(tid=datas['thread_id'], title=datas['title']))
            widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], False, datas['text'],
                            datas['picture'], -1, datas['time_str'], '', -2, -1, -1, False)

            item.setSizeHint(widget.size())
            self.listWidget_5.addItem(item)
            self.listWidget_5.setItemWidget(item, widget)

    def start_search(self):
        index = self.comboBox.currentIndex()
        if not self.lineEdit.text():
            QMessageBox.critical(self, '填写错误', '请先输入搜索关键字再搜索。', QMessageBox.Ok)
        elif index == 1 and not self.lineEdit_2.text():
            QMessageBox.critical(self, '填写错误', '请先输入你要搜索的吧名再搜索。', QMessageBox.Ok)
        elif self.clear_list_all():
            if index == 0:
                self.search_global_async('thread')
                self.search_global_async('forum')
                self.search_global_async('user')
            elif index == 1:
                self.search_forum_async('thread_single_forum')
                self.search_forum_async('reply_single_forum')

    def search_forum_async(self, search_area):
        if not self.page[search_area]['loading'] and not self.page[search_area]['page'] == -1:
            start_background_thread(self.search_forum, (self.lineEdit.text(), search_area, self.lineEdit_2.text()))

    def search_forum(self, query, search_area, forum_name):
        try:
            self.page[search_area]['loading'] = True

            if search_area == 'thread_single_forum':
                params = {
                    'st': "5",
                    'tt': "1",
                    'ct': "2",
                    'cv': request_mgr.TIEBA_CLIENT_VERSION,
                    'fname': forum_name,
                    'word': query,
                    'pn': str(self.page[search_area]['page']),
                    'rn': "20"
                }
                response = request_mgr.run_get_api('/mo/q/search/thread', bduss=self.bduss, stoken=self.stoken,
                                                   params=params, use_mobile_header=True)
                if response['no'] == 0:
                    for thread in response['data']['post_list']:
                        data = {'type': search_area,
                                'user_name': thread['user']['show_nickname'],
                                'user_portrait_pixmap': None,
                                'forum_head_pixmap': None,
                                'thread_id': int(thread['tid']),
                                'forum_id': thread['forum_id'],
                                'forum_name': thread['forum_info']['forum_name'],
                                'title': thread["title"],
                                'text': cut_string(thread['content'], 50),
                                'picture': [],
                                'timestamp': thread['time'],
                                'portrait': ''}

                        # 处理portrait
                        if thread["user"]["portrait"].startswith(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/')[1].split('?')[0]
                        elif thread["user"]["portrait"].startswith('http://tb.himg.baidu.com/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'http://tb.himg.baidu.com/sys/portrait/item/')[1].split('?')[0]
                        else:
                            data['portrait'] = thread["user"]["portrait"]

                        # 获取吧头像
                        forum_head_pixmap = QPixmap()
                        url = thread["forum_info"]["avatar"]
                        response_ = requests.get(
                            url,
                            headers=request_mgr.header)
                        if response_.content:
                            forum_head_pixmap.loadFromData(response_.content)
                            forum_head_pixmap = forum_head_pixmap.scaled(15, 15, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
                            data['forum_head_pixmap'] = forum_head_pixmap

                        # 获取用户头像
                        portrait = data['portrait']
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        data['user_portrait_pixmap'] = user_head_pixmap

                        # 获取主图片
                        if thread.get("media"):
                            for m in thread['media']:
                                if m["type"] == "pic":  # 是图片
                                    pixmap = QPixmap()
                                    url = m["small_pic"]
                                    response_ = requests.get(url, headers=request_mgr.header)
                                    if response_.content:
                                        pixmap.loadFromData(response_.content)
                                        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                               Qt.SmoothTransformation)
                                        data['picture'].append(pixmap)

                        self.add_result.emit(data)
            elif search_area == 'reply_single_forum':
                params = {
                    'st': "5",
                    'tt': "3",
                    'ct': "2",
                    'cv': request_mgr.TIEBA_CLIENT_VERSION,
                    'fname': forum_name,
                    'word': query,
                    'pn': str(self.page[search_area]['page']),
                    'rn': "20"
                }
                response = request_mgr.run_get_api('/mo/q/search/thread', bduss=self.bduss, stoken=self.stoken,
                                                   params=params, use_mobile_header=True)
                if response['no'] == 0:
                    for thread in response['data']['post_list']:
                        data = {'type': search_area,
                                'user_name': thread['user']['show_nickname'],
                                'user_portrait_pixmap': None,
                                'forum_head_pixmap': None,
                                'thread_id': int(thread['tid']),
                                'post_id': int(thread['pid']),
                                'forum_id': thread['forum_id'],
                                'forum_name': thread['forum_info']['forum_name'],
                                'title': thread["title"],
                                'text': cut_string(thread['content'], 50),
                                'picture': [],
                                'timestamp': thread['time'],
                                'portrait': '',
                                'timestr': ''}

                        # 处理portrait
                        if thread["user"]["portrait"].startswith(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/')[1].split('?')[0]
                        elif thread["user"]["portrait"].startswith('http://tb.himg.baidu.com/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'http://tb.himg.baidu.com/sys/portrait/item/')[1].split('?')[0]
                        else:
                            data['portrait'] = thread["user"]["portrait"]

                        # 获取吧头像
                        forum_head_pixmap = QPixmap()
                        url = thread["forum_info"]["avatar"]
                        response_ = requests.get(
                            url,
                            headers=request_mgr.header)
                        if response_.content:
                            forum_head_pixmap.loadFromData(response_.content)
                            forum_head_pixmap = forum_head_pixmap.scaled(15, 15, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
                            data['forum_head_pixmap'] = forum_head_pixmap

                        # 转换时间为字符串
                        timestr = timestamp_to_string(data['timestamp'])
                        data['time_str'] = timestr

                        # 获取用户头像
                        portrait = data['portrait']
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        data['user_portrait_pixmap'] = user_head_pixmap

                        self.add_result.emit(data)
        except Exception as e:
            print(f'{type(e)}\n{e}')
        else:
            if response['data']['has_more']:
                self.page[search_area]['page'] += 1
            else:
                self.page[search_area]['page'] = -1
        finally:
            self.page[search_area]['loading'] = False

    def search_global_async(self, search_area):
        if not self.page[search_area]['loading'] and not self.page[search_area]['page'] == -1:
            start_background_thread(self.search_global, (self.lineEdit.text(), search_area))

    def search_global(self, query, search_area):
        try:
            self.page[search_area]['loading'] = True
            if search_area == 'thread':
                params = {
                    'word': query,
                    'pn': str(self.page[search_area]['page']),
                    'st': "5",
                    'ct': "1",
                    'cv': "99.9.101",
                    'tt': "1",
                    'is_use_zonghe': "1"
                }
                response = request_mgr.run_get_api('/mo/q/search/thread', bduss=self.bduss, stoken=self.stoken,
                                                   params=params, use_mobile_header=True)
                if response['no'] == 0:
                    for thread in response['data']['post_list']:
                        data = {'type': search_area,
                                'user_name': thread['user']['show_nickname'],
                                'user_portrait_pixmap': None,
                                'forum_head_pixmap': None,
                                'thread_id': int(thread['tid']),
                                'forum_id': thread['forum_id'],
                                'forum_name': thread['forum_info']['forum_name'],
                                'title': thread["title"],
                                'text': cut_string(thread['content'], 50),
                                'picture': [],
                                'timestamp': thread['create_time'],
                                'portrait': ''}

                        # 处理portrait
                        if thread["user"]["portrait"].startswith(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'https://gss0.bdstatic.com/6LZ1dD3d1sgCo2Kml5_Y_D3/sys/portrait/item/')[1].split('?')[0]
                        elif thread["user"]["portrait"].startswith('http://tb.himg.baidu.com/sys/portrait/item/'):
                            data['portrait'] = thread["user"]["portrait"].split(
                                'http://tb.himg.baidu.com/sys/portrait/item/')[1].split('?')[0]
                        else:
                            data['portrait'] = thread["user"]["portrait"]

                        # 获取吧头像
                        forum_head_pixmap = QPixmap()
                        url = thread["forum_info"]["avatar"]
                        response_ = requests.get(
                            url,
                            headers=request_mgr.header)
                        if response_.content:
                            forum_head_pixmap.loadFromData(response_.content)
                            forum_head_pixmap = forum_head_pixmap.scaled(15, 15, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
                            data['forum_head_pixmap'] = forum_head_pixmap

                        # 获取用户头像
                        portrait = data['portrait']
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        data['user_portrait_pixmap'] = user_head_pixmap

                        # 获取主图片
                        if thread.get("media"):
                            for m in thread['media']:
                                if m["type"] == "pic":  # 是图片
                                    pixmap = QPixmap()
                                    url = m["small_pic"]
                                    response_ = requests.get(url, headers=request_mgr.header)
                                    if response_.content:
                                        pixmap.loadFromData(response_.content)
                                        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                               Qt.SmoothTransformation)
                                        data['picture'].append(pixmap)

                        self.add_result.emit(data)
            elif search_area == 'forum':
                params = {
                    'word': query,
                    'needbrand': "1",
                    'godrn': "3"
                }
                response = request_mgr.run_get_api('/mo/q/search/forum', bduss=self.bduss, stoken=self.stoken,
                                                   params=params, use_mobile_header=True)
                if response['no'] == 0:
                    if response['data']['exactMatch']:
                        # 准确吧结果
                        data = {'type': search_area,
                                'forum_head_pixmap': None,
                                'forum_id': response['data']['exactMatch']['forum_id'],
                                'forum_name': response['data']['exactMatch']['forum_name'],
                                'desp': '[准确结果] ' + response['data']['exactMatch']['slogan'],
                                'member_num': response['data']['exactMatch']['concern_num_ori'],
                                'post_num': response['data']['exactMatch']['post_num_ori']}

                        # 获取吧头像
                        forum_head_pixmap = QPixmap()
                        url = response['data']['exactMatch']['avatar']
                        response_ = requests.get(
                            url,
                            headers=request_mgr.header)
                        if response_.content:
                            forum_head_pixmap.loadFromData(response_.content)
                            forum_head_pixmap = forum_head_pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
                            data['forum_head_pixmap'] = forum_head_pixmap

                        self.add_result.emit(data)
                    for forum in response['data']['fuzzyMatch']:  # 相似结果
                        data = {'type': search_area,
                                'forum_head_pixmap': None,
                                'forum_id': forum['forum_id'],
                                'forum_name': forum['forum_name'],
                                'desp': '与你搜索的内容相关',
                                'member_num': forum['concern_num_ori'],
                                'post_num': forum['post_num_ori']}

                        # 获取吧头像
                        forum_head_pixmap = QPixmap()
                        url = forum['avatar']
                        response_ = requests.get(
                            url,
                            headers=request_mgr.header)
                        if response_.content:
                            forum_head_pixmap.loadFromData(response_.content)
                            forum_head_pixmap = forum_head_pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
                            data['forum_head_pixmap'] = forum_head_pixmap

                        self.add_result.emit(data)
            elif search_area == 'user':
                params = {
                    'word': query
                }
                response = request_mgr.run_get_api('/mo/q/search/user', bduss=self.bduss, stoken=self.stoken,
                                                   params=params, use_mobile_header=True)
                if response['no'] == 0:
                    if response['data']['exactMatch']:
                        # 准确用户结果
                        data = {'type': search_area,
                                'user_id': response['data']['exactMatch']['id'],
                                'name': response['data']['exactMatch']['show_nickname'],
                                'portrait': response['data']['exactMatch']['encry_uid'],
                                'tieba_id': response['data']['exactMatch']['tieba_uid']}

                        self.add_result.emit(data)
                    for user in response['data']['fuzzyMatch']:  # 相似结果
                        data = {'type': search_area,
                                'user_id': user['id'],
                                'name': user['show_nickname'],
                                'portrait': user['encry_uid'],
                                'tieba_id': user['tieba_uid']}

                        if self.checkBox.isChecked():
                            if user['tieba_uid'] and user['fans_num'] > 0:
                                self.add_result.emit(data)
                        else:
                            self.add_result.emit(data)
        except Exception as e:
            print(f'{type(e)}\n{e}')
        else:
            if response['data'].get('has_more', False):
                self.page[search_area]['page'] += 1
            else:
                self.page[search_area]['page'] = -1
        finally:
            self.page[search_area]['loading'] = False


class ForumShowWindow(QWidget, ba_head.Ui_Form):
    """吧入口窗口，显示基础吧信息和吧内贴子等"""
    forum_name = ''
    page = {'latest_reply': 1, 'latest_send': 1, 'hot': 1, 'top': 1, 'treasure': 1}
    added_thread_count = 0
    isloading = False
    update_signal = pyqtSignal(dict)
    add_thread = pyqtSignal(dict)
    thread_refresh_ok = pyqtSignal()
    follow_forum_ok = pyqtSignal(bool)

    def __init__(self, bduss, stoken, fid):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.forum_id = fid

        self.page = {'latest_reply': 1, 'latest_send': 1, 'hot': 1, 'top': 1, 'treasure': 1}
        self.listwidgets = [self.listWidget, self.listWidget_2, self.listWidget_3, self.listWidget_4, self.listWidget_5]
        for i in self.listwidgets:
            i.setStyleSheet('QListWidget{outline:0px;}'
                            'QListWidget::item:hover {color:white; background-color:white;}'
                            'QListWidget::item:selected {color:white; background-color:white;}')
            i.verticalScrollBar().setSingleStep(20)
            i.verticalScrollBar().valueChanged.connect(self.scroll_load_more)

        self.init_load_flash()
        self.label_9.hide()
        self.pushButton.hide()
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.tabWidget.setCurrentIndex(profile_mgr.local_config['forum_view_settings']['default_sort'])
        self.update_signal.connect(self.update_info_ui)
        self.add_thread.connect(self.add_thread_)
        self.thread_refresh_ok.connect(self.show_load_ok_msg)
        self.pushButton_2.clicked.connect(self.refresh_all)
        self.follow_forum_ok.connect(self.show_follow_result)
        self.pushButton.clicked.connect(self.do_follow_forum)
        self.pushButton_3.clicked.connect(self.open_detail_window)
        self.pushButton_5.clicked.connect(self.open_search_window)
        self.pushButton_4.clicked.connect(
            lambda: open_url_in_browser(f'https://tieba.baidu.com/f?kw={self.forum_name}'))

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_F5:
            self.refresh_all()

    def closeEvent(self, a0):
        self.flash_shower.hide()
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)

    def open_search_window(self):
        search_window = TiebaSearchWindow(self.bduss, self.stoken, self.forum_name)
        qt_window_mgr.add_window(search_window)

    def open_detail_window(self):
        forum_detail_window = ForumDetailWindow(self.bduss, self.stoken, self.forum_id)
        qt_window_mgr.add_window(forum_detail_window)

    def show_follow_result(self, r):
        if r:
            self.pushButton.setText('已关注')
            self.pushButton.setEnabled(False)
            self.pushButton.setToolTip('已关注本吧')
            QMessageBox.information(self, '提示', f'关注成功，现在你是本吧的吧成员了。祝你在{self.forum_name}吧玩得愉快！',
                                    QMessageBox.Ok)
        else:
            QMessageBox.critical(self, '提示', '关注失败，请再试一次。', QMessageBox.Ok)

    def do_follow_forum(self):
        async def get_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    r = await client.follow_forum(self.forum_id)
                    self.follow_forum_ok.emit(bool(r))
            except Exception as e:
                print(type(e))
                print(e)

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(get_detail())

    def add_thread_(self, infos):
        # 这些数据是为了对照用的
        # 'type': tpe,
        # 'thread_id': thread_id,
        # 'forum_id': forum_id,
        # 'title': title,
        # 'content': content,
        # 'user_name': user_name,
        # 'user_portrait_pixmap': user_head_pixmap,
        # 'forum_name': '',
        # 'forum_pixmap': QPixmap(),
        # 'view_pixmap': preview_pixmap,
        # 'time_stamp': timestr,
        # 'view_count': view_count,
        # 'agree_count': agree_count,
        # 'reply_count': reply_count,
        # 'repost_count': repost_count
        item = QListWidgetItem()
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)

        widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], infos['content'],
                         infos['forum_pixmap'], infos['forum_name'])
        widget.set_picture(infos['view_pixmap'])
        widget.set_thread_values(infos['view_count'], infos['agree_count'], infos['reply_count'], infos['repost_count'])
        widget.is_treasure = infos['is_treasure']
        widget.is_top = infos['is_top']
        widget.label.hide()
        widget.label_10.hide()
        widget.pushButton_3.hide()
        widget.label_2.setText(infos['time_stamp'])
        widget.adjustSize()
        item.setSizeHint(widget.size())

        if infos['type'] == 'latest_reply':
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif infos['type'] == 'latest_send':
            self.listWidget_5.addItem(item)
            self.listWidget_5.setItemWidget(item, widget)
        elif infos['type'] == 'hot':
            self.listWidget_3.addItem(item)
            self.listWidget_3.setItemWidget(item, widget)
        elif infos['type'] == 'top':
            self.listWidget_4.addItem(item)
            self.listWidget_4.setItemWidget(item, widget)
        elif infos['type'] == 'treasure':
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)

        self.added_thread_count += 1

    def show_load_ok_msg(self):
        # 初始化计时器
        self.text_timer = QTimer(self)
        self.text_timer.setSingleShot(True)
        self.text_timer.setInterval(5000)
        self.text_timer.timeout.connect(self.label_5.clear)

        self.label_5.setText(f'贴子刷新成功，已为你推荐 {self.added_thread_count} 条内容')
        self.text_timer.start()
        self.added_thread_count = 0

    def refresh_all(self):
        if not self.isloading:
            # 清理内存
            for i in self.listwidgets:
                i.clear()
            QPixmapCache.clear()
            gc.collect()

            # 启动刷新
            self.page = {'latest_reply': 1, 'latest_send': 1, 'hot': 1, 'top': 1, 'treasure': 1}
            self.get_threads_async()

    def scroll_load_more(self):
        if not self.isloading:
            flag_latest_reply = self.listWidget.verticalScrollBar().value() == self.listWidget.verticalScrollBar().maximum()
            flag_latest_send = self.listWidget_5.verticalScrollBar().value() == self.listWidget_5.verticalScrollBar().maximum()
            flag_hot = self.listWidget_3.verticalScrollBar().value() == self.listWidget_3.verticalScrollBar().maximum()
            flag_top = self.listWidget_4.verticalScrollBar().value() == self.listWidget_4.verticalScrollBar().maximum()
            flag_treasure = self.listWidget_2.verticalScrollBar().value() == self.listWidget_2.verticalScrollBar().maximum()

            if flag_latest_send and self.tabWidget.currentIndex() == 3:
                self.get_threads_async(thread_type="latest_send")
            if flag_latest_reply and self.tabWidget.currentIndex() == 2:
                self.get_threads_async(thread_type="latest_reply")
            if flag_hot and self.tabWidget.currentIndex() == 4:
                self.get_threads_async(thread_type="hot")
            if flag_top and self.tabWidget.currentIndex() == 0:
                self.get_threads_async(thread_type="top")
            if flag_treasure and self.tabWidget.currentIndex() == 1:
                self.get_threads_async(thread_type="treasure")

    def get_threads_async(self, thread_type="all"):
        if not self.isloading:
            if thread_type == 'all':
                self.label_5.setText('贴子刷新中...')
            start_background_thread(self.get_threads, (thread_type,))

    def get_threads(self, thread_type="all"):
        def emit_data(tpe, thread):
            if tpe == 'latest_reply':
                timestr = '最近回复于 ' + timestamp_to_string(thread.last_time)
            else:
                timestr = '发布于 ' + timestamp_to_string(thread.create_time)
            thread_id = thread.tid
            forum_id = self.forum_id
            title = thread.title
            _text = make_thread_content(thread.contents.objs, previewPlainText=True)
            content = cut_string(_text, 50)
            user_name = thread.user.nick_name_new
            portrait = thread.user.portrait
            preview_pixmap = []
            view_count = thread.view_num
            agree_count = thread.agree
            reply_count = thread.reply_num
            repost_count = thread.share_num
            is_treasure = thread.is_good
            is_top = thread.is_top

            user_head_pixmap = QPixmap()
            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            for j in thread.contents.imgs:
                hash = j.hash
                pixmap = QPixmap()
                pixmap.loadFromData(cache_mgr.get_bd_hash_img(hash))
                pixmap = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                preview_pixmap.append(pixmap)

            tdata = {'type': tpe,
                     'thread_id': thread_id,
                     'forum_id': forum_id,
                     'title': title,
                     'content': content,
                     'user_name': user_name,
                     'user_portrait_pixmap': user_head_pixmap,
                     'forum_name': '',
                     'forum_pixmap': QPixmap(),
                     'view_pixmap': preview_pixmap,
                     'time_stamp': timestr,
                     'view_count': view_count,
                     'agree_count': agree_count,
                     'reply_count': reply_count,
                     'repost_count': repost_count,
                     'is_treasure': is_treasure,
                     'is_top': is_top}
            self.add_thread.emit(tdata)

        async def get_latest_reply_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['latest_reply'])
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('latest_reply', i)
            except Exception as e:
                print(type(e))
                print(e)

        async def get_latest_send_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['latest_send'],
                                                       sort=aiotieba.ThreadSortType.CREATE)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('latest_send', i)
            except Exception as e:
                print(type(e))
                print(e)

        async def get_hot_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['hot'],
                                                       sort=aiotieba.ThreadSortType.HOT)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('hot', i)
            except Exception as e:
                print(type(e))
                print(e)

        async def get_top_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['top'],
                                                       sort=aiotieba.ThreadSortType.REPLY)
                    for i in threads.objs:
                        if i.is_top:
                            emit_data('top', i)
            except Exception as e:
                print(type(e))
                print(e)

        async def get_treasure_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['treasure'],
                                                       sort=aiotieba.ThreadSortType.REPLY, is_good=True)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('treasure', i)
            except Exception as e:
                print(type(e))
                print(e)

        def run_a_async(func):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(func())

        def start_all_process():
            thread_list = []
            self.isloading = True

            if thread_type == 'latest_reply' or thread_type == 'all':
                thread_list.append(start_background_thread(run_a_async, (get_latest_reply_detail,)))
            if thread_type == 'latest_send' or thread_type == 'all':
                thread_list.append(start_background_thread(run_a_async, (get_latest_send_detail,)))
            if thread_type == 'hot' or thread_type == 'all':
                thread_list.append(start_background_thread(run_a_async, (get_hot_detail,)))
            if thread_type == 'top' or thread_type == 'all':
                thread_list.append(start_background_thread(run_a_async, (get_top_detail,)))
            if thread_type == 'treasure' or thread_type == 'all':
                thread_list.append(start_background_thread(run_a_async, (get_treasure_detail,)))

            for i in thread_list:
                i.join()

            if thread_type == 'all':
                for k in tuple(self.page.keys()):
                    self.page[k] += 1
            else:
                self.page[thread_type] += 1
            if thread_type == "all":
                self.thread_refresh_ok.emit()
            else:
                self.added_thread_count = 0
            self.isloading = False

        start_all_process()

    def load_info_async(self):
        self.flash_shower.show()
        start_background_thread(self.load_info)

    def update_info_ui(self, datas):
        # tdata = {'name': forum_name, 'pixmap': forum_pixmap, 'slogan': forum_slogan, 'follownum': follow_count,
        #          'postnum': post_count, 'admin_name': forum_admin_name, 'admin_pixmap': forum_admin_pixmap}
        self.setWindowTitle(datas['name'] + '吧')
        self.setWindowIcon(QIcon(datas['pixmap']))

        self.label_3.setText('{0} 人关注，{1} 条贴子'.format(datas['follownum'], datas['postnum']))
        self.label.setPixmap(datas['pixmap'])
        self.label_2.setText(datas['name'] + '吧')

        if datas['is_followed'] == 1:
            qss = ('QLabel{color: rgb(255,255,255);background-color: [color];border-width: 1px 4px;border-style: '
                   'solid;border-color: [color]}')
            if 1 <= datas['uf_level'] <= 3:  # 绿牌
                qss = qss.replace('[color]', 'rgb(101, 211, 171)')
            elif 4 <= datas['uf_level'] <= 9:  # 蓝牌
                qss = qss.replace('[color]', 'rgb(101, 161, 255)')
            elif 10 <= datas['uf_level'] <= 15:  # 黄牌
                qss = qss.replace('[color]', 'rgb(253, 194, 53)')
            elif datas['uf_level'] >= 16:  # 橙牌老东西
                qss = qss.replace('[color]', 'rgb(247, 126, 48)')

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss
            self.label_9.setText(datas['level_info'])
            self.label_9.show()

        if datas['admin_name']:
            self.label_6.setPixmap(datas['admin_pixmap'])
            self.label_7.setText(datas['admin_name'])
        else:
            self.label_6.hide()
            self.gridLayout_5.removeWidget(self.label_6)
            self.label_7.setText('本吧暂时没有吧主。')

        if datas['is_followed'] == 1:
            self.pushButton.setText('已关注')
            self.pushButton.setEnabled(False)
            self.pushButton.setToolTip('已关注此吧')
        elif datas['is_followed'] == 2:
            self.pushButton.setText('登录后即可关注')
            self.pushButton.setEnabled(False)
        self.pushButton.show()
        self.flash_shower.hide()

    def load_info(self):
        async def get_detail():
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                # 获取吧信息
                aiotieba.logging.get_logger().info(f'forum (id {self.forum_id}) loading head_info')
                forum = await client.get_forum(self.forum_id)

                level_info = ''
                level_value = 1
                if self.bduss:
                    aiotieba.logging.get_logger().info(
                        f'forum (id {self.forum_id}, name {forum.fname}) loading level_info')
                    forum_level_info = await client.get_forum_level(self.forum_id)
                    isFollowed = 1 if forum_level_info.is_like else 0
                    if forum_level_info.is_like:
                        level_info = f'Lv.{forum_level_info.user_level} {forum_level_info.level_name}'
                        level_value = forum_level_info.user_level
                else:
                    isFollowed = 2
                self.forum_name = forum_name = forum.fname
                forum_slogan = forum.slogan
                follow_count = forum.member_num
                post_count = forum.post_num
                if forum.has_bawu:
                    aiotieba.logging.get_logger().info(
                        f'forum (id {self.forum_id}, name {forum_name}) loading bazhu_info')
                    bawuinfo = await client.get_bawu_info(self.forum_id)
                    forum_admin_name = bawuinfo.admin[0].nick_name_new
                    aiotieba.logging.get_logger().info(
                        f'forum (id {self.forum_id}, name {forum_name}) loading bazhu_portrait_bin_info')
                    forum_admin_pixmap = QPixmap()
                    forum_admin_pixmap.loadFromData(cache_mgr.get_portrait(bawuinfo.admin[0].portrait))
                    forum_admin_pixmap = forum_admin_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                else:
                    forum_admin_name = ''
                    forum_admin_pixmap = None
                aiotieba.logging.get_logger().info(
                    f'forum (id {self.forum_id}, name {forum_name}) loading headimg_bin_info')
                forum_pixmap = QPixmap()
                response = requests.get(forum.small_avatar, headers=request_mgr.header)
                if response.content:
                    forum_pixmap.loadFromData(response.content)
                    forum_pixmap = forum_pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                aiotieba.logging.get_logger().info(
                    f'forum (id {self.forum_id}, name {forum_name}) head_info all load ok, sending to qt thread')
                tdata = {'name': forum_name, 'pixmap': forum_pixmap, 'slogan': forum_slogan, 'follownum': follow_count,
                         'postnum': post_count, 'admin_name': forum_admin_name, 'admin_pixmap': forum_admin_pixmap,
                         'is_followed': isFollowed, 'level_info': level_info, 'uf_level': level_value}
                self.update_signal.emit(tdata)

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(get_detail())
