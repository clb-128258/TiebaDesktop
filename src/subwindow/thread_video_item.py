from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFileDialog

import consts
from publics.funcs import start_background_thread, http_downloader, format_second, large_num_to_string, \
    open_url_in_browser
from publics import qt_image, webview2, profile_mgr, funcs
from subwindow import base_ui
from ui import thread_video_item
import base64
import os


class VideoWebView(webview2.QWebView2View):
    def __init__(self, parent):
        super().__init__()
        self.setParent(parent)
        self.parent_window = parent

        self.loading_widget = funcs.LoadingFlashWidget(caption='视频正在赶来的路上...')
        self.loading_widget.cover_widget(self)

        self.webview_profile = webview2.WebViewProfile(
            data_folder=f'{consts.datapath}/webview_data/{profile_mgr.current_uid}',
            enable_transparent_bg=True,
            enable_zoom_factor=False,
            enable_error_page=False,
            enable_context_menu=False,
            enable_keyboard_keys=False,
            enable_link_hover_text=False,
            user_agent=f'[default_ua] CLBTiebaDesktop/{consts.APP_VERSION_STR}', )

        self.titleChanged.connect(self.setWindowTitle)
        self.iconChanged.connect(self.setWindowIcon)
        self.loadStarted.connect(self.loading_widget.show)
        self.loadFinished.connect(self.loading_widget.hide)
        self.fullScreenRequested.connect(self.on_webview_into_fullscreen)

    def closeEvent(self, a0):
        a0.ignore()

        # 在全屏模式下调用js执行退出全屏
        if self.isWindow():
            self.runJavaScriptAsync('window.videoPlayer.exitFullscreen();')

    def init_video_render(self, url):
        self.loadAfterRender(url)
        self.setProfile(self.webview_profile)

        self.initRender()
        self.loading_widget.show()
        self.show()

    def on_webview_into_fullscreen(self):
        if self.isHtmlInFullScreenState():
            self.setParent(None)  # 不显示在父组件里
            self.showFullScreen()  # 全屏显示
        else:
            self.show_in_parent()

    def show_in_parent(self):
        self.setParent(self.parent_window)  # 重新回到父组件
        self.setGeometry(0, 0, self.parent_window.width(), self.parent_window.height())
        self.show()


class ThreadVideoItem(base_ui.WindowBaseQWidget, thread_video_item.Ui_Form):
    """嵌入在列表的视频贴入口组件"""
    source_link = ''
    cover_link = ''
    source_link_b64 = ''
    cover_link_b64 = ''
    webview_player_link = ''
    length = 0
    view_num = 0

    webview = None
    is_webview_alive = False  # webview是否对用户展示

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.toolButton_2.setIcon(QIcon(f'ui/icon_white/play_arrow.png'))
        self.toolButton.setIcon(QIcon(f'ui/icon_white/download.png'))
        self.toolButton_3.setIcon(QIcon(f'ui/icon_white/jumpto.png'))
        self.setFixedHeight(500)

        self.toolButton.clicked.connect(self.save_video)
        self.toolButton_3.clicked.connect(self.play_video_in_browser)
        self.toolButton_2.clicked.connect(self.start_video_webview)

        self.cover_img = qt_image.MultipleImage()
        self.cover_img.imageLoadSucceed.connect(self.set_cover_pixmap)

        self.destroyed.connect(self.on_destroyed)

    def on_destroyed(self):
        self.label.clear()
        self.cover_img.destroyImage()

        if self.webview:
            self.webview.hide()

            # 清理内存
            self.webview.destroyWebviewUntilComplete()
            self.webview.destroy()
            self.webview.deleteLater()

    def resizeEvent(self, a0):
        self.move_widgets()

    def set_cover_pixmap(self):
        if not self.cover_img.isImageLoaded():
            return

        original_pixmap = self.cover_img.currentPixmap().scaled(self.width(), self.height(),
                                                                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rect = QRect(
            int((original_pixmap.width() - self.width()) / 2),
            int((original_pixmap.height() - self.height()) / 2),
            self.width(),
            self.height(),
        )

        original_pixmap = original_pixmap.copy(rect)
        resized_pixmap = qt_image.add_cover_radius_angle_for_pixmap(original_pixmap)

        del original_pixmap
        self.label.clear()
        self.label.setPixmap(resized_pixmap)

    def move_widgets(self):
        if self.is_webview_alive:
            self.webview.setGeometry(0, 0, self.width(), self.height())
        else:
            move_value = 5

            self.frame.adjustSize()
            self.label.setGeometry(0, 0, self.width(), self.height())
            self.toolButton_2.move(int((self.width() - self.toolButton_2.width()) / 2),
                                   int((self.height() - self.toolButton_2.height()) / 2))
            self.frame.move(self.width() - move_value - self.frame.width(),
                            self.height() - move_value - self.frame.height())

            self.set_cover_pixmap()

    def play_video_in_browser(self):
        open_url_in_browser(self.webview_player_link)

    def on_webview_into_fullscreen(self, fullscreen):
        if not fullscreen:
            # 在退出全屏时回到窗口
            window = self.window()

            window.showNormal()
            window.raise_()
            if not window.isActiveWindow():
                window.activateWindow()

        self.is_webview_alive = not fullscreen
        self.move_widgets()

    def on_webview_crashed(self):
        self.is_webview_alive = False

        self.webview.hide()
        self.frame.show()
        self.toolButton_2.show()
        self.move_widgets()

    def on_webview_alive(self, success):
        if success:
            self.is_webview_alive = True

            self.frame.hide()
            self.toolButton_2.hide()
            self.move_widgets()
        else:
            self.on_webview_crashed()

    def start_video_webview(self):
        if os.name != 'nt':
            return

        if self.webview:
            self.webview.show()
            self.webview.reload()
        else:
            self.webview = VideoWebView(self)
            self.webview.loadFinished.connect(self.on_webview_alive)
            self.webview.renderProcessTerminated.connect(self.on_webview_crashed)
            self.webview.fullScreenRequested.connect(self.on_webview_into_fullscreen)

            self.webview.setGeometry(0, 0, self.width(), self.height())
            self.webview.init_video_render(self.webview_player_link)

        self.frame.hide()
        self.toolButton_2.hide()

    def save_video(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择视频保存位置', '', '视频文件 (*.mp4)')
        if path:
            start_background_thread(http_downloader, (path, self.source_link))

    def setdatas(self, src, len_, views, cover_src):
        self.source_link = src.replace('http://', 'https://')  # 启用https
        self.cover_link = cover_src.replace('http://', 'https://')
        self.source_link_b64 = base64.b64encode(self.source_link.encode()).decode()
        self.cover_link_b64 = base64.b64encode(self.cover_link.encode()).decode()
        self.webview_player_link = f'https://clb.tiebadesktop.localpage.jsplayer/video_play_main.html?url_b64={self.source_link_b64}&cover_b64={self.cover_link_b64}'

        self.length = len_
        self.view_num = views
        self.label_3.setText(f'{format_second(len_)} | {large_num_to_string(views, endspace=True)}浏览')

        self.cover_img.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                    cover_src,
                                    coverType=qt_image.ImageCoverType.NoCover)
        self.cover_img.loadImage()

        self.move_widgets()
        self.adjustSize()
