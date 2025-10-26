import asyncio

import aiotieba
import yarl
from PyQt5.QtCore import Qt, QPoint, QSize, QByteArray, QTimer
from PyQt5.QtGui import QIcon, QMovie
from PyQt5.QtWidgets import QWidget, QMenu, QAction

from consts import datapath
from publics import webview2, profile_mgr, qt_window_mgr
from publics.funcs import open_url_in_browser, cut_string

from ui import tb_browser


class TiebaWebBrowser(QWidget, tb_browser.Ui_Form):
    """贴吧页面内置浏览器"""
    menu = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.toolButton.setIcon(QIcon('ui/back.png'))
        self.toolButton_2.setIcon(QIcon('ui/forward.png'))
        self.toolButton_3.setIcon(QIcon('ui/refresh.png'))
        self.toolButton_5.setIcon(QIcon('ui/os_browser.png'))
        self.toolButton_6.setIcon(QIcon('ui/jumpto.png'))
        self.toolButton_4.setIcon(QIcon('ui/download.png'))

        self.default_profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}',
                                                       enable_link_hover_text=False,
                                                       enable_zoom_factor=True, enable_error_page=True,
                                                       enable_context_menu=True, enable_keyboard_keys=True,
                                                       handle_newtab_byuser=True)

        self.tabWidget.tabCloseRequested.connect(self.remove_widget)
        self.tabWidget.currentChanged.connect(self.on_tab_changed)
        self.lineEdit.returnPressed.connect(self.load_new_page)
        self.toolButton.clicked.connect(self.button_back)
        self.toolButton_2.clicked.connect(self.button_forward)
        self.toolButton_3.clicked.connect(self.button_refresh)
        self.toolButton_5.clicked.connect(self.button_os_browser)
        self.toolButton_6.clicked.connect(self.button_open_client)
        self.toolButton_4.clicked.connect(self.button_open_downloads)

    def closeEvent(self, a0):
        a0.accept()
        while self.tabWidget.count() != 0:
            self.remove_widget(0)
        qt_window_mgr.del_window(self)

    def keyPressEvent(self, a0):
        if a0.modifiers() == Qt.ControlModifier and a0.key() == Qt.Key_W:
            self.remove_widget(self.tabWidget.currentIndex())

    def parse_weburl_to_tburl(self):
        tb_url = ''
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            if widget.isRenderInitOk():
                url = widget.url()
                tb_thread_urls = ('http://tieba.baidu.com/p/', 'https://tieba.baidu.com/p/',)
                tb_forum_urls = ('http://tieba.baidu.com/f', 'https://tieba.baidu.com/f',)
                tb_homepage_urls = ('http://tieba.baidu.com/home/', 'https://tieba.baidu.com/home/')
                if url.startswith(tb_thread_urls):
                    thread_id = url.split('?')[0].split('/')[-1]
                    tb_url = f'tieba_thread://{thread_id}'
                elif url.startswith(tb_forum_urls):
                    forum_name = yarl.URL(url).query['kw']
                    tb_url = f'tieba_forum_namely://{forum_name}'
                elif url.startswith(tb_homepage_urls):
                    portrait = yarl.URL(url).query.get('id')
                    if portrait:
                        tb_url = f'user://{portrait}'

        return tb_url

    def button_back(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.back()

    def button_forward(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.forward()

    def button_refresh(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.reload()

    def button_os_browser(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            open_url_in_browser(widget.url(), True)

    def button_open_client(self):
        tieba_url = self.parse_weburl_to_tburl()
        if tieba_url:
            open_url_in_browser(tieba_url)

    def button_open_downloads(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            widget.openDefaultDownloadDialog()

    def load_new_page(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            url = self.lineEdit.text()
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            widget.load(url)

    def on_tab_changed(self):
        self.reset_url_text()
        self.reset_main_title()
        self.reset_client_button_visitable()

    def reset_client_button_visitable(self):
        tieba_url = self.parse_weburl_to_tburl()
        if tieba_url:
            self.toolButton_6.show()
        else:
            self.toolButton_6.hide()

    def reset_main_title(self):
        widget = self.tabWidget.currentWidget()
        if widget:
            self.setWindowIcon(widget.windowIcon())
            self.setWindowTitle(cut_string(widget.windowTitle(), 20) + ' - 贴吧桌面')

    def reset_url_text(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View):
            self.lineEdit.setText(widget.url())
        else:
            self.lineEdit.setText('')

    def handle_fullscreen(self, is_fullscreen):
        if is_fullscreen:
            self.showFullScreen()
            self.frame.hide()
            self.tabWidget.tabBar().hide()
        else:
            self.showNormal()
            self.frame.show()
            self.tabWidget.tabBar().show()

    def add_new_page(self, url):
        def stop_ani():
            webview.show_movie.stop()
            webview.setWindowIcon(webview.icon())
            webview.setWindowTitle(webview.title())

        webview2.loadLibs()

        webview = webview2.QWebView2View()
        webview.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        webview.setWindowTitle('正在加载...')

        webview.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        webview.show_movie.setScaledSize(QSize(50, 50))
        webview.show_movie.frameChanged.connect(
            lambda: webview.setWindowIcon(QIcon(webview.show_movie.currentPixmap())))

        webview.titleChanged.connect(webview.setWindowTitle)
        webview.iconChanged.connect(webview.setWindowIcon)
        webview.fullScreenRequested.connect(self.handle_fullscreen)
        webview.windowCloseRequested.connect(lambda: self.remove_widget(self.tabWidget.indexOf(webview)))
        webview.newtabSignal.connect(self.add_new_page)
        webview.loadStarted.connect(webview.show_movie.start)
        webview.loadStarted.connect(lambda: webview.setWindowTitle('正在加载...'))
        webview.loadFinished.connect(stop_ani)
        webview.urlChanged.connect(self.reset_url_text)
        webview.urlChanged.connect(self.reset_client_button_visitable)
        webview.setProfile(self.default_profile)
        webview.loadAfterRender(url)

        self.add_new_widget(webview)
        webview.initRender()

    def add_new_widget(self, widget: QWidget):
        self.tabWidget.addTab(widget, widget.windowIcon(), widget.windowTitle())
        widget.windowIconChanged.connect(lambda icon: self.tabWidget.setTabIcon(self.tabWidget.indexOf(widget), icon))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabText(self.tabWidget.indexOf(widget), cut_string(title, 20)))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabToolTip(self.tabWidget.indexOf(widget), title))
        widget.windowIconChanged.connect(self.reset_main_title)
        widget.windowTitleChanged.connect(self.reset_main_title)

        self.tabWidget.setCurrentWidget(widget)

    def remove_widget(self, index: int):
        widget = self.tabWidget.widget(index)
        self.tabWidget.removeTab(index)
        if isinstance(widget, webview2.QWebView2View):
            widget.destroyWebview()
            widget.show_movie.stop()
        widget.deleteLater()
        del widget

        if self.tabWidget.count() == 0:
            self.close()
