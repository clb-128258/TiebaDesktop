import gc
import yarl
import pyperclip
import os

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QMenu, QAction, QLabel, QWidget, QWidgetAction, QTableWidgetItem
from PyQt5.QtGui import QTextDocumentFragment, QIcon, QPixmapCache, QPixmap

from publics import funcs, profile_mgr, qt_window_mgr, app_logger, request_mgr
from ui import tb_emoji_selector


def create_thread_content_menu(parent_label: QLabel):
    def open_search_window(text):
        from subwindow.tieba_search_entry import TiebaSearchWindow
        window = TiebaSearchWindow(profile_mgr.current_bduss, profile_mgr.current_stoken)
        qt_window_mgr.add_window(window)
        window.lineEdit.setText(text)
        window.start_search()

    def get_search_engine_link():
        try:
            settings = profile_mgr.local_config['other_settings']['context_menu_search_engine']
            if settings['preset']:
                return profile_mgr.sep_name_map_inverted[settings['preset']], profile_mgr.search_engine_presets[
                    settings['preset']]
            else:
                return '自定义引擎', settings['custom_url']
        except Exception as e:
            app_logger.log_exception(e)
            return 'Bing', profile_mgr.search_engine_presets['bing']

    selected_text = parent_label.selectedText()
    all_text = QTextDocumentFragment.fromHtml(parent_label.text()).toPlainText() if parent_label.text().startswith(
        '<') else parent_label.text()

    menu = QMenu(parent_label)

    copy_selected = QAction('复制所选', parent_label)
    copy_selected.triggered.connect(lambda: pyperclip.copy(selected_text))
    if not selected_text or selected_text == all_text:
        copy_selected.setVisible(False)
    menu.addAction(copy_selected)

    copy_all = QAction('复制全文', parent_label)
    copy_all.triggered.connect(lambda: pyperclip.copy(all_text))
    menu.addAction(copy_all)

    select_all = QAction('全选文本', parent_label)
    select_all.triggered.connect(lambda: parent_label.setSelection(0, len(all_text)))
    menu.addAction(select_all)

    menu.addSeparator()

    search_tb = QAction(f'在贴吧内搜索“{selected_text}”', parent_label)
    search_tb.triggered.connect(lambda: open_search_window(selected_text))
    if not selected_text:
        search_tb.setVisible(False)
    menu.addAction(search_tb)

    # 链接直接跳转
    if selected_text.startswith((request_mgr.SCHEME_HTTP, request_mgr.SCHEME_HTTPS)):
        url = yarl.URL(selected_text)
        jump_webpage = QAction(f'跳转到网页 {url.host}', parent_label)
        jump_webpage.triggered.connect(lambda: funcs.open_url_in_browser(selected_text))
        menu.addAction(jump_webpage)

    engine_name, engine_link = get_search_engine_link()
    engine_link = engine_link.replace('[query]', selected_text)
    search_network = QAction(f'在 {engine_name} 中搜索“{selected_text}”', parent_label)
    search_network.triggered.connect(lambda: funcs.open_url_in_browser(engine_link))
    if not selected_text:
        search_network.setVisible(False)
    menu.addAction(search_network)

    return menu


class EmojiItem(QTableWidgetItem):
    def __init__(self, emoji_name):
        super().__init__()
        self.emoji_name = emoji_name
        self._is_img_loaded = False
        self.current_icon = None

        self.setSizeHint(QSize(35, 40))
        self.setToolTip(profile_mgr.emoticons_list_inverted[self.emoji_name])

    def __del__(self):
        del self.emoji_name
        del self._is_img_loaded
        del self.current_icon

    def load_emoji_img(self):
        if not self._is_img_loaded:
            file_path = f'./ui/emoticons/{self.emoji_name}.png'
            if os.path.isfile(file_path):
                self.current_icon = QIcon(file_path)
                self.setIcon(self.current_icon)
            else:
                app_logger.log_WARN(f'emoticon {self.emoji_name} was not found')
            self._is_img_loaded = True


class TiebaEmojiSelector(QWidget, tb_emoji_selector.Ui_Form):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.tableWidget.setIconSize(QSize(30, 30))
        self.label_2.setPixmap(
            QPixmap('ui/quiz_black.png').scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.frame.hide()

        self.tableWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_images)
        self.tableWidget.itemDoubleClicked.connect(self.on_emoji_selected)
        self.lineEdit.textChanged.connect(lambda: self.load_emojis(True))
        self.pushButton.clicked.connect(self.on_custom_emoticon_required)

        self.selected_emoji = ''
        self.emoji_items_list = []
        self.menu = None

        self.load_emojis()

    def showEvent(self, a0):
        a0.accept()
        self.activateWindow()
        self.scroll_load_images()

    def on_emoji_selected(self, item):
        self.selected_emoji = item.emoji_name
        self.menu.close()

    def on_custom_emoticon_required(self):
        self.selected_emoji = self.lineEdit.text()
        self.menu.close()

    def clear_emojis(self):
        self.emoji_items_list.clear()
        self.tableWidget.clear()
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(0)
        QPixmapCache.clear()
        gc.collect()

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

                emoji_item = EmojiItem(emoji_name)
                self.tableWidget.setItem(current_row, current_column, emoji_item)
                self.tableWidget.resizeColumnToContents(current_column)
                self.tableWidget.resizeRowToContents(current_row)
                self.emoji_items_list.append(emoji_item)

                # 跳转到下一行
                current_column += 1
                if current_column + 1 > max_column_count:
                    current_column = 0
                    current_row += 1
                    self.tableWidget.insertRow(current_row)

        if load_image_after_add:
            self.scroll_load_images()

        if not self.emoji_items_list:
            self.frame.show()
        else:
            self.frame.hide()

    def pop_selector(self, pos):
        self.menu = QMenu()
        self.menu.setObjectName('selectorContainerMenu')
        self.menu.setStyleSheet("""
            QMenu#selectorContainerMenu {
                background-color: white; /* 设置背景色 */
                border: 1px solid #CCCCCC; /* 设置边框 */
                padding: 0px;   /* 去掉菜单整体的内边距 */
                margin: 0px;    /* 去掉菜单整体的外边距 */
            }""")

        action = QWidgetAction(self)
        action.setDefaultWidget(self)
        self.menu.addAction(action)

        self.menu.exec(pos)
        self.clear_emojis()
        self.menu.deleteLater()

        return self.selected_emoji, profile_mgr.emoticons_list_inverted.get(self.selected_emoji, self.selected_emoji)
