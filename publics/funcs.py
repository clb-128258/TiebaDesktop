import os
import pathlib
import platform
import queue
import subprocess
import threading
import time

import pyperclip
import requests
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QByteArray, QSize, QEvent
from PyQt5.QtGui import QMovie, QIcon, QPixmap
from PyQt5.QtWidgets import QWidget, QListWidgetItem, QTreeWidgetItem

import consts
import aiotieba
import json

from publics import aes, profile_mgr, request_mgr, qt_window_mgr, cache_mgr
from ui import loading_amt, user_item

datapath = consts.datapath


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
        from subwindow.tieba_web_browser import TiebaWebBrowser
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
        from subwindow.user_home_page import UserHomeWindow
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
