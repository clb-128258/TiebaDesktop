from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QWidget

from publics import qt_window_mgr, qt_image
from publics.funcs import open_url_in_browser

from ui import agreed_item


class AgreedThreadItem(QWidget, agreed_item.Ui_Form):
    """互动列表中被点赞的内容"""
    portrait = ''
    thread_id = -1
    post_id = -1
    is_post = False

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.label_10.setContextMenuPolicy(Qt.NoContextMenu)
        self.label_6.linkActivated.connect(self.handle_link_event)
        self.label_10.linkActivated.connect(self.handle_link_event)
        self.pushButton.clicked.connect(self.show_subcomment_window)
        self.label_3.installEventFilter(self)  # 重写事件过滤器
        self.label_4.installEventFilter(self)  # 重写事件过滤器

        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentImageChanged.connect(
            lambda: self.label_4.setPixmap(self.portrait_image.currentPixmap()))
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.left_image = qt_image.MultipleImage()
        self.left_image.currentImageChanged.connect(lambda: self.label_2.setPixmap(self.left_image.currentPixmap()))
        self.destroyed.connect(self.left_image.destroyImage)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease and source in (
                self.label_3, self.label_4):
            self.open_user_homepage(self.portrait)
        return super(AgreedThreadItem, self).eventFilter(source, event)  # 照常处理事件

    def load_images(self):
        self.portrait_image.loadImage()
        if self.left_image.isImageInfoValid():
            self.left_image.loadImage()

    def show_subcomment_window(self):
        if self.is_post:
            from subwindow.reply_sub_comments import ReplySubComments
            fwindow = ReplySubComments(self.bduss, self.stoken, self.thread_id, self.post_id, -1, -1,
                                       show_thread_button=True)
        else:
            from subwindow.thread_detail_view import ThreadDetailView
            fwindow = ThreadDetailView(self.bduss, self.stoken, self.thread_id)
        qt_window_mgr.add_window(fwindow)

    def open_ba_detail(self, fid):
        from subwindow.forum_show_window import ForumShowWindow
        forum_window = ForumShowWindow(self.bduss, self.stoken, int(fid))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def open_thread(self, tid):
        from subwindow.thread_detail_view import ThreadDetailView
        third_party_thread = ThreadDetailView(self.bduss, self.stoken, int(tid))
        qt_window_mgr.add_window(third_party_thread)

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
