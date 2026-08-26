import asyncio

import aiotieba
from PyQt5.QtWidgets import QLabel, QAction, QMessageBox
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QEvent

from publics import qt_window_mgr, qt_image, profile_mgr, account_mgr, app_logger
from publics.base_ui_elements import top_toast_widget, base_ui
from publics.baidu_features import tieba_apis
from publics.funcs import timestamp_to_string, large_num_to_string, show_label_pixmap_with_animation, \
    start_background_thread, open_url_in_browser

from ui import tie_preview


class AsyncLoadImage(qt_image.MultipleImage):
    """
    将被异步加载的图片内容

    Args:
        src_link (str): 图片链接
        baidu_hash (str): 百度图床hash
    """

    def __init__(self, src_link: str, baidu_hash: str = ''):
        super().__init__()
        self.isLoaded = False

        self.src_link = src_link
        self.baidu_hash = baidu_hash

        img_type = qt_image.ImageLoadSource.BaiduHash if baidu_hash else qt_image.ImageLoadSource.HttpLink
        img_src = baidu_hash if baidu_hash else src_link
        self.setImageInfo(img_type,
                          img_src,
                          expectSize=(200, 200),
                          coverType=qt_image.ImageCoverType.RadiusAngleCoverCentrally)

    def set_pixmap_on_label(self, pixmap: QPixmap, label: QLabel):
        show_label_pixmap_with_animation(label, pixmap)

    def load_image_on_qtLabel(self, label: QLabel):
        if not self.isLoaded:
            self.currentPixmapChanged.connect(lambda pixmap: self.set_pixmap_on_label(pixmap, label),
                                              Qt.QueuedConnection)
            label.destroyed.connect(self.destroyImage)

            self.loadImage()
            self.isLoaded = True


