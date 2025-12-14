import asyncio
import gc

import aiotieba
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache
from PyQt5.QtWidgets import QDialog, QListWidgetItem

from publics import qt_window_mgr, top_toast_widget
from publics.funcs import start_background_thread, make_thread_content, timestamp_to_string, \
    listWidget_get_visible_widgets
import publics.logging as logging

from ui import reply_comments


class ReplySubComments(QDialog, reply_comments.Ui_Dialog):
    """楼中楼窗口，可查看楼中楼内的回复"""
    isLoading = False
    page = 1
    add_comment = pyqtSignal(dict)
    set_floor_info = pyqtSignal(tuple)

    def __init__(self, bduss, stoken, thread_id, post_id, floor, comment_count, show_thread_button=False):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = thread_id
        self.post_id = post_id
        self.floor_num = floor
        self.comment_count = comment_count

        self.setWindowFlags(Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.init_top_toaster()
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.listWidget.setStyleSheet('QListWidget{outline:0px;}'
                                      'QListWidget::item:hover {color:white; background-color:white;}'
                                      'QListWidget::item:selected {color:white; background-color:white;}')

        self.add_comment.connect(self.ui_add_comment)
        self.set_floor_info.connect(self.ui_set_floor_info)
        self.pushButton_2.clicked.connect(self.refresh_comments)
        self.pushButton.clicked.connect(self.open_thread_detail)
        self.listWidget.verticalScrollBar().valueChanged.connect(self.load_from_scroll)
        if not show_thread_button:
            self.pushButton.hide()
        if self.floor_num == -1 and self.comment_count == -2:
            self.label.setText('楼中楼回复')
        else:
            self.label.setText(f'第 {self.floor_num} 楼的回复，共 {self.comment_count} 条')

        self.load_comments_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id))
        qt_window_mgr.add_window(thread_window)

    def load_item_images(self):
        lws = listWidget_get_visible_widgets(self.listWidget)
        for i in lws:
            i.load_images()

    def refresh_comments(self):
        if not self.isLoading:
            # 清理内存
            self.listWidget.clear()
            QPixmapCache.clear()
            gc.collect()

            self.page = 1
            self.load_comments_async()

    def load_from_scroll(self):
        self.load_item_images()

        if self.listWidget.verticalScrollBar().value() == self.listWidget.verticalScrollBar().maximum():
            self.load_comments_async()

    def ui_set_floor_info(self, datas):
        if datas[0] == -1:
            self.top_toaster.showToast(
                top_toast_widget.ToastMessage(datas[1], 2000, top_toast_widget.ToastIconType.ERROR))
        else:
            self.label.setText(f'第 {datas[0]} 楼的回复，共 {datas[1]} 条')

    def ui_add_comment(self, datas):
        from subwindow.thread_reply_item import ReplyItem
        widget = ReplyItem(self.bduss, self.stoken)
        widget.show_msg_outside = True
        widget.load_by_callback = True
        widget.messageAdded.connect(lambda text: self.top_toaster.showToast(
            top_toast_widget.ToastMessage(text, 2000, top_toast_widget.ToastIconType.INFORMATION)))
        widget.portrait = datas['portrait']
        widget.thread_id = datas['thread_id']
        widget.post_id = datas['post_id']
        if not datas['is_floor']:
            widget.is_comment = True
            if datas['replyobj']:
                widget.set_reply_text(
                    '回复用户 <a href=\"user://{uid}\">{u}</a>: '.format(uid=datas['reply_uid'], u=datas['replyobj']))
            widget.setdatas(datas['portrait'], datas['user_name'], datas['is_author'], datas['content'], [],
                            -1,
                            datas['create_time_str'], '', -1,
                            datas['agree_count'], datas['ulevel'], datas['is_bawu'], voice_info=datas['voice_info'])
        else:
            widget.is_comment = False
            widget.set_reply_text(f'当前楼层信息')
            widget.setdatas(datas['portrait'], datas['user_name'], False, datas['content'],
                            datas['pictures'],
                            datas['floor'],
                            datas['create_time_str'], '', -1, -1, datas['ulevel'], datas['is_bawu'],
                            voice_info=datas['voice_info'])

        item = QListWidgetItem()
        item.setSizeHint(widget.size())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, widget)

        self.load_item_images()

    def load_comments_async(self):
        if not self.isLoading and self.page != -1:
            start_background_thread(self.load_comments)

    def load_comments(self):
        async def dosign():
            self.isLoading = True
            try:
                logging.log_INFO(
                    f'loading sub-replies (thread_id {self.thread_id} post_id {self.post_id} page {self.page})')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    comments = await client.get_comments(self.thread_id, self.post_id, self.page)
                    if comments.err:
                        raise Exception(comments.err)
                    if self.floor_num == -1 and self.comment_count == -2:
                        self.set_floor_info.emit((comments.post.floor, comments.page.total_count))
                    logging.log_INFO(
                        f'itering sub-replies (thread_id {self.thread_id} post_id {self.post_id} floor {comments.post.floor} page {self.page})')

                    if self.page == 1:
                        # 获取当前楼层信息
                        floor_thread = comments.post
                        content = make_thread_content(floor_thread.contents.objs)
                        portrait = floor_thread.user.portrait
                        user_name = floor_thread.user.nick_name_new
                        time_str = timestamp_to_string(floor_thread.create_time)
                        user_level = floor_thread.user.level
                        is_bawu = floor_thread.user.is_bawu
                        thread_id = floor_thread.tid
                        post_id = floor_thread.pid
                        floor = floor_thread.floor
                        reply_num = comments.page.total_count

                        voice_info = {'have_voice': False, 'src': '', 'length': 0}
                        if floor_thread.contents.voice:
                            voice_info['have_voice'] = True
                            voice_info[
                                'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={floor_thread.contents.voice.md5}&play_from=pb_voice_play'
                            voice_info['length'] = floor_thread.contents.voice.duration

                        preview_pixmap = []
                        for j in floor_thread.contents.imgs:
                            # width, height, src, view_src
                            src = j.origin_src
                            view_src = j.src
                            height = j.show_height
                            width = j.show_width
                            preview_pixmap.append(
                                {'width': width, 'height': height, 'src': src, 'view_src': view_src})

                        tdata = {'is_floor': True, 'content': content, 'portrait': portrait, 'user_name': user_name,
                                 'create_time_str': time_str, 'ulevel': user_level, 'is_bawu': is_bawu,
                                 'thread_id': thread_id, 'post_id': post_id, 'voice_info': voice_info,
                                 'pictures': preview_pixmap, 'floor': floor, 'reply_num': reply_num}

                        self.add_comment.emit(tdata)

                    for t in comments.objs:
                        content = make_thread_content(t.contents.objs)
                        portrait = t.user.portrait
                        user_name = t.user.nick_name_new
                        agree_num = t.agree
                        time_str = timestamp_to_string(t.create_time)
                        user_level = t.user.level
                        is_author = t.is_thread_author
                        is_bawu = t.user.is_bawu
                        thread_id = t.tid
                        post_id = t.pid
                        be_replied_user = ''
                        replyer_uid = 0
                        if t.reply_to_id != 0:
                            uinfo = await client.get_user_info(t.reply_to_id, aiotieba.ReqUInfo.NICK_NAME)
                            be_replied_user = uinfo.nick_name_new
                            replyer_uid = t.reply_to_id

                        voice_info = {'have_voice': False, 'src': '', 'length': 0}
                        if t.contents.voice:
                            voice_info['have_voice'] = True
                            voice_info[
                                'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={t.contents.voice.md5}&play_from=pb_voice_play'
                            voice_info['length'] = t.contents.voice.duration

                        tdata = {'is_floor': False, 'content': content, 'portrait': portrait, 'user_name': user_name,
                                 'agree_count': agree_num,
                                 'create_time_str': time_str, 'is_author': is_author, 'ulevel': user_level,
                                 'replyobj': be_replied_user, 'reply_uid': replyer_uid, 'is_bawu': is_bawu,
                                 'thread_id': thread_id, 'post_id': post_id, 'voice_info': voice_info}

                        self.add_comment.emit(tdata)
            except Exception as e:
                logging.log_exception(e)
                self.set_floor_info.emit((-1, str(e)))
            else:
                if comments.has_more:
                    self.page += 1
                else:
                    self.page = -1
                logging.log_INFO(
                    f'load sub-replies (thread_id {self.thread_id} post_id {self.post_id}) finished and page changed to {self.page}')
            finally:
                self.isLoading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()
