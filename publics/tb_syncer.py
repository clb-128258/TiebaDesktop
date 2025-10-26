import queue
import time

from PyQt5.QtCore import QObject, pyqtSignal

from publics import request_mgr
from publics.funcs import start_background_thread
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
        logging.log_INFO('notice syncer started')
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
                    logging.log_exception(e)
                else:
                    self.noticeCountChanged.emit()
                finally:
                    time.sleep(5)
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
        resp = request_mgr.run_post_api('/c/s/msg', request_mgr.calc_sign(payloads), use_mobile_header=True,
                                        host_type=2)
        self.unread_msg_counts = resp['message']
        if self.unread_msg_counts:
            self.unread_msg_counts['count'] = 0
            for k, v in tuple(self.unread_msg_counts.items()):
                if k != 'count':
                    self.unread_msg_counts['count'] += v
