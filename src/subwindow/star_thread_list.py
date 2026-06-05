import asyncio
import gc
import aiotieba

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache
from PyQt5.QtWidgets import QListWidgetItem

from publics import qt_window_mgr, profile_mgr, top_toast_widget, tieba_apis
from publics.funcs import start_background_thread, listWidget_get_visible_widgets, cleanup_listWidget, \
    LoadingFlashWidget, get_exception_string, timestamp_to_string
import publics.app_logger as logging
from subwindow import base_ui
from ui import star_list


def get_forum_id(forum_name):
    async def get_fid():
        try:
            async with aiotieba.Client(proxy=True) as client:
                fid = await client.get_fid(forum_name)
                return fid
        except:
            return 0

    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    return int(asyncio.run(get_fid()))


class StaredThreadsList(base_ui.WindowBaseQDialog, star_list.Ui_Dialog):
    """收藏的贴子列表，可查看已收藏的贴子"""
    add_thread = pyqtSignal(dict)
    thread_load_finished = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.page = 0
        self.isloading = False

        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_ui_elements()

        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_list_info)
        self.listWidget.verticalScrollBar().setSingleStep(25)

        self.add_thread.connect(self.add_star_threads_ui)
        self.refresh_button.clicked.connect(self.refresh_star_threads)
        self.thread_load_finished.connect(self.on_load_finished)

        self.get_star_threads_async()

    def reset_theme(self):
        super().reset_theme()
        color = profile_mgr.get_theme_color_string()
        self.listWidget.setStyleSheet(f'QListWidget{{outline:0px; background-color:{color};}}'
                                      f'QListWidget::item:hover {{color:{color}; background-color:{color};}}'
                                      f'QListWidget::item:selected {{color:{color}; background-color:{color};}}')
        # 设置列表内容的样式
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            widget.reset_theme()

    def closeEvent(self, a0):
        cleanup_listWidget(self.listWidget)
        self.top_toaster.deleteLater()
        self.loading_widget.deleteLater()
        self.refresh_button.deleteLater()

        a0.accept()
        qt_window_mgr.del_window(self)

    def resizeEvent(self, a0):
        self.refresh_button.move_button()

    def init_ui_elements(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self.listWidget)

        self.refresh_button = base_ui.FloatingButton(self)
        self.refresh_button.set_button_status(base_ui.NarrowButtonStatus.Refresh)

    def load_images(self):
        widgets = listWidget_get_visible_widgets(self.listWidget)  # 获取可见的widget列表
        for i in widgets:
            i.load_all_AsyncImage()  # 异步加载里面的图片

    def scroll_load_list_info(self):
        self.load_images()

        if self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value():
            self.get_star_threads_async()  # 加载下一页

    def on_load_finished(self, result):
        self.loading_widget.hide()
        self.refresh_button.show()

        if result['toast']:
            self.top_toaster.showToast(result['toast'])

    def add_star_threads_ui(self, infos):
        item = QListWidgetItem()
        from subwindow.thread_preview_item import ThreadView, AsyncLoadImage
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
        widget.load_by_callback = True

        widget.set_infos(infos['user_portrait'],
                         infos['user_name'],
                         infos['title'], '', None,
                         infos['forum_name'])
        if infos['picture']:
            widget.set_picture([AsyncLoadImage(infos['picture'])])
        else:
            widget.set_picture([])

        html_text = '<html><body><p>'
        html_text += f'发布于 {infos["publish_time"]}<br>'
        if infos['is_del']:
            html_text += '<span style="color:red;">该贴已被作者删除</span>'
        else:
            html_text += (f'最近回复于 {infos["last_reply_time"]}<br>'
                          f'楼主已更新到第 {infos["latest_floor"]} 楼')
        html_text += '</p></body></html>'

        widget.label_11.show()
        widget.label_11.setText(html_text)

        widget.label.hide()
        widget.adjustSize()
        item.setSizeHint(widget.size())

        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)
        self.load_images()

    def refresh_star_threads(self):
        if not self.isloading:
            self.loading_widget.show()
            self.refresh_button.hide()

            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()
            self.page = 1

            self.get_star_threads_async()

    def get_star_threads_async(self):
        if not self.isloading and self.page != -1:
            start_background_thread(self.get_star_threads)

    def get_star_threads(self):
        def iter_thread_item(resp):
            for thread in resp['store_thread']:
                data = {'user_name': thread['author']['name_show'],
                        'user_portrait': thread["author"]["user_portrait"],
                        'thread_id': thread['thread_id'],
                        'forum_id': get_forum_id(thread['forum_name']),
                        'forum_name': thread['forum_name'],
                        'title': thread["title"],
                        'picture': thread['media'][0]["small_pic"] if thread.get("media") and thread['media'][0][
                            'type'] == 'pic' else None,
                        'is_del': bool(int(thread.get('is_deleted', 0))),
                        'latest_floor': int(thread['post_no']),
                        'publish_time': timestamp_to_string(int(thread['create_time'])),
                        'last_reply_time': timestamp_to_string(int(thread['last_time']))}

                self.add_thread.emit(data)

            thread_num = len(resp['store_thread'])
            if thread_num == 0:
                self.page = -1
            else:
                self.page += thread_num

        def fetch_store_items():
            self.isloading = True
            result = {'toast': None}

            try:
                logging.log_INFO(f'loading userThreadStoreList page {self.page}')
                resp = tieba_apis.thread_store(self.bduss, self.stoken, self.page)

                if resp['error']['errno'] == '0':
                    iter_thread_item(resp)
                else:
                    error_code = int(resp['error']['errno'])
                    error_msg = resp['error']['errmsg']

                    toast = top_toast_widget.ToastMessage(f'{error_msg} (错误代码 {error_code})',
                                                          icon_type=top_toast_widget.ToastIconType.ERROR)
                    result['toast'] = toast
            except Exception as e:
                logging.log_exception(e)

                toast = top_toast_widget.ToastMessage(get_exception_string(e),
                                                      icon_type=top_toast_widget.ToastIconType.ERROR)
                result['toast'] = toast
            finally:
                self.thread_load_finished.emit(result)
                self.isloading = False

        fetch_store_items()
