import yarl
import json
from PyQt5.QtCore import Qt, QSize, QByteArray, QMimeData, QPoint, QTimer, QEvent
from PyQt5.QtGui import QIcon, QMovie, QMouseEvent, QDrag, QCursor
from PyQt5.QtWidgets import QWidget, QTabBar, QApplication, QLabel, QTabWidget, QMenu, QAction, QMessageBox

from consts import datapath, APP_VERSION_STR
from publics import webview2, profile_mgr, qt_window_mgr, cache_mgr, top_toast_widget, app_logger
from publics.funcs import open_url_in_browser, cut_string, start_background_thread

from ui import tb_browser

moved_out_tabs = {}


class ExtPreviewLabel(QLabel):
    def __init__(self, parent):
        super().__init__()
        self.parent_widget = parent
        self.setParent(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 始终置顶
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 背景透明
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)  # 不获得焦点

    def set_pixmap(self, pixmap):
        self.clear()  # 先清理之前的图片
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self.setStyleSheet("QLabel{background-color: white;}")

    def hide_pixmap(self):
        self.clear()
        self.hide()


class ExtTabBar(QTabBar):
    def __init__(self, parent_window: QWidget, parent_tabwidget: QTabWidget):
        super().__init__()
        self.setStyleSheet("""QTabBar {
            border: none;
            qproperty-drawBase: false;
        }
        QTabBar::tab {
            padding: 6px 10px;
            border-radius: 14px;
        }
        QTabBar::tab:hover {
            font: 9pt "微软雅黑";
            background: rgb(232, 232, 232);
        }
        QTabBar::tab:selected {
            font: 9pt "微软雅黑";
            background: rgb(202, 202, 202);
        }
        QTabBar::close-button {
            image: url(./ui/close_black.png);
            width: 21px;
            height: 21px;
        }
        QTabBar::close-button:hover {
            background-color: rgba(0, 0, 0, 0.1);
        }
        QTabBar::close-button:pressed {
            background-color: rgba(0, 0, 0, 0.3);
        }
        """)
        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.setAcceptDrops(True)  # 允许拖入

        self.dragStartPos = QPoint()  # 记录鼠标按下时的位置
        self.draggedTabIdx = -1  # 当前被拖动的tab索引
        self.current_drag_distance = -1  # 指针与tab左侧间距
        self.current_drag_distance_y = -1  # 指针与tab上侧间距
        self._dragging_out = False  # 标记是否正在拖出
        self.moved_value_x = -1  # 指针与整个窗口的x偏移值
        self.moved_value_y = -1  # 指针与整个窗口的y偏移值
        self.dragged_tab_index = -1  # 在有标签页拖入时，鼠标下面的tab索引
        self.draggedin_tab_id = -1  # 在有标签页拖入时，将被拖入tab的id
        self.parent_window = parent_window
        self.parent_tabwidget = parent_tabwidget

        self.drag_preview_label = ExtPreviewLabel(self)
        self.drag_pixmap = None

    def create_new_browser(self, widget, window_pos, window_size):
        browser = TiebaWebBrowser()
        browser.add_new_widget(widget)
        qt_window_mgr.add_window(browser)
        browser.resize(window_size)
        browser.move(window_pos)

    def dragEnterEvent(self, a0):
        if a0.mimeData().hasFormat("tiebadesktop/web-browser-tab"):  # 先判断格式类型
            self.draggedin_tab_id = int(a0.mimeData().data("tiebadesktop/web-browser-tab").data().decode())
            tab_info = moved_out_tabs.get(self.draggedin_tab_id)
            if tab_info and tab_info['parent_window'] != self.parent_window:  # 检查tabid是否有效，并且不是从自己窗口拖出来的
                a0.setDropAction(Qt.DropAction.MoveAction)
                a0.accept()
            else:
                a0.setDropAction(Qt.DropAction.IgnoreAction)
                a0.ignore()
        else:
            a0.setDropAction(Qt.DropAction.IgnoreAction)
            a0.ignore()

    def dropEvent(self, a0):
        a0.accept()

        self.dragged_tab_index = self.tabAt(a0.pos())
        self.dragged_tab_index = self.dragged_tab_index if self.dragged_tab_index != -1 else self.count()
        tab_info = moved_out_tabs.get(self.draggedin_tab_id)

        tab_info['parent_window'].remove_widget(tab_info['parent_tabwidget'].indexOf(tab_info['widget']),
                                                False)  # 从原来的窗口中移除
        self.parent_window.insert_new_widget(tab_info['widget'], self.dragged_tab_index)  # 在新窗口里添加

        # 清理内存
        del moved_out_tabs[self.draggedin_tab_id]
        self.dragged_tab_index = -1
        self.draggedin_tab_id = -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.dragStartPos = event.pos()
            self.draggedTabIdx = self.tabAt(event.pos())  # 获取被点击的tab的索引

            # 计算指针与tab项左侧的距离
            # 这个选项只能在第一次拖动中设置，因为接下来鼠标的坐标随时会发生变化
            tab_rect = self.tabRect(self.draggedTabIdx)
            self.current_drag_distance = event.pos().x() - tab_rect.x()

            # 计算指针与tab项上侧的距离
            self.current_drag_distance_y = event.pos().y() if event.pos().y() <= self.height() else self.height()

            # 计算指针与整个窗口的偏移值
            self.moved_value_x = event.pos().x()
            self.moved_value_y = self.parent_window.frame.height() + event.pos().y() + 32  # 考虑窗口上方的标题栏

            # 设置预览图
            self.drag_preview_label.clear()
            self.drag_pixmap = self.grab(tab_rect)
            self.drag_preview_label.set_pixmap(self.drag_pixmap)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # 事件合法性检查
        if event.buttons() != Qt.LeftButton:
            return
        if self.draggedTabIdx < 0:
            return

        # 如果移动的距离超过了某个阈值，开始拖动
        if (event.pos() - self.dragStartPos).manhattanLength() < QApplication.startDragDistance():
            return

        mouse_pos = self.parent_window.mapFromGlobal(event.globalPos())
        parent_rect = self.parent_window.rect()
        top_area_height = self.parent_window.frame.height() + self.height()
        if (parent_rect.left() - 5 <= mouse_pos.x() <= parent_rect.right() + 5
                and self.parent_window.frame.height() - 5 <= mouse_pos.y() <= top_area_height + 5):
            # 如果移动范围在tab区域内，就不拖出窗口，只是显示预览图
            self.drag_preview_label.move(event.pos().x() - self.current_drag_distance, 0)
            self.drag_preview_label.show()
        else:
            self._dragging_out = True
            self.drag_preview_label.hide_pixmap()  # 拖出去了把预览隐藏
            drag = QDrag(self)
            mimeData = QMimeData()

            # 构造tab信息
            tab_widget = self.parent_tabwidget.widget(self.draggedTabIdx)
            tab_id = id(tab_widget)
            moved_out_tabs[tab_id] = {'widget': tab_widget,
                                      'parent_window': self.parent_window,
                                      'parent_tabwidget': self.parent_tabwidget,
                                      'id': tab_id}
            byteArray = QByteArray(str(tab_id).encode())
            mimeData.setData("tiebadesktop/web-browser-tab", byteArray)

            drag.setPixmap(self.drag_pixmap)
            drag.setHotSpot(QPoint(self.current_drag_distance, self.current_drag_distance_y))
            drag.setMimeData(mimeData)
            drag_result = drag.exec_(Qt.DropAction.MoveAction)

            if drag_result == Qt.DropAction.IgnoreAction:  # 在拖出窗口但是没有被处理时
                cursor_pos = QCursor.pos()
                if self.count() > 1:  # 有多个标签页
                    # 直接新建独立窗口并容纳标签页
                    widget = self.parent_tabwidget.widget(self.draggedTabIdx)
                    self.parent_window.remove_widget(self.draggedTabIdx, False)  # 从旧的里面删除
                    self.create_new_browser(widget,
                                            QPoint(cursor_pos.x() - self.current_drag_distance,
                                                   cursor_pos.y() - self.moved_value_y),
                                            self.parent_window.size())
                else:  # 只有一个标签页
                    # 直接移动当前窗口的位置
                    if self.parent_window.isMaximized():  # 最大化时先还原
                        self.parent_window.showNormal()
                    self.parent_window.move(cursor_pos.x() - self.moved_value_x,
                                            cursor_pos.y() - self.moved_value_y)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_preview_label.hide_pixmap()  # 先隐藏预览图

        if not self._dragging_out:
            # 松开鼠标时，如果不是拖出，就执行真正的替换tab
            targetIdx = self.tabAt(QPoint(event.pos().x(), 5))  # 获取的 tab 索引
            if targetIdx == -1:
                # 如果不在任何 tab 上，尝试判断是在末尾还是开头
                if event.pos().x() > self.tabRect(self.count() - 1).right():
                    targetIdx = self.count()  # 插入到最后
                elif event.pos().x() < self.tabRect(0).left():
                    targetIdx = 0  # 最前面
                else:
                    return

            if targetIdx != self.draggedTabIdx:
                # 移动 tab
                self.moveTab(self.draggedTabIdx, targetIdx)

        self.draggedTabIdx = -1  # 重置被拖动的tab索引
        self._dragging_out = False
        self.current_drag_distance = -1
        self.current_drag_distance_y = -1
        self.moved_value_x = -1
        self.moved_value_y = -1
        self.drag_pixmap = None
        super().mouseReleaseEvent(event)


