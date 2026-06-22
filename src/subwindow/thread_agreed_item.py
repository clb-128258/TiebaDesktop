from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QCursor

from publics import qt_window_mgr, qt_image, profile_mgr
from publics.funcs import open_url_in_browser, show_label_pixmap_with_animation
from subwindow import base_ui

from ui import agreed_item


class AgreedThreadItem(base_ui.WindowBaseQWidget, agreed_item.Ui_Form):
    """互动列表中被点赞的内容"""
    portrait = ''
    thread_id = -1
    post_id = -1
    item_type = 0  # 1回复 2楼中楼 3主题

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.label_10.setContextMenuPolicy(Qt.NoContextMenu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_10.linkActivated.connect(self.handle_link_event)
        self.pushButton.clicked.connect(self.show_subcomment_window)
        self.label_6.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.label_6.customContextMenuRequested.connect(self.show_content_menu)
        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器

        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label_4, pixmap))
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.left_image = qt_image.MultipleImage()
        self.left_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label_2, pixmap))
        self.destroyed.connect(self.left_image.destroyImage)

    def reset_theme(self):
        super().reset_theme()
        self.add_extend_qss(f'QPushButton{{color: {profile_mgr.get_theme_font_color_string()};}}')

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease and source in (
                self.label_3, self.label_4):
            self.open_user_homepage(self.portrait)
        return super(AgreedThreadItem, self).eventFilter(source, event)  # 照常处理事件

    def show_content_menu(self):
        menu = base_ui.create_thread_content_menu(self.label_6)
        menu.exec(QCursor.pos())

    def load_images(self):
        self.portrait_image.loadImage()
        if self.left_image.isImageInfoValid():
            self.left_image.loadImage()

    def show_subcomment_window(self):
        if self.item_type == 2:
            from subwindow.reply_sub_comments import ReplySubComments
            fwindow = ReplySubComments(self.bduss, self.stoken, self.thread_id, self.post_id, -1, -2,
                                       show_thread_button=True, is_subfloor=True)
            qt_window_mgr.add_window(fwindow)
        elif self.item_type == 1:
            self.open_thread_window(self.thread_id, self.post_id)
        elif self.item_type == 3:
            self.open_thread_window(self.thread_id)

    def open_thread_window(self, thread_id, pos_pid=0):
        from subwindow.thread_detail_view import ThreadDetailView
        fwindow = ThreadDetailView(self.bduss, self.stoken, thread_id, last_post_id=pos_pid)
        qt_window_mgr.add_window(fwindow)

    def open_user_homepage(self, uid):
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def handle_link_event(self, url):
        open_url_in_browser(url)

    def setdatas(self, uicon: str, uname: str, text: str, pixmap_link: str, timestr: str, toptext: str):
        self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait, uicon,
                                         qt_image.ImageCoverType.RoundCover, (20, 20))
        self.label_3.setText(uname)
        self.label.setText(timestr)
        self.label_6.setText(text)
        self.label_10.setText(toptext)
        if pixmap_link:
            self.label_2.setFixedHeight(100)
            self.left_image.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                         pixmap_link,
                                         expectSize=(100, 100),
                                         coverType=qt_image.ImageCoverType.RadiusAngleCover)
        else:
            self.label_2.hide()

        self.adjustSize()
