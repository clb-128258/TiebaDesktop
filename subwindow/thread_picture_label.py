import gc

import pyperclip
import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QCursor
from PyQt5.QtWidgets import QLabel, QMenu, QAction, QFileDialog

from publics import request_mgr
from publics.funcs import start_background_thread, http_downloader


class ThreadPictureLabel(QLabel):
    """嵌入在列表的贴子图片"""
    set_picture_signal = pyqtSignal(QPixmap)
    opic_view = None

    def __init__(self, width, height, src, view_src):
        super().__init__()
        self.src_addr = src
        self.width_n = width
        self.height_n = height
        self.preview_src = view_src

        self.setToolTip('图片正在加载...')
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.set_picture_signal.connect(self.set_picture)
        self.customContextMenuRequested.connect(self.init_picture_contextmenu)
        self.setFixedSize(self.width_n + 20, self.height_n + 35)

        self.load_picture_async()

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.show_big_picture()

    def set_picture(self, pixmap):
        self.setPixmap(pixmap)
        self.setToolTip('贴子图片')

    def load_picture_async(self):
        start_background_thread(self.load_picture)

    def load_picture(self):
        pixmap = QPixmap()
        response = requests.get(self.preview_src, headers=request_mgr.header)
        if response.content:
            pixmap.loadFromData(response.content)
            if pixmap.width() != self.width_n + 20 or pixmap.height() != self.height_n + 35:
                pixmap = pixmap.scaled(self.width_n + 20, self.height_n + 35, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation)
        self.set_picture_signal.emit(pixmap)

    def init_picture_contextmenu(self):
        menu = QMenu()

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
            self.opic_view = None

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
            self.opic_view.show()

    def save_picture(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择图片保存位置', '', 'JPEG 图片 (*.jpg;*.jpeg)')
        if path:
            start_background_thread(http_downloader, (path, self.src_addr))
