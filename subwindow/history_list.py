from datetime import datetime

from PyQt5.QtCore import Qt

from ui import view_history, view_history_item, view_history_single_item
from publics import profile_mgr, cache_mgr, qt_window_mgr, funcs

from PyQt5.QtWidgets import QWidget, QListWidgetItem, QMessageBox, QGraphicsDropShadowEffect
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtCore import pyqtSignal, QSize


def get_day_str(ts: int):
    weekIndex = {0: '一',
                 1: '二',
                 2: '三',
                 3: '四',
                 4: '五',
                 5: '六',
                 6: '日'}
    dt = datetime.fromtimestamp(ts)

    return f"{dt.year}年{dt.month}月{dt.day}日 星期{weekIndex[dt.weekday()]}"


class SingleHistoryItem(QWidget, view_history_single_item.Ui_Form):
    history_info = {}
    setIconAsync = pyqtSignal(QPixmap)

    def __init__(self, parent_listwidget: QWidget, info: dict = None):
        super().__init__()
        self.setupUi(self)

        self.parent_listwidget = parent_listwidget

        self.toolButton_3.hide()

        self.setIconAsync.connect(self.label.setPixmap)

        if info:
            self.set_info(info)

    def mouseDoubleClickEvent(self, a0):
        if self.history_info['type'] == 1:
            url = 'tieba_thread://' + str(self.history_info["thread_info"]["thread_id"])
        elif self.history_info['type'] == 2:
            url = 'user://' + str(self.history_info["user_info"]["uid"])
        elif self.history_info['type'] == 3:
            url = 'tieba_forum://' + str(self.history_info["forum_info"]["forum_id"])
        elif self.history_info['type'] == 4:
            url = str(self.history_info["web_info"]["web_url"])
        else:
            url = ''

        if url:
            funcs.open_url_in_browser(url)

    def sizeHint(self):
        height = self.height()
        # 获取父QListWidget的宽度
        width = self.parent_listwidget.width()

        return QSize(width, height)

    def load_icon(self):
        pixmap = QPixmap()
        if self.history_info['type'] == 2:
            pixmap.loadFromData(cache_mgr.get_portrait(self.history_info["user_info"]["portrait"]))
        elif self.history_info['type'] == 3:
            pixmap.loadFromData(cache_mgr.get_md5_icon(self.history_info["forum_info"]["icon_md5"]))
        elif self.history_info['type'] == 4:
            pixmap.loadFromData(cache_mgr.get_md5_icon(self.history_info["web_info"]["web_icon_md5"]))

        if pixmap.isNull():
            pixmap.load('ui/tieba_logo_small.png')
        pixmap = pixmap.scaled(20, 20, transformMode=Qt.SmoothTransformation)

        self.setIconAsync.emit(pixmap)

    def load_icon_async(self):
        funcs.start_background_thread(self.load_icon)

    def set_info(self, info: dict):
        self.history_info = info

        title = ''
        if info['type'] == 1:
            title = info["thread_info"]["title"]
        elif info['type'] == 2:
            title = info["user_info"]["nickname"]
        elif info['type'] == 3:
            title = info["forum_info"]["forum_name"] + '吧'
        elif info['type'] == 4:
            title = info["web_info"]["web_title"]

        self.label_2.setText(funcs.cut_string(title, 30))
        self.label_3.setText(funcs.timestamp_to_string(info['time']))
        self.load_icon_async()

        self.adjustSize()


class DayHistoryItem(QWidget, view_history_item.Ui_Form):
    def __init__(self, date_str: str, parent_listwidget: QWidget):
        super().__init__()
        self.setupUi(self)

        self.list_height = 0
        self.parent_listwidget = parent_listwidget
        self.init_shadow_effect()
        self.label.setText(date_str)

    def init_shadow_effect(self):
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(10)  # 阴影模糊半径
        shadow_effect.setColor(QColor(0, 0, 0, 50))  # 阴影颜色和透明度
        shadow_effect.setOffset(2, 2)  # 阴影偏移量

        # 将阴影效果应用到 QFrame
        self.frame.setGraphicsEffect(shadow_effect)

    def sizeHint(self):
        """
        重写 sizeHint，确保返回一个能容纳所有内容的尺寸。
        这个方法会被 QListWidget 调用以确定 item 的大小。
        也可使用此方法获取本组件的最佳大小。
        """
        # 使用 self.list_height + 一些边距
        height = self.list_height + self.frame_2.height() + self.line.height() + 90

        # 获取父QListWidget的宽度
        width = self.parent_listwidget.width()

        return QSize(width, height)

    def add_single_item(self, widget: SingleHistoryItem):
        item = QListWidgetItem()
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

        self.list_height += widget.height()
        self.listWidget.setFixedHeight(self.list_height)
        self.setFixedHeight(self.sizeHint().height())


class HistoryViewWindow(QWidget, view_history.Ui_Form):
    """浏览记录窗口"""
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.widget_list = {}
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label.hide()
        self.listWidget_2.setStyleSheet('QListWidget#listWidget_2{outline:0px;}'
                                        'QListWidget#listWidget_2::item:hover {color:white; background-color:white;}'
                                        'QListWidget#listWidget_2::item:selected {color:white; background-color:white;}')
        self.listWidget_2.verticalScrollBar().setSingleStep(20)

        self.listWidget.currentRowChanged.connect(self.load_history)
        self.pushButton.clicked.connect(self.clear_history)
        self.pushButton_2.clicked.connect(lambda: self.load_history())

        self.listWidget.setCurrentRow(0)

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def clear_history(self):
        if QMessageBox.warning(self, '警告', '确认要清空浏览记录吗？',
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            profile_mgr.view_history.clear()
            profile_mgr.save_view_history()
            self.load_history()
            QMessageBox.information(self, '提示', '浏览记录清空成功。')

    def load_history(self, index: int = -1):
        if index == -1:
            index = self.listWidget.currentRow()

        for i in range(self.listWidget_2.count()):
            self.listWidget_2.itemWidget(self.listWidget_2.item(i)).listWidget.clear()
        self.listWidget_2.clear()
        self.widget_list.clear()

        for history_item in profile_mgr.view_history:
            if index in (history_item['type'], 0):
                day_str = get_day_str(history_item['time'])
                day_widget = self.widget_list.get(day_str)
                if not day_widget:
                    day_widget = DayHistoryItem(day_str, self.listWidget_2)
                    self.widget_list[day_str] = day_widget

                single_item = SingleHistoryItem(day_widget.listWidget, history_item)
                day_widget.add_single_item(single_item)

        if self.widget_list.values():
            self.label.hide()
            self.listWidget_2.show()

            for widget in self.widget_list.values():
                item = QListWidgetItem()
                item.setSizeHint(widget.size())
                self.listWidget_2.addItem(item)
                self.listWidget_2.setItemWidget(item, widget)
        else:
            self.label.show()
            self.listWidget_2.hide()
