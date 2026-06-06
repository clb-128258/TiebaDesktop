import asyncio
import gc

import aiotieba
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmapCache
from PyQt5.QtWidgets import QListWidgetItem

from publics import qt_window_mgr, top_toast_widget, profile_mgr, qt_image
from publics.funcs import start_background_thread, make_thread_content, timestamp_to_string, \
    listWidget_get_visible_widgets, get_exception_string, cleanup_listWidget, LoadingFlashWidget, large_num_to_string
import publics.app_logger as logging
from subwindow import base_ui

from ui import reply_comments


class ReplySubComments(base_ui.WindowBaseQDialog, reply_comments.Ui_Dialog):
    """楼中楼窗口，可查看楼中楼内的回复"""
    isLoading = False
    page = 1
    thread_author_uid = 0

    add_comment = pyqtSignal(dict)
    set_thread_info = pyqtSignal(dict)
    comment_load_finished = pyqtSignal(str)

    def __init__(self,
                 bduss, stoken,
                 thread_id, post_id,
                 floor, comment_count,
                 show_thread_button=False,
                 is_subfloor=False):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = thread_id
        self.post_id = post_id
        self.floor_num = floor
        self.comment_count = comment_count
        self.is_postId_from_subFloor = is_subfloor
        self.show_thread_frame = show_thread_button

        self.setWindowFlags(Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_ui_elements()

        self.add_comment.connect(self.ui_add_comment)
        self.set_thread_info.connect(self.ui_set_thread_info)
        self.comment_load_finished.connect(self.on_load_finished)
        self.refresh_button.clicked.connect(self.refresh_comments)
        self.pushButton.clicked.connect(self.open_thread_detail)
        self.listWidget.verticalScrollBar().valueChanged.connect(self.load_from_scroll)
        self.pushButton_2.clicked.connect(self.open_thread_author_homepage)

        if not show_thread_button:
            self.frame_3.hide()
            self.gridLayout_4.setContentsMargins(5, 5, 5, 5)

        if self.floor_num == -1 and self.comment_count == -2:
            self.setWindowTitle('楼中楼回复')
        else:
            self.setWindowTitle(f'第 {self.floor_num} 楼的回复 ({self.comment_count} 条)')

        self.load_comments_async()

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
        self.thread_user_portrait_image.destroyImage()

        a0.accept()
        qt_window_mgr.del_window(self)

    def resizeEvent(self, a0):
        self.refresh_button.move_button()

    def init_ui_elements(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self)

        self.refresh_button = base_ui.FloatingButton(self)
        self.refresh_button.set_button_status(base_ui.NarrowButtonStatus.Refresh)

        self.thread_user_portrait_image = qt_image.MultipleImage()
        self.thread_user_portrait_image.currentPixmapChanged.connect(self.label_2.setPixmap)

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), last_post_id=self.post_id)
        qt_window_mgr.add_window(thread_window)

    def open_thread_author_homepage(self):
        if not self.thread_author_uid:
            return

        from subwindow.user_home_page import UserHomeWindow
        user_window = UserHomeWindow(self.bduss, self.stoken, self.thread_author_uid)
        qt_window_mgr.add_window(user_window)

    def load_item_images(self):
        lws = listWidget_get_visible_widgets(self.listWidget)
        for i in lws:
            i.load_images()

    def refresh_comments(self):
        if not self.isLoading:
            # 显示页面
            self.loading_widget.show()
            self.refresh_button.hide()

            # 清理内存
            cleanup_listWidget(self.listWidget)
            QPixmapCache.clear()
            gc.collect()

            self.page = 1
            self.load_comments_async()

    def load_from_scroll(self):
        self.load_item_images()

        if self.listWidget.verticalScrollBar().value() == self.listWidget.verticalScrollBar().maximum():
            self.load_comments_async()

    def on_load_finished(self, result_msg):
        if result_msg:
            toast = top_toast_widget.ToastMessage(result_msg, 2000, top_toast_widget.ToastIconType.ERROR)
            self.top_toaster.showToast(toast)

        self.loading_widget.hide()
        self.refresh_button.show()

    def ui_set_thread_info(self, datas):
        self.setWindowTitle(f'第 {datas["floor_info"]["floor_pos"]} 楼的回复 ({datas["floor_info"]["reply_num"]} 条)')

        if self.show_thread_frame:
            self.thread_author_uid = datas['author']['author_uid']
            self.label_3.setText(datas['author']['author_name'])
            self.label_9.setText(f'原主题贴作者 | 吧内等级 Lv.{datas["author"]["level"]}')

            self.thread_user_portrait_image.destroyImage()
            self.thread_user_portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                                         datas['author']['author_portrait'],
                                                         qt_image.ImageCoverType.RoundCover,
                                                         (40, 40)
                                                         )

            self.label_5.setText('主题：' + datas['title'])
            self.label_8.setVisible(datas['is_help'])
            self.label_7.setText(f'来自 {datas["forum_name"]}吧 | '
                                 f'{large_num_to_string(datas["thread_reply_num"], endspace=True)}条回复')

            self.thread_user_portrait_image.loadImage()

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
            widget.set_reply_text(f'主楼层信息')
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
        async def add_posts_info(comments):
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
                be_replied_user = t.reply_to_nick_name_new
                replyer_uid = t.reply_to_id

                voice_info = {'have_voice': False, 'src': '', 'length': 0}
                if t.contents.voice:
                    voice_info['have_voice'] = True
                    voice_info[
                        'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={t.contents.voice.md5}&play_from=pb_voice_play'
                    voice_info['length'] = t.contents.voice.duration

                tdata = {'is_floor': False,
                         'content': content,
                         'portrait': portrait,
                         'user_name': user_name,
                         'agree_count': agree_num,
                         'create_time_str': time_str,
                         'is_author': is_author,
                         'ulevel': user_level,
                         'replyobj': be_replied_user,
                         'reply_uid': replyer_uid,
                         'is_bawu': is_bawu,
                         'thread_id': thread_id,
                         'post_id': post_id,
                         'voice_info': voice_info}

                self.add_comment.emit(tdata)

        async def set_ui_top_info(comments):
            thread = comments.thread
            forum = comments.forum
            floor = comments.post

            top_data = {'author': {'author_name': thread.user.nick_name_new,
                                   'author_portrait': thread.user.portrait,
                                   'author_uid': thread.user.user_id,
                                   'level': thread.user.level},
                        'title': thread.title,
                        'thread_id': thread.title,
                        'thread_reply_num': thread.reply_num,
                        'is_help': thread.type == 71,
                        'forum_name': forum.fname,
                        'forum_id': forum.fid,
                        'floor_info': {'floor_pos': floor.floor,
                                       'reply_num': comments.page.total_count}
                        }

            self.set_thread_info.emit(top_data)

        async def add_current_floor_info(comments):
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
            floor = floor_thread.floor if floor_thread.floor != 0 else -1
            reply_num = comments.page.total_count

            from_subfloor = False
            if self.is_postId_from_subFloor:
                old_pid = self.post_id
                self.post_id = post_id
                self.is_postId_from_subFloor = False

                from_subfloor = True
                logging.log_INFO(f'sub floor pid {old_pid} changed into floor pid {post_id}')

            voice_info = {'have_voice': False, 'src': '', 'length': 0}
            if floor_thread.contents.voice:
                voice_info['have_voice'] = True
                voice_info[
                    'src'] = f'https://tiebac.baidu.com/c/p/voice?voice_md5={floor_thread.contents.voice.md5}'
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

            tdata = {'is_floor': True,
                     'content': content,
                     'portrait': portrait,
                     'user_name': user_name,
                     'create_time_str': time_str,
                     'ulevel': user_level,
                     'is_bawu': is_bawu,
                     'thread_id': thread_id,
                     'post_id': post_id,
                     'voice_info': voice_info,
                     'pictures': preview_pixmap,
                     'floor': floor,
                     'reply_num': reply_num,
                     'load_from_subfloor': from_subfloor}

            self.add_comment.emit(tdata)

        async def run_task():
            self.isLoading = True
            try:
                logging.log_INFO(f'loading sub-replies '
                                 f'(thread_id {self.thread_id} '
                                 f'post_id {self.post_id} '
                                 f'page {self.page})')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    comments = await client.get_comments(self.thread_id, self.post_id,
                                                         self.page, is_comment=self.is_postId_from_subFloor)
                    if comments.err:
                        raise comments.err

                    await set_ui_top_info(comments)

                    if self.page == 1:
                        await add_current_floor_info(comments)
                    await add_posts_info(comments)

            except Exception as e:
                logging.log_exception(e)
                self.comment_load_finished.emit(get_exception_string(e))
            else:
                if comments.has_more:
                    self.page += 1
                else:
                    self.page = -1
                logging.log_INFO(f'load sub-replies (thread_id '
                                 f'{self.thread_id} '
                                 f'post_id {self.post_id}) '
                                 f'finished and page changed to {self.page}')
                self.comment_load_finished.emit('')
            finally:
                self.isLoading = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_task())

        start_async()
