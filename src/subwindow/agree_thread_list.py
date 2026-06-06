import asyncio
import gc

import publics.app_logger as logging
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache
from PyQt5.QtWidgets import QListWidgetItem

from publics import qt_window_mgr, request_mgr, profile_mgr, top_toast_widget
from publics.funcs import timestamp_to_string, start_background_thread, cut_string, listWidget_get_visible_widgets, \
    cleanup_listWidget, LoadingFlashWidget, get_exception_string
from subwindow import base_ui
from ui import star_list


class AgreedThreadsList(base_ui.WindowBaseQDialog, star_list.Ui_Dialog):
    """点赞的贴子列表，和最新版贴吧一样，可查看点赞过的贴子\n
    由于和收藏列表一样都是贴子列表，所以直接继承star_list.Ui_Dialog来写"""
    add_thread = pyqtSignal(dict)
    thread_load_finished = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.page = 1
        self.isloading = False

        self.init_ui_elements()
        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowTitle('点赞列表')
        self.resize(720, 520)

        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_list_info)
        self.listWidget.verticalScrollBar().setSingleStep(25)

        self.add_thread.connect(self.add_agreed_threads_ui)
        self.refresh_button.clicked.connect(self.refresh_agreed_threads)
        self.thread_load_finished.connect(self.on_load_finished)

        self.refresh_agreed_threads()

    def reset_theme(self):
        super().reset_theme()
        self.loading_widget.reset_theme()

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

    def on_load_finished(self, result):
        self.loading_widget.hide()
        self.refresh_button.show()

        if result['toast']:
            self.top_toaster.showToast(result['toast'])

    def load_item_images(self):
        for thread in listWidget_get_visible_widgets(self.listWidget):
            from subwindow.thread_preview_item import ThreadView
            from subwindow.thread_reply_item import ReplyItem
            if isinstance(thread, ThreadView):
                thread.load_all_AsyncImage()
            elif isinstance(thread, ReplyItem):
                thread.load_images()

    def scroll_load_list_info(self):
        self.load_item_images()

        if self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value():
            self.get_agreed_threads_async()

    def add_agreed_threads_ui(self, infos):
        item = QListWidgetItem()

        if infos['type'] == 0:
            from subwindow.thread_preview_item import ThreadView, AsyncLoadImage
            widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
            widget.load_by_callback = True

            widget.set_infos(infos['portrait'], infos['user_name'], infos['title'], infos['text'],
                             infos['forum_head_avatar'],
                             infos['forum_name'])
            widget.set_thread_values(infos['thread_data']['vn'], infos['thread_data']['ag'],
                                     infos['thread_data']['rpy'], infos['thread_data']['rpt'], infos['timestamp'])
            widget.set_picture(list(AsyncLoadImage(link) for link in infos['picture']))
            widget.adjustSize()
        else:
            from subwindow.thread_reply_item import ReplyItem
            widget = ReplyItem(self.bduss, self.stoken)
            timestr = timestamp_to_string(infos['timestamp'])
            widget.portrait = infos['portrait']
            widget.thread_id = infos['thread_id']
            widget.post_id = infos['post_id']
            widget.allow_home_page = True
            widget.subcomment_show_thread_button = True
            widget.load_by_callback = True
            widget.set_reply_text(
                '<a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下的回复：'.format(
                    fname=infos['forum_name'], tname=infos['title'], tid=infos['thread_id'],
                    fid=infos['forum_id']))
            widget.setdatas(infos['portrait'], infos['user_name'], False, infos['text'],
                            infos['picture'], -1, timestr, '', -2, -1, -1, False)

        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)
        self.load_item_images()

    def refresh_agreed_threads(self):
        if not self.isloading:
            self.loading_widget.show()
            self.refresh_button.hide()

            cleanup_listWidget(self.listWidget)
            QPixmapCache.clear()
            gc.collect()
            self.page = 1

            self.get_agreed_threads_async()

    def get_agreed_threads_async(self):
        if not self.isloading and self.page != -1:
            start_background_thread(self.get_agreed_threads)

    def get_agreed_threads(self):
        logging.log_INFO(f'loading userAgreedThreadsList page {self.page}')

        result = {'toast': None}
        self.isloading = True

        try:
            payload = {
                'BDUSS': self.bduss,
                'stoken': self.stoken,
                'tab_id': "0",
                'pn': str(self.page),
                'rn': "20",
            }
            resp = request_mgr.run_post_api(f'/c/u/feed/userAgree',
                                            payloads=payload,
                                            bduss=self.bduss,
                                            stoken=self.stoken,
                                            use_mobile_header=True)

            for thread in resp['data']["thread_list"]:
                # 贴子类型0为主题，1为回复
                data = {'type': 1 if thread.get('top_agree_post') else 0,
                        'user_name': thread['author']['name_show'],
                        'thread_id': thread['tid'],
                        'post_id': 0,
                        'forum_id': thread['forum_info']['id'],
                        'forum_name': thread['forum_info']['name'],
                        'title': thread["title"],
                        'text': cut_string(thread['abstract'][0]['text'], 50),
                        'picture': [],
                        'timestamp': thread['create_time'],
                        'thread_data': {'vn': thread["view_num"], 'ag': thread["agree_num"],
                                        'rpy': thread["reply_num"], 'rpt': thread["share_num"]},
                        'portrait': thread["author"]["portrait"].split('?')[0],
                        'forum_head_avatar': ''}

                # 获取回复贴数据
                if postinfo := thread.get('top_agree_post'):
                    data['post_id'] = postinfo['id']
                    data['timestamp'] = postinfo["time"]
                    data['thread_data']['ag'] = postinfo["agree"]['agree_num']
                    data['user_name'] = postinfo['author']['name_show']
                    data['portrait'] = postinfo["author"]["portrait"].split('?')[0]
                    text = ''
                    for i in postinfo['content']:
                        if i['type'] == 0:  # 是文本
                            text += i['text']
                        elif i['type'] == 3:  # 是图片
                            data['picture'].append(
                                {'width': int(i['bsize'].split(',')[0]), 'height': int(i['bsize'].split(',')[1]),
                                 'src': i['origin_src'], 'view_src': i['src']})
                    data['text'] = cut_string(text, 50)

                # 获取吧头像
                data['forum_head_avatar'] = thread["forum_info"]["avatar"]

                # 获取主题贴图片
                if thread.get("media") and data['type'] == 0:
                    for m in thread['media']:
                        if m["type"] == 3:  # 是图片
                            url = m["small_pic"]
                            data['picture'].append(url)

                self.add_thread.emit(data)
        except Exception as e:
            logging.log_exception(e)

            toast = top_toast_widget.ToastMessage(get_exception_string(e),
                                                  icon_type=top_toast_widget.ToastIconType.ERROR)
            result['toast'] = toast
        else:
            logging.log_INFO(
                f'load userAgreedThreadsList page {self.page} successful')
            if not resp['data']['has_more']:
                self.page = -1
            else:
                self.page += 1
        finally:
            self.thread_load_finished.emit(result)
            self.isloading = False
