from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QFileDialog

from consts import datapath
from publics import webview2
from publics import profile_mgr
from publics.funcs import start_background_thread, http_downloader, format_second
from ui import thread_video_item


class ThreadVideoItem(QWidget, thread_video_item.Ui_Form):
    """嵌入在列表的视频贴入口组件"""
    source_link = ''
    length = 0
    view_num = 0
    webview = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.webview_show_html = profile_mgr.video_webview_show_html
        self.pushButton_3.hide()

        self.pushButton.clicked.connect(self.save_video)
        self.pushButton_2.clicked.connect(self.play_video)
        self.pushButton_3.clicked.connect(self.destroy_webview)

    def handle_webview_fullscreen(self):
        if self.webview.isHtmlInFullScreenState():
            self.webview.showFullScreen()
        else:
            self.webview.showNormal()

    def destroy_webview(self):
        self.webview.close()
        self.pushButton_3.hide()
        self.webview.destroyWebview()
        self.webview = None

    def play_video(self):
        if self.webview:
            self.webview.show()
            self.webview.raise_()
            if self.webview.isMinimized():
                self.webview.showNormal()
            if not self.webview.isActiveWindow():
                self.webview.activateWindow()
        else:
            self.webview = webview2.QWebView2View()

            self.webview.resize(920, 530)
            self.webview.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
            self.webview.setWindowTitle('WebView 视频播放器')

            self.webview.titleChanged.connect(self.webview.setWindowTitle)
            self.webview.fullScreenRequested.connect(self.handle_webview_fullscreen)
            self.webview.windowCloseRequested.connect(self.destroy_webview)
            self.webview.renderInitializationCompleted.connect(self.pushButton_3.show)
            self.webview.renderInitializationCompleted.connect(lambda: self.webview.setHtml(self.webview_show_html))

            profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}',
                                              enable_link_hover_text=False,
                                              enable_zoom_factor=False, enable_error_page=True,
                                              enable_context_menu=True, enable_keyboard_keys=True,
                                              handle_newtab_byuser=False, disable_web_safe=True)
            self.webview.setProfile(profile)

            self.webview.initRender()
            self.webview.show()

    def save_video(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择视频保存位置', '', '视频文件 (*.mp4)')
        if path:
            right_link = self.source_link.replace('tb-video.bdstatic.com', 'bos.nj.bpc.baidu.com')
            start_background_thread(http_downloader, (path, right_link))

    def setdatas(self, src, len_, views):
        self.source_link = src
        self.length = len_
        self.view_num = views
        right_link = self.source_link.replace('tb-video.bdstatic.com', 'bos.nj.bpc.baidu.com')
        self.webview_show_html = self.webview_show_html.replace('[vurl]', right_link)

        self.label_3.setText(f'时长 {format_second(len_)}，浏览量 {views}')
