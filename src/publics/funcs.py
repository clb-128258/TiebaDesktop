import asyncio
import os
import pathlib
import socket
import subprocess
import threading
import time
import datetime
import ctypes
import aiohttp.client_exceptions

import pyperclip
import requests
from PyQt5.QtCore import pyqtSignal, Qt, QByteArray, QSize, QEvent, QTimer
from PyQt5.QtGui import QMovie, QIcon, QPixmap
from PyQt5.QtWidgets import QWidget, QListWidgetItem, QTreeWidgetItem

import consts
import aiotieba
import json

from publics import aes, profile_mgr, request_mgr, qt_window_mgr, qt_image
import publics.app_logger as logging
from publics.toasting import init_AUMID
from ui import loading_amt, user_item


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
    logging.log_INFO('Creating user data')

    if not os.path.isdir(consts.datapath):
        init_AUMID(consts.WINDOWS_AUMID, '贴吧桌面', pathlib.Path(f"{os.getcwd()}/ui/tieba_logo_big_single.ico"))

    expect_folder = [consts.datapath,
                     f'{consts.datapath}/webview_data',
                     f'{consts.datapath}/logs',
                     f'{consts.datapath}/image_caches',
                     f'{consts.datapath}/cache_index',
                     f'{consts.datapath}/webview_data/default']  # 欲创建的文件夹
    expect_secret_json = {f'{consts.datapath}/user_bduss': {'current_bduss': '', 'login_list': []}}  # 欲创建的加密json文件
    expect_json = {f'{consts.datapath}/config.json': profile_mgr.local_config_model,
                   f'{consts.datapath}/cache_index/fidfname_index.json': {},
                   f'{consts.datapath}/d2id_flag': {'uid': ''},
                   f'{consts.datapath}/view_history': [],
                   f'{consts.datapath}/post_drafts': {},
                   f'{consts.datapath}/window_rects.json': {}}  # 欲创建的json文件

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


def listWidget_get_visible_widgets(listWidget):
    """获取qlistwidget中所有可见的qwidget条目"""

    # https://stackoverflow.com/questions/63724917/get-current-visible-qlistwidget-items
    rect = listWidget.viewport().contentsRect()
    top = listWidget.indexAt(rect.topLeft())
    result = []
    if top.isValid():
        bottom = listWidget.indexAt(rect.bottomLeft())
        if not bottom.isValid():
            bottom = listWidget.model().index(listWidget.count() - 1)
        for index in range(top.row(), bottom.row() + 1):
            result.append(listWidget.itemWidget(listWidget.item(index)))
    return result


