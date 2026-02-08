from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from publics import qt_window_mgr, qt_image
from publics.funcs import timestamp_to_string, large_num_to_string

from ui import tie_preview


class AsyncLoadImage(qt_image.MultipleImage):
    """
    将被异步加载的图片内容

    Args:
        src_link (str): 图片链接
        baidu_hash (str): 百度图床hash
    """

    def __init__(self, src_link: str, baidu_hash: str = ''):
        super().__init__()
        self.isLoaded = False

        self.src_link = src_link
        self.baidu_hash = baidu_hash

        img_type = qt_image.ImageLoadSource.BaiduHash if baidu_hash else qt_image.ImageLoadSource.HttpLink
        img_src = baidu_hash if baidu_hash else src_link
        self.setImageInfo(img_type,
                          img_src,
                          expectSize=(200, 200),
                          coverType=qt_image.ImageCoverType.RadiusAngleCoverCentrally)

    def load_image_on_qtLabel(self, label: QLabel):
        if not self.isLoaded:
            self.currentPixmapChanged.connect(label.setPixmap, Qt.QueuedConnection)
            label.destroyed.connect(self.destroyImage)
            self.loadImage()
            self.isLoaded = True


class ThreadView(QWidget, tie_preview.Ui_Form):
    """贴子在列表内的预览小组件"""
    is_treasure = False
    is_top = False
    load_by_callback = False
    is_loaded = False

    def __init__(self, bduss, tid, fid, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = tid
        self.forum_id = fid
        self.piclist = None
        self.agree_num = 0
        self.reply_num = 0
        self.send_time = 0

        self.label_11.hide()
        self.pushButton_3.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.open_thread_detail)

        self.portrait_image = qt_image.MultipleImage()
        self.forum_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(self.label_4.setPixmap)
        self.forum_image.currentPixmapChanged.connect(self.label.setPixmap)
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.destroyed.connect(self.forum_image.destroyImage)

    def load_all_AsyncImage(self):
        if not self.is_loaded:
            self._load_pictures()
            if self.portrait_image.isImageInfoValid():
                self.portrait_image.loadImage()
            if self.forum_image.isImageInfoValid():
                self.forum_image.loadImage()
            self.is_loaded = True

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView, ThreadPreview

        preview_info = ThreadPreview()
        preview_info.title = self.label_5.text()
        preview_info.text = self.label_6.text()
        preview_info.user_name = self.label_3.text()
        preview_info.forum_name = self.label_2.text()
        preview_info.agree_num = self.agree_num
        preview_info.reply_num = self.reply_num
        preview_info.send_time = self.send_time
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), self.is_treasure,
                                         self.is_top, preview_info)
        qt_window_mgr.add_window(thread_window)

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow

        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_thread_values(self, view, agree, reply, repost, send_time=0):
        self.agree_num = agree
        self.reply_num = reply
        self.send_time = send_time

        text = (f'{large_num_to_string(view, endspace=True)}次浏览，'
                f'{large_num_to_string(agree, endspace=True)}人点赞，'
                f'{large_num_to_string(reply, endspace=True)}条回复，'
                f'{large_num_to_string(repost, endspace=True)}次转发')
        if send_time > 0:
            timestr = '发布于 ' + timestamp_to_string(send_time)
            text += '\n' + timestr
        self.label_11.show()
        self.label_11.setText(text)

    def set_infos(self, uicon, uname, title, text, baicon, baname):
        if isinstance(uicon, QPixmap):
            self.label_4.setPixmap(uicon)
        elif isinstance(uicon, str):
            self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait, uicon,
                                             qt_image.ImageCoverType.RoundCover,
                                             (20, 20))
            if not self.load_by_callback and not self.is_loaded:
                self.portrait_image.loadImage()
        self.label_3.setText(uname)
        self.label_5.setText(title)
        self.label_6.setText(text)
        self.label_2.setText((baname + '吧') if baname else "贴吧动态")

        if isinstance(baicon, QPixmap):
            self.label.setPixmap(baicon)
        elif isinstance(baicon, str):
            self.forum_image.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                          baicon,
                                          qt_image.ImageCoverType.RoundCover,
                                          (17, 17))
            if not self.load_by_callback and not self.is_loaded:
                self.forum_image.loadImage()
        else:
            self.label.hide()

        if not text:
            self.label_6.hide()
        if not title:
            self.label_5.hide()

    def _load_pictures(self):
        try:
            labels = [self.label_7, self.label_8, self.label_9]
            for i in range(len(self.piclist)):
                picture = self.piclist[i]
                qtlabel = labels[i]
                if isinstance(picture, QPixmap):
                    qtlabel.setPixmap(picture)
                elif isinstance(picture, AsyncLoadImage):
                    picture.load_image_on_qtLabel(qtlabel)
        except IndexError:
            return

    def set_picture(self, piclist):
        self.piclist = piclist
        labels = [self.label_7, self.label_8, self.label_9]

        self.label_7.clear()
        self.label_8.clear()
        self.label_9.clear()
        if len(piclist) == 0:
            self.gridLayout.removeWidget(self.frame_2)
        else:
            for i in range(1, len(labels) + 1):
                if i <= len(self.piclist):
                    labels[i - 1].setMinimumHeight(200)

            if not self.load_by_callback:
                self._load_pictures()
