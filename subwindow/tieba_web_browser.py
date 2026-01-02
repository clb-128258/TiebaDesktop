import yarl
import json
from PyQt5.QtCore import Qt, QSize, QByteArray
from PyQt5.QtGui import QIcon, QMovie
from PyQt5.QtWidgets import QWidget
from consts import datapath
from publics import webview2, profile_mgr, qt_window_mgr, cache_mgr, top_toast_widget, logging
from publics.funcs import open_url_in_browser, cut_string, start_background_thread

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
                                                       handle_newtab_byuser=True, disable_web_safe=True)

        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

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
        if isinstance(widget, ExtWebView2):
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
        if isinstance(widget, ExtWebView2):
            widget.back()

    def button_forward(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
            widget.forward()

    def button_refresh(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
            widget.reload()

    def button_os_browser(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
            open_url_in_browser(widget.url(), True)

    def button_open_client(self):
        tieba_url = self.parse_weburl_to_tburl()
        if tieba_url:
            open_url_in_browser(tieba_url)

    def button_open_downloads(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
            widget.openDefaultDownloadDialog()

    def load_new_page(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
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
        if isinstance(widget, ExtWebView2):
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
        webview = ExtWebView2(self.default_profile, url)
        webview.bind_to_tab_container(self)
        webview.initRender()
        self.add_new_widget(webview)

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
        if isinstance(widget, ExtWebView2):
            widget.destroyWebview()
            widget.show_movie.stop()
        widget.deleteLater()
        del widget

        if self.tabWidget.count() == 0:
            self.close()


class ExtWebView2(webview2.QWebView2View):
    """经过重写的webview2"""

    def __init__(self, profile: webview2.WebViewProfile, url: str):
        super().__init__()

        self.tab_container = None

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowTitle('正在加载...')

        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(50, 50))
        self.show_movie.frameChanged.connect(
            lambda: self.setWindowIcon(QIcon(self.show_movie.currentPixmap())))

        self.titleChanged.connect(self.setWindowTitle)
        self.iconChanged.connect(self.setWindowIcon)

        self.loadStarted.connect(self.start_ani)
        self.loadFinished.connect(self.stop_ani)
        self.jsBridgeReceived.connect(self.parse_js_msg)

        self.setProfile(profile)
        self.loadAfterRender(url)

    def parse_js_msg(self, jsonify_text):
        logging.log_INFO(f'received text from jsbridge: {jsonify_text}')

        json_data = json.loads(jsonify_text)
        if json_data['type'] == 'topToast':
            toast_msg = top_toast_widget.ToastMessage(json_data['argDatas']['text'], json_data['argDatas']['duration'],
                                                      json_data['argDatas']['iconType'])
            self.show_toast_to_parent(toast_msg)
        elif json_data['type'] == 'closePage':
            if self.tab_container:
                self.tab_container.remove_widget(self.tab_container.tabWidget.indexOf(self))

    def show_toast_to_parent(self, msg):
        if self.tab_container:
            self.tab_container.top_toaster.showToast(msg)

    def record_history(self, icon_url, title, url):
        if url:
            if icon_url and not icon_url.startswith(
                    ('http://clb.tiebadesktop.localpage', 'https://clb.tiebadesktop.localpage')):
                md5 = cache_mgr.save_md5_ico(icon_url)
            else:
                md5 = ''
            profile_mgr.add_view_history(4, {"web_icon_md5": md5, "web_title": title, "web_url": url})

    def start_ani(self):
        self.show_movie.start()
        self.setWindowTitle('正在加载...')

    def stop_ani(self, isok):
        self.show_movie.stop()
        self.setWindowIcon(self.icon())
        self.setWindowTitle(self.title())

        if isok:
            start_background_thread(self.record_history, (self.iconUrl(), self.title(), self.url()))
        else:
            start_background_thread(self.record_history, ('', self.url(), self.url()))

    def bind_to_tab_container(self, tc: TiebaWebBrowser):
        try:
            self.fullScreenRequested.disconnect()
            self.windowCloseRequested.disconnect()
            self.newtabSignal.connect.disconnect()
            self.urlChanged.connect.disconnect()
        except TypeError:
            pass

        self.fullScreenRequested.connect(tc.handle_fullscreen)
        self.windowCloseRequested.connect(lambda: tc.remove_widget(tc.tabWidget.indexOf(self)))
        self.newtabSignal.connect(tc.add_new_page)
        self.urlChanged.connect(tc.reset_url_text)
        self.urlChanged.connect(tc.reset_client_button_visitable)
        self.tab_container = tc