def large_num_to_string(num: int, prespace=False, endspace=False):
    """
    把大数字转换为字符串

    Args:
        num (int): 欲转换的数字
        prespace (bool): 在结果数值没有单位后缀时 是否在前面添加空格字符
        endspace (bool): 在结果数值没有单位后缀时 是否在后面添加空格字符
    """
    if num < 10 ** 4:
        return (' ' if prespace else "") + str(num) + (' ' if endspace else "")
    elif 10 ** 4 <= num < 10 ** 8:
        return str(round(num / 10 ** 4, 2)) + ' 万'
    elif num >= 10 ** 8:
        return str(round(num / 10 ** 8, 2)) + ' 亿'


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
            _text += f'[语音] {format_second(i.duration)}'
        elif type(i) == aiotieba.get_posts._classdef.FragVideo and previewPlainText:
            _text += f'[视频] 时长 {format_second(i.duration)} | {large_num_to_string(i.view_num, endspace=True)}次浏览'

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
    logging.log_INFO(f'start download {src} to local file {path}.')
    resp = requests.get(src, headers=request_mgr.header, stream=True)
    if resp.status_code == 200:
        logging.log_INFO(f'server returned status code 200, start to write data.')
        f = open(path + '.crdownload', 'wb')
        for i in resp.iter_content(chunk_size=128 * 1024):
            f.write(i)
        f.close()
        os.rename(path + '.crdownload', path)  # 改回最终文件格式
        logging.log_INFO(f'file write finish, download OK.')
    else:
        logging.log_INFO(f'can not download file because http {resp.status_code} error.')


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
    """根据url打开相应的界面"""
    from subwindow.forum_show_window import ForumShowWindow
    from subwindow.thread_detail_view import ThreadDetailView
    from subwindow.user_home_page import UserHomeWindow
    from subwindow.tieba_web_browser import TiebaWebBrowser

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

    def open_ba_detail(fname_id):
        async def get_fid():
            try:
                async with aiotieba.Client(proxy=True) as client:
                    fid = await client.get_fid(fname_id)
                    return fid
            except:
                return 0

        if isinstance(fname_id, str):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            fid = asyncio.run(get_fid())
        else:
            fid = fname_id

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
    elif url.startswith('tieba_forum://'):
        open_ba_detail(int(url.replace('tieba_forum://', '')))
    elif url.startswith(('http://clb.tiebadesktop.localpage', 'https://clb.tiebadesktop.localpage')):  # 内部链接
        open_in_webview()
    else:
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
        timestr = f'{int(time_separation)} 秒前'
    elif time_separation < 3600:  # 一小时以内
        timestr = f'{int(time_separation / 60)} 分钟前'
    elif time_separation < 86400:  # 一天以内
        timestr = f'{int(time_separation / 3600)} 小时前'
    elif time_separation < 604800:  # 一星期以内
        timeArray = time.localtime(ts)
        nodate_timestr = time.strftime("%H:%M:%S", timeArray)
        pass_days = int(time_separation / 86400)
        if pass_days == 1:
            pass_days_str = '昨天'
        elif pass_days == 2:
            pass_days_str = '前天'
        else:
            pass_days_str = f'{pass_days} 天前'

        timestr = f'{pass_days_str}的 {nodate_timestr}'
    elif ts >= datetime.datetime(datetime.datetime.now().year, 1, 1, 0, 0, 0).timestamp():  # 今年以内
        timeArray = time.localtime(ts)
        timestr = time.strftime("%m-%d %H:%M:%S", timeArray)
    else:  # 更早的
        timeArray = time.localtime(ts)
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)

    return timestr


def system_has_network():
    """
    检测用户的电脑是否有网络连接

    Notes:
        在 Windows 下采用 InternetGetConnectedState 函数检测连接状态，返回结果可能不准确
    """

    def has_default_route_linux():
        if not os.path.exists("/proc/net/route"):
            return False
        with open("/proc/net/route") as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == "00000000":  # 默认路由的目标是 0.0.0.0（十六进制）
                    return True
        return False

    def has_default_route_windows():
        wininet = ctypes.windll.wininet
        flags = ctypes.c_uint(0)
        connected = wininet.InternetGetConnectedState(ctypes.byref(flags), 0)
        return bool(connected)

    if os.name == 'nt':
        return has_default_route_windows()
    elif os.name == 'posix':
        return has_default_route_linux()
    else:
        return None


