from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QObject, pyqtSignal, Qt

from publics import qt_window_mgr, request_mgr, logging, cache_mgr
from publics.funcs import timestamp_to_string, large_num_to_string, start_background_thread
import requests

from ui import tie_preview


class AsyncLoadImage(QObject):
    """
    将被异步加载的图片内容

    Args:
        src_link (str): 图片链接
        baidu_hash (str): 百度图床hash
    """
    _imageLoaded = pyqtSignal(bool)

    def __init__(self, src_link: str, baidu_hash: str = ''):
        super().__init__()
        self._image_binary = None
        self._image_pixmap = None
        self.isLoaded = False

        self.src_link = src_link
        self.baidu_hash = baidu_hash

    def load_image_on_qtLabel(self, label: QLabel):
        def on_img_loaded(success):
            if success and not label.isHidden():
                label.setToolTip('贴子图片')
                label.setPixmap(self._image_pixmap)
            else:
                label.setToolTip('此图片加载失败')
                self.isLoaded = False

        if not self.isLoaded:
            self._imageLoaded.connect(on_img_loaded, Qt.QueuedConnection)
            self.load_image_async()
            self.isLoaded = True

    def load_image_async(self):
        start_background_thread(self.load_image)

    def load_qtPixmap(self):
        self._image_pixmap = QPixmap()
        self._image_pixmap.loadFromData(self._image_binary)
        if self._image_pixmap.isNull():
            raise AttributeError('QPixmap.loadFromData failed')
        self._image_pixmap = self._image_pixmap.scaled(200, 200,
                                                       Qt.KeepAspectRatio,
                                                       Qt.SmoothTransformation)

    def load_image(self):
        try:
            if not self.baidu_hash:
                resp = requests.get(self.src_link, headers=request_mgr.header)
                resp.raise_for_status()
                self._image_binary = resp.content
            else:
                self._image_binary = cache_mgr.get_bd_hash_img(self.baidu_hash)

            if not self._image_binary:
                raise AttributeError('image binary data is null')
            self.load_qtPixmap()
        except Exception as e:
            logging.log_exception(e)
            self._imageLoaded.emit(False)
        else:
            self._imageLoaded.emit(True)


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

        self.label_11.hide()
        self.pushButton_3.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.open_thread_detail)

    def load_all_AsyncImage(self):
        if not self.is_loaded:
            self._load_pictures()
            self.is_loaded = True

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), self.is_treasure,
                                         self.is_top)
        qt_window_mgr.add_window(thread_window)

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow

        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_thread_values(self, view, agree, reply, repost, send_time=0):
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
        self.label_4.setPixmap(uicon)
        self.label_3.setText(uname)
        self.label_5.setText(title)
        self.label_6.setText(text)
        self.label_2.setText((baname + '吧') if baname else "贴吧动态")

        if baicon:
            self.label.setPixmap(baicon)
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
