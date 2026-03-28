"""贴吧表情选择器"""
import os

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QTableWidgetItem, QWidgetAction

from publics import profile_mgr, app_logger, funcs
from subwindow.base_ui import WindowBaseQWidget, BaseQMenu
from ui import tb_emoji_selector


class EmojiItem(QTableWidgetItem):
    """基于 QTableWidgetItem 的表情条目"""

    def __init__(self, emoji_name):
        super().__init__()
        self.emoji_name = emoji_name
        self._is_img_loaded = False
        self.current_icon = None

        self.setSizeHint(QSize(35, 40))
        self.setToolTip(profile_mgr.emoticons_list_inverted[self.emoji_name])

    def load_emoji_img(self):
        if not self._is_img_loaded:
            file_path = f'./ui/emoticons/{self.emoji_name}.png'
            if os.path.isfile(file_path):
                self.current_icon = QIcon(file_path)
                self.setIcon(self.current_icon)
            else:
                app_logger.log_WARN(f'emoticon {self.emoji_name} was not found')
            self._is_img_loaded = True


class TiebaEmojiSelector(WindowBaseQWidget, tb_emoji_selector.Ui_Form):
    """贴吧黄豆表情选择器组件"""
    emoji_selector_instance = None
    emoji_selector_menu_instance = None
    emoji_item_instances_map = dict()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.tableWidget.setIconSize(QSize(30, 30))
        self.label_2.setPixmap(
            QPixmap('ui/icon_black/quiz.png').scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.frame.hide()

        self.tableWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_images)
        self.tableWidget.itemDoubleClicked.connect(self.on_emoji_selected)
        self.lineEdit.textChanged.connect(lambda: self.load_emojis(True))
        self.pushButton.clicked.connect(self.on_custom_emoticon_required)

        self.selected_emoji = ''

        self.load_emojis()

    def showEvent(self, a0):
        super().showEvent(a0)
        self.activateWindow()
        self.scroll_load_images()

    def on_emoji_selected(self, item):
        self.selected_emoji = item.emoji_name
        self.emoji_selector_menu_instance.close()

    def on_custom_emoticon_required(self):
        self.selected_emoji = self.lineEdit.text()
        self.emoji_selector_menu_instance.close()

    def clear_emojis(self):
        # 从最后一行/列开始取，避免索引偏移问题
        for row in range(self.tableWidget.rowCount()):
            for col in range(self.tableWidget.columnCount()):
                self.tableWidget.takeItem(row, col)
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(0)

    def scroll_load_images(self):
        items = funcs.tableWidget_get_visible_items(self.tableWidget)
        for i in items:
            i.load_emoji_img()

    def load_emojis(self, load_image_after_add=False):
        self.clear_emojis()

        max_column_count = 8
        current_row, current_column = 0, 0
        emoticons_list_sorted = list(profile_mgr.emoticons_list_inverted.keys())
        emoticons_list_sorted.sort(key=lambda e: len(e.encode()))
        search_keyword_text = self.lineEdit.text()

        self.tableWidget.insertRow(0)
        for emoji_name in emoticons_list_sorted:
            has_usable_text = bool(search_keyword_text)
            is_kw_contained = search_keyword_text in emoji_name or search_keyword_text in \
                              profile_mgr.emoticons_list_inverted[emoji_name]

            if not has_usable_text or is_kw_contained:
                if self.tableWidget.columnCount() < current_column + 1:
                    self.tableWidget.insertColumn(current_column)

                # 优先从 emoji_item_instances_map 取表情对象
                if not (emoji_item := self.emoji_item_instances_map.get(emoji_name)):
                    emoji_item = EmojiItem(emoji_name)
                    self.emoji_item_instances_map[emoji_name] = emoji_item

                self.tableWidget.setItem(current_row, current_column, emoji_item)
                self.tableWidget.resizeColumnToContents(current_column)
                self.tableWidget.resizeRowToContents(current_row)

                # 跳转到下一行
                current_column += 1
                if current_column + 1 > max_column_count:
                    current_column = 0
                    current_row += 1
                    self.tableWidget.insertRow(current_row)

        if load_image_after_add:
            self.scroll_load_images()

        if self.tableWidget.rowCount() * self.tableWidget.columnCount() == 0:
            self.frame.show()
        else:
            self.frame.hide()

    def pop_selector(self, pos):
        self.selected_emoji = ''
        self.emoji_selector_menu_instance.exec(pos)

        if self.lineEdit.text():  # 用户输入了内容
            self.lineEdit.setText('')  # 清空输入的内容，同时恢复表情列表到默认状态

        return self.selected_emoji, profile_mgr.emoticons_list_inverted.get(self.selected_emoji, self.selected_emoji)

    @classmethod
    def get_instance(cls):
        if not cls.emoji_selector_instance:
            # 没有实例时创建实例
            cls.emoji_selector_instance = TiebaEmojiSelector()
            cls.emoji_selector_menu_instance = BaseQMenu(cls.emoji_selector_instance)

            action = QWidgetAction(cls.emoji_selector_instance)
            action.setDefaultWidget(cls.emoji_selector_instance)
            cls.emoji_selector_menu_instance.addAction(action)

        # 懒更新主题
        cls.emoji_selector_instance.reset_theme()
        cls.emoji_selector_menu_instance.reset_theme()

        return cls.emoji_selector_instance