def get_exception_string(error: Exception):
    """获取错误对象的字符串解释"""

    def extract_gai_error(exc):
        if isinstance(exc, socket.gaierror):
            return exc
        cause = getattr(exc, '__cause__', None) or getattr(exc, '__context__', None)
        if cause is not None and cause is not exc:  # 防止循环
            return extract_gai_error(cause)
        return None

    def extract_system_error(exc):
        try:
            error_string = str(exc)
            error_string = error_string.split('Failed to establish a new connection: ')[-1][0:-3]
            if error_string.startswith('[WinError '):
                code = int(error_string.split(' ')[1][0:-1])
                msg = ' '.join(error_string.split(' ')[2:])
                return code, msg
            else:
                return None, error_string
        except:
            return None, str(exc)

    if isinstance(error, aiotieba.exception.TiebaServerError):
        return f'{error.msg} (错误代码 {error.code})'
    elif isinstance(error, aiotieba.exception.HTTPStatusError):
        return f'HTTP {error.code} {error.msg} 错误'
    elif isinstance(error, aiotieba.exception.TiebaValueError):
        return '服务器返回的字段值有误'
    elif isinstance(error, aiotieba.exception.ContentTypeError):
        return 'HTTP 报文中的 Content-Type 无法被解析'

    elif isinstance(error, requests.exceptions.HTTPError):
        return f'HTTP {error.response.status_code} 错误'
    elif isinstance(error, requests.exceptions.ProxyError):
        return f'代理服务器不可达，请检查代理设置，或是尝试关闭正在使用的代理软件'
    elif isinstance(error, requests.exceptions.SSLError):
        return f'SSL 校验失败'
    elif isinstance(error, requests.exceptions.Timeout):
        return f'网络连接超时'
    elif isinstance(error, requests.exceptions.ContentDecodingError):
        return f'HTTP 报文解析失败'
    elif isinstance(error, requests.exceptions.ChunkedEncodingError):
        return f'服务器返回了无效的数据包'
    elif isinstance(error, requests.exceptions.TooManyRedirects):
        return f'重定向次数过多，可能已引发服务器的风控机制'
    elif isinstance(error, requests.exceptions.MissingSchema):
        return f'链接语法不正确，无法解析'
    elif isinstance(error, requests.exceptions.JSONDecodeError):
        return f'JSON 解析失败'
    elif isinstance(error, requests.exceptions.ConnectionError):
        has_network = system_has_network()
        gai_err = extract_gai_error(error)
        system_error = extract_system_error(error)
        if not has_network:
            return '未连接到互联网，请检查网络设置，并检查网线是否已插好'
        elif gai_err:
            return f'DNS 解析失败，请检查 DNS 设置'
        else:
            return f'网络连接错误: {system_error[1]}{f" (错误代码 {system_error[0]})" if system_error[0] else ""}'

    elif isinstance(error, aiohttp.client_exceptions.ClientConnectorDNSError):
        has_network = system_has_network()
        if not has_network:
            return '未连接到互联网，请检查网络设置，并检查网线是否已插好'
        else:
            return f'DNS 解析失败，请检查 DNS 设置'
    elif isinstance(error, aiohttp.client_exceptions.ClientProxyConnectionError):
        return f'代理服务器不可达，请检查代理设置，或是尝试关闭正在使用的代理软件'
    elif isinstance(error, aiohttp.client_exceptions.ServerTimeoutError):
        return f'网络连接超时'
    elif isinstance(error, aiohttp.client_exceptions.ClientSSLError):
        return f'SSL 校验失败'

    elif isinstance(error, KeyError):
        return '数据的参数不全'
    elif isinstance(error, json.JSONDecodeError):
        return f'JSON 解析失败'
    else:
        return str(error)


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
    __user_real_portrait = ''
    __user_avatar_loaded = False
    show_homepage_by_click = False
    switchRequested = pyqtSignal(tuple)
    deleteRequested = pyqtSignal(tuple)
    doubleClicked = pyqtSignal()
    load_by_callback = False

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.label_3.setToolTip(
            '请注意，贴吧 ID 与用户 ID 不同，贴吧 ID 显示在贴吧 APP 的个人主页上，用户 ID 则主要供 APP 内部使用。')

        self.toolButton.setIcon(QIcon('ui/content_copy.png'))
        self.toolButton.clicked.connect(self.show_toolbutton_icon)

        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentImageChanged.connect(
            lambda: self.label.setPixmap(self.portrait_image.currentPixmap()))
        self.destroyed.connect(self.portrait_image.destroyImage)

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.doubleClicked.emit()
        if self.show_homepage_by_click:
            self.open_user_homepage(self.user_portrait_id)

    def show_toolbutton_icon(self):
        self.toolButton.setIcon(QIcon('ui/checked.png'))
        QTimer.singleShot(2000, lambda: self.toolButton.setIcon(QIcon('ui/content_copy.png')))

    def open_user_homepage(self, uid):
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def get_portrait(self):
        if not self.__user_avatar_loaded:
            self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                             self.__user_real_portrait,
                                             qt_image.ImageCoverType.RoundCover,
                                             (50, 50))
            self.portrait_image.loadImage()
            self.__user_avatar_loaded = True

    def setdatas(self, uicon, uname, uid=-1, show_switch=False, is_current_user=False, is_tieba_uid=False,
                 custom_desp_str=''):
        if uicon:
            if isinstance(uicon, QPixmap):
                self.label.setPixmap(uicon)
            elif isinstance(uicon, str):
                self.__user_real_portrait = uicon
                if not self.load_by_callback:
                    self.get_portrait()
        else:
            self.label.hide()
        self.label_2.setText(uname)

        if custom_desp_str:
            self.label_3.setText(custom_desp_str)
            self.label_3.setToolTip('')
            self.toolButton.hide()
        elif uid != -1:
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
