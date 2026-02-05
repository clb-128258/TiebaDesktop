import asyncio
import os
import platform
import queue
import subprocess
import time

import aiotieba
import requests

from PyQt5.QtCore import QObject, pyqtSignal

import consts
from publics import request_mgr, toasting, cache_mgr, profile_mgr
from publics.funcs import start_background_thread, system_has_network, open_url_in_browser
import publics.logging as logging


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
    activeWindow = pyqtSignal()
    is_running = False
    latest_count = -1

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

    def run_msg_sync_immedently(self):
        """立刻执行一次消息同步"""
        if self.is_running:
            self.event_queue.put('query_msg')

    def have_basic_unread_notice(self):
        """当前是否存在未读的点赞、回复、@通知"""
        return self.get_basic_unread_notice_count() != 0

    def have_unread_notice(self):
        """当前是否存在未读通知"""
        return self.get_unread_notice_count(UnreadMessageType.TOTAL_COUNT) != 0

    def get_basic_unread_notice_count(self):
        """获取未读的点赞、回复、@通知数"""
        return (self.get_unread_notice_count(UnreadMessageType.AGREE) +
                self.get_unread_notice_count(UnreadMessageType.AT) +
                self.get_unread_notice_count(UnreadMessageType.REPLY))

    def get_unread_notice_count(self, msg_type):
        """获取某个类型的未读通知数"""
        return self.unread_msg_counts.get(msg_type, 0)

    def save_toast_settings(self, ntype):
        profile_mgr.local_config["notify_settings"][ntype] = False
        profile_mgr.save_local_config()

    def show_offline_toast(self):
        def open_network_panel():
            if platform.system() == 'Windows':  # windows 系统
                if int(platform.version().split('.')[-1]) < 10240:  # win10以下系统
                    subprocess.call('control /name Microsoft.NetworkandSharingCenter', shell=True)
                else:
                    # win10 以后系统调用 UWP 设置
                    open_url_in_browser('ms-settings:network')

        if profile_mgr.local_config["notify_settings"]["offline_notify"]:
            toasting.showMessage('你的电脑未连接到互联网',
                                 '本软件的主要功能将无法使用。\n单击此通知可打开系统的网络设置界面。',
                                 buttons=[toasting.Button('关闭此类通知',
                                                          lambda: self.save_toast_settings('offline_notify'))],
                                 callback=open_network_panel,
                                 lowerText='无网络通知')

    def show_interact_toast(self, title, text, icon_path=''):
        async def set_read():
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                # 把互动消息全部获取一遍，这样服务器就会标记已读
                await client.get_replys()
                await client.get_ats()

                payload = {
                    'BDUSS': self.bduss,
                    '_client_type': '2',
                    '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                    'rn': '20',
                    'stoken': self.stoken,
                }
                request_mgr.run_post_api('/c/u/feed/agreeme', payloads=request_mgr.calc_sign(payload),
                                         use_mobile_header=True, host_type=2)

        def start_async(func):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(func())

        toasting.showMessage(title,
                             text,
                             icon=icon_path,
                             buttons=[toasting.Button('标记为已读', lambda: start_async(set_read)),
                                      toasting.Button('关闭此类通知',
                                                      lambda: self.save_toast_settings('enable_interact_notify'))],
                             callback=self.activeWindow.emit,
                             lowerText='新消息通知')

    def get_interactMsgAlter(self):
        """通过接口 https://tiebac.baidu.com/c/s/interactMsgAlter 获取详细的互动消息信息，并发出通知"""
        interact_count = self.get_basic_unread_notice_count()
        if profile_mgr.local_config["notify_settings"]["enable_interact_notify"] and interact_count > 0:
            payloads = {
                "BDUSS": self.bduss,
                "_client_type": "2",
                "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                "need_get_all": "1",
                "stoken": self.stoken,
            }
            resp = request_mgr.run_post_api('/c/s/interactMsgAlter',
                                            request_mgr.calc_sign(payloads),
                                            use_mobile_header=True,
                                            host_type=2)
            if resp['data'].get('title'):
                title = resp['data']['title']
                text = resp['data']['desc']

                if icon_list := resp['data'].get("icon_list"):
                    link = icon_list[-1]

                    if link.startswith('http://tb.himg.baidu.com/sys/portrait/item/'):
                        portrait = link.split('/')[-1].replace('.jpg', '')
                        cache_path = f'{consts.datapath}/image_caches/portrait_{portrait}.jpg'
                        if not os.path.isfile(cache_path):
                            cache_mgr.save_portrait(portrait)
                    else:
                        timestr = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time()))
                        cache_path = f'{consts.datapath}/image_caches/ToastNotifyIconCache_{timestr}.jpg'
                        icon_response = requests.get(link, headers=request_mgr.header)
                        if icon_response.content and icon_response.status_code == 200:
                            with open(cache_path, 'wb') as file:
                                file.write(icon_response.content)

                    self.show_interact_toast(title, text, cache_path)

    def run_sleeper(self):
        sleeper_time = 60

        for i in range(sleeper_time):
            time.sleep(1)
            if not self.event_queue.empty():
                return self.event_queue.get()

        return ''

    def unread_notice_sync_thread(self):
        """未读通知数同步线程"""
        self.is_running = True
        is_offline = False
        logging.log_INFO('notice syncer started')
        while True:
            try:
                if self.bduss and self.stoken:
                    self.load_unread_notice_from_api()
                    is_offline = False

                    if self.latest_count != self.get_basic_unread_notice_count():
                        self.latest_count = self.get_basic_unread_notice_count()
                        self.noticeCountChanged.emit()
                        if self.latest_count != 0:
                            start_background_thread(self.get_interactMsgAlter)
            except Exception as e:
                logging.log_exception(e)
                if not system_has_network() and not is_offline:
                    is_offline = True
                    self.show_offline_toast()
            finally:
                e = self.run_sleeper()
                if e == 'stop':
                    break
                elif e == 'query_msg':
                    continue
        self.is_running = False
        logging.log_INFO('notice syncer stopped')

    def load_unread_notice_from_api(self):
        """从接口重新加载未读通知数"""
        payloads = {
            "BDUSS": self.bduss,
            "_client_type": "2",
            "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
            "stoken": self.stoken,
        }
        resp = request_mgr.run_post_api('/c/s/msg',
                                        request_mgr.calc_sign(payloads),
                                        use_mobile_header=True,
                                        host_type=2)
        self.unread_msg_counts = resp['message']
        if self.unread_msg_counts:
            self.unread_msg_counts['count'] = 0
            for k, v in tuple(self.unread_msg_counts.items()):
                if k != 'count':
                    self.unread_msg_counts['count'] += v
