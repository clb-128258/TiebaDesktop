import asyncio
import gc
import sys
import time
import typing
import json

import aiotieba
import pyperclip

from PyQt5.QtCore import pyqtSignal, Qt, QEvent, QPoint, QSize, QRect, QTimer, QObject
from PyQt5.QtGui import QIcon, QPixmapCache, QFont, QCursor, QPixmap
from PyQt5.QtWidgets import QAction, QMessageBox, QListWidgetItem

import consts

from publics import profile_mgr, qt_window_mgr, top_toast_widget, qt_image, webview2
from publics.funcs import LoadingFlashWidget, open_url_in_browser, start_background_thread, make_thread_content, \
    timestamp_to_string, cut_string, large_num_to_string, get_exception_string, get_dict_value_treely, \
    cleanup_listWidget
import publics.app_logger as logging
from publics.tieba_apis import add_post, agree_thread_or_post, OpAgreeObjectType, store_thread, cancel_store_thread, \
    pb_page
from subwindow import base_ui, tieba_emoji_selector, tieba_user_selector
from subwindow.tieba_image_uploader import TiebaImageUploader
from ui import tie_detail_view

narrow_status_map = {1: base_ui.NarrowButtonStatus.ArrowRight, 2: base_ui.NarrowButtonStatus.ArrowLeft}


def get_item_top(list_widget, index):
    """获取某个条目的顶部纵坐标"""
    if index < 0:
        return -sys.maxsize
    if index >= list_widget.count():
        return sys.maxsize
    return list_widget.visualItemRect(list_widget.item(index)).top()


def find_first_at_or_below(list_widget, y):
    """找到第一个可见的条目"""
    low, high = 0, list_widget.count()

    # 二分查找
    while low < high:
        mid = (low + high) // 2
        if get_item_top(list_widget, mid) < y:
            low = mid + 1
        else:
            high = mid
    return low


def find_last_at_or_above(list_widget, y):
    """找到最后一个可见的条目"""
    low, high = -1, list_widget.count() - 1

    # 二分查找
    while low < high:
        mid = (low + high + 1) // 2
        if get_item_top(list_widget, mid) <= y:
            low = mid
        else:
            high = mid - 1
    return low


class ThreadPreview:
    """要预填充的贴子信息"""
    forum_name = ''  # 最后须带吧字
    user_name = ''
    send_time = 0
    agree_num = 0
    reply_num = ''

    title = ''
    text = ''


