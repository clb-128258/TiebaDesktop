import asyncio
import aiotieba
import pyperclip

from PyQt5.QtCore import pyqtSignal, Qt, QEvent, QSize, QPoint
from PyQt5.QtGui import QPixmap, QCursor, QIcon
from PyQt5.QtWidgets import QMessageBox, QListWidgetItem, QAction

from typing import Union

from publics import qt_window_mgr, profile_mgr, qt_image, account_mgr, app_logger, top_toast_widget
from publics.funcs import start_background_thread, open_url_in_browser, large_num_to_string, get_exception_string, \
    show_label_pixmap_with_animation
import publics.app_logger as logging
from publics.baidu_features.tieba_apis import agree_thread_or_post, OpAgreeObjectType, store_thread
from subwindow import base_ui

from ui import comment_view


def find_first_reply_window(post_id, show_thread_button) -> bool:
    """
    寻找并调起第一个与传参相匹的楼中楼窗口

    Return:
        找到了返回True，没找到返回False
    """

    from subwindow.reply_sub_comments import ReplySubComments
    for w in qt_window_mgr.distributed_window:
        if isinstance(w, ReplySubComments) and w.pushButton.isVisible() == show_thread_button and w.post_id == post_id:
            w.show()
            w.raise_()
            if w.isMinimized():
                w.showNormal()
            if not w.isActiveWindow():
                w.activateWindow()
            return True

    return False