class TiebaWebBrowser(QWidget, tb_browser.Ui_Form):
    """贴吧页面内置浏览器"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.toolButton.setIcon(QIcon('ui/back.png'))
        self.toolButton_2.setIcon(QIcon('ui/forward.png'))
        self.toolButton_3.setIcon(QIcon('ui/refresh.png'))
        self.toolButton_5.setIcon(QIcon('ui/os_browser.png'))
        self.toolButton_6.setIcon(QIcon('ui/jumpto.png'))
        self.toolButton_4.setIcon(QIcon('ui/download.png'))
        self.toolButton_4.setIcon(QIcon('ui/download.png'))
        self.toolButton_7.setIcon(QIcon('ui/more_horiz.png'))

        font_family = ["Microsoft YaHei",
                       "MS Shell Dlg 2",
                       "PingFang SC",
                       "Hiragino Sans GB",
                       "sans-serif"] if not profile_mgr.local_config['webview_settings']['disable_font_cover'] else []
        self.default_profile = webview2.WebViewProfile(data_folder=f'{datapath}/webview_data/{profile_mgr.current_uid}',
                                                       enable_link_hover_text=False,
                                                       enable_zoom_factor=True,
                                                       enable_error_page=True,
                                                       enable_context_menu=True,
                                                       enable_keyboard_keys=True,
                                                       handle_newtab_byuser=True,
                                                       disable_web_safe=False,
                                                       font_family=font_family,
                                                       user_agent=f'[default_ua] CLBTiebaDesktop/{APP_VERSION_STR}',
                                                       )

        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

        self.tab_bar = ExtTabBar(self, self.tabWidget)
        self.tabWidget.setTabBar(self.tab_bar)
        self.draggedin_tab_id = -1

        self.tabWidget.tabCloseRequested.connect(self.remove_widget)
        self.tabWidget.currentChanged.connect(self.on_tab_changed)
        self.lineEdit.returnPressed.connect(self.load_new_page)
        self.toolButton.clicked.connect(self.button_back)
        self.toolButton_2.clicked.connect(self.button_forward)
        self.toolButton_3.clicked.connect(self.button_refresh)
        self.toolButton_5.clicked.connect(self.button_os_browser)
        self.toolButton_6.clicked.connect(self.button_open_client)
        self.toolButton_4.clicked.connect(self.button_open_downloads)
        self.toolButton_7.clicked.connect(self.button_context_menu)

        self.has_context_menu = False
        self.lineEdit.installEventFilter(self)

        self.window_active_looper = QTimer(self)
        self.window_active_looper.setInterval(100)
        self.window_active_looper.timeout.connect(self.handle_window_frozen)
        if profile_mgr.local_config["webview_settings"]["view_frozen"]:
            self.window_active_looper.start()

    def eventFilter(self, source, event):
        if source == self.lineEdit and event.type() == QEvent.Type.ContextMenu:
            self.has_context_menu = True
        elif source == self.lineEdit and event.type() == QEvent.Type.FocusIn:
            self.has_context_menu = False
        return super(type(self), self).eventFilter(source, event)

    def closeEvent(self, a0):
        a0.accept()
        self.window_active_looper.stop()
        while self.tabWidget.count() != 0:
            self.remove_widget(0)
        qt_window_mgr.del_window(self)

    def keyPressEvent(self, a0):
        if a0.modifiers() == Qt.ControlModifier and a0.key() == Qt.Key_W:
            self.remove_widget(self.tabWidget.currentIndex())

    def dragEnterEvent(self, a0):
        if a0.mimeData().hasFormat("tiebadesktop/web-browser-tab"):  # 先判断格式类型
            self.draggedin_tab_id = int(a0.mimeData().data("tiebadesktop/web-browser-tab").data().decode())
            tab_info = moved_out_tabs.get(self.draggedin_tab_id)
            if tab_info and tab_info['parent_window'] != self:  # 检查tabid是否有效，并且不是从自己窗口拖出来的
                a0.setDropAction(Qt.DropAction.MoveAction)
                a0.accept()
            else:
                a0.setDropAction(Qt.DropAction.IgnoreAction)
                a0.ignore()
        else:
            a0.setDropAction(Qt.DropAction.IgnoreAction)
            a0.ignore()

    def dropEvent(self, a0):
        a0.accept()
        tab_info = moved_out_tabs.get(self.draggedin_tab_id)

        tab_info['parent_window'].remove_widget(tab_info['parent_tabwidget'].indexOf(tab_info['widget']),
                                                False)  # 从原来的窗口中移除
        self.add_new_widget(tab_info['widget'])  # 在新窗口里添加

        # 清理内存
        del moved_out_tabs[self.draggedin_tab_id]
        self.draggedin_tab_id = -1

    def parse_weburl_to_tburl(self):
        tb_url = ''
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2) and widget.isRenderInitOk():
            url = widget.url()
            tb_thread_urls = ('http://tieba.baidu.com/p/', 'https://tieba.baidu.com/p/',)
            tb_forum_urls = ('http://tieba.baidu.com/f', 'https://tieba.baidu.com/f',)
            tb_homepage_urls = ('http://tieba.baidu.com/home/', 'https://tieba.baidu.com/home/')
            if url.startswith(tb_thread_urls):
                thread_id = url.split('?')[0].split('/')[-1]
                tb_url = f'tieba_thread://{thread_id}'
            elif url.startswith(tb_forum_urls):
                forum_name = yarl.URL(url).query.get('kw')
                if forum_name:
                    tb_url = f'tieba_forum_namely://{forum_name}'
            elif url.startswith(tb_homepage_urls):
                portrait = yarl.URL(url).query.get('id')
                if portrait:
                    tb_url = f'user://{portrait}'

        return tb_url

    def handle_window_frozen(self):
        for i in range(self.tabWidget.count()):
            widget = self.tabWidget.widget(i)
            if isinstance(widget, ExtWebView2):
                is_active = (i == self.tabWidget.currentIndex()
                             and not self.isMinimized()
                             and not self.has_context_menu)
                if is_active:
                    widget.setFrozenModeEnabled(False)
                else:
                    widget.setFrozenModeEnabled(True)

    def clean_browser_cache(self):
        widget = self.tabWidget.currentWidget()
        if (isinstance(widget, webview2.QWebView2View)
                and widget.isRenderInitOk()
                and QMessageBox.warning(self,
                                        '数据清理提示',
                                        '确认要清理浏览器缓存吗？\n'
                                        '这会清理你的磁盘缓存、下载历史和浏览历史，'
                                        '且下次访问网站的速度可能会变慢。',
                                        QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes):
            widget.clearCacheData()
            self.top_toaster.showToast(
                top_toast_widget.ToastMessage('缓存清理成功', icon_type=top_toast_widget.ToastIconType.SUCCESS))

    def clean_browser_cookies(self):
        widget = self.tabWidget.currentWidget()
        if (isinstance(widget, webview2.QWebView2View)
                and widget.isRenderInitOk()
                and QMessageBox.warning(self,
                                        '数据清理提示',
                                        '确认要清理浏览器状态性数据吗？\n'
                                        '这会清理你的 Cookies、自动填充、密码保存及所有 DOM 存储，'
                                        '你将丢失在浏览器内的账号登录状态。\n'
                                        '此操作不可撤销，请谨慎操作。',
                                        QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes):
            widget.clearCookies()
            self.top_toaster.showToast(
                top_toast_widget.ToastMessage('状态性数据清理成功', icon_type=top_toast_widget.ToastIconType.SUCCESS))

    def button_context_menu(self):
        widget = self.tabWidget.currentWidget()
        if isinstance(widget, webview2.QWebView2View) and widget.isRenderInitOk():
            menu = QMenu()
            current_zoom = QAction(f'当前网页缩放 {int(widget.zoomFactor() * 100)}%', self)
            current_zoom.setEnabled(False)
            menu.addAction(current_zoom)

            zoom_bigger = QAction('增加 10% 缩放', self)
            zoom_bigger.triggered.connect(lambda: widget.setZoomFactor(widget.zoomFactor() + 0.1))
            menu.addAction(zoom_bigger)

            zoom_smaller = QAction('减小 10% 缩放', self)
            zoom_smaller.triggered.connect(lambda: widget.setZoomFactor(widget.zoomFactor() - 0.1))
            menu.addAction(zoom_smaller)

            zoom_reset = QAction('恢复默认缩放', self)
            zoom_reset.triggered.connect(lambda: widget.setZoomFactor(1.0))
            menu.addAction(zoom_reset)

            menu.addSeparator()

            print_page = QAction('打印网页', self)
            print_page.triggered.connect(widget.openPrintDialog)
            menu.addAction(print_page)

            taskmgr = QAction('任务管理器', self)
            taskmgr.triggered.connect(widget.openChromiumTaskmgrWindow)
            menu.addAction(taskmgr)

            devtools = QAction('开发者工具', self)
            devtools.triggered.connect(widget.openDevtoolsWindow)
            menu.addAction(devtools)

            menu.addSeparator()

            clear_cache = QAction('清理缓存', self)
            clear_cache.triggered.connect(self.clean_browser_cache)
            menu.addAction(clear_cache)

            clear_cookie = QAction('清理状态性数据', self)
            clear_cookie.triggered.connect(self.clean_browser_cookies)
            menu.addAction(clear_cookie)

            self.has_context_menu = True
            bt_pos = self.toolButton_7.mapToGlobal(QPoint(0, 0))
            menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.toolButton_7.height()))
            self.has_context_menu = False

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
            if not url.startswith(('http://', 'https://', 'edge://')):
                url = 'https://' + url
            widget.load(url)

    def on_tab_changed(self):
        self.reset_url_text()
        self.reset_main_title()
        self.reset_top_buttons_visitable()

    def reset_top_buttons_visitable(self):
        tieba_url = self.parse_weburl_to_tburl()
        self.toolButton_6.setVisible(bool(tieba_url))

        widget = self.tabWidget.currentWidget()
        if isinstance(widget, ExtWebView2):
            self.toolButton.setEnabled(widget.canBack())
            self.toolButton_2.setVisible(widget.canForward())

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
        webview.initRender()
        self.add_new_widget(webview)

    def insert_new_widget(self, widget: QWidget, index: int):
        self.tabWidget.insertTab(index, widget, widget.windowIcon(), cut_string(widget.windowTitle(), 20))
        widget.windowIconChanged.connect(lambda icon: self.tabWidget.setTabIcon(self.tabWidget.indexOf(widget), icon))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabText(self.tabWidget.indexOf(widget), cut_string(title, 20)))
        widget.windowTitleChanged.connect(
            lambda title: self.tabWidget.setTabToolTip(self.tabWidget.indexOf(widget), title))

        widget.windowIconChanged.connect(self.reset_main_title)
        widget.windowTitleChanged.connect(self.reset_main_title)

        if isinstance(widget, ExtWebView2):
            widget.bind_to_tab_container(self)

        self.tabWidget.setCurrentWidget(widget)

    def add_new_widget(self, widget: QWidget):
        self.insert_new_widget(widget, self.tabWidget.count())

    def remove_widget(self, index: int, clean_memory=True):
        widget = self.tabWidget.widget(index)
        self.tabWidget.removeTab(index)
        try:
            widget.windowTitleChanged.disconnect()
            widget.windowIconChanged.disconnect()
        except TypeError:
            pass

        if clean_memory:
            if isinstance(widget, ExtWebView2):
                widget.destroyWebviewUntilComplete()
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
        self.renderProcessTerminated.connect(lambda errcode:
                                             self.show_toast_to_parent(
                                                 top_toast_widget.ToastMessage(
                                                     f'底层 WebView2 进程 {self.renderProcessID()} 异常退出，'
                                                     f'进程退出码为 {errcode}。'
                                                     f'网页内容将会无法显示，请尝试刷新页面',
                                                     icon_type=top_toast_widget.ToastIconType.ERROR)
                                             )
                                             )

        self.setProfile(profile)
        self.loadAfterRender(url)

    def parse_js_msg(self, jsonify_text):
        app_logger.log_INFO(f'received text from jsbridge: {jsonify_text}')

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

    def record_history(self, icon_bin, title, url):
        md5 = cache_mgr.save_md5_ico_from_bin(icon_bin) if icon_bin else ''
        profile_mgr.add_view_history(4, {"web_icon_md5": md5, "web_title": title, "web_url": url})

    def start_ani(self):
        self.show_movie.start()
        self.setWindowTitle('正在加载...')

    def stop_ani(self, isok):
        self.show_movie.stop()
        self.setWindowIcon(self.icon())
        self.setWindowTitle(self.title())
        if isok:
            start_background_thread(self.record_history, (self.iconBinary(), self.title(), self.url()))
        else:
            start_background_thread(self.record_history, (b'', self.title(), self.url()))

    def bind_to_tab_container(self, tc: TiebaWebBrowser):
        try:
            self.fullScreenRequested.disconnect()
            self.windowCloseRequested.disconnect()
            self.newtabSignal.disconnect()
            self.urlChanged.disconnect()
        except TypeError:
            pass

        self.fullScreenRequested.connect(tc.handle_fullscreen)
        self.windowCloseRequested.connect(lambda: tc.remove_widget(tc.tabWidget.indexOf(self)))
        self.newtabSignal.connect(tc.add_new_page)
        self.urlChanged.connect(tc.reset_url_text)
        self.urlChanged.connect(tc.reset_top_buttons_visitable)
        self.tab_container = tc
