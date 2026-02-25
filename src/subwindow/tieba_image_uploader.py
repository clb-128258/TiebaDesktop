"""贴吧图片上传相关类"""
import gc
import hashlib
import queue
import requests
import threading
import time

from PyQt5.QtCore import Qt, pyqtSignal, QByteArray, QBuffer, QIODevice, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPixmapCache, QMovie, QImage
from PyQt5.QtWidgets import QDialog, QFileDialog, QApplication, QMenu, QAction, QMessageBox

from publics import request_mgr, top_toast_widget, funcs, profile_mgr, app_logger, qt_image
from ui import tb_image_uploader


class UploadedImage:
    """已经被上传到贴吧服务器的图片"""

    def __init__(self, image_id: str, origin_width: int, origin_height: int, origin_json_info: dict):
        self.image_id = image_id
        self.origin_width = origin_width
        self.origin_height = origin_height
        self.origin_json_info = origin_json_info

        self.status_code = int(origin_json_info['error_code'])
        self.is_succeed = self.status_code == 0

    def __del__(self):
        self.clear_datas()

    def clear_datas(self):
        del self.image_id
        del self.origin_width
        del self.origin_height
        del self.origin_json_info
        del self.status_code
        del self.is_succeed
        gc.collect()


class WillUploadImage:
    """将被上传的图片类"""

    def __init__(self, image_data: bytes = b''):
        self.image_binary = None
        self.image_pixmap = None
        self.origin_width = None
        self.origin_height = None
        self.image_md5 = None
        self.image_load_error_info = ''

        if image_data:
            self.load_datas(image_data)

    def __del__(self):
        self.clear_datas()

    def clear_datas(self):
        del self.image_binary
        del self.image_pixmap
        del self.image_md5
        del self.origin_width
        del self.origin_height
        del self.image_load_error_info

        QPixmapCache.clear()
        gc.collect()

        self.image_binary = None
        self.image_pixmap = None
        self.origin_width = None
        self.origin_height = None
        self.image_md5 = None
        self.image_load_error_info = ''

    def load_datas(self, image_data: bytes):
        self.image_binary = image_data
        self._load_pixmap()
        self._calc_md5()

    def _calc_md5(self):
        self.image_md5 = hashlib.md5(self.image_binary).hexdigest()

    def _load_pixmap(self):
        self.image_pixmap = QPixmap()
        self.image_pixmap.loadFromData(self.image_binary)
        self.origin_height = self.image_pixmap.height()
        self.origin_width = self.image_pixmap.width()

        self.image_pixmap = qt_image.add_cover_radius_angle_for_pixmap(self.image_pixmap, 500, 500)


