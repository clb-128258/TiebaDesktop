import os
import threading
import time

import requests
from PyQt5.QtCore import pyqtSignal, QEvent, Qt, QMimeData, QUrl, QByteArray, QSize, QBuffer, QIODevice
from PyQt5.QtGui import QPixmap, QIcon, QDrag, QImage, QTransform, QMovie
from PyQt5.QtWidgets import QWidget, QApplication, QMenu, QAction, QFileDialog

import publics.app_logger as logging
from publics import request_mgr, top_toast_widget, profile_mgr
from ui import image_viewer


class NetworkImageViewer(QWidget, image_viewer.Ui_Form):
    """图片查看器窗口，支持旋转缩放图片，以及保存"""
    updateImage = pyqtSignal(QPixmap)
    finishDownload = pyqtSignal(bool)
    gifLoaded = pyqtSignal(bytes)
    closed = pyqtSignal()
    start_pos = None
    isDraging = False
    originalImage = None
    downloadOk = False
    isResizing = False
    isGif = False
    gif_container = None

    round_angle = 0
    is_horizontal_mirror = False
    is_vertical_mirror = False

    def __init__(self, src):
        super().__init__()
        self.setupUi(self)
        self.src = src

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label.setText('图片加载中...')
        self.init_menu()
        self.init_top_toaster()
        self.scrollArea.viewport().installEventFilter(self)  # 重写事件过滤器

        self.updateImage.connect(self._resizeslot)
        self.spinBox.valueChanged.connect(self.resize_image)
        self.finishDownload.connect(self.update_download_state)
        self.gifLoaded.connect(self.show_gif)

        self.load_image()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Wheel and source is self.scrollArea.viewport():
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.wheelEvent(event)  # 手动执行缩放事件
                return True  # 让qt忽略事件
        return super(NetworkImageViewer, self).eventFilter(source, event)  # 否则照常处理事件

    def show_as_config(self):
        window_rect = profile_mgr.get_window_rects(type(self))
        if not window_rect:
            self.show()
            return

        if window_rect[4]:
            self.showMaximized()
        else:
            self.setGeometry(window_rect[0],
                             window_rect[1],
                             window_rect[2],
                             window_rect[3])
            self.show()

    def save_geometry_config(self):
        profile_mgr.add_window_rects(type(self),
                                     self.x(), self.y() + 32,
                                     self.width(), self.height(),
                                     self.isMaximized())

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def closeEvent(self, e):
        self.save_geometry_config()
        self.closed.emit()
        e.accept()

    def mousePressEvent(self, a0):
        self.start_pos = a0.pos()

    def mouseMoveEvent(self, a0):
        if a0.buttons() and Qt.MouseButton.LeftButton and self.downloadOk:
            distance = (a0.pos() - self.start_pos).manhattanLength()

            timestr = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time()))
            temp_name = '{0}/{1}.{2}'.format(os.getenv('temp'), f'PictureDownload_{timestr}',
                                             'gif' if self.isGif else 'jpg')
            if distance >= QApplication.startDragDistance():
                self.isDraging = True
                self.reset_title()
                if self.isGif:
                    if not self.gif_byte_array.isNull():
                        with open(temp_name, 'wb') as file:
                            file.write(self.gif_byte_array.data())
                else:
                    if not self.originalImage.isNull():
                        self.originalImage.save(temp_name)
                mime_data = QMimeData()
                url = QUrl()
                url.setUrl("file:///" + temp_name)
                mime_data.setUrls((url,))

                drag = QDrag(self)
                drag.setMimeData(mime_data)
                drag.setHotSpot(a0.pos())
                drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.LinkAction, Qt.DropAction.CopyAction)
                if os.path.isfile(temp_name):
                    os.remove(temp_name)
                self.isDraging = False
                self.reset_title()

    def destroyEvent(self):
        try:
            self.show_movie.stop()
            if self.gif_container:
                self.gif_container.stop()
                self.gif_buffer.close()
                self.gif_byte_array.clear()
            del self.originalImage
            self.deleteLater()
        except:
            pass

    def init_menu(self):
        menu = QMenu(self)

        self.action_pause_gif = QAction('暂停 GIF 播放', self)
        self.action_pause_gif.triggered.connect(self.pause_play_gif)
        menu.addAction(self.action_pause_gif)

        menu.addSeparator()

        transform_left = QAction('顺时针旋转 90 度', self)
        transform_left.triggered.connect(self.transform_image_left)
        menu.addAction(transform_left)

        transform_right = QAction('逆时针旋转 90 度', self)
        transform_right.triggered.connect(self.transform_image_right)
        menu.addAction(transform_right)

        menu.addSeparator()

        self.mirror_horizontal = QAction('水平翻转', self)
        self.mirror_horizontal.setCheckable(True)
        self.mirror_horizontal.setChecked(self.is_horizontal_mirror)
        self.mirror_horizontal.triggered.connect(self.mirror_horizontally)
        menu.addAction(self.mirror_horizontal)

        self.mirror_vertical = QAction('垂直翻转', self)
        self.mirror_vertical.setCheckable(True)
        self.mirror_vertical.setChecked(self.is_vertical_mirror)
        self.mirror_vertical.triggered.connect(self.mirror_vertically)
        menu.addAction(self.mirror_vertical)

        menu.addSeparator()

        reset_pixmap = QAction('复原图片', self)
        reset_pixmap.triggered.connect(self.reset_image)
        menu.addAction(reset_pixmap)

        self.pushButton_2.setMenu(menu)

        share_menu = QMenu(self)

        self.action_copyto = QAction('复制', self)
        self.action_copyto.triggered.connect(
            lambda: QApplication.clipboard().setPixmap(QPixmap.fromImage(self.originalImage)))
        self.action_copyto.triggered.connect(
            lambda: self.top_toaster.showToast(
                top_toast_widget.ToastMessage('复制成功', icon_type=top_toast_widget.ToastIconType.SUCCESS)))
        share_menu.addAction(self.action_copyto)

        save = QAction('保存', self)
        save.triggered.connect(self.save_file)
        share_menu.addAction(save)

        self.pushButton_4.setMenu(share_menu)

    def mirror_vertically(self):
        self.is_vertical_mirror = not self.is_vertical_mirror
        self.resize_image()

    def mirror_horizontally(self):
        self.is_horizontal_mirror = not self.is_horizontal_mirror
        self.resize_image()

    def transform_image_left(self):
        self.round_angle += 90
        self.resize_image()

    def transform_image_right(self):
        self.round_angle += -90
        self.resize_image()

    def reset_image(self):
        self.round_angle = 0
        self.is_vertical_mirror = False
        self.is_horizontal_mirror = False
        self.spinBox.setValue(100)
        self.resize_image()

    def reset_title(self):
        append_text = ''
        if self.isDraging:
            append_text += '[拖拽图片到外部] '
        if self.spinBox.value() != 100:
            append_text += f'[缩放 {self.spinBox.value()} %] '
        if self.round_angle != 0:
            if self.round_angle < 0:
                append_text += f'[逆时针旋转 {abs(self.round_angle)}°] '
            elif self.round_angle > 0:
                append_text += f'[顺时针旋转 {self.round_angle}°] '
        if self.is_horizontal_mirror:
            append_text += f'[水平翻转] '
        if self.is_vertical_mirror:
            append_text += f'[垂直翻转] '

        if append_text:
            self.setWindowTitle(f'{append_text} - 图片查看器')
        else:
            self.setWindowTitle('图片查看器')

    def _resizeslot(self, pixmap):
        self.label.setPixmap(pixmap)
        self.scrollAreaWidgetContents.setMinimumSize(pixmap.width(), pixmap.height())

        self.mirror_horizontal.setChecked(self.is_horizontal_mirror)
        self.mirror_vertical.setChecked(self.is_vertical_mirror)
        self.reset_title()

    def _resizedo(self, ruler):
        self.isResizing = True
        if self.originalImage is None:
            image = QImage()
            self.originalImage = image

            success_flag = False
            try:
                response = requests.get(self.src, headers=request_mgr.header)
                if response.content:
                    if response.headers['content-type'] == 'image/gif':
                        self.isGif = True
                        success_flag = True
                        self.gifLoaded.emit(response.content)
                    elif self.originalImage.loadFromData(response.content):
                        success_flag = True
            except Exception as e:
                logging.log_exception(e)
            finally:
                self.finishDownload.emit(success_flag)

        result_image = self.originalImage
        if not result_image.isNull():
            if self.round_angle != 0:
                result_image = result_image.transformed(QTransform().rotate(self.round_angle))
            if ruler != 1:
                nw = int(self.originalImage.width() * ruler)
                nh = int(self.originalImage.height() * ruler)
                if int(self.round_angle / 90) % 2 != 0:
                    # 交换图片长宽值以实现正确缩放
                    _ = nh
                    nh = nw
                    nw = _
                result_image = result_image.scaled(nw, nh, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
            result_image = result_image.mirrored(self.is_horizontal_mirror, self.is_vertical_mirror)
            self.updateImage.emit(QPixmap.fromImage(result_image))
        self.isResizing = False

    def resize_image(self):
        if not self.isResizing:
            if abs(self.round_angle) == 360:
                self.round_angle = 0
            thread = threading.Thread(target=self._resizedo, args=(self.spinBox.value() / 100,), daemon=True)
            thread.start()

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and self.downloadOk:
            if event.angleDelta().y() > 0:
                value = 10
            else:
                value = -10
            self.spinBox.setValue(self.spinBox.value() + value)

    def save_file(self):
        file_type_text = 'GIF 动图文件 (*.gif)' if self.isGif else 'JPG 图片文件 (*.jpg;*.jpeg)'

        path, tpe = QFileDialog.getSaveFileName(self, '保存图片', '', file_type_text)
        if path:
            try:
                if self.isGif:
                    if not self.gif_byte_array.isNull():
                        with open(path, 'wb') as file:
                            file.write(self.gif_byte_array.data())
                    else:
                        raise EOFError('gif image data is null')
                else:
                    if not self.originalImage.isNull():
                        self.originalImage.save(path)
                    else:
                        raise EOFError('static image data is null')
            except Exception as e:
                self.top_toaster.showToast(
                    top_toast_widget.ToastMessage(str(e), icon_type=top_toast_widget.ToastIconType.ERROR))
            else:
                self.top_toaster.showToast(
                    top_toast_widget.ToastMessage('文件保存成功', icon_type=top_toast_widget.ToastIconType.SUCCESS))

    def update_download_state(self, f):
        self.show_movie.stop()
        if not f:
            self.reset_title()
            self.label.clear()
            self.top_toaster.showToast(top_toast_widget.ToastMessage('图片加载失败，请重新加载试试',
                                                                     icon_type=top_toast_widget.ToastIconType.ERROR))
        else:
            self.downloadOk = True
            self.pushButton_4.setEnabled(True)
            self.pushButton_2.setEnabled(True)
            self.spinBox.setEnabled(True)

            if self.isGif:
                self.action_copyto.setEnabled(False)
            else:
                self.action_pause_gif.setVisible(False)

    def pause_play_gif(self):
        if self.isGif:
            if self.gif_container.state() == QMovie.MovieState.Paused:
                self.gif_container.setPaused(False)
                self.action_pause_gif.setText('暂停 GIF 播放')
            elif self.gif_container.state() == QMovie.MovieState.Running:
                self.gif_container.setPaused(True)
                self.action_pause_gif.setText('恢复 GIF 播放')

    def show_gif(self, gif_bytes):
        def on_frame_changed():
            self.originalImage = self.gif_container.currentImage()
            self.resize_image()

        def on_play_failed():
            self.downloadOk = False
            self.pushButton_4.setEnabled(False)
            self.pushButton_2.setEnabled(False)
            self.spinBox.setEnabled(False)
            self.label.clear()
            self.top_toaster.showToast(top_toast_widget.ToastMessage('GIF 播放失败，图片数据可能已损坏',
                                                                     icon_type=top_toast_widget.ToastIconType.ERROR))

        self.gif_byte_array = QByteArray(gif_bytes)
        self.gif_buffer = QBuffer(self.gif_byte_array)
        self.gif_buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        self.gif_container = QMovie(self)
        self.gif_container.frameChanged.connect(on_frame_changed)
        self.gif_container.error.connect(on_play_failed)
        self.gif_container.setDevice(self.gif_buffer)
        self.gif_container.setCacheMode(QMovie.CacheMode.CacheAll)

        if self.gif_container.isValid():
            self.gif_container.jumpToFrame(0)
            self.gif_container.start()
        else:
            on_play_failed()

    def load_image(self):
        self.setWindowTitle(f'[加载中...] - 图片查看器')

        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(100, 100))
        self.show_movie.frameChanged.connect(lambda: self.label.setPixmap(self.show_movie.currentPixmap()))

        self.resize_image()
        self.show_movie.start()
