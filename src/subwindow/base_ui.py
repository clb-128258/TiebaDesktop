from PyQt5.QtWidgets import QMenu, QAction, QLabel
from PyQt5.QtGui import QTextDocumentFragment
from publics import funcs, profile_mgr, qt_window_mgr
import pyperclip


def create_thread_content_menu(parent_label: QLabel):
    def open_search_window(text):
        from subwindow.tieba_search_entry import TiebaSearchWindow
        window = TiebaSearchWindow(profile_mgr.current_bduss, profile_mgr.current_stoken)
        qt_window_mgr.add_window(window)
        window.lineEdit.setText(text)
        window.start_search()

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

    search_network = QAction(f'在 Bing 中搜索“{selected_text}”', parent_label)
    search_network.triggered.connect(lambda: funcs.open_url_in_browser(f'https://www.bing.com/search?q={selected_text}'))
    if not selected_text:
        search_network.setVisible(False)
    menu.addAction(search_network)

    return menu