class TiebaImageUploader(QDialog, tb_image_uploader.Ui_Dialog):
    imageLoaded = pyqtSignal(WillUploadImage)
    uploadStateUpdated = pyqtSignal(str)
    uploadFinished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setAcceptDrops(True)

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton.setIcon(QIcon('ui/arrow_back_white.png'))
        self.pushButton_3.setIcon(QIcon('ui/arrow_forward_white.png'))
        self.pushButton_3.setIconSize(QSize(25, 25))
        self.pushButton.setIconSize(QSize(25, 25))

        self.init_ui_elements()
        self.init_add_image_menu()

        self.imageLoaded.connect(self._on_image_loaded)
        self.pushButton_10.clicked.connect(lambda: self.delete_image())
        self.pushButton_5.clicked.connect(self.close)
        self.pushButton.clicked.connect(self.switch_prev_image)
        self.pushButton_4.clicked.connect(self.upload_images_async)
        self.pushButton_3.clicked.connect(self.switch_next_image)
        self.uploadStateUpdated.connect(lambda text: self.loading_widget.set_caption(True, text))
        self.uploadFinished.connect(self._on_image_uploaded)

        self.image_list = []
        self.uploaded_image_list = []
        self.current_image_index = -1
        self.is_uploading = False

    def closeEvent(self, a0):
        def run_close():
            self.show_movie.stop()
            self.show_movie.deleteLater()
            self.image_list.clear()
            a0.accept()

        if self.is_uploading:
            a0.ignore()
        elif not self.image_list or self.uploaded_image_list:
            run_close()
        elif QMessageBox.warning(self, '警告', '确认要取消图片上传吗？你在此所做的任何更改都将不会保存。',
                                 QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            run_close()
        else:
            a0.ignore()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()
        elif a0.modifiers() == Qt.KeyboardModifier.ControlModifier and a0.key() == Qt.Key.Key_V:
            self.add_image(from_cb=True)

    def dragEnterEvent(self, a0):
        def ignore():
            a0.setDropAction(Qt.DropAction.IgnoreAction)
            a0.ignore()

        def accept():
            a0.setDropAction(Qt.DropAction.CopyAction)
            a0.accept()

        if a0.mimeData().hasUrls():
            flag = True
            for url in a0.mimeData().urls():
                if not url.toLocalFile().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    flag = False
                    break

            accept() if flag else ignore()
        else:
            ignore()

    def dropEvent(self, a0):
        a0.accept()

        file_list = list(url.toLocalFile() for url in a0.mimeData().urls())
        self.add_image(filelist=file_list)

    def init_ui_elements(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

        self.loading_widget = funcs.LoadingFlashWidget()
        self.loading_widget.cover_widget(self)
        self.loading_widget.hide()

        self.show_movie = QMovie('ui/upload.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(270, 190))
        self.show_movie.frameChanged.connect(lambda: self.label_5.setPixmap(self.show_movie.currentPixmap()))

    def init_add_image_menu(self):
        menu = QMenu(self)

        from_file = QAction('从本地文件上传', self)
        from_file.triggered.connect(self.ask_add_image)
        menu.addAction(from_file)

        from_cb = QAction('从剪切板获取', self)
        from_cb.triggered.connect(lambda: self.add_image(from_cb=True))
        menu.addAction(from_cb)

        self.pushButton_8.setMenu(menu)

    def delete_image(self, index=-1):
        index = index if index != -1 else self.current_image_index
        del self.image_list[index]

        if index <= self.current_image_index:
            self.switch_image(self.current_image_index - 1)

    def switch_next_image(self):
        if self.current_image_index == len(self.image_list) - 1:
            self.switch_image(0)
        else:
            self.switch_image(self.current_image_index + 1)

    def switch_prev_image(self):
        if self.current_image_index == 0:
            self.switch_image(len(self.image_list) - 1)
        else:
            self.switch_image(self.current_image_index - 1)

    def switch_image(self, index=-1):
        image_num = len(self.image_list)
        is_list_empty = image_num == 0
        if self.current_image_index == -1 and not is_list_empty:
            self.current_image_index = 0
        if is_list_empty:
            self.current_image_index = -1

        index = index if index != -1 else self.current_image_index

        if self.current_image_index != -1:
            image = self.image_list[index]
            self.current_image_index = index
            self.label.setPixmap(image.image_pixmap)
        self.update_image_list_state()

    def update_image_list_state(self):
        image_num = len(self.image_list)
        is_list_empty = image_num == 0

        self.label_4.setText(f'第 {self.current_image_index + 1} 张，共 {image_num} 张')
        self.pushButton_4.setEnabled(not is_list_empty)
        self.pushButton_10.setEnabled(not is_list_empty)
        self.pushButton.setVisible(not is_list_empty)
        self.pushButton_3.setVisible(not is_list_empty)

        if is_list_empty:
            self.label.hide()
            self.label.clear()
            self.frame_2.show()
            self.setWindowTitle('上传图片')
            self.show_movie.start()
        else:
            self.frame_2.hide()
            self.label.show()
            self.setWindowTitle(f'[{self.current_image_index + 1}/{image_num}] 上传图片')
            self.show_movie.stop()

    def _on_image_loaded(self, image):
        if image.image_load_error_info:
            msg = top_toast_widget.ToastMessage(image.image_load_error_info,
                                                icon_type=top_toast_widget.ToastIconType.ERROR)
            self.top_toaster.showToast(msg)
        else:
            self.image_list.append(image)

        self.update_image_list_state()
        if self.current_image_index == -1:
            self.switch_image()

    def add_image(self, filelist=None, from_qimage: QImage = None, from_cb=False):
        """
        向图片选择器添加一个图片，支持从本地文件、QImage 对象、剪切板加载图像

        Args:
            filelist (list[str]): 本地文件路径列表
            from_qimage (QImage): 直接要加载的 QImage 对象
            from_cb (bool): 是否从剪切板获取图片对象

        Notes:
            本方法一次只能加载一种来源的图片，每次调用此方法时应当只提供一种图片来源\n
            三种加载来源的优先级为: 本地文件 > QImage 对象 > 剪切板
        """
        if filelist:
            for i in filelist:
                funcs.start_background_thread(self.add_image_from_file, args=(i,))
        elif from_qimage:
            funcs.start_background_thread(self.add_image_from_qimage, args=(from_qimage,))
        elif from_cb:
            funcs.start_background_thread(self.add_image_from_cb)

    def check_duplicated(self, image):
        for i in self.image_list:
            if i.image_md5 == image.image_md5:
                return True

        return False

    def add_image_from_file(self, image_path):
        image_obj = WillUploadImage()
        try:
            with open(image_path, 'rb') as file:
                file_data = file.read()
                image_obj.load_datas(file_data)

            if self.check_duplicated(image_obj):  # 检测到重复
                image_obj.clear_datas()
                image_obj.image_load_error_info = '已上传过相同的图片，请勿重复上传'
        except Exception as e:
            app_logger.log_exception(e)
            image_obj.clear_datas()
            image_obj.image_load_error_info = funcs.get_exception_string(e)
        finally:
            self.imageLoaded.emit(image_obj)

    def add_image_from_qimage(self, qimage_obj):
        image_obj = WillUploadImage()
        try:
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.WriteOnly)

            qimage_obj.save(buffer, 'PNG')
            binary_data = byte_array.data()
            image_obj.load_datas(binary_data)

            if self.check_duplicated(image_obj):  # 检测到重复
                image_obj.clear_datas()
                image_obj.image_load_error_info = '已上传过相同的图片，请勿重复上传'
        except Exception as e:
            app_logger.log_exception(e)
            image_obj.clear_datas()
            image_obj.image_load_error_info = funcs.get_exception_string(e)
        finally:
            self.imageLoaded.emit(image_obj)

    def add_image_from_cb(self):
        def show_no_image_msg():
            image_obj = WillUploadImage()
            image_obj.image_load_error_info = '剪切板中没有任何图片'
            self.imageLoaded.emit(image_obj)

        clipboard = QApplication.clipboard()
        if clipboard.mimeData().hasImage():
            image = clipboard.image()
            self.add_image_from_qimage(image)
        elif clipboard.mimeData().hasUrls():
            file_list = list(url.toLocalFile() for url in clipboard.mimeData().urls())
            contain_flag = False
            for path in file_list:
                if path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    self.add_image_from_file(path)
                    contain_flag = True

            if not contain_flag:
                show_no_image_msg()
        else:
            show_no_image_msg()

    def ask_add_image(self, parent_window=None):
        parent_window = parent_window if parent_window else self

        file_list, file_type = QFileDialog.getOpenFileNames(parent_window, '选择图片', '',
                                                            '所有受支持格式 (*.png;*.jpg;*.jpeg;*.gif;*.webp);;'
                                                            'PNG 图片 (*.png);;'
                                                            'JPEG 图片 (*.jpg;*.jpeg);;'
                                                            'GIF 图片 (*.gif);;'
                                                            'WebP 图像 (*.webp)')

        if file_list:
            self.add_image(file_list)

        return bool(file_list)

    def _on_image_uploaded(self, msg):
        self.is_uploading = False
        if msg:
            self.loading_widget.hide()
            msg = top_toast_widget.ToastMessage(msg,
                                                icon_type=top_toast_widget.ToastIconType.ERROR)
            self.top_toaster.showToast(msg)
        else:
            self.close()

    def upload_images_async(self):
        self.is_uploading = True
        self.loading_widget.set_caption(caption='正在上传图片...')
        self.loading_widget.show()
        funcs.start_background_thread(self.upload_images)

    def upload_single_img(self, image: WillUploadImage, process_queue: queue.Queue):
        payloads = {
            "BDUSS": profile_mgr.current_bduss,
            "_client_type": "2",
            "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
            "alt": "json",
            "chunkNo": "1",
            "groupId": "1",
            "height": str(image.origin_height),
            "isFinish": "1",
            "is_bjh": "0",
            "resourceId": image.image_md5.upper(),
            "saveOrigin": "1",
            "stoken": profile_mgr.current_stoken,
            "support_image": "jepgwebp",
            "width": str(image.origin_width)
        }
        data = {
            'chunk': (f'image_{image.image_md5}', image.image_binary)
        }

        session = requests.Session()
        session.trust_env = True
        response = session.post(f'{request_mgr.SCHEME_HTTP}{request_mgr.TIEBA_APP_HOST}/c/s/uploadPicture',
                                headers=request_mgr.header_android,
                                data=payloads,
                                files=data)
        response.close()
        session.close()
        response.raise_for_status()

        jsonify = response.json()
        uploaded_obj = UploadedImage(jsonify.get('picId', ''), image.origin_width, image.origin_height, jsonify)
        process_queue.put(uploaded_obj)

        return uploaded_obj

    def upload_images(self):
        max_running_thread_num = 7
        process_queue = queue.Queue()
        thread_pool = []
        total_num = len(self.image_list)

        def update_ui_text(finish_num):
            self.uploadStateUpdated.emit(f'正在上传图片 (已完成 {finish_num} / 总数 {total_num})...')

        def process_queue_looper():
            finish_num = 0
            fail_num = 0

            update_ui_text(finish_num)
            while finish_num != total_num:
                if not process_queue.empty():
                    image = process_queue.get()

                    self.uploaded_image_list.append(image)
                    finish_num += 1
                    fail_num += (1 if not image.is_succeed else 0)

                    update_ui_text(finish_num)
                else:
                    time.sleep(0.01)
            else:
                upload_resp_text = '' if fail_num == 0 else f'有 {fail_num} 张图片上传失败，请重新上传'
                if not upload_resp_text:
                    self.uploadStateUpdated.emit('图片全部上传成功，窗口即将关闭...')
                    time.sleep(1)

                self.uploadFinished.emit(upload_resp_text)

        def wait_threads():
            running_thread_pool = []

            def wait_running_threads(wait_for_all=False):
                # 等待当前线程全部执行完成
                while running_thread_pool:
                    running_thread_pool[0].join()
                    running_thread_pool.pop(0)
                    if len(running_thread_pool) < max_running_thread_num and not wait_for_all:
                        break

            for thread in thread_pool:
                if len(running_thread_pool) < max_running_thread_num:  # 在线程池空余时
                    thread.start()
                    running_thread_pool.append(thread)
                elif len(running_thread_pool) >= max_running_thread_num:  # 在当前运行线程数达到上限时
                    # 先等待一个可用的线程位
                    wait_running_threads()

                    # 等待完后再新增线程
                    thread.start()
                    running_thread_pool.append(thread)

            wait_running_threads(wait_for_all=True)  # 等待最后启动的线程

        for img in self.image_list:
            thread = threading.Thread(target=self.upload_single_img, args=(img, process_queue), daemon=True)
            thread_pool.append(thread)

        funcs.start_background_thread(wait_threads)
        process_queue_looper()

    def exec_window(self):
        self.update_image_list_state()
        self.exec()
        return self.uploaded_image_list
