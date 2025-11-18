import asyncio
import gc

import aiotieba
import pyperclip
import requests
from PyQt5.QtCore import pyqtSignal, Qt, QEvent, QPoint
from PyQt5.QtGui import QIcon, QPixmapCache, QPixmap
from PyQt5.QtWidgets import QWidget, QMenu, QAction, QMessageBox, QListWidgetItem

from publics import profile_mgr, qt_window_mgr, request_mgr, cache_mgr, top_toast_widget
from publics.funcs import LoadingFlashWidget, open_url_in_browser, start_background_thread, make_thread_content, \
    timestamp_to_string, cut_string, large_num_to_string
import publics.logging as logging
from ui import tie_detail_view


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
        self.init_top_toaster()

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
        self.label_9.installEventFilter(self)  # 重写事件过滤器

        self.flash_shower.show()
        self.get_thread_head_info_async()
        self.get_sub_thread_async()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if source in (self.label_3, self.label_4):
                self.open_user_homepage(self.user_id)
            elif source == self.label_9:
                self.open_forum_detail_page()

        return super(ThreadDetailView, self).eventFilter(source, event)  # 照常处理事件

    def closeEvent(self, a0):
        from subwindow.thread_video_item import ThreadVideoItem
        self.flash_shower.hide()
        a0.accept()
        if self.listWidget.count() == 1:
            widget = self.listWidget.itemWidget(self.listWidget.item(0))
            if isinstance(widget, ThreadVideoItem):
                if widget.webview:
                    widget.destroy_webview()
        for i in range(self.listWidget_4.count()):
            item = self.listWidget_4.item(i)
            widget = self.listWidget_4.itemWidget(item)
            widget.deleteLater()
            del item

        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

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
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def open_forum_detail_page(self):
        from subwindow.forum_detail import ForumDetailWindow
        forum_detail_page = ForumDetailWindow(self.bduss, self.stoken, self.forum_id, 2)
        qt_window_mgr.add_window(forum_detail_page)

    def handle_link_event(self, url):
        open_url_in_browser(url)

    def add_post_ok_action(self, isok):
        toast = top_toast_widget.ToastMessage()

        if not isok:
            self.lineEdit.setText('')
            self.comboBox.setCurrentIndex(1)
            toast.title = '回贴成功'
            toast.icon_type = top_toast_widget.ToastIconType.SUCCESS
        else:
            toast.title = isok
            toast.icon_type = top_toast_widget.ToastIconType.ERROR
        self.top_toaster.showToast(toast)

    def add_post_async(self):
        if not self.lineEdit.text():
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='请输入内容后再回贴',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        elif not self.bduss:
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='目前处于游客状态，请登录后再回贴',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
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
                logging.log_INFO(f'post thread {self.thread_id}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    result = await client.add_post(self.forum_id, self.thread_id, self.lineEdit.text())
                    if result:
                        self.add_post_signal.emit('')
                    else:
                        self.add_post_signal.emit(str(result.err))
            except Exception as e:
                logging.log_exception(e)
                self.add_post_signal.emit('程序内部出错，请重试')

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dopost())

        start_async()

    def agree_thread_ok_action(self, isok):
        self.pushButton_4.setText(large_num_to_string(self.agree_num, endspace=True) + '个赞')
        if isok == '[ALREADY_AGREE]':
            if QMessageBox.information(self, '已经点过赞了', '你已经点过赞了，是否要取消点赞？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.agree_thread_async(True)
        else:
            toast = top_toast_widget.ToastMessage(isok, 2000, top_toast_widget.ToastIconType.INFORMATION)
            self.top_toaster.showToast(toast)

    def agree_thread_async(self, is_cancel=False):
        start_background_thread(self.agree_thread, (is_cancel,))

    def agree_thread(self, iscancel=False):
        logging.log_INFO(f'agree thread {self.thread_id}')
        try:
            if not self.bduss:
                self.agree_thread_signal.emit('登录后即可为贴子点赞')
            elif self.user_id == 0:
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
                        self.agree_thread_signal.emit("点赞成功 首赞经验 +2" if is_expa2 else "点赞成功")
                    elif int(response['error_code']) == 3280001:
                        self.agree_thread_signal.emit('[ALREADY_AGREE]')
                    else:
                        self.agree_thread_signal.emit(response['error_msg'])

        except Exception as e:
            print(type(e))
            print(e)
            self.agree_thread_signal.emit('程序内部出错，请重试')

    def store_thread_ok_action(self, isok):
        toast = top_toast_widget.ToastMessage(isok, 2000, top_toast_widget.ToastIconType.INFORMATION)
        self.top_toaster.showToast(toast)

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
            logging.log_INFO(f'store thread {self.thread_id}')
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
                        self.store_thread_signal.emit(f'贴子已收藏到第 {floor} 楼')
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
                        self.store_thread_signal.emit('取消收藏成功')
                    else:
                        self.store_thread_signal.emit(result['error'])
            except Exception as e:
                logging.log_exception(e)
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
        from subwindow.forum_show_window import ForumShowWindow
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
        from subwindow.thread_reply_item import ReplyItem
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
        widget.show_msg_outside = True
        widget.messageAdded.connect(lambda text: self.top_toaster.showToast(
            top_toast_widget.ToastMessage(text, 2000, top_toast_widget.ToastIconType.INFORMATION)))
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
            logging.log_INFO(f'loading thread {self.thread_id} replies list page {self.reply_page}')
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
                        logging.log_INFO(
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
                                view_src = j.big_src
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

                        logging.log_INFO(
                            f'load thread {self.thread_id} replies list page {self.reply_page} ok')

                        if sort_type == aiotieba.PostSortType.DESC:  # 在倒序查看时要递减页数
                            self.reply_page -= 1
                        else:
                            self.reply_page += 1
                        if not thread_info.page.has_more:
                            self.reply_page = -1
                            self.show_reply_end_text.emit(0)

            except Exception as e:
                logging.log_exception(e)
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
                self.pushButton_2.setToolTip(datas['forum_slogan'] if datas['forum_slogan'] else "点击进入此吧")
            else:
                self.setWindowTitle(datas['title'] + ' - 贴吧动态')
                self.pushButton_2.hide()
            self.pushButton_4.setText(large_num_to_string(datas['agree_count'], endspace=True) + '个赞')
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
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(255, 172, 29);}'
            elif datas['uf_level'] >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48);}'

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss

            if not datas['view_pixmap'] and not datas['video_info']['have_video'] and not datas['voice_info'][
                'have_voice'] and not datas['repost_info']['have_repost']:
                self.listWidget.hide()
            else:
                if datas['video_info']['have_video']:
                    from subwindow.thread_video_item import ThreadVideoItem
                    video_widget = ThreadVideoItem()
                    video_widget.setdatas(datas['video_info']['src'], datas['video_info']['length'],
                                          datas['video_info']['view'])
                    item = QListWidgetItem()
                    item.setSizeHint(video_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, video_widget)
                    self.update_listwidget_size(video_widget.height() + 5)

                if datas['voice_info']['have_voice']:
                    from subwindow.thread_voice_item import ThreadVoiceItem
                    voice_widget = ThreadVoiceItem()
                    voice_widget.setdatas(datas['voice_info']['src'], datas['voice_info']['length'])
                    item = QListWidgetItem()
                    item.setSizeHint(voice_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, voice_widget)
                    self.update_listwidget_size(voice_widget.height())

                for i in datas['view_pixmap']:
                    from subwindow.thread_picture_label import ThreadPictureLabel
                    label = ThreadPictureLabel(i['width'], i['height'], i['src'], i['view_src'])

                    item = QListWidgetItem()
                    item.setSizeHint(label.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, label)

                    self.update_listwidget_size(i['height'] + 35)

                if datas['repost_info']['have_repost']:
                    from subwindow.thread_preview_item import ThreadView

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
                    logging.log_INFO(f'loading thread {self.thread_id} main info')
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
                            forum_slogan = forum_info.slogan
                        else:
                            forum_name = ''
                            forum_pic_url = ''
                            forum_slogan = ''

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

                        profile_mgr.add_view_history(1,
                                                     {"thread_id": self.thread_id,
                                                      "title": f'{title} - {forum_name}吧'})

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
                                 'repost_info': repost_info,  # 转发贴信息
                                 'forum_slogan': forum_slogan  # 吧标语
                                 }

                        logging.log_INFO(
                            f'load thread {self.thread_id} main info ok, send to qt side')
                        self.head_data_signal.emit(tdata)
            except Exception as e:
                logging.log_exception(e)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()
