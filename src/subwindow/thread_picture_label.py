import gc

import pyperclip
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QLabel, QMenu, QAction, QFileDialog

from publics import profile_mgr, qt_image
from publics.funcs import start_background_thread, http_downloader
from publics.qt_image import ImageType


class ThreadPictureLabel(QLabel):
    """嵌入在列表的贴子图片"""
    opic_view = None

    def __init__(self, width, height, src, view_src):
        super().__init__()
        self.src_addr = src
        self.width_n = width
        self.height_n = height + 5
        self.preview_src = view_src

        self.image_loader = qt_image.MultipleImage()
        self.image_loader.currentPixmapChanged.connect(self.set_picture)
        self.image_loader.imageLoadSucceed.connect(lambda: self.on_img_loaded(True))
        self.image_loader.imageLoadFailed.connect(lambda: self.on_img_loaded(False))
        self.image_loader.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                       self.preview_src,
                                       coverType=qt_image.ImageCoverType.RadiusAngleCover,
                                       expectSize=(self.width_n, self.height_n))

        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setToolTip('图片正在加载...')
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.init_picture_contextmenu)
        self.destroyed.connect(self.on_destroy)

        self.setFixedSize(self.width_n, self.height_n)

    def on_destroy(self):
        self.image_loader.destroyImage()
        if self.opic_view:
            self.opic_view.close()

    def on_img_loaded(self, success):
        if success:
            self.setToolTip('')
            if not profile_mgr.local_config['thread_view_settings']['play_gif'] and self.image_loader.isDynamicImage():
                self.image_loader.stopPlayDynamicImage()
        else:
            self.setToolTip('图片加载失败，请重试')

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.show_big_picture()

    def set_picture(self, pixmap):
        self.setPixmap(pixmap)

    def load_picture_async(self):
        self.image_loader.loadImage()

    def pause_play_gif(self):
        if self.image_loader.isDynamicImage():
            if self.image_loader.isDynamicPlaying():
                self.image_loader.pausePlayDynamicImage()
            else:
                self.image_loader.unpausePlayDynamicImage()

    def init_picture_contextmenu(self):
        menu = QMenu()

        action_pause_gif = QAction(self)
        action_pause_gif.triggered.connect(self.pause_play_gif)
        if not self.image_loader.isDynamicImage():
            action_pause_gif.setVisible(False)
        else:
            if not self.image_loader.isDynamicPlaying():
                action_pause_gif.setText('恢复 GIF/WEBP 播放')
            else:
                action_pause_gif.setText('暂停 GIF/WEBP 播放')
        menu.addAction(action_pause_gif)

        show_o = QAction('显示大图', self)
        show_o.triggered.connect(self.show_big_picture)
        menu.addAction(show_o)

        save = QAction('保存图片', self)
        save.triggered.connect(self.save_picture)
        menu.addAction(save)

        copy_src = QAction('复制图片链接', self)
        copy_src.triggered.connect(lambda: pyperclip.copy(self.src_addr))
        menu.addAction(copy_src)

        menu.exec(QCursor.pos())

    def show_big_picture(self):
        def close_memory_clear():
            self.opic_view.destroyEvent()
            del self.opic_view
            gc.collect()

        if self.opic_view:
            self.opic_view.raise_()
            if self.opic_view.isMinimized():
                self.opic_view.showNormal()
            if not self.opic_view.isActiveWindow():
                self.opic_view.activateWindow()
        else:
            from subwindow.net_imageview import NetworkImageViewer
            self.opic_view = NetworkImageViewer(self.src_addr)
            self.opic_view.closed.connect(close_memory_clear)
            self.opic_view.show_as_config()

    def save_picture(self):
        file_type_text_index = {ImageType.Gif: 'GIF 动图文件 (*.gif)',
                                ImageType.Webp: 'Webp 图片文件 (*.webp)',
                                ImageType.OtherStatic: 'JPG 图片文件 (*.jpg;*.jpeg)'}
        file_type_text = file_type_text_index.get(self.image_loader.imageType(), ImageType.OtherStatic)

        path, type_ = QFileDialog.getSaveFileName(self, '选择图片保存位置', '', file_type_text)
        if path:
            start_background_thread(http_downloader, (path, self.src_addr))