class ReplyItem(base_ui.WindowBaseQWidget, comment_view.Ui_Form):
    """嵌入在列表里的回复贴内容"""
    height_count = 0
    c_count = -1
    floor = -1

    portrait = ''
    thread_id = -1
    post_id = -1
    forum_id = -1

    allow_home_page = True
    subcomment_show_thread_button = False
    agree_num = 0
    is_comment = False

    load_by_callback = False
    show_msg_outside = False
    is_agreed = False

    agree_thread_signal = pyqtSignal(str)
    messageAdded = pyqtSignal(top_toast_widget.ToastMessage)
    postItemDeleted = pyqtSignal()

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.image_list = []
        self.__is_loaded = False

        icon_size = QSize(20, 20)
        self.pushButton_3.setIconSize(icon_size)
        self.pushButton.setIconSize(icon_size)

        self.label_13.hide()
        self.label_10.hide()
        self.listWidget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.label_10.setContextMenuPolicy(Qt.NoContextMenu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_6.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label_6.customContextMenuRequested.connect(self.show_text_content_menu)
        self.label_10.linkActivated.connect(self.handle_link_event)
        self.pushButton.clicked.connect(self.show_subcomment_window)
        self.pushButton_3.clicked.connect(self.agree_thread_from_click)
        self.agree_thread_signal.connect(self.agree_thread_ok_action)
        self.toolButton.clicked.connect(self.init_more_menu)

        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label_4, pixmap))
        self.destroyed.connect(self.portrait_image.destroyImage)

        # 重写事件过滤器
        self.label_3.installEventFilter(self)
        self.label_4.installEventFilter(self)
        self.label_9.installEventFilter(self)

    def reset_theme(self):
        from subwindow.thread_picture_label import ThreadPictureLabel

        super().reset_theme()
        self.add_extend_qss(f'QPushButton{{color: {profile_mgr.get_theme_font_color_string()};}}')

        bg_policy, font_policy = profile_mgr.get_theme_policy_string()
        self.toolButton.setIcon(QIcon(f'ui/icon_{font_policy}/more_horiz.png'))
        self.pushButton.setIcon(QIcon(f'ui/icon_{font_policy}/comment.png'))

        self.set_agree_button_status()

        # 设置列表内容的样式
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            if not isinstance(widget, ThreadPictureLabel):
                widget.reset_theme()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if source in (self.label_3, self.label_4) and self.allow_home_page:
                self.open_user_homepage(self.portrait)
            elif source is self.label_9:
                self.open_forum_detail_page()

        return super(ReplyItem, self).eventFilter(source, event)  # 照常处理事件

    def set_agree_button_status(self):
        self.pushButton_3.setText(f' {large_num_to_string(self.agree_num)}')

        bg_policy, font_policy = profile_mgr.get_theme_policy_string()
        if not self.is_agreed:
            self.pushButton_3.setIcon(QIcon(f'ui/icon_{font_policy}/thumb_up.png'))
        else:
            self.pushButton_3.setIcon(QIcon(f'ui/thumb_up_filled.png'))

    def show_text_content_menu(self):
        menu = base_ui.create_thread_content_menu(self.label_6)
        menu.exec(QCursor.pos())

    def load_images(self):
        if not self.__is_loaded:
            if self.portrait_image.isImageInfoValid():
                self.portrait_image.loadImage()

            for i in self.image_list:
                i.load_picture_async()

            self.__is_loaded = True

    def agree_thread_ok_action(self, isok):
        self.set_agree_button_status()

        if isok == '[ALREADY_AGREE]':
            if QMessageBox.information(self, '已经点过赞了', '你已经点过赞了，是否要取消点赞？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.agree_thread_async(True)
        else:
            if self.show_msg_outside:
                toast = top_toast_widget.ToastMessage()
                toast.icon_type = top_toast_widget.ToastIconType.INFORMATION
                toast.title = isok
                self.messageAdded.emit(toast)
            else:
                QMessageBox.information(self, '点赞操作完成', isok)

    def agree_thread_from_click(self):
        self.agree_thread_async(self.is_agreed)

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
                response = agree_thread_or_post(self.bduss,
                                                self.stoken,
                                                self.thread_id,
                                                self.post_id,
                                                iscancel,
                                                OpAgreeObjectType.SubComment if self.is_comment else OpAgreeObjectType.FloorPost)
                if int(response['error_code']) == 0:
                    if iscancel:
                        self.is_agreed = False
                        self.agree_num -= 1
                        self.agree_thread_signal.emit('取消点赞成功')
                    else:
                        self.is_agreed = True
                        self.agree_num += 1
                        is_expa2 = bool(int(response["data"]["agree"]["is_first_agree"]))
                        self.agree_thread_signal.emit("点赞成功 首赞经验 +2" if is_expa2 else "点赞成功")
                elif int(response['error_code']) == 3280001:
                    self.is_agreed = True
                    self.agree_thread_signal.emit('[ALREADY_AGREE]')
                else:
                    self.agree_thread_signal.emit(response['error_msg'])

        except Exception as e:
            logging.log_exception(e)
            self.agree_thread_signal.emit(get_exception_string(e))

    def show_subcomment_window(self):
        if self.c_count != 0:
            if not find_first_reply_window(self.post_id, self.subcomment_show_thread_button):
                from subwindow.reply_sub_comments import ReplySubComments
                replyWindow = ReplySubComments(self.bduss,
                                               self.stoken,
                                               self.thread_id,
                                               self.post_id,
                                               self.floor,
                                               self.c_count,
                                               show_thread_button=self.subcomment_show_thread_button,
                                               is_subfloor=self.is_comment)
                qt_window_mgr.add_window(replyWindow)
        else:
            if self.show_msg_outside:
                toast = top_toast_widget.ToastMessage()
                toast.icon_type = top_toast_widget.ToastIconType.INFORMATION
                toast.title = f'第 {self.floor} 楼还没有任何回复'
                self.messageAdded.emit(toast)
            else:
                QMessageBox.information(self, '暂无回复', f'第 {self.floor} 楼还没有任何回复。', QMessageBox.Ok)

    def open_forum_detail_page(self):
        from subwindow.forum_detail import ForumDetailWindow
        forum_detail_page = ForumDetailWindow(self.bduss, self.stoken, self.forum_id, 2)
        qt_window_mgr.add_window(forum_detail_page)

    def open_user_blacklister(self):
        from subwindow.single_blacklist import SingleUserBlacklistWindow
        blacklister = SingleUserBlacklistWindow(self.bduss, self.stoken, self.portrait)
        qt_window_mgr.add_window(blacklister)

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

    def setdatas(self,
                 uicon: Union[QPixmap, str],
                 uname: str,
                 islz: bool,
                 text: str,
                 pixmaps: list,
                 floor: int,
                 timestr: str,
                 ip: str,
                 reply_count: int,
                 agree_count: int,
                 level: int,
                 isbawu: bool,
                 voice_info=None):
        if voice_info is None:
            voice_info = {'have_voice': False}

        if isinstance(uicon, QPixmap):
            self.label_4.setPixmap(qt_image.add_cover_for_pixmap(uicon))
        else:
            self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                             uicon,
                                             qt_image.ImageCoverType.RoundCover,
                                             (25, 25))
        self.label_3.setText(uname)

        text_ = ''
        is_high_agree = floor == 0
        if floor != -1:
            self.floor = floor
            text_ += ("置顶高赞回答" if is_high_agree else f'第 {floor} 楼') + ' | '
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
                self.pushButton.setText(' 查看楼中楼')
            else:
                self.pushButton.setText(f' {large_num_to_string(reply_count)}')

        if agree_count != -1:
            self.agree_num = agree_count
            self.set_agree_button_status()
        else:
            self.pushButton_3.hide()

        self.label_6.setVisible(bool(text))
        self.label_6.setText(f'<div style=\"white-space:normal;word-break: break-all;\">{text}</div>')
        self.label_8.setVisible(islz)
        self.label_11.setVisible(isbawu)

        if level == -1:
            self.label_9.hide()
        else:
            self.label_9.setText(f'Lv.{level}')
            qss = ''
            if 0 <= level <= 3:  # 绿牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 211, 171); border-radius: 7px;}'
            elif 4 <= level <= 9:  # 蓝牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 161, 255); border-radius: 7px;}'
            elif 10 <= level <= 15:  # 黄牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(255, 172, 29); border-radius: 7px;}'
            elif level >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48); border-radius: 7px;}'

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
                self.image_list.append(label)

                self.update_listwidget_size(i['height'] + 5)

            if voice_info['have_voice']:
                from subwindow.thread_voice_item import ThreadVoiceItem
                voice_widget = ThreadVoiceItem()
                voice_widget.setdatas(voice_info['src'], voice_info['length'])
                item = QListWidgetItem()
                item.setSizeHint(voice_widget.size())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, voice_widget)
                self.update_listwidget_size(voice_widget.height())

        if not self.load_by_callback:
            self.load_images()

        self.label_6.adjustSize()
        self.adjustSize()

    def init_more_menu(self):
        author_is_self = account_mgr.GlobalAccountContainer.get_current_account().portrait == self.portrait

        menu = base_ui.BaseQMenu()

        copy_link = QAction('复制链接', self)
        copy_link.triggered.connect(lambda: self.do_action_async("copy_post_link"))
        menu.addAction(copy_link)

        open_in_browser = QAction('浏览器打开', self)
        open_in_browser.triggered.connect(self.open_post_in_browser)
        menu.addAction(open_in_browser)

        menu.addSeparator()

        store_thread = QAction('收藏到此楼', self)
        store_thread.triggered.connect(lambda: self.do_action_async("store_thread"))
        menu.addAction(store_thread)

        block_author = QAction('拉黑用户', self)
        block_author.setVisible(not author_is_self)
        block_author.triggered.connect(self.open_user_blacklister)
        menu.addAction(block_author)

        delete_thread = QAction('删除此回复', self)
        delete_thread.setVisible(author_is_self)
        delete_thread.triggered.connect(lambda: self.do_action_async("del_post"))
        menu.addAction(delete_thread)

        bt_pos = self.toolButton.mapToGlobal(QPoint(0, 0))
        menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.toolButton.height()))

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'del_post':
            if QMessageBox.warning(self, '删除回复贴',
                                   '确认要删除这条回复贴吗？此操作不可撤销。',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def doaction():
            turn_data = {'success': False, 'text': '', 'delete_item': False}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'del_post':
                        r = await client.del_post(self.forum_id, self.thread_id, self.post_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['text'] = '回复删除成功'
                            turn_data['delete_item'] = True
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'store_thread':
                        result = store_thread(self.bduss, self.stoken, self.thread_id, self.post_id)
                        if result['error_code'] == '0':
                            turn_data['success'] = True
                            turn_data['text'] = '收藏成功'
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = result['error_msg']
                    elif action_type == 'copy_post_link':
                        link = f'https://tieba.baidu.com/p/{self.thread_id}?pid={self.post_id}'
                        pyperclip.copy(link)
                        turn_data['success'] = True
                        turn_data['text'] = '复制成功'
            except Exception as e:
                app_logger.log_exception(e)
                turn_data['success'] = False
                turn_data['text'] = str(e)
            finally:
                toast = top_toast_widget.ToastMessage()
                toast.icon_type = top_toast_widget.ToastIconType.SUCCESS if turn_data[
                    'success'] else top_toast_widget.ToastIconType.ERROR
                toast.title = turn_data['text']
                self.messageAdded.emit(toast)

                if turn_data['delete_item']:
                    self.postItemDeleted.emit()

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def open_post_in_browser(self):
        link = f'https://tieba.baidu.com/p/{self.thread_id}?pid={self.post_id}'
        open_url_in_browser(link)
