import gc

import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache, QPixmap
from PyQt5.QtWidgets import QDialog, QListWidget, QMessageBox, QListWidgetItem

from publics import qt_window_mgr, request_mgr, cache_mgr, qt_image
from publics.funcs import UserItem, start_background_thread, cut_string, timestamp_to_string, \
    listWidget_get_visible_widgets
from ui import forum_search


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
        self.listWidget_2.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_images(self.listWidget_2))
        self.listWidget_4.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_images(self.listWidget_4))
        self.listWidget_5.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_images(self.listWidget_5))

        if forum_name:
            self.lineEdit_2.setText(forum_name)
            self.comboBox.setCurrentIndex(1)
        self.handle_search_type_switch(self.comboBox.currentIndex())

        self.add_result.connect(self._ui_add_search_result)
        self.comboBox.currentIndexChanged.connect(self.handle_search_type_switch)
        self.pushButton.clicked.connect(self.start_search)

    def closeEvent(self, a0):
        for i in self.listwidgets:
            i.clear()
        QPixmapCache.clear()
        gc.collect()

        a0.accept()
        qt_window_mgr.del_window(self)

    def scroll_load_images(self, lw: QListWidget):
        from subwindow.thread_preview_item import ThreadView
        from subwindow.thread_reply_item import ReplyItem
        widgets = listWidget_get_visible_widgets(lw)  # 获取可见的widget列表
        for i in widgets:
            if isinstance(i, ThreadView):
                i.load_all_AsyncImage()  # 异步加载里面的图片
            elif isinstance(i, ReplyItem):
                i.load_images()  # 异步加载里面的图片

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
            from subwindow.thread_preview_item import ThreadView, AsyncLoadImage
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)
            widget.load_by_callback = True

            widget.set_infos(datas['portrait'], datas['user_name'], datas['title'], datas['text'],
                             datas['forum_head_avatar'],
                             datas['forum_name'])
            widget.set_picture(list(AsyncLoadImage(i) for i in datas['picture']))
            widget.adjustSize()

            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
            self.scroll_load_images(self.listWidget_2)
        elif datas['type'] == 'forum':
            from subwindow.forum_item import ForumItem
            item = QListWidgetItem()
            widget = ForumItem(datas['forum_id'], True, self.bduss, self.stoken, datas['forum_name'])
            widget.set_info(datas['avatar'], datas['forum_name'] + '吧', datas['desp'])
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
            from subwindow.thread_preview_item import ThreadView, AsyncLoadImage
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)
            widget.load_by_callback = True

            widget.set_infos(datas['portrait'], datas['user_name'], datas['title'], datas['text'],
                             datas['forum_head_avatar'],
                             datas['forum_name'])
            widget.set_picture(list(AsyncLoadImage(i) for i in datas['picture']))
            widget.adjustSize()

            item.setSizeHint(widget.size())
            self.listWidget_4.addItem(item)
            self.listWidget_4.setItemWidget(item, widget)
            self.scroll_load_images(self.listWidget_4)
        elif datas['type'] == 'reply_single_forum':
            from subwindow.thread_reply_item import ReplyItem
            item = QListWidgetItem()
            widget = ReplyItem(self.bduss, self.stoken)

            widget.load_by_callback = True
            widget.portrait = datas['portrait']
            widget.thread_id = datas['thread_id']
            widget.post_id = datas['post_id']
            widget.allow_home_page = True
            widget.subcomment_show_thread_button = True
            widget.set_reply_text(
                '<a href=\"tieba_thread://{tid}\">{title}</a>'.format(tid=datas['thread_id'], title=datas['title']))
            widget.setdatas(datas['portrait'], datas['user_name'], False, datas['text'],
                            datas['picture'], -1, datas['time_str'], '', -2, -1, -1, False)

            item.setSizeHint(widget.size())
            self.listWidget_5.addItem(item)
            self.listWidget_5.setItemWidget(item, widget)
            self.scroll_load_images(self.listWidget_5)

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
                                'forum_head_avatar': '',
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
                        data['forum_head_avatar'] = thread["forum_info"]["avatar"]

                        # 获取主图片
                        if thread.get("media"):
                            for m in thread['media']:
                                if m["type"] == "pic":  # 是图片
                                    url = m["small_pic"]
                                    data['picture'].append(url)

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

                        # 转换时间为字符串
                        timestr = timestamp_to_string(data['timestamp'])
                        data['time_str'] = timestr

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
                                'forum_head_avatar': '',
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
                        data['forum_head_avatar'] = thread["forum_info"]["avatar"]

                        # 获取主图片
                        if thread.get("media"):
                            for m in thread['media']:
                                if m["type"] == "pic":  # 是图片
                                    url = m["small_pic"]
                                    data['picture'].append(url)

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
                                'avatar': response['data']['exactMatch']['avatar'],
                                'forum_id': response['data']['exactMatch']['forum_id'],
                                'forum_name': response['data']['exactMatch']['forum_name'],
                                'desp': '[准确结果] ' + response['data']['exactMatch']['slogan'],
                                'member_num': response['data']['exactMatch']['concern_num_ori'],
                                'post_num': response['data']['exactMatch']['post_num_ori']}

                        self.add_result.emit(data)
                    for forum in response['data']['fuzzyMatch']:  # 相似结果
                        data = {'type': search_area,
                                'avatar': forum['avatar'],
                                'forum_id': forum['forum_id'],
                                'forum_name': forum['forum_name'],
                                'desp': '与你搜索的内容相关',
                                'member_num': forum['concern_num_ori'],
                                'post_num': forum['post_num_ori']}

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
