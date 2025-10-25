import gc
import os
import threading

import requests
from PyQt5.QtCore import pyqtSignal, QEvent, Qt, QMimeData, QUrl, QByteArray, QSize
from PyQt5.QtGui import QPixmap, QIcon, QDrag, QImage, QTransform, QMovie
from PyQt5.QtWidgets import QWidget, QApplication, QMenu, QAction, QFileDialog, QMessageBox

from publics import request_mgr
from ui import image_viewer


class NetworkImageViewer(QWidget, image_viewer.Ui_Form):
    """图片查看器窗口，支持旋转缩放图片，以及保存"""
    updateImage = pyqtSignal(QPixmap)
    finishDownload = pyqtSignal(bool)
    closed = pyqtSignal()
    start_pos = None
    round_angle = 0
    isDraging = False
    originalImage = None
    downloadOk = False
    isResizing = False

    def __init__(self, src):
        super().__init__()
        self.setupUi(self)
        self.src = src

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label.setText('图片加载中...')
        self.init_menu()
        self.scrollArea.viewport().installEventFilter(self)  # 重写事件过滤器

        self.updateImage.connect(self._resizeslot)
        self.spinBox.valueChanged.connect(self.resize_image)
        self.finishDownload.connect(self.update_download_state)

        self.load_image()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Wheel and source is self.scrollArea.viewport():
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.wheelEvent(event)  # 手动执行缩放事件
                return True  # 让qt忽略事件
        return super(NetworkImageViewer, self).eventFilter(source, event)  # 否则照常处理事件

    def closeEvent(self, e):
        self.closed.emit()
        e.accept()

    def mousePressEvent(self, a0):
        self.start_pos = a0.pos()

    def mouseMoveEvent(self, a0):
        if a0.buttons() and Qt.MouseButton.LeftButton and self.downloadOk:
            distance = (a0.pos() - self.start_pos).manhattanLength()
            temp_name = '{0}/{1}'.format(os.getenv('temp'), 'view_pic.jpg')
            if distance >= QApplication.startDragDistance():
                self.isDraging = True
                self.reset_title()
                if not self.originalImage.isNull():
                    self.originalImage.save(temp_name)
                mime_data = QMimeData()
                url = QUrl()
                url.setUrl("file:///" + temp_name)
                mime_data.setUrls((url,))

                drag = QDrag(self)
                drag.setMimeData(mime_data)
                drag.setHotSpot(a0.pos())
                drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction | Qt.DropAction.LinkAction,
                          Qt.DropAction.CopyAction)
                self.isDraging = False
                self.reset_title()

    def destroyEvent(self):
        try:
            self.show_movie.stop()
            del self.originalImage
            self.destroy()
            self.deleteLater()
            gc.collect()
        except:
            pass

    def init_menu(self):
        menu = QMenu(self)

        transform_left = QAction('顺时针旋转 90 度', self)
        transform_left.triggered.connect(self.transform_image_left)
        menu.addAction(transform_left)
        transform_right = QAction('逆时针旋转 90 度', self)
        transform_right.triggered.connect(self.transform_image_right)
        menu.addAction(transform_right)
        reset_pixmap = QAction('复原图片', self)
        reset_pixmap.triggered.connect(self.reset_image)
        menu.addAction(reset_pixmap)

        self.pushButton_2.setMenu(menu)

        share_menu = QMenu(self)

        copyto = QAction('复制', self)
        copyto.triggered.connect(lambda: QApplication.clipboard().setPixmap(QPixmap.fromImage(self.originalImage)))
        share_menu.addAction(copyto)

        save = QAction('保存', self)
        save.triggered.connect(self.save_file)
        share_menu.addAction(save)

        self.pushButton_4.setMenu(share_menu)

    def transform_image_left(self):
        self.round_angle += 90
        self.resize_image()

    def transform_image_right(self):
        self.round_angle += -90
        self.resize_image()

    def reset_image(self):
        self.round_angle = 0
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
        if append_text:
            self.setWindowTitle(f'{append_text} - 图片查看器')
        else:
            self.setWindowTitle('图片查看器')

    def _resizeslot(self, pixmap):
        self.label.setPixmap(pixmap)
        self.scrollAreaWidgetContents.setMinimumSize(pixmap.width(), pixmap.height())
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
                    if self.originalImage.loadFromData(response.content):
                        success_flag = True
            except Exception as e:
                print(type(e))
                print(e)
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
        path, tpe = QFileDialog.getSaveFileName(self, '保存图片', '',
                                                'JPG 图片文件 (*.jpg;*.jpeg)')
        if path:
            try:
                if not self.originalImage.isNull():
                    self.originalImage.save(path)
            except Exception as e:
                QMessageBox.critical(self, '文件保存失败', str(e), QMessageBox.StandardButton.Ok)
            else:
                QMessageBox.information(self, '提示', '文件保存成功。', QMessageBox.StandardButton.Ok)

    def update_download_state(self, f):
        self.show_movie.stop()
        if not f:
            self.label.setText('图片加载失败，请重新打开图片窗口以重新加载。')
        else:
            self.downloadOk = True
            self.pushButton_4.setEnabled(True)
            self.pushButton_2.setEnabled(True)
            self.spinBox.setEnabled(True)

    def load_image(self):
        self.setWindowTitle(f'[加载中...] - 图片查看器')

        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(100, 100))
        self.show_movie.frameChanged.connect(lambda: self.label.setPixmap(self.show_movie.currentPixmap()))

        self.resize_image()
        self.show_movie.start()
