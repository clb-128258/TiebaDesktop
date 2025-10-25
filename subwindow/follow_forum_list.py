import asyncio
import gc

import aiotieba
import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmapCache, QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QListWidgetItem

from publics import request_mgr
from publics.funcs import start_background_thread
from ui import follow_ba


class FollowForumList(QWidget, follow_ba.Ui_Form):
    """关注吧列表组件"""
    add_ba = pyqtSignal(list)
    ba_add_ok = pyqtSignal()

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.add_ba.connect(self.add_bar)
        self.ba_add_ok.connect(lambda: self.pushButton_2.setEnabled(True))
        self.pushButton_2.clicked.connect(self.get_bars_async)
        self.pushButton.clicked.connect(self.show_onekey_sign)
        self.listWidget.verticalScrollBar().setSingleStep(25)

    def keyPressEvent(self, a0):
        a0.accept()
        if a0.key() == Qt.Key.Key_F5:
            self.get_bars_async()

    def show_onekey_sign(self):
        if self.bduss and self.stoken:
            from subwindow.tb_sign_dialog import SignAllDialog
            d = SignAllDialog(self.bduss, self.stoken)
            d.exec()
        else:
            QMessageBox.information(self, '提示', '请先登录账号后再进行签到。', QMessageBox.Ok)

    def add_bar(self, data):
        from subwindow.forum_item import ForumItem
        item = QListWidgetItem()
        widget = ForumItem(data[3], data[4], self.bduss, self.stoken, data[1])
        widget.set_info(data[0], data[1] + '吧', data[2])
        widget.set_level_color(data[5])
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

    def get_bars_async(self):
        if self.bduss:
            self.label_2.hide()
            self.listWidget.show()
            self.pushButton_2.setEnabled(False)

            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()

            start_background_thread(self.get_bars)
        else:
            self.listWidget.hide()
            self.label_2.show()

    def get_bars(self):
        async def func():
            try:
                aiotieba.logging.get_logger().info('loading userself follow forum list')

                payload = {
                    'BDUSS': self.bduss,
                    'stoken': self.stoken,
                    'sort_type': "3",
                    'call_from': "1",
                }
                bars = request_mgr.run_post_api('/c/f/forum/forumGuide', payloads=payload, bduss=self.bduss,
                                                stoken=self.stoken, use_mobile_header=True)['like_forum']
                for forum in bars:
                    name = forum['forum_name']
                    pixmap = QPixmap()
                    response = requests.get(forum['avatar'], headers=request_mgr.header)
                    if response.content:
                        pixmap.loadFromData(response.content)
                        pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                    level_str = forum['level_name']
                    level_value = forum['level_id']
                    ba_info_str = f'[Lv.{level_value}] {level_str}'
                    self.add_ba.emit([pixmap, name, ba_info_str, forum['forum_id'], forum['is_sign'] == 1, level_value])
            finally:
                self.ba_add_ok.emit()
                aiotieba.logging.get_logger().info('load userself follow forum list complete')

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func())
