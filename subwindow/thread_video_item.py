from PyQt5.QtWidgets import QWidget, QFileDialog
from publics.funcs import start_background_thread, http_downloader, format_second, large_num_to_string, \
    open_url_in_browser
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
        self.pushButton_3.hide()

        self.pushButton.clicked.connect(self.save_video)
        self.pushButton_2.clicked.connect(self.play_video)

    def play_video(self):
        open_url_in_browser(f'https://clb.tiebadesktop.localpage.jsplayer/video_play_main.html?url={self.source_link}')

    def save_video(self):
        path, type_ = QFileDialog.getSaveFileName(self, '选择视频保存位置', '', '视频文件 (*.mp4)')
        if path:
            start_background_thread(http_downloader, (path, self.source_link))

    def setdatas(self, src, len_, views):
        self.source_link = src
        self.length = len_
        self.view_num = views
        self.source_link = self.source_link.replace('tb-video.bdstatic.com', 'bos.nj.bpc.baidu.com')

        self.label_3.setText(f'时长 {format_second(len_)}，浏览量 {large_num_to_string(views)}')
