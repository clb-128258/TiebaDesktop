from PyQt5.QtWidgets import QWidget

from publics import qt_window_mgr
from publics.funcs import timestamp_to_string, large_num_to_string

from ui import tie_preview


class ThreadView(QWidget, tie_preview.Ui_Form):
    """贴子在列表内的预览小组件"""
    is_treasure = False
    is_top = False

    def __init__(self, bduss, tid, fid, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.thread_id = tid
        self.forum_id = fid

        self.label_11.hide()
        self.pushButton_3.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.open_thread_detail)

    def open_thread_detail(self):
        from subwindow.thread_detail_view import ThreadDetailView
        thread_window = ThreadDetailView(self.bduss, self.stoken, int(self.thread_id), self.is_treasure,
                                         self.is_top)
        qt_window_mgr.add_window(thread_window)

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow

        forum_window = ForumShowWindow(self.bduss, self.stoken, int(self.forum_id))
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_thread_values(self, view, agree, reply, repost, send_time=0):
        text = (f'{large_num_to_string(view, endspace=True)}次浏览，'
                f'{large_num_to_string(agree, endspace=True)}人点赞，'
                f'{large_num_to_string(reply, endspace=True)}条回复，'
                f'{large_num_to_string(repost, endspace=True)}次转发')
        if send_time > 0:
            timestr = '发布于 ' + timestamp_to_string(send_time)
            text += '\n' + timestr
        self.label_11.show()
        self.label_11.setText(text)

    def set_infos(self, uicon, uname, title, text, baicon, baname):
        self.label_4.setPixmap(uicon)
        self.label_3.setText(uname)
        self.label_5.setText(title)
        self.label_6.setText(text)
        self.label_2.setText(baname + '吧')

        if baicon:
            self.label.setPixmap(baicon)
        else:
            self.label.hide()

        if not text:
            self.label_6.hide()
        if not title:
            self.label_5.hide()

    def set_picture(self, piclist):
        labels = [self.label_7, self.label_8, self.label_9]
        self.label_7.clear()
        self.label_8.clear()
        self.label_9.clear()
        if len(piclist) == 0:
            self.gridLayout.removeWidget(self.frame_2)
        else:
            try:
                for i in range(len(piclist)):
                    labels[i].setPixmap(piclist[i])
            except IndexError:
                return
