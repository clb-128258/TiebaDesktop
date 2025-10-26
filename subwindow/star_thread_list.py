import asyncio
import gc

import aiotieba
import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache, QPixmap
from PyQt5.QtWidgets import QDialog, QListWidgetItem

from publics import qt_window_mgr, request_mgr, cache_mgr
from publics.funcs import start_background_thread
import publics.logging as logging
from ui import star_list


class StaredThreadsList(QDialog, star_list.Ui_Dialog):
    """收藏的贴子列表，可查看已收藏的贴子"""
    add_thread = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.page = 1
        self.isloading = False

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))

        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_list_info)
        self.listWidget.verticalScrollBar().setSingleStep(25)

        self.add_thread.connect(self.add_star_threads_ui)
        self.pushButton.clicked.connect(self.refresh_star_threads)

        self.get_star_threads_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def scroll_load_list_info(self):
        if self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value():
            self.get_star_threads_async()

    def add_star_threads_ui(self, infos):
        item = QListWidgetItem()
        from subwindow.thread_preview_item import ThreadView
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)

        widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], '', None,
                         infos['forum_name'])
        if infos['picture']:
            widget.set_picture([infos['picture']])
        else:
            widget.set_picture([])
        if infos['is_del']:
            widget.label_11.show()
            widget.label_11.setStyleSheet('QLabel{color: red;}')
            widget.label_11.setText('该贴已被作者删除')

        widget.label.hide()
        widget.adjustSize()
        item.setSizeHint(widget.size())

        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def refresh_star_threads(self):
        if not self.isloading:
            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()
            self.page = 1

        self.get_star_threads_async()

    def get_star_threads_async(self):
        if not self.isloading and self.page != -1:
            start_background_thread(self.get_star_threads)

    def get_star_threads(self):
        async def run_func():
            try:
                self.isloading = True
                logging.log_INFO(
                    f'loading userThreadStoreList page {self.page}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    resp = request_mgr.run_get_api(f'/mg/o/threadstore?pn={self.page}&rn=10&eqid=&refer=',
                                                   bduss=self.bduss, stoken=self.stoken)
                    for thread in resp['data']['store_thread']:
                        data = {'user_name': thread['author']['show_nickname'], 'user_portrait_pixmap': None,
                                'thread_id': thread['tid'], 'forum_id': await client.get_fid(thread['forum_name']),
                                'forum_name': thread['forum_name'], 'title': thread["title"], 'picture': None,
                                'is_del': bool(thread['is_deleted'])}

                        portrait = thread["author"]["portrait"].split('?')[0]
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                        user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        data['user_portrait_pixmap'] = user_head_pixmap

                        if thread.get("media"):
                            pixmap = QPixmap()
                            url = thread['media'][0]["cover_img"]
                            response = requests.get(url, headers=request_mgr.header)
                            if response.content:
                                pixmap.loadFromData(response.content)
                                data['picture'] = pixmap

                        self.add_thread.emit(data)
            except Exception as e:
                logging.log_exception(e)
            else:
                logging.log_INFO(
                    f'load userThreadStoreList page {self.page} successful')
                if not resp['data']['has_more']:
                    self.page = -1
                else:
                    self.page += 1
            finally:
                self.isloading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()


def import_circularly():
    from subwindow.thread_preview_item import ThreadView
