import asyncio
import gc

import publics.logging as logging
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QWidget, QListWidgetItem

from publics import request_mgr, top_toast_widget
from publics.funcs import start_background_thread, listWidget_get_visible_widgets, get_exception_string
from ui import follow_ba


class FollowForumList(QWidget, follow_ba.Ui_Form):
    """关注吧列表组件"""
    add_ba = pyqtSignal(list)
    ba_add_ok = pyqtSignal(str)
    is_first_show = False

    def __init__(self, bduss, stoken, parent):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.parent_window = parent
        self.add_ba.connect(self.add_bar)
        self.ba_add_ok.connect(self.on_ba_add_ok)
        self.pushButton_2.clicked.connect(self.get_bars_async)
        self.pushButton.clicked.connect(self.show_onekey_sign)
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_images)

    def keyPressEvent(self, a0):
        a0.accept()
        if a0.key() == Qt.Key.Key_F5:
            self.get_bars_async()

    def on_ba_add_ok(self, msg):
        self.pushButton_2.setEnabled(True)
        if msg:
            self.parent_window.toast_widget.showToast(
                top_toast_widget.ToastMessage(msg, icon_type=top_toast_widget.ToastIconType.ERROR)
            )

    def scroll_load_images(self):
        items = listWidget_get_visible_widgets(self.listWidget)
        for i in items:
            i.load_avatar()

    def show_onekey_sign(self):
        if self.bduss and self.stoken:
            from subwindow.tb_sign_dialog import SignAllDialog
            d = SignAllDialog(self.bduss, self.stoken)
            d.exec()
        else:
            self.parent_window.toast_widget.showToast(
                top_toast_widget.ToastMessage('请先登录账号后再进行签到', icon_type=top_toast_widget.ToastIconType.INFORMATION)
            )

    def add_bar(self, data):
        from subwindow.forum_item import ForumItem
        item = QListWidgetItem()
        widget = ForumItem(data[3], data[4], self.bduss, self.stoken, data[1])
        widget.load_by_callback = True
        widget.set_info(data[0], data[1] + '吧', leveldesp=data[2])
        widget.set_level_color(data[5])
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

        self.scroll_load_images()

    def get_bars_async(self):
        self.listWidget.clear()
        QPixmapCache.clear()
        gc.collect()

        if self.bduss:
            self.label_2.hide()
            self.listWidget.show()
            self.pushButton_2.setEnabled(False)

            start_background_thread(self.get_bars)
        else:
            self.listWidget.hide()
            self.label_2.show()

    def get_bars(self):
        async def func():
            try:
                logging.log_INFO('loading userself follow forum list')

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
                    level_str = forum['level_name']
                    level_value = forum['level_id']
                    ba_info_str = f'Lv.{level_value} {level_str}'
                    self.add_ba.emit(
                        [forum['avatar'], name, ba_info_str, forum['forum_id'], forum['is_sign'] == 1, level_value])
            except Exception as e:
                logging.log_exception(e)
                self.ba_add_ok.emit(get_exception_string(e))
            else:
                self.ba_add_ok.emit('')
            finally:
                logging.log_INFO('load userself follow forum list complete')

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func())
