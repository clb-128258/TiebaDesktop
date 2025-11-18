import gc

import pyperclip
import requests
from PyQt5.QtCore import pyqtSignal, Qt, QByteArray, QBuffer, QIODevice, QSize
from PyQt5.QtGui import QPixmap, QCursor, QMovie
from PyQt5.QtWidgets import QLabel, QMenu, QAction, QFileDialog

from publics import request_mgr, profile_mgr
from publics.funcs import start_background_thread, http_downloader


class ThreadPictureLabel(QLabel):
    """嵌入在列表的贴子图片"""
    set_picture_signal = pyqtSignal(QPixmap)
    set_gif_signal = pyqtSignal(bytes)
    opic_view = None
    isGif = False

    def __init__(self, width, height, src, view_src):
        super().__init__()
        self.src_addr = src
        self.width_n = width + 20
        self.height_n = height + 35
        self.preview_src = view_src

        self.setToolTip('图片正在加载...')
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.set_picture_signal.connect(self.set_picture)
        self.set_gif_signal.connect(self.set_gif_picture)
        self.customContextMenuRequested.connect(self.init_picture_contextmenu)
        self.destroyed.connect(self.on_destroy)
        self.setFixedSize(self.width_n, self.height_n)

        self.load_picture_async()

    def on_destroy(self):
        if self.isGif:
            self.gif_container.stop()
            self.gif_buffer.close()
            self.gif_byte_array.clear()
        if self.opic_view:
            self.opic_view.close()

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.show_big_picture()

    def set_picture(self, pixmap):
        self.setPixmap(pixmap)
        self.setToolTip('贴子图片')

    def set_gif_picture(self, gif_bytes):
        def on_frame_changed():
            self.setPixmap(self.gif_container.currentPixmap())

        def on_play_failed():
            self.setToolTip('无法播放 GIF 动图，你可以尝试查看大图。')

        self.gif_byte_array = QByteArray(gif_bytes)
        self.gif_buffer = QBuffer(self.gif_byte_array)
        self.gif_buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        self.gif_container = QMovie(self)
        self.gif_container.frameChanged.connect(on_frame_changed)
        self.gif_container.error.connect(on_play_failed)
        self.gif_container.setScaledSize(QSize(self.width_n, self.height_n))
        self.gif_container.setDevice(self.gif_buffer)
        self.gif_container.setCacheMode(QMovie.CacheMode.CacheAll)

        if self.gif_container.isValid():
            self.gif_container.jumpToFrame(0)
            if profile_mgr.local_config['thread_view_settings']['play_gif']:
                self.gif_container.start()
            self.setToolTip('GIF 动图，右键可暂停播放')
        else:
            on_play_failed()

    def load_picture_async(self):
        start_background_thread(self.load_picture)

    def load_picture(self):
        pixmap = QPixmap()
        response = requests.get(self.preview_src, headers=request_mgr.header)
        if response.content:
            if response.headers['content-type'] == 'image/gif':
                self.isGif = True
                self.set_gif_signal.emit(response.content)
                return
            else:
                pixmap.loadFromData(response.content)
                if pixmap.width() != self.width_n or pixmap.height() != self.height_n:
                    pixmap = pixmap.scaled(self.width_n, self.height_n, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
        self.set_picture_signal.emit(pixmap)

    def pause_play_gif(self):
        if self.isGif:
            if self.gif_container.state() == QMovie.MovieState.Paused:
                self.gif_container.setPaused(False)
            elif self.gif_container.state() == QMovie.MovieState.Running:
                self.gif_container.setPaused(True)
            elif self.gif_container.state() == QMovie.MovieState.NotRunning:
                self.gif_container.start()

    def init_picture_contextmenu(self):
        menu = QMenu()

        action_pause_gif = QAction(self)
        action_pause_gif.triggered.connect(self.pause_play_gif)
        if not self.isGif:
            action_pause_gif.setVisible(False)
        else:
            if self.gif_container.state() == QMovie.MovieState.Paused:
                action_pause_gif.setText('恢复 GIF 播放')
            elif self.gif_container.state() == QMovie.MovieState.Running:
                action_pause_gif.setText('暂停 GIF 播放')
            elif self.gif_container.state() == QMovie.MovieState.NotRunning:
                action_pause_gif.setText('开始播放 GIF')
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
            self.opic_view.show()

    def save_picture(self):
        file_type_text = 'GIF 动图文件 (*.gif)' if self.isGif else 'JPG 图片文件 (*.jpg;*.jpeg)'

        path, type_ = QFileDialog.getSaveFileName(self, '选择图片保存位置', '', file_type_text)
        if path:
            start_background_thread(http_downloader, (path, self.src_addr))
