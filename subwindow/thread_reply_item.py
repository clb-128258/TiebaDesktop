import aiotieba
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QEvent
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QListWidgetItem

from publics import request_mgr, qt_window_mgr, profile_mgr
from publics.funcs import start_background_thread, open_url_in_browser
import publics.logging as logging

from ui import comment_view


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

    show_msg_outside = False
    messageAdded = pyqtSignal(str)

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
            if self.show_msg_outside:
                self.messageAdded.emit(isok)
            else:
                QMessageBox.information(self, '点赞操作完成', isok)

    def agree_thread_async(self, is_cancel=False):
        start_background_thread(self.agree_thread, (is_cancel,))

    def agree_thread(self, iscancel=False):
        logging.log_INFO(f'agree reply/comment {self.post_id} in thread {self.thread_id}')
        try:
            if not self.bduss:
                self.agree_thread_signal.emit('你还没有登录，登录后即可为这条回复点赞')
            elif self.portrait == '00000000':
                self.agree_thread_signal.emit('不能给匿名用户点赞')
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
                        self.agree_thread_signal.emit('取消点赞成功')
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
                        self.agree_thread_signal.emit("点赞成功 首赞经验 +2" if is_expa2 else "点赞成功")
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
                from subwindow.reply_sub_comments import ReplySubComments
                self.replyWindow = ReplySubComments(self.bduss, self.stoken, self.thread_id, self.post_id, self.floor,
                                                    self.c_count, show_thread_button=self.subcomment_show_thread_button)
            self.replyWindow.show()
            self.replyWindow.raise_()
            if self.replyWindow.isMinimized():
                self.replyWindow.showNormal()
            if not self.replyWindow.isActiveWindow():
                self.replyWindow.activateWindow()
        else:
            if self.show_msg_outside:
                self.messageAdded.emit(f'第 {self.floor} 楼还没有任何回复')
            else:
                QMessageBox.information(self, '暂无回复', f'第 {self.floor} 楼还没有任何回复。', QMessageBox.Ok)

    def update_listwidget_size(self, h):
        # 动态更新内容列表大小
        self.height_count += h
        self.listWidget.setFixedHeight(self.height_count)

    def open_ba_detail(self, fid):
        from subwindow.forum_show_window import ForumShowWindow
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(fid))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def open_thread(self, tid):
        from subwindow.thread_detail_view import ThreadDetailView
        third_party_thread = ThreadDetailView(self.bduss, self.stoken, int(tid))
        qt_window_mgr.add_window(third_party_thread)

    def open_user_homepage(self, uid):
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def handle_link_event(self, url):
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
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(255, 172, 29);}'
            elif level >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48);}'

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss

        if not pixmaps and not voice_info['have_voice']:
            self.listWidget.hide()
        else:
            for i in pixmaps:
                from subwindow.thread_picture_label import ThreadPictureLabel
                label = ThreadPictureLabel(i['width'], i['height'], i['src'], i['view_src'])

                item = QListWidgetItem()
                item.setSizeHint(label.size())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, label)

                self.update_listwidget_size(i['height'] + 35)

            if voice_info['have_voice']:
                from subwindow.thread_voice_item import ThreadVoiceItem
                voice_widget = ThreadVoiceItem()
                voice_widget.setdatas(voice_info['src'], voice_info['length'])
                item = QListWidgetItem()
                item.setSizeHint(voice_widget.size())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, voice_widget)
                self.update_listwidget_size(voice_widget.height())

        self.adjustSize()
