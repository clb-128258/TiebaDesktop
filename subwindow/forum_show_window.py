import asyncio
import gc

import aiotieba
import requests
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmapCache, QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QListWidgetItem

from publics import profile_mgr, qt_window_mgr, cache_mgr, request_mgr, qt_image
from publics.funcs import open_url_in_browser, LoadingFlashWidget, start_background_thread, timestamp_to_string, \
    make_thread_content, cut_string, large_num_to_string, listWidget_get_visible_widgets
import publics.logging as logging

from ui import ba_head


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
        for i in range(len(self.listwidgets)):
            lw = self.listwidgets[i]

            lw.setStyleSheet('QListWidget{outline:0px;}'
                             'QListWidget::item:hover {color:white; background-color:white;}'
                             'QListWidget::item:selected {color:white; background-color:white;}')
            lw.verticalScrollBar().setSingleStep(20)
            lw.verticalScrollBar().valueChanged.connect(self.scroll_load_more)
            lw.verticalScrollBar().valueChanged.connect(self.threadList_load_image)

        self.forum_avatar = qt_image.MultipleImage()
        self.forum_avatar.currentPixmapChanged.connect(self.label.setPixmap)
        self.forum_avatar.currentPixmapChanged.connect(lambda pixmap: self.setWindowIcon(QIcon(pixmap)))
        self.forum_admin_portrait = qt_image.MultipleImage()
        self.forum_admin_portrait.currentPixmapChanged.connect(self.label_6.setPixmap)

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
        self.tabWidget.currentChanged.connect(self.threadList_load_image)
        self.pushButton_4.clicked.connect(
            lambda: open_url_in_browser(f'https://tieba.baidu.com/f?kw={self.forum_name}'))

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_F5:
            self.refresh_all()

    def closeEvent(self, a0):
        self.flash_shower.hide()
        self.forum_avatar.destroyImage()
        self.forum_admin_portrait.destroyImage()
        for i in self.listwidgets:
            i.clear()

        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)

    def threadList_load_image(self):
        for lw in self.listwidgets:
            if lw.parent() == self.tabWidget.currentWidget():
                widgets = listWidget_get_visible_widgets(lw)
                for i in widgets:
                    i.load_all_AsyncImage()

    def open_search_window(self):
        from subwindow.tieba_search_entry import TiebaSearchWindow
        search_window = TiebaSearchWindow(self.bduss, self.stoken, self.forum_name)
        qt_window_mgr.add_window(search_window)

    def open_detail_window(self):
        from subwindow.forum_detail import ForumDetailWindow
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
                logging.log_exception(e)

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
        from subwindow.thread_preview_item import ThreadView, AsyncLoadImage
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
        widget.load_by_callback = True

        widget.set_infos(infos['user_portrait'], infos['user_name'], infos['title'], infos['content'],
                         infos['forum_pixmap'], infos['forum_name'])
        widget.set_picture(list(AsyncLoadImage(image.src, image.hash) for image in infos['view_pixmap']))
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
        self.threadList_load_image()

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
        try:
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
                preview_pixmap = thread.contents.imgs
                view_count = thread.view_num
                agree_count = thread.agree
                reply_count = thread.reply_num
                repost_count = thread.share_num
                is_treasure = thread.is_good
                is_top = thread.is_top

                tdata = {'type': tpe,
                         'thread_id': thread_id,
                         'forum_id': forum_id,
                         'title': title,
                         'content': content,
                         'user_name': user_name,
                         'user_portrait': portrait,
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
        except Exception as e:
            logging.log_exception(e)

        async def get_latest_reply_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['latest_reply'])
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('latest_reply', i)
            except Exception as e:
                logging.log_exception(e)

        async def get_latest_send_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['latest_send'],
                                                       sort=aiotieba.ThreadSortType.CREATE)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('latest_send', i)
            except Exception as e:
                logging.log_exception(e)

        async def get_hot_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['hot'],
                                                       sort=aiotieba.ThreadSortType.HOT)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('hot', i)
            except Exception as e:
                logging.log_exception(e)

        async def get_top_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['top'],
                                                       sort=aiotieba.ThreadSortType.REPLY)
                    for i in threads.objs:
                        if i.is_top:
                            emit_data('top', i)
            except Exception as e:
                logging.log_exception(e)

        async def get_treasure_detail():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    threads = await client.get_threads(self.forum_id, pn=self.page['treasure'],
                                                       sort=aiotieba.ThreadSortType.REPLY, is_good=True)
                    for i in threads.objs:
                        if not i.is_top:
                            emit_data('treasure', i)
            except Exception as e:
                logging.log_exception(e)

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
        if datas['error']:
            QMessageBox.critical(self, '进吧失败', datas['error'], QMessageBox.Ok)
            self.close()
        else:
            self.setWindowTitle(datas['name'] + '吧')
            self.label_3.setText('{0}人关注，{1}条贴子'.format(large_num_to_string(datas['follownum'], endspace=True),
                                                              large_num_to_string(datas['postnum'], endspace=True)))
            self.label_2.setText(datas['name'] + '吧')
            self.forum_avatar.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                           datas['avatar'],
                                           qt_image.ImageCoverType.RoundCover,
                                           (50, 50))
            self.forum_avatar.loadImage()

            if datas['is_followed'] == 1:
                qss = ('QLabel{color: rgb(255,255,255);background-color: [color];border-width: 1px 4px;border-style: '
                       'solid;border-color: [color]; border-radius: 5px;}')
                if 1 <= datas['uf_level'] <= 3:  # 绿牌
                    qss = qss.replace('[color]', 'rgb(101, 211, 171)')
                elif 4 <= datas['uf_level'] <= 9:  # 蓝牌
                    qss = qss.replace('[color]', 'rgb(101, 161, 255)')
                elif 10 <= datas['uf_level'] <= 15:  # 黄牌
                    qss = qss.replace('[color]', 'rgb(255, 172, 29)')
                elif datas['uf_level'] >= 16:  # 橙牌老东西
                    qss = qss.replace('[color]', 'rgb(247, 126, 48)')

                self.label_9.setStyleSheet(qss)  # 为不同等级设置qss
                self.label_9.setText(datas['level_info'])
                self.label_9.show()

            if datas['admin_name']:
                self.label_7.setText(datas['admin_name'])
                self.forum_admin_portrait.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                                       datas['admin_portrait'],
                                                       qt_image.ImageCoverType.RoundCover,
                                                       (20, 20))
                self.forum_admin_portrait.loadImage()
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
                try:
                    # 获取吧信息
                    logging.log_INFO(f'forum (id {self.forum_id}) loading head_info')
                    forum_name = await client.get_fname(self.forum_id)
                    if not forum_name:
                        raise NameError(f'forum name is empty (id {self.forum_id})')
                    else:
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'kw': forum_name,
                            'stoken': self.stoken
                        }

                        resp = request_mgr.run_post_api('/c/f/frs/frsBottom', request_mgr.calc_sign(payload),
                                                        bduss=self.bduss,
                                                        stoken=self.stoken, host_type=2, use_mobile_header=True)
                        if resp['error_code'] != 0:
                            raise Exception(f'{resp["error_msg"]} (错误代码 {resp["error_code"]})')

                        level_info = ''
                        level_value = 1
                        if self.bduss:
                            isFollowed = 1 if resp["forum"]["is_like"] else 0
                            if resp["forum"]["is_like"]:
                                level_info = f'Lv.{resp["forum"]["user_level"]} {resp["forum"]["level_name"]}'
                                level_value = resp["forum"]["user_level"]
                        else:
                            isFollowed = 2
                        self.forum_name = forum_name = resp["forum"]["name"]
                        forum_slogan = resp["forum"]["slogan"]
                        follow_count = resp["forum"]["member_num"]
                        post_count = resp["forum"]["post_num"]
                        if admin_info := resp["forum"].get("managers"):
                            forum_admin_name = admin_info[0]["show_name"]
                            forum_admin_portrait = admin_info[0]["portrait"].split('?')[0]
                        else:
                            forum_admin_name = ''
                            forum_admin_portrait = ''

                        forum_avatar = resp['forum']["avatar"]

                        md5v = cache_mgr.save_md5_ico(resp['forum']["avatar"])
                        profile_mgr.add_view_history(3, {"icon_md5": md5v, "forum_id": self.forum_id,
                                                         "forum_name": self.forum_name})

                        logging.log_INFO(
                            f'forum (id {self.forum_id}, name {forum_name}) head_info all load ok, sending to qt thread')
                except Exception as e:
                    logging.log_exception(e)
                    tdata = {'error': str(e)}
                else:
                    tdata = {"error": '',
                             'name': forum_name,
                             'avatar': forum_avatar,
                             'slogan': forum_slogan,
                             'follownum': follow_count,
                             'postnum': post_count,
                             'admin_name': forum_admin_name,
                             'admin_portrait': forum_admin_portrait,
                             'is_followed': isFollowed,
                             'level_info': level_info,
                             'uf_level': level_value}
                finally:
                    self.update_signal.emit(tdata)

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(get_detail())