class AddPostCaptchaWebView(base_ui.WindowBaseQDialog):
    """发贴遇到验证码时，显示验证码网页的webview"""

    class CaptchaDataGetter(QObject, webview2.HttpDataRewriter):
        is_captcha_token_got = False
        captchaTokenGot = pyqtSignal(dict)

        def onResponseCaught(self, url: str, statusCode: int, header: typing.Dict[str, str],
                             content: typing.Optional[bytes]):
            if statusCode == 200 and not self.is_captcha_token_got:
                json_data = json.loads(content.decode())
                if json_data['code'] == 0:
                    self.is_captcha_token_got = True
                    time.sleep(1)  # 休眠一秒，保证ui显示效果
                    self.captchaTokenGot.emit(json_data['data'])
                else:
                    logging.log_WARN(f'tieba add post captcha failed with json info {json_data}')
            else:
                logging.log_WARN(f'tieba add post captcha failed with HTTP status code {statusCode}')

            return statusCode, header, content

    def __init__(self, captcha_md5, h5_link):
        super().__init__()

        self.captcha_md5 = captcha_md5
        self.h5_link = h5_link
        self.captcha_success_json_info = None

        self.setWindowTitle('交互式发贴验证码')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.resize(800, 600)

        self.webview = webview2.QWebView2View()
        self.http_catcher = self.CaptchaDataGetter()
        self.http_catcher.captchaTokenGot.connect(self.on_captcha_succeed)
        self.webview.setParent(self)
        self.profile = webview2.WebViewProfile(data_folder=f'{consts.datapath}/webview_data/{profile_mgr.current_uid}',
                                               user_agent=f'[default_ua] CLBTiebaDesktop/{consts.APP_VERSION_STR}',
                                               enable_link_hover_text=False,
                                               enable_zoom_factor=False,
                                               enable_error_page=True,
                                               enable_context_menu=True,
                                               enable_keyboard_keys=True,
                                               handle_newtab_byuser=False,
                                               http_rewriter={
                                                   '*://seccaptcha.baidu.com/v1/webapi/verint/verify/*': self.http_catcher},
                                               enable_transparent_bg=get_dict_value_treely(
                                                   profile_mgr.local_config,
                                                   ['webview_settings', 'transparent_bg_color'], False))
        self.webview.setProfile(self.profile)
        self.webview.loadAfterRender(h5_link)
        self.webview.initRender()

    def resizeEvent(self, a0):
        self.webview.setGeometry(0, 0, self.width(), self.height())

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def closeEvent(self, a0):
        if not self.http_catcher.is_captcha_token_got:
            if QMessageBox.warning(self, '提示', '确认要取消本次验证码校验吗？如果取消验证，那么本次发贴操作将被取消。',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.webview.destroyWebviewUntilComplete()
                a0.accept()
            else:
                a0.ignore()
        else:
            self.webview.destroyWebviewUntilComplete()
            a0.accept()

    def exec_window(self):
        self.exec()
        return self.captcha_md5, self.captcha_success_json_info

    def on_captcha_succeed(self, data):
        self.captcha_success_json_info = data
        self.close()


class ThreadDetailView(base_ui.WindowBaseQWidget, tie_detail_view.Ui_Form):
    """主题贴详情窗口，可以浏览主题贴详细内容和回复"""
    first_floor_pid = -1  # 首楼回复id
    forum_id = -1  # 吧id
    user_id = -1  # 楼主用户id
    last_post_id = 0  # 回复列表中最新的pid，用于拉取回复列表

    reply_page = 1  # 当前回复页数
    reply_total_pages = 0  # 回复列表总页数
    first_loaded_page = 0  # 首次加载回复时的页码

    agree_num = 0  # 点赞数
    reply_num = 0  # 回贴数
    store_num = 0  # 收藏数
    has_agreed = False  # 是否已点赞
    has_stored = False  # 是否已收藏

    is_getting_replys = False  # 是否正在加载回复列表
    is_textedit_menu_poping = False  # 是否在发贴textedit上右键
    narrow_mode_index = 1  # 窄布局模式下的显示页面
    height_count = 0  # 首楼展示部分所有内容组件的高度
    height_count_replies = 0  # 回复列表内所有组件的高度
    width_count_replies = 0  # 回复列表内所有组件的宽度

    head_data_signal = pyqtSignal(dict)
    add_reply = pyqtSignal(dict)
    show_reply_end_text = pyqtSignal(dict)
    store_thread_signal = pyqtSignal(str)
    agree_thread_signal = pyqtSignal(str)
    add_post_signal = pyqtSignal(dict)
    reply_loaded_signal = pyqtSignal()

    def __init__(self, bduss, stoken, tid, is_treasure=False, is_top=False, preview_info=None, last_post_id=0):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = tid
        self.is_treasure = is_treasure
        self.is_top = is_top

        self.lz_portrait = qt_image.MultipleImage()
        self.forum_avatar = qt_image.MultipleImage()

        self.label_2.hide()
        self.label_8.hide()
        self.label_11.hide()
        self.label_12.hide()
        self.label_13.hide()
        self.frame_3.hide()
        self.frame_7.hide()
        self.pushButton_12.hide()
        self.pushButton_13.hide()
        self.collapse_text_area()

        icon_size = QSize(23, 23)
        self.pushButton_4.setIconSize(icon_size)
        self.pushButton_11.setIconSize(icon_size)
        self.pushButton.setIconSize(icon_size)

        icon_size_large = QSize(30, 30)
        self.pushButton_12.setIconSize(icon_size_large)
        self.pushButton_13.setIconSize(icon_size_large)

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))

        self.comboBox.setCurrentIndex(profile_mgr.local_config['thread_view_settings']['default_sort'])
        self.checkBox.setChecked(profile_mgr.local_config['thread_view_settings']['enable_lz_only'])
        self.label_2.setContextMenuPolicy(Qt.NoContextMenu)
        self.init_narrow_switch_button()
        self.init_load_flash()
        self.init_top_toaster()

        self.pushButton.clicked.connect(self.init_more_menu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_6.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label_6.customContextMenuRequested.connect(lambda: self.show_content_menu(self.label_6))
        self.label_5.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label_5.customContextMenuRequested.connect(lambda: self.show_content_menu(self.label_5))
        self.head_data_signal.connect(self.update_ui_head_info)
        self.pushButton_2.clicked.connect(self.open_ba_detail)
        self.add_reply.connect(self.add_reply_ui)
        self.show_reply_end_text.connect(self.show_end_reply_ui)
        self.store_thread_signal.connect(self.store_thread_ok_action)
        self.agree_thread_signal.connect(self.agree_thread_ok_action)
        self.reply_loaded_signal.connect(self.on_reply_loaded)
        self.add_post_signal.connect(self.add_post_ok_action)
        self.scrollArea.verticalScrollBar().valueChanged.connect(self.load_sub_threads_from_scroll)
        self.comboBox.currentIndexChanged.connect(lambda: self.load_sub_threads_refreshly())
        self.checkBox.stateChanged.connect(lambda: self.load_sub_threads_refreshly())
        self.label_2.linkActivated.connect(self.end_label_link_event)
        self.pushButton_4.clicked.connect(lambda: self.agree_thread_async())
        self.pushButton_3.clicked.connect(lambda: self.add_post_async())
        self.pushButton_7.clicked.connect(self.submit_pagejump)
        self.pushButton_12.clicked.connect(self.jump_prev_page)
        self.pushButton_13.clicked.connect(self.jump_next_page)
        self.pushButton_8.clicked.connect(self.jump_first_page)
        self.toolButton.clicked.connect(self.frame_7.hide)
        self.lz_portrait.currentPixmapChanged.connect(self.label_4.setPixmap)
        self.forum_avatar.currentPixmapChanged.connect(self.label_14.setPixmap)
        self.toolButton_2.clicked.connect(self.frame_3.hide)
        self.pushButton_5.clicked.connect(self.show_addpost_image_switcher)
        self.pushButton_10.clicked.connect(self.show_addpost_emoji_selector)
        self.pushButton_6.clicked.connect(self.show_addpost_atuser_selector)
        self.pushButton_11.clicked.connect(lambda: self.store_thread_async())
        self.toolButton_3.clicked.connect(self.show_pagejump_bar)

        # 重写事件过滤器
        add_post_area_widgets = [self.label_3, self.label_4,
                                 self.label_9, self.textEdit,
                                 self.textEdit.viewport(),
                                 self.textEdit.horizontalScrollBar(),
                                 self.textEdit.verticalScrollBar(),
                                 self.pushButton_3, self.pushButton_5,
                                 self.pushButton_6, self.pushButton_10]
        for w in add_post_area_widgets:
            w.installEventFilter(self)

        if preview_info:
            self.flash_shower.hide()
            self.set_ui_head_preview(preview_info)
        else:
            self.flash_shower.show()

        self.get_thread_head_info_async()
        self.load_sub_threads_refreshly(last_post_id=last_post_id)

    def reset_theme(self):
        from subwindow.thread_picture_label import ThreadPictureLabel
        super().reset_theme()

        listwidgets = [self.listWidget, self.listWidget_4]
        flat_buttons = [self.pushButton, self.pushButton_4, self.pushButton_11, self.pushButton_13, self.pushButton_12]
        color = profile_mgr.get_theme_color_string()
        font_color = profile_mgr.get_theme_font_color_string()
        bg_policy, font_policy = profile_mgr.get_theme_policy_string()

        for lw in listwidgets:
            lw.setStyleSheet(f'QListWidget{{outline:0px; background-color:{color};}}'
                             f'QListWidget::item:hover {{color:{color}; background-color:{color};}}'
                             f'QListWidget::item:selected {{color:{color}; background-color:{color};}}')
            lw.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            # 设置列表内容的样式
            for i in range(lw.count()):
                widget = lw.itemWidget(lw.item(i))
                if not isinstance(widget, ThreadPictureLabel):
                    widget.reset_theme()

        for btn in flat_buttons:
            btn.setStyleSheet(f'QPushButton{{color: {font_color};}}')

        self.post_area_flash_shower.reset_theme()
        self.flash_shower.reset_theme()
        self.scrollAreaWidgetContents_2.setStyleSheet(
            f'QWidget#scrollAreaWidgetContents_2 {{background-color: {color};}}')

        self.label_19.setPixmap(
            QPixmap(f'ui/icon_{font_policy}/warning.png').scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.toolButton_2.setIcon(QIcon(f'ui/icon_{font_policy}/close.png'))
        self.toolButton.setIcon(QIcon(f'ui/icon_{font_policy}/close.png'))
        self.toolButton_3.setIcon(QIcon(f'ui/icon_{font_policy}/page.png'))
        self.pushButton.setIcon(QIcon(f'ui/icon_{font_policy}/share.png'))
        self.pushButton_12.setIcon(QIcon(f'ui/icon_{font_policy}/arrow_warm_up.png'))
        self.pushButton_13.setIcon(QIcon(f'ui/icon_{font_policy}/arrow_cool_down.png'))
        self.update_agree_button_status()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if source in (self.label_3, self.label_4):
                self.open_user_homepage(self.user_id)
            elif source == self.label_9:
                self.open_forum_detail_page()
        elif event.type() == QEvent.Type.FocusIn:
            if source == self.textEdit:
                self.is_textedit_menu_poping = False
                self.lay_text_area()
        elif event.type() == QEvent.Type.FocusOut:
            local_pos = self.frame.mapFromGlobal(QCursor.pos())
            is_mouse_contained = self.frame.rect().contains(local_pos)

            if source == self.textEdit and not self.is_textedit_menu_poping and not is_mouse_contained:
                self.collapse_text_area()
        elif event.type() == QEvent.Type.ContextMenu:
            if source in (
                    self.textEdit.viewport(),
                    self.textEdit.verticalScrollBar(),
                    self.textEdit.horizontalScrollBar()):
                self.is_textedit_menu_poping = True
        elif event.type() == QEvent.Type.KeyRelease:
            if (
                    source == self.textEdit
                    and event.modifiers() == Qt.KeyboardModifier.ControlModifier
                    and event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
            ):
                self.add_post_async()

        return super(ThreadDetailView, self).eventFilter(source, event)  # 照常处理事件

    def closeEvent(self, a0):
        from subwindow.thread_video_item import ThreadVideoItem

        inputted_text = self.textEdit.toPlainText()
        profile_mgr.add_post_draft(self.thread_id, inputted_text)

        self.flash_shower.hide()
        a0.accept()

        self.forum_avatar.destroyImage()
        self.lz_portrait.destroyImage()

        # 显式销毁视频webview
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            if isinstance(widget, ThreadVideoItem):
                widget.on_destroyed()
                break

        lw_list = [self.listWidget, self.listWidget_4]
        for lw in lw_list:
            cleanup_listWidget(lw)

        qt_window_mgr.del_window(self)

    def resizeEvent(self, a0):
        self.adjust_narrow_button()

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)

        self.post_area_flash_shower = LoadingFlashWidget()
        self.post_area_flash_shower.cover_widget(self.scrollArea)

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def show_copy_success_toast(self):
        toast_msg = top_toast_widget.ToastMessage('复制成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)
        self.top_toaster.showToast(toast_msg)

    def end_label_link_event(self, url):
        if url == 'reload_replies':
            self.load_sub_threads_refreshly()

    def show_content_menu(self, plabel):
        menu = base_ui.create_thread_content_menu(plabel)
        menu.exec(QCursor.pos())

    def adjust_narrow_button(self):
        if self.width() <= 800:
            if self.narrow_mode_index == 1:
                self.scrollArea_2.show()
                self.frame_5.hide()
                self.gridLayout_11.setColumnStretch(0, 1)
                self.gridLayout_11.setColumnStretch(1, 0)
            elif self.narrow_mode_index == 2:
                self.scrollArea_2.hide()
                self.frame_5.show()
                self.gridLayout_11.setColumnStretch(0, 0)
                self.gridLayout_11.setColumnStretch(1, 1)

            self.narrow_switch_button.move_button()
            self.narrow_switch_button.show()
        else:
            self.gridLayout_11.setColumnStretch(0, 1)
            self.gridLayout_11.setColumnStretch(1, 1)
            self.scrollArea_2.show()
            self.frame_5.show()
            self.narrow_switch_button.hide()

    def switch_narrow_button_status(self):
        if self.narrow_mode_index == 1:
            self.gridLayout_11.setColumnStretch(0, 0)
            self.gridLayout_11.setColumnStretch(1, 1)
            self.scrollArea_2.hide()
            self.frame_5.show()
            self.narrow_mode_index = 2
        elif self.narrow_mode_index == 2:
            self.gridLayout_11.setColumnStretch(0, 1)
            self.gridLayout_11.setColumnStretch(1, 0)
            self.scrollArea_2.show()
            self.frame_5.hide()
            self.narrow_mode_index = 1

        self.narrow_switch_button.set_button_status(narrow_status_map[self.narrow_mode_index])

    def init_narrow_switch_button(self):
        self.narrow_switch_button = base_ui.FloatingButton(self)
        self.narrow_switch_button.clicked.connect(self.switch_narrow_button_status)
        self.narrow_switch_button.set_button_status(narrow_status_map[self.narrow_mode_index])

    def init_more_menu(self):
        url = f'https://tieba.baidu.com/p/{self.thread_id}'

        menu = base_ui.BaseQMenu()

        copy_id = QAction('复制贴子 ID', self)
        copy_id.triggered.connect(lambda: pyperclip.copy(str(self.thread_id)))
        copy_id.triggered.connect(self.show_copy_success_toast)
        menu.addAction(copy_id)

        copy_link = QAction('复制链接', self)
        copy_link.triggered.connect(lambda: pyperclip.copy(url))
        copy_link.triggered.connect(self.show_copy_success_toast)
        menu.addAction(copy_link)

        open_link = QAction('浏览器打开', self)
        open_link.triggered.connect(lambda: open_url_in_browser(url))
        menu.addAction(open_link)

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

    def update_pagejump_num(self):
        if self.reply_page == -1:  # 最后1页
            final_current_page = 1 if self.comboBox.currentIndex() == 1 else self.reply_total_pages
        elif self.reply_num == 0 or self.reply_page == -2:  # 没有回复，页数未加载
            final_current_page = -1
        else:
            # 加载线程会把页数加一，方便下次加载，真正的当前页数为 self.reply_page-1，倒序则反之
            final_current_page = self.reply_page + (1 if self.comboBox.currentIndex() == 1 else -1)

        if final_current_page != -1:
            self.spinBox.setRange(1, self.reply_total_pages)
            self.spinBox.setValue(final_current_page)
            self.label_17.setText(f'页，共有 {self.reply_total_pages} 页')
        else:
            self.frame_7.hide()

    def show_pagejump_bar(self):
        if self.reply_num == 0:
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='该主题还没有任何回复，没有页面可以跳转',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        elif self.reply_page == -2:  # 请求倒序加载，但最后页面还未获取
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='必须先加载出总页数才可跳页',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        else:
            self.update_pagejump_num()
            self.frame_7.show()

    def jump_prev_page(self):
        self.spinBox.setValue(self.spinBox.value() - 1)
        self.submit_pagejump()

    def jump_next_page(self):
        self.pushButton_13.setEnabled(False)
        self.pushButton_13.setText('正在加载下一页...')
        self.get_sub_thread_async()

    def jump_first_page(self):
        self.spinBox.setValue(1)
        self.submit_pagejump()

    def submit_pagejump(self):
        if self.reply_page == -1:  # 最后1页
            final_current_page = 1 if self.comboBox.currentIndex() == 1 else self.reply_total_pages
        else:
            # 加载线程会把页数加一，方便下次加载，真正的当前页数为 self.reply_page-1，倒序则反之
            final_current_page = self.reply_page + (1 if self.comboBox.currentIndex() == 1 else -1)

        if final_current_page == self.spinBox.value():
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title=f'现在已经在第 {final_current_page} 页',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        else:
            self.reply_page = self.spinBox.value()
            self.load_sub_threads_refreshly(reset_page=False)

    def show_addpost_image_switcher(self):
        dialog = TiebaImageUploader()
        image_list = dialog.exec_window()
        if image_list:
            insert_text = '\n'.join(f'#(pic,{i.image_id},{i.origin_width},{i.origin_height})' for i in image_list)
            self.textEdit.insertPlainText(insert_text)

        dialog.deleteLater()

    def show_addpost_atuser_selector(self):
        selector = tieba_user_selector.TiebaUserSelector.get_instance()
        self.lay_text_area()

        self.is_textedit_menu_poping = True
        btn = self.pushButton_6
        bt_pos = btn.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x(), bt_pos.y() + btn.height() + 8)
        selected_user = selector.pop_selector(show_pos)
        if selected_user:
            self.textEdit.insertPlainText(f"#(at, {selected_user['portrait']}, {selected_user['user_name']})")
        self.is_textedit_menu_poping = False

    def show_addpost_emoji_selector(self):
        selector = tieba_emoji_selector.TiebaEmojiSelector.get_instance()
        self.lay_text_area()

        self.is_textedit_menu_poping = True
        btn = self.pushButton_10
        bt_pos = btn.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x(), bt_pos.y() + btn.height() + 8)

        emoji_id, emoji_text = selector.pop_selector(show_pos)
        if emoji_text:
            self.textEdit.insertPlainText(emoji_text)
        self.is_textedit_menu_poping = False

    def lay_text_area(self):
        self.frame_2.show()
        self.textEdit.setPlaceholderText('来都来了，说两句吧\n'
                                         'Ctrl+Enter 可快速发送回复')
        self.textEdit.setFont(QFont('微软雅黑', 10))
        self.textEdit.setFixedHeight(100)
        self.textEdit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.textEdit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def collapse_text_area(self):
        self.frame_2.hide()
        self.frame_2.close()
        self.textEdit.setPlaceholderText('来都来了，说两句吧')
        self.textEdit.setFont(QFont('微软雅黑', 9))
        self.textEdit.setFixedHeight(28)
        self.textEdit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textEdit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def add_post_ok_action(self, msg):
        toast = top_toast_widget.ToastMessage()
        toast.title = msg['text']

        if msg['success']:
            self.textEdit.setText('')
            self.is_textedit_menu_poping = False
            self.collapse_text_area()
            toast.icon_type = top_toast_widget.ToastIconType.SUCCESS

            # 异步跳转到最后一页
            self.reply_page = self.reply_total_pages
            QTimer.singleShot(4000, lambda: self.load_sub_threads_refreshly(reset_page=False))
        else:
            toast.icon_type = top_toast_widget.ToastIconType.ERROR

        self.top_toaster.showToast(toast)
        self.frame.setEnabled(True)
        self.pushButton_3.setText('发贴')

        # 验证码模式特判
        if msg['is_captcha']:
            md5 = msg['captcha_info']['md5']
            h5_link = msg['captcha_info']['link']

            dialog = AddPostCaptchaWebView(md5, h5_link)
            md5, json_info = dialog.exec_window()
            if json_info:
                self.add_post_async(md5, json_info)
            else:
                self.top_toaster.showToast(top_toast_widget.ToastMessage('用户已取消交互验证',
                                                                         icon_type=top_toast_widget.ToastIconType.INFORMATION))

    def add_post_async(self, captcha_md5=None, captcha_json_info=None):
        if not self.textEdit.toPlainText():
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='请输入内容后再回贴',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        elif not self.bduss:
            self.top_toaster.showToast(top_toast_widget.ToastMessage(title='目前处于游客状态，请登录后再回贴',
                                                                     icon_type=top_toast_widget.ToastIconType.INFORMATION))
        else:
            if not (captcha_md5 and captcha_json_info):
                show_string = ('回复功能目前还处于测试阶段。\n'
                               '使用本软件回贴可能会遇到发贴失败、弹验证码等情况，甚至可能导致你的账号被全吧永久封禁。\n'
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
            else:
                flag = True

            if flag:
                self.frame.setEnabled(False)
                self.pushButton_3.setText('发送中...')
                start_background_thread(self.add_post, args=(captcha_md5, captcha_json_info))

    def add_post(self, captcha_md5, captcha_json_info):
        emit_data = {'success': False,
                     'text': '',
                     'is_captcha': False,
                     'captcha_info': {'md5': '', 'link': ''}
                     }
        try:
            result = add_post(self.bduss, self.stoken, self.forum_id, self.thread_id, self.textEdit.toPlainText(),
                              captcha_md5, captcha_json_info)
            if result.error.errorno == 0:
                emit_data['success'] = True
                exp_text = f'经验 +{result.data.exp.inc}' if result.data.exp.inc not in ('0', '') else '本次回贴没有增加任何经验值'
                emit_data['text'] = f'回贴成功，{exp_text}'
            elif result.data.info.need_vcode == '1':
                emit_data['success'] = False
                emit_data['is_captcha'] = True
                emit_data['captcha_info']['md5'] = result.data.info.vcode_md5
                emit_data['captcha_info']['link'] = result.data.info.vcode_pic_url
                emit_data['text'] = '服务器要求输入验证码，请在弹出的验证网页中完成验证。如多次弹出验证，建议使用官方客户端发贴'
            else:
                emit_data['success'] = False
                emit_data['text'] = f'{result.error.errmsg} (错误代码 {result.error.errorno})'
        except Exception as e:
            logging.log_exception(e)
            emit_data['success'] = False
            emit_data['text'] = get_exception_string(e)
        finally:
            self.add_post_signal.emit(emit_data)

    def agree_thread_ok_action(self, isok):
        self.update_agree_button_status()

        if isok == '[ALREADY_AGREE]':
            if QMessageBox.information(self, '已经点过赞了', '你已经点过赞了，是否要取消点赞？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.agree_thread_async(True)
        else:
            toast = top_toast_widget.ToastMessage(isok, 2000, top_toast_widget.ToastIconType.INFORMATION)
            self.top_toaster.showToast(toast)

    def agree_thread_async(self, is_cancel: bool = None):
        start_background_thread(self.agree_thread, (self.has_agreed if is_cancel is None else is_cancel,))

    def agree_thread(self, iscancel=False):
        logging.log_INFO(f'agree thread {self.thread_id}')
        try:
            if not self.bduss:
                self.agree_thread_signal.emit('登录后即可为贴子点赞')
            elif self.user_id == 0:
                self.agree_thread_signal.emit('不能给匿名用户点赞')
            else:
                response = agree_thread_or_post(self.bduss, self.stoken, self.thread_id, self.first_floor_pid, iscancel,
                                                OpAgreeObjectType.Thread)
                if int(response['error_code']) == 0:
                    if iscancel:
                        self.agree_num -= 1
                        self.has_agreed = False
                        self.agree_thread_signal.emit('取消点赞成功')
                    else:
                        self.agree_num += 1
                        self.has_agreed = True
                        is_expa2 = bool(int(response["data"].get("agree", {"is_first_agree": False})["is_first_agree"]))
                        self.agree_thread_signal.emit("点赞成功 首赞经验 +2" if is_expa2 else "点赞成功")

                elif int(response['error_code']) == 3280001:
                    self.agree_num += 1
                    self.agree_thread_signal.emit('[ALREADY_AGREE]')
                    self.has_agreed = True
                else:
                    self.agree_thread_signal.emit(response['error_msg'])
        except Exception as e:
            logging.log_exception(e)
            self.agree_thread_signal.emit(get_exception_string(e))

    def store_thread_ok_action(self, isok):
        self.update_agree_button_status()

        toast = top_toast_widget.ToastMessage(isok, 2000, top_toast_widget.ToastIconType.INFORMATION)
        self.top_toaster.showToast(toast)

    def store_thread_async(self, is_cancel: bool = None):
        item = self.listWidget_4.currentItem()
        if not item:
            # 没有回贴就使用第一楼的pid
            pid = self.first_floor_pid
            floor = 1
        else:
            reply_widget = self.listWidget_4.itemWidget(item)
            pid = reply_widget.post_id
            floor = reply_widget.floor
        start_background_thread(self.store_thread, (pid, self.has_stored if is_cancel is None else is_cancel, floor))

    def store_thread(self, current_post_id: int, is_cancel=False, floor=-1):
        async def dosign():
            logging.log_INFO(f'store thread {self.thread_id}')
            try:
                if not self.bduss:
                    self.store_thread_signal.emit('登录后即可收藏贴子')
                    return

                if not is_cancel:
                    result = store_thread(self.bduss, self.stoken, self.thread_id, current_post_id)
                    if result['error_code'] == '0':
                        self.store_thread_signal.emit(f'贴子已收藏到第 {floor} 楼')
                        self.has_stored = True
                        self.store_num += 1
                    else:
                        self.store_thread_signal.emit(result['error_msg'])
                else:
                    result = cancel_store_thread(self.bduss, self.stoken, self.thread_id, current_post_id)
                    if result['no'] == 0:
                        self.store_thread_signal.emit('取消收藏成功')
                        self.has_stored = False
                        self.store_num -= 1
                    else:
                        self.store_thread_signal.emit(result['error'])
            except Exception as e:
                logging.log_exception(e)
                self.store_thread_signal.emit(get_exception_string(e))

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def load_sub_threads_refreshly(self, reset_page=True, last_post_id=0):
        if not self.is_getting_replys:
            # 清理内存
            cleanup_listWidget(self.listWidget_4)
            QPixmapCache.clear()
            gc.collect()

            self.pushButton_12.hide()
            self.listWidget_4.show()
            self.height_count_replies = 0
            self.width_count_replies = 0

            # 初始化页数
            sort_type = self.comboBox.currentIndex()
            if reset_page:
                self.reply_page = -2 if sort_type == 1 else 1

            self.last_post_id = last_post_id
            self.first_loaded_page = self.reply_page

            # 启动刷新
            self.scrollArea.verticalScrollBar().setValue(0)
            self.post_area_flash_shower.show()
            self.get_sub_thread_async()

    def load_sub_thread_images(self):
        widgets = self.get_visible_replies()
        for w in widgets:
            w.load_images()

    def load_sub_threads_from_scroll(self):
        self.load_sub_thread_images()

        if self.scrollArea.verticalScrollBar().value() == self.scrollArea.verticalScrollBar().maximum():
            self.get_sub_thread_async()

    def get_visible_replies(self):
        reply_widgets = []
        scroll_area = self.scrollArea
        list_widget = self.listWidget_4

        if list_widget.count() == 0:
            return reply_widgets

        scroll_y = scroll_area.verticalScrollBar().value()
        viewport_rect = QRect(0, scroll_y,
                              scroll_area.viewport().width(),
                              scroll_area.viewport().height())

        list_pos = list_widget.mapTo(scroll_area.widget(), QPoint(0, 0))
        visible_top = viewport_rect.top() - list_pos.y()
        visible_bottom = viewport_rect.bottom() - list_pos.y()

        visible_top = max(visible_top, 0)
        visible_bottom = min(visible_bottom, list_widget.height() - 1)

        first = find_first_at_or_below(list_widget, visible_top)
        last = find_last_at_or_above(list_widget, visible_bottom)

        if first >= list_widget.count() or last < 0 or first > last:  # 在数值不合法时
            return reply_widgets

        for i in range(first, last + 1):
            reply_widgets.append(list_widget.itemWidget(list_widget.item(i)))

        return reply_widgets

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def update_listwidget_size(self, h):
        self.height_count += h
        self.listWidget.setFixedHeight(self.height_count)

    def show_end_reply_ui(self, data):
        self.label_2.show()
        self.post_area_flash_shower.hide()
        if self.listWidget_4.count() == 0:
            self.listWidget_4.hide()

        self.label_2.setText(f"———  {data['text']}  ———")
        if data['toast']:
            self.top_toaster.showToast(data['toast'])

    def on_reply_loaded(self):
        self.label_7.setText(f'回复区 ({self.reply_num} 条回复)')
        self.update_pagejump_num()
        self.load_sub_thread_images()
        self.pushButton_13.hide()

        sort_type = self.comboBox.currentIndex()

        # 获取当前页面，带末页判断和抵消子线程加减
        current_page = self.reply_total_pages if self.reply_page == -1 else \
            (self.reply_page + 1 if sort_type == 1 else self.reply_page - 1)
        if self.first_loaded_page == current_page:
            show_next_page_btn = self.listWidget_4.minimumHeight() <= self.scrollArea.height() and self.reply_page != -1
            show_prev_page_btn_asc = current_page > 1 and sort_type in (0, 2)
            show_prev_page_btn_desc = self.reply_total_pages - current_page > 0 and sort_type == 1

            if show_next_page_btn:
                self.pushButton_13.setEnabled(True)
                self.pushButton_13.setText('加载下一页内容')
                self.pushButton_13.show()
            if show_prev_page_btn_asc or show_prev_page_btn_desc:
                self.pushButton_12.show()

        self.post_area_flash_shower.hide()

    def add_reply_ui(self, datas):
        item = QListWidgetItem()
        from subwindow.thread_reply_item import ReplyItem
        widget = ReplyItem(self.bduss, self.stoken)
        widget.portrait = datas['portrait']
        widget.is_comment = False
        widget.load_by_callback = True
        widget.thread_id = self.thread_id
        widget.post_id = datas['post_id']
        widget.setdatas(datas['portrait'], datas['user_name'], datas['is_author'], datas['content'],
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
        self.is_getting_replys = True
        logging.log_INFO(f'loading thread {self.thread_id} replies list page {self.reply_page}')

        try:
            sort_type = self.comboBox.currentIndex()
            if self.reply_page == -2:
                page_pbinfo = pb_page(self.bduss, self.stoken,
                                      self.thread_id, 1, 30,
                                      only_see_lz=self.checkBox.isChecked())
                if page_pbinfo.error.errorno != 0:
                    raise Exception(f'获取最新页数失败: {page_pbinfo.error.errmsg} '
                                    f'(错误代码 {page_pbinfo.error.errorno})')
                else:
                    # 在获取到最大页数后也更新 first_loaded_page 的值
                    self.reply_page = page_pbinfo.data.page.total_page
                    self.first_loaded_page = self.reply_page

            proto_response = pb_page(self.bduss, self.stoken,
                                     self.thread_id,
                                     self.reply_page, 30,
                                     sort_type, self.checkBox.isChecked(),
                                     self.last_post_id)
            thread_info = aiotieba.get_posts.Posts.from_tbdata(proto_response.data)

            if proto_response.error.errorno != 0:
                raise Exception(f'回复加载失败: {proto_response.error.errmsg} '
                                f'(错误代码 {proto_response.error.errorno})')
            else:
                self.reply_num = thread_info.thread.reply_num - 1
                self.reply_total_pages = thread_info.page.total_page

                if self.last_post_id:
                    # 带回复 id 加载一定是刷新式的加载，因此也要更新 first_loaded_page
                    self.reply_page = thread_info.page.current_page
                    self.first_loaded_page = self.reply_page

            if thread_info.thread.reply_num == 1:
                self.reply_page = -1

                endtext_data = {'text': '还没有人回贴，别让楼主寂寞太久', 'toast': None}
                self.show_reply_end_text.emit(endtext_data)
            else:
                for t in thread_info.objs:
                    if t.floor == 1:  # 跳过第一楼
                        continue

                    content = make_thread_content(t.contents.objs)
                    floor = -1 if sort_type == 2 else t.floor
                    reply_num = t.reply_num
                    portrait = t.user.portrait
                    user_name = t.user.nick_name_new
                    agree_num = t.agree
                    time_str = timestamp_to_string(t.create_time)
                    user_ip = t.user.ip
                    user_level = t.user.level
                    user_ip = user_ip if user_ip else ''
                    is_author = t.is_thread_author
                    is_bawu = t.user.is_bawu
                    grow_level = t.user.glevel
                    post_id = t.pid

                    voice_info = {'have_voice': False, 'src': '', 'length': 0}
                    if t.contents.voice:
                        voice_info['have_voice'] = True
                        voice_info['src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={t.contents.voice.md5}'
                        voice_info['length'] = t.contents.voice.duration

                    preview_pixmap = []
                    for j in t.contents.imgs:
                        # width, height, src, view_src
                        src = j.origin_src
                        view_src = j.big_src
                        height = j.show_height
                        width = j.show_width
                        preview_pixmap.append({'width': width, 'height': height,
                                               'src': src, 'view_src': view_src})

                    tdata = {'content': content,
                             'portrait': portrait,
                             'user_name': user_name,
                             'view_pixmap': preview_pixmap,
                             'agree_count': agree_num,
                             'create_time_str': time_str,
                             'user_ip': user_ip,
                             'is_author': is_author,
                             'floor': floor,
                             'reply_num': reply_num,
                             'ulevel': user_level,
                             'post_id': post_id,
                             'is_bawu': is_bawu,
                             'grow_level': grow_level,
                             'voice_info': voice_info}

                    self.add_reply.emit(tdata)

                logging.log_INFO(
                    f'load thread {self.thread_id} replies list page {self.reply_page} ok')

                if sort_type == 1:  # 在倒序查看时要递减页数
                    self.reply_page -= 1
                else:
                    self.reply_page += 1
                if not thread_info.page.has_more:
                    self.reply_page = -1

                    endtext_data = {'text': '你已经到达了贴子的尽头', 'toast': None}
                    self.show_reply_end_text.emit(endtext_data)
        except Exception as e:
            logging.log_exception(e)

            toast = top_toast_widget.ToastMessage(get_exception_string(e),
                                                  icon_type=top_toast_widget.ToastIconType.ERROR)
            endtext_data = {'text': '服务器开小差了，请试试 <a href="reload_replies">重新加载</a>', 'toast': toast}
            self.show_reply_end_text.emit(endtext_data)
        finally:
            self.is_getting_replys = False
            self.reply_loaded_signal.emit()

    def update_agree_button_status(self):
        bg_color, font_color = profile_mgr.get_theme_policy_string()

        self.pushButton_4.setText(' ' + large_num_to_string(self.agree_num))
        self.pushButton_11.setText(' ' + large_num_to_string(self.store_num))

        icon = f'ui/thumb_up_filled.png' if self.has_agreed else f'ui/icon_{font_color}/thumb_up.png'
        self.pushButton_4.setIcon(QIcon(icon))

        icon = f'ui/star_filled.png' if self.has_stored else f'ui/icon_{font_color}/star.png'
        self.pushButton_11.setIcon(QIcon(icon))

    def set_ui_head_preview(self, datas: ThreadPreview):
        if datas.forum_name.startswith(('最近回复于', '发布于')):
            datas.forum_name = '未知贴吧'

        self.setWindowTitle(datas.title + ' - ' + datas.forum_name)
        self.label_15.setText(datas.forum_name)
        self.label_14.hide()
        self.label_21.hide()

        self.pushButton_4.setText(large_num_to_string(datas.agree_num, endspace=True) + '个赞')
        self.label_3.setText(datas.user_name)
        if datas.send_time:
            self.label.setText(timestamp_to_string(datas.send_time))
        self.label_5.setText(datas.title)
        self.label_6.setText(datas.text)
        self.label_7.setText('回复区 ({n} 条回复)'.format(n=str(datas.reply_num)))
        if self.is_treasure:
            self.label_13.show()
        else:
            self.horizontalLayout_2.removeWidget(self.label_13)
        if self.is_top:
            self.label_12.show()
        else:
            self.horizontalLayout_2.removeWidget(self.label_12)

    def update_ui_head_info(self, datas):
        if datas['err_info']:
            QMessageBox.critical(self, '贴子加载失败', datas['err_info'], QMessageBox.Ok)
            self.close()
        else:
            self.flash_shower.hide()
            if self.forum_id != 0:
                self.setWindowTitle(datas['title'] + ' - ' + datas['forum_name'] + '吧')
                self.label_15.setText(datas['forum_name'] + '吧')
                if datas['forum_slogan']:
                    self.label_21.show()
                    self.label_21.setText(datas['forum_slogan'])
                else:
                    self.label_21.hide()

                self.label_14.clear()
                self.label_14.show()
                self.forum_avatar.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                               datas['forum_avatar'],
                                               qt_image.ImageCoverType.RoundCover,
                                               (50, 50))
                self.forum_avatar.loadImage()
            else:
                self.setWindowTitle(datas['title'] + ' - 贴吧动态')
                self.frame_4.hide()

            self.lz_portrait.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                          datas['author_portrait'],
                                          qt_image.ImageCoverType.RoundCover,
                                          (50, 50))
            self.lz_portrait.loadImage()

            if profile_mgr.local_config['thread_view_settings']['hide_ip']:
                self.label.setText(datas['create_time_str'])
            else:
                self.label.setText('{time} | IP 属地 {ip}'.format(time=datas['create_time_str'], ip=datas['user_ip']))
            self.label_5.setText(datas['title'])
            self.label_6.setText(datas['content'])
            self.label_3.setText(datas['user_name'])
            self.label_10.setText('Lv.' + str(datas['user_grow_level']))
            self.label_7.setText('回复区 ({n} 条回复)'.format(n=str(datas['post_num'])))
            self.textEdit.setText(datas['draft_text'])
            self.update_agree_button_status()
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
                self.frame_8.hide()
            if datas['content_statement'] and get_dict_value_treely(profile_mgr.local_config,
                                                                    ['thread_view_settings', 'show_statement'], True):
                self.frame_3.show()
                self.label_20.setText('内容声明：' + datas['content_statement'])

            self.label_9.setText('Lv.{0}'.format(datas['uf_level']))
            qss = ''
            if 0 <= datas['uf_level'] <= 3:  # 绿牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 211, 171); border-radius: 7px;}'
            elif 4 <= datas['uf_level'] <= 9:  # 蓝牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(101, 161, 255); border-radius: 7px;}'
            elif 10 <= datas['uf_level'] <= 15:  # 黄牌
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(255, 172, 29); border-radius: 7px;}'
            elif datas['uf_level'] >= 16:  # 橙牌老东西
                qss = 'QLabel{color: rgb(255, 255, 255);background-color: rgb(247, 126, 48); border-radius: 7px;}'

            self.label_9.setStyleSheet(qss)  # 为不同等级设置qss

            no_rich_content_flags = [bool(datas['view_pixmap']),
                                     datas['video_info']['have_video'],
                                     datas['voice_info']['have_voice'],
                                     datas['repost_info']['have_repost'],
                                     datas['manager_election_info']['have_manager_election']]
            if True not in no_rich_content_flags:
                self.listWidget.hide()
            else:
                if datas['video_info']['have_video']:
                    from subwindow.thread_video_item import ThreadVideoItem
                    video_widget = ThreadVideoItem()
                    video_widget.setdatas(datas['video_info']['src'], datas['video_info']['length'],
                                          datas['video_info']['view'], datas['video_info']['cover_src'])
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

                    self.update_listwidget_size(i['height'] + 5)
                    label.load_picture_async()

                if datas['repost_info']['have_repost']:
                    from subwindow.thread_preview_item import ThreadView

                    repost_widget = ThreadView(self.bduss, datas['repost_info']['thread_id'],
                                               datas['repost_info']['forum_id'], self.stoken)
                    repost_widget.set_infos(datas['repost_info']['author_portrait'],
                                            datas['repost_info']['author_name'],
                                            datas['repost_info']['title'],
                                            datas['repost_info']['content'],
                                            None,
                                            datas['repost_info']['forum_name'])
                    repost_widget.set_picture([])
                    repost_widget.label_11.show()
                    repost_widget.label_11.setText('这是被转发的贴子。')
                    repost_widget.adjustSize()

                    item = QListWidgetItem()
                    item.setSizeHint(repost_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, repost_widget)
                    self.update_listwidget_size(repost_widget.height())

                if datas['vote_info']['have_vote']:
                    from subwindow.thread_vote_item import ThreadVoteItem, VoteItem

                    option_list = []
                    for o in datas['vote_info']['options']:
                        item = VoteItem(o['id'])
                        item.set_info(o['text'], o['total_num'], o['current_num'], o['is_chosen'],
                                      o['is_current_chose'])
                        option_list.append(item)

                    vote_widget = ThreadVoteItem(datas['vote_info']['is_multi'], self.thread_id, self.forum_id)
                    vote_widget.set_info(datas['vote_info']['title'],
                                         datas['vote_info']['vote_num'],
                                         datas['vote_info']['vt_user_num'],
                                         option_list)
                    vote_widget.msgPopped.connect(self.top_toaster.showToast)
                    vote_widget.adjustSize()

                    item = QListWidgetItem()
                    item.setSizeHint(vote_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, vote_widget)
                    self.update_listwidget_size(vote_widget.height())

                if datas['manager_election_info']['have_manager_election']:
                    from subwindow.thread_election_item import ThreadManagerElectionItem

                    election_widget = ThreadManagerElectionItem()
                    election_widget.set_info(datas['manager_election_info']['can_vote'],
                                             datas['manager_election_info']['status'],
                                             datas['manager_election_info']['vote_num'],
                                             datas['manager_election_info']['vote_start_time'])

                    item = QListWidgetItem()
                    item.setSizeHint(election_widget.size())
                    self.listWidget.addItem(item)
                    self.listWidget.setItemWidget(item, election_widget)
                    self.update_listwidget_size(election_widget.height())

    def get_thread_head_info_async(self):
        start_background_thread(self.get_thread_head_info)

    def get_thread_head_info(self):
        async def run_async():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    logging.log_INFO(f'loading thread {self.thread_id} main info')

                    proto_response = pb_page(self.bduss, self.stoken,
                                             self.thread_id, 1, 2)
                    thread_info = aiotieba.get_posts.Posts.from_tbdata(proto_response.data)

                    if proto_response.error.errorno != 0:
                        raise Exception(f'{proto_response.error.errmsg} (错误代码 {proto_response.error.errorno})')

                    self.forum_id = forum_id = thread_info.forum.fid
                    if self.forum_id != 0:
                        forum_proto = proto_response.data.forum
                        forum_name = forum_proto.name
                        forum_pic_url = forum_proto.avatar
                        forum_slogan = (f'{large_num_to_string(forum_proto.member_num, endspace=True)}人关注 | '
                                        f'{large_num_to_string(forum_proto.post_num, endspace=True)}条贴子')
                    else:
                        forum_name = ''
                        forum_pic_url = ''
                        forum_slogan = ''

                    preview_pixmap = []
                    self.has_agreed = bool(proto_response.data.thread.agree.has_agree)
                    self.has_stored = proto_response.data.thread.collect_status == 2
                    self.agree_num = thread_info.thread.agree
                    self.store_num = proto_response.data.thread.collect_num
                    self.user_id = thread_info.thread.user.user_id
                    self.first_floor_pid = thread_info.thread.pid
                    self.reply_num = post_num = thread_info.thread.reply_num - 1
                    title = thread_info.thread.title
                    content = make_thread_content(thread_info.thread.contents.objs)
                    portrait = thread_info.thread.user.portrait
                    user_name = thread_info.thread.user.nick_name_new
                    time_str = timestamp_to_string(thread_info.thread.create_time)
                    user_ip = thread_info.thread.user.ip
                    user_ip = user_ip if user_ip else '未知'
                    is_help = thread_info.thread.is_help
                    user_forum_level = thread_info.thread.user.level
                    user_grow_level = thread_info.thread.user.glevel
                    is_forum_manager = bool(thread_info.thread.user.is_bawu)
                    content_statement = proto_response.data.thread.content_statement

                    video_info = {'have_video': False, 'src': '', 'cover_src': '', 'length': 0, 'view': 0,
                                  'is_vertical': False}
                    if thread_info.thread.contents.video:
                        video_info['have_video'] = True
                        video_info['src'] = proto_response.data.thread.video_info.video_url  # 获取带参数的正确链接
                        video_info['length'] = thread_info.thread.contents.video.duration
                        video_info['view'] = thread_info.thread.contents.video.view_num
                        video_info['cover_src'] = proto_response.data.thread.video_info.small_thumbnail_url
                        video_info['is_vertical'] = bool(proto_response.data.thread.video_info.is_vertical)

                    voice_info = {'have_voice': False, 'src': '', 'length': 0}
                    if thread_info.thread.contents.voice:
                        voice_info['have_voice'] = True
                        voice_info[
                            'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={thread_info.thread.contents.voice.md5}&play_from=pb_voice_play'
                        voice_info['length'] = thread_info.thread.contents.voice.duration

                    repost_info = {'have_repost': thread_info.thread.is_share,
                                   'author_portrait_pixmap': None,
                                   'author_name': '',
                                   'title': '',
                                   'content': '',
                                   'thread_id': -1,
                                   'forum_id': -1,
                                   'forum_name': ''}
                    if thread_info.thread.is_share:
                        repost_user_info = await client.get_user_info(thread_info.thread.share_origin.author_id,
                                                                      aiotieba.enums.ReqUInfo.PORTRAIT | aiotieba.enums.ReqUInfo.NICK_NAME)
                        repost_info['author_portrait'] = repost_user_info.portrait
                        repost_info['author_name'] = repost_user_info.nick_name_new

                        repost_info['title'] = thread_info.thread.share_origin.title
                        repost_info['content'] = cut_string(
                            make_thread_content(thread_info.thread.share_origin.contents, True), 150)
                        repost_info['thread_id'] = thread_info.thread.share_origin.tid
                        repost_info['forum_id'] = thread_info.thread.share_origin.fid
                        repost_info['forum_name'] = thread_info.thread.share_origin.fname

                    vote_info = {'have_vote': bool(thread_info.thread.vote_info.title),
                                 'title': '',
                                 'vote_num': 0,
                                 'vt_user_num': 0,
                                 'is_multi': False,
                                 'chose_option_index': 0,
                                 'options': []}
                    if vote_info['have_vote']:
                        vote_info_proto = proto_response.data.thread.origin_thread_info.poll_info
                        vote_info['title'] = thread_info.thread.vote_info.title
                        vote_info['vote_num'] = thread_info.thread.vote_info.total_vote
                        vote_info['vt_user_num'] = thread_info.thread.vote_info.total_user
                        vote_info['is_multi'] = thread_info.thread.vote_info.is_multi
                        vote_info['chose_option_index'] = int(
                            vote_info_proto.polled_value if vote_info_proto.polled_value else -1)

                        vote_options_proto = vote_info_proto.options
                        for o in vote_options_proto:
                            vote_option = {'id': o.id,
                                           'text': o.text,
                                           'is_chosen': bool(vote_info_proto.is_polled),
                                           'is_current_chose': o.id == vote_info['chose_option_index'],
                                           'total_num': thread_info.thread.vote_info.total_vote,
                                           'current_num': o.num}
                            vote_info['options'].append(vote_option)

                    manager_election_info = {
                        'have_manager_election': bool(proto_response.data.manager_election.status),
                        'can_vote': bool(proto_response.data.manager_election.can_vote),
                        'vote_num': int(proto_response.data.manager_election.vote_num),
                        'vote_start_time': int(
                            proto_response.data.manager_election.begin_vote_time),
                        'status': int(proto_response.data.manager_election.status)}

                    for j in thread_info.thread.contents.imgs:
                        # width, height, src, view_src
                        src = j.origin_src
                        view_src = j.big_src
                        height = j.show_height
                        width = j.show_width
                        preview_pixmap.append({'width': width, 'height': height, 'src': src, 'view_src': view_src})

                    draft_text = profile_mgr.get_post_draft(self.thread_id)
                    profile_mgr.add_view_history(1,
                                                 {"thread_id": self.thread_id,
                                                  "title": f'{title} - {forum_name}吧'})

                    tdata = {'forum_id': forum_id,  # 吧id
                             'title': title,  # 标题
                             'content': content,  # 正文内容
                             'author_portrait': portrait,  # 作者portrait
                             'user_name': user_name,  # 作者昵称
                             'forum_name': forum_name,  # 吧名称
                             'forum_avatar': forum_pic_url,  # 吧头像链接
                             'view_pixmap': preview_pixmap,  # 主题内图片列表
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
                             'forum_slogan': forum_slogan,  # 吧标语
                             'vote_info': vote_info,  # 投票信息
                             'draft_text': draft_text,  # 草稿文本
                             'content_statement': content_statement,  # 内容提示，如 "疑似含AI内容"
                             'manager_election_info': manager_election_info,  # 吧主竞选信息
                             }

                    logging.log_INFO(
                        f'load thread {self.thread_id} main info ok, send to qt side')
                    self.head_data_signal.emit(tdata)
            except Exception as e:
                self.head_data_signal.emit({'err_info': get_exception_string(e)})
                logging.log_exception(e)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_async())

        start_async()