class ThreadView(base_ui.InsideWidgetBaseQWidget, tie_preview.Ui_Form):
    """贴子在列表内的预览小组件"""
    is_treasure = False
    is_top = False
    load_by_callback = False
    is_loaded = False

    allow_open_home_page = True

    threadItemDeleted = pyqtSignal()
    messagePushed = pyqtSignal(top_toast_widget.ToastMessage)

    def __init__(self, bduss: str, tid: int, fid: int, stoken: str, author_portrait: str):
        super().__init__()
        self.setupUi(self)
        self.reset_theme()

        self.bduss = bduss
        self.stoken = stoken

        self.thread_id = tid
        self.forum_id = fid
        self.author_portrait = author_portrait
        self.first_post_id = 0

        self.piclist = None

        self.agree_num = 0
        self.reply_num = 0
        self.send_time = 0

        self.label_11.hide()
        self.pushButton_3.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.open_thread_detail)
        self.toolButton.clicked.connect(self.init_more_menu)

        self.portrait_image = qt_image.MultipleImage()
        self.forum_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label_4, pixmap))
        self.forum_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label, pixmap))
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.destroyed.connect(self.forum_image.destroyImage)

        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器

    def reset_theme(self):
        super().reset_theme()
        self.add_extend_qss(f'QPushButton{{color: {profile_mgr.get_theme_font_color_string()};}}')

        bg_policy, font_policy = profile_mgr.get_theme_policy_string()
        self.toolButton.setIcon(QIcon(f'ui/icon_{font_policy}/more_horiz.png'))

    def eventFilter(self, source, event):
        if (event.type() == QEvent.Type.MouseButtonRelease
                and source in (self.label_3, self.label_4)
                and self.allow_open_home_page):
            open_url_in_browser(f'user://{self.author_portrait}')

        return super(ThreadView, self).eventFilter(source, event)  # 照常处理事件

    def load_all_AsyncImage(self):
        if not self.is_loaded:
            self._load_pictures()
            if self.portrait_image.isImageInfoValid():
                self.portrait_image.loadImage()
            if self.forum_image.isImageInfoValid():
                self.forum_image.loadImage()
            self.is_loaded = True

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView, ThreadPreview

        preview_info = ThreadPreview()
        preview_info.title = self.label_5.text()
        preview_info.text = self.label_6.text()
        preview_info.user_name = self.label_3.text()
        preview_info.forum_name = self.label_2.text()
        preview_info.agree_num = self.agree_num
        preview_info.reply_num = self.reply_num
        preview_info.send_time = self.send_time
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), self.is_treasure,
                                         self.is_top, preview_info)
        qt_window_mgr.add_window(thread_window)

    def open_user_blacklister(self):
        from subwindow.single_blacklist import SingleUserBlacklistWindow
        blacklister = SingleUserBlacklistWindow(self.bduss, self.stoken, self.author_portrait)
        qt_window_mgr.add_window(blacklister)

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow

        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def init_more_menu(self):
        author_is_self = account_mgr.GlobalAccountContainer.get_current_account().portrait == self.author_portrait

        menu = base_ui.BaseQMenu()

        dislike_thread = QAction('不想看该贴子', self)
        dislike_thread.setVisible(not author_is_self)
        dislike_thread.triggered.connect(lambda: self.do_action_async("dislike_thread"))
        menu.addAction(dislike_thread)

        dislike_forum = QAction('屏蔽所在吧', self)
        dislike_forum.setVisible(bool(self.forum_id))
        dislike_forum.triggered.connect(lambda: self.do_action_async("block_forum"))
        menu.addAction(dislike_forum)

        block_author = QAction('拉黑楼主', self)
        block_author.setVisible(not author_is_self)
        block_author.triggered.connect(self.open_user_blacklister)
        menu.addAction(block_author)

        menu.addSeparator()

        private_thread = QAction('个人主页隐藏', self)
        private_thread.setVisible(author_is_self)
        private_thread.triggered.connect(lambda: self.do_action_async("private_thread"))
        menu.addAction(private_thread)

        public_thread = QAction('个人主页公开', self)
        public_thread.setVisible(author_is_self)
        public_thread.triggered.connect(lambda: self.do_action_async("public_thread"))
        menu.addAction(public_thread)

        delete_thread = QAction('删除此贴', self)
        delete_thread.setVisible(author_is_self)
        delete_thread.triggered.connect(lambda: self.do_action_async("del_thread"))
        menu.addAction(delete_thread)

        bt_pos = self.toolButton.mapToGlobal(QPoint(0, 0))
        menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.toolButton.height()))

    def set_thread_values(self, view=-1, agree=-1, reply=-1, repost=-1, send_time=0):
        self.agree_num = agree if agree != -1 else 0
        self.reply_num = reply if reply != -1 else 0
        self.send_time = send_time

        text = ''
        value_strings = [[f'{large_num_to_string(view, endspace=True)}次浏览', view],
                         [f'{large_num_to_string(agree, endspace=True)}人点赞', agree],
                         [f'{large_num_to_string(reply, endspace=True)}条回复', reply],
                         [f'{large_num_to_string(repost, endspace=True)}次转发', repost]]

        for vstr, value in value_strings:
            if value != -1:
                text += vstr + ' | '
        text = text[:-3]

        if send_time > 0:
            timestr = '发布于 ' + timestamp_to_string(send_time)
            text += '\n' + timestr

        self.label_11.show()
        self.label_11.setText(text)

    def set_infos(self, uicon, uname, title, text, baicon, baname):
        if isinstance(uicon, QPixmap):
            self.label_4.setPixmap(uicon)
        elif isinstance(uicon, str):
            self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait, uicon,
                                             qt_image.ImageCoverType.RoundCover,
                                             (20, 20))
            if not self.load_by_callback and not self.is_loaded:
                self.portrait_image.loadImage()

        self.label_3.setText(uname)
        self.label_5.setText(title)
        self.label_6.setText(text)
        self.label_2.setText((baname + '吧') if baname else "贴吧动态")

        if isinstance(baicon, QPixmap):
            self.label.setPixmap(baicon)
        elif isinstance(baicon, str):
            self.forum_image.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                          baicon,
                                          qt_image.ImageCoverType.RoundCover,
                                          (17, 17))
            if not self.load_by_callback and not self.is_loaded:
                self.forum_image.loadImage()
        else:
            self.label.hide()

        if not text:
            self.label_6.hide()
        if not title:
            self.label_5.hide()

    def _load_pictures(self):
        try:
            labels = [self.label_7, self.label_8, self.label_9]
            for i in range(len(self.piclist)):
                picture = self.piclist[i]
                qtlabel = labels[i]
                if isinstance(picture, QPixmap):
                    qtlabel.setPixmap(picture)
                elif isinstance(picture, AsyncLoadImage):
                    picture.load_image_on_qtLabel(qtlabel)
        except IndexError:
            return

    def set_picture(self, piclist):
        self.piclist = piclist
        labels = [self.label_7, self.label_8, self.label_9]

        self.label_7.clear()
        self.label_8.clear()
        self.label_9.clear()
        if len(piclist) == 0:
            self.gridLayout.removeWidget(self.frame_2)
        else:
            for i in range(1, len(labels) + 1):
                if i <= len(self.piclist):
                    labels[i - 1].setMinimumHeight(200)

            if not self.load_by_callback:
                self._load_pictures()

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'del_thread':
            if QMessageBox.warning(self, '删除贴子',
                                   '删除该主题贴会导致该贴子下的所有回复被一并删除，且该操作不可恢复。\n确认要删除该主题贴吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def init_post_id(client):
            if self.first_post_id:
                return

            thread_info = await client.get_posts(self.thread_id)
            self.first_post_id = thread_info.thread.pid

        async def doaction():
            turn_data = {'success': False, 'text': '', 'delete_item': False}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'del_thread':
                        r = await client.del_thread(self.forum_id, self.thread_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['text'] = '贴子删除成功'
                            turn_data['delete_item'] = True
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'block_forum':
                        r = await client.dislike_forum(self.forum_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['text'] = f'屏蔽该吧成功，可以在手机 APP 中查看'
                            turn_data['delete_item'] = True
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'dislike_thread':
                        result = tieba_apis.submit_dislike_thread(self.bduss, self.stoken,
                                                                  self.thread_id,
                                                                  self.forum_id)
                        if result['error_code'] == '0':
                            turn_data['success'] = True
                            turn_data['delete_item'] = True
                            turn_data['text'] = '反馈成功，系统将减少此类内容推荐'
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = result['error_msg']
                    elif action_type == 'private_thread':
                        await init_post_id(client)
                        r = await client.set_thread_private(self.forum_id, self.thread_id, self.first_post_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['text'] = f'隐藏贴子成功'
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'public_thread':
                        await init_post_id(client)
                        r = await client.set_thread_public(self.forum_id, self.thread_id, self.first_post_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['text'] = f'公开贴子成功'
                        else:
                            turn_data['success'] = False
                            turn_data['text'] = f'{r.err}'
            except Exception as e:
                app_logger.log_exception(e)
                turn_data['success'] = False
                turn_data['text'] = str(e)
            finally:
                toast = top_toast_widget.ToastMessage()
                toast.icon_type = top_toast_widget.ToastIconType.SUCCESS if turn_data[
                    'success'] else top_toast_widget.ToastIconType.ERROR
                toast.title = turn_data['text']
                self.messagePushed.emit(toast)

                if turn_data['delete_item']:
                    self.threadItemDeleted.emit()

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()
