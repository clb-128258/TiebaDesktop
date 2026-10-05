import pyperclip

from PyQt5.QtCore import QSize, QPoint
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFileDialog, QAction

from publics import audio_stream_player, profile_mgr
from publics.funcs import format_second, http_downloader, start_background_thread
from publics.base_ui_elements import base_ui

from ui import thread_voice_item


class ThreadVoiceItem(base_ui.InsideWidgetBaseQWidget, thread_voice_item.Ui_Form):
    """嵌入在列表的语音贴播放组件"""
    source_link = ''
    length = 0
    play_engine = None
    slider_dragging = False  # 用户是否正在拖动进度条

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.play_engine = audio_stream_player.HttpMp3Player()

        self.reset_theme()
        self.set_play_button_status()

        size = QSize(30, 30)
        self.pushButton_2.setIconSize(size)
        self.pushButton.setIconSize(size)

        self.play_engine.playEvent.connect(self.handle_events)
        self.play_engine.positionChanged.connect(self.handle_position_changed)
        self.pushButton.clicked.connect(self.start_pause_audio)
        self.pushButton_2.clicked.connect(self.play_engine.stop_play)
        self.toolButton.clicked.connect(self.create_more_menu)

        # 进度条：拖动结束后定位，直接点击进度条也会立即定位
        self.slider_dragging = False
        self.horizontalSlider.setRange(0, 1)
        self.horizontalSlider.setValue(0)
        self.horizontalSlider.sliderPressed.connect(self.handle_slider_pressed)
        self.horizontalSlider.sliderReleased.connect(self.handle_slider_released)
        self.horizontalSlider.valueChanged.connect(self.handle_slider_value_changed)

        self.destroyed.connect(self.play_engine.stop_play)

    def reset_theme(self):
        super().reset_theme()

        font_color = profile_mgr.get_theme_policy_string()[1]

        stop_icon = QIcon(f'ui/icon_{font_color}/stop.png')
        more_icon = QIcon(f'ui/icon_{font_color}/more_horiz.png')

        self.pushButton_2.setIcon(stop_icon)
        self.toolButton.setIcon(more_icon)

        self.set_play_button_status()

    def set_play_button_status(self):
        font_color = profile_mgr.get_theme_policy_string()[1]

        play_icon = QIcon(f'ui/icon_{font_color}/play_arrow.png')
        pause_icon = QIcon(f'ui/icon_{font_color}/pause.png')

        if not self.play_engine.is_audio_playing():
            self.pushButton.setIcon(play_icon)
            self.pushButton_2.hide()
        elif not self.play_engine.is_audio_pause():
            self.pushButton.setIcon(pause_icon)
            self.pushButton_2.show()
        elif self.play_engine.is_audio_pause():
            self.pushButton.setIcon(play_icon)
            self.pushButton_2.show()

    def start_pause_audio(self):
        if not self.play_engine.is_audio_playing():
            self.play_engine.start_play()
        elif not self.play_engine.is_audio_pause():
            self.play_engine.pause_play()
        elif self.play_engine.is_audio_pause():
            self.play_engine.unpause_play()

    def handle_events(self, type_):
        self.set_play_button_status()

        if type_ == audio_stream_player.EventType.STOP:
            self.reset_progress()

    def handle_position_changed(self, position):
        """播放位置变化时刷新进度条与时间文字"""
        if self.slider_dragging:
            return

        self.horizontalSlider.blockSignals(True)
        self.horizontalSlider.setValue(self.position_to_slider(position))
        self.horizontalSlider.blockSignals(False)
        self.update_time_text(position)

    def handle_slider_pressed(self):
        self.slider_dragging = True

    def handle_slider_released(self):
        self.slider_dragging = False
        self.play_engine.seek_to(self.horizontalSlider.value() / 1000)

    def handle_slider_value_changed(self, value):
        """拖动过程中只刷新时间文字，直接点击进度条则立即定位"""
        position = value / 1000
        self.update_time_text(position)
        if not self.slider_dragging:
            self.play_engine.seek_to(position)

    def reset_progress(self):
        """把进度条复位到起点"""
        self.horizontalSlider.blockSignals(True)
        self.horizontalSlider.setValue(0)
        self.horizontalSlider.blockSignals(False)
        self.update_time_text(0)

    def position_to_slider(self, position):
        """把播放位置（秒）转换成进度条数值（毫秒）"""
        duration = self.play_engine.get_duration() or self.length
        if duration <= 0:
            return 0

        return max(0, min(int(position * 1000), int(duration * 1000)))

    def update_time_text(self, position):
        duration = self.play_engine.get_duration() or self.length
        self.label_3.setText(f'{format_second(position)} / {format_second(duration)}')

    def setdatas(self, src, len_):
        self.source_link = src
        self.play_engine.mp3_url = src
        self.play_engine.set_duration(len_)
        self.play_engine.seek_to(0)
        self.length = len_

        self.horizontalSlider.blockSignals(True)
        self.horizontalSlider.setRange(0, max(1, int(len_ * 1000)))
        self.horizontalSlider.setValue(0)
        self.horizontalSlider.blockSignals(False)
        self.reset_progress()

    def create_more_menu(self):
        menu = base_ui.BaseQMenu()

        save_voice_file = QAction('保存语音文件', self)
        save_voice_file.triggered.connect(self.save_audio_file)
        menu.addAction(save_voice_file)

        copy_link = QAction('复制语音链接', self)
        copy_link.triggered.connect(lambda: pyperclip.copy(self.source_link))
        menu.addAction(copy_link)

        bt_pos = self.toolButton.mapToGlobal(QPoint(0, 0))
        menu.exec(QPoint(bt_pos.x(), bt_pos.y() + self.toolButton.height()))

    def save_audio_file(self):
        path, type_ = QFileDialog.getSaveFileName(self, '保存语音文件', '', 'Adaptive Multi-Rate 音频文件 (*.amr)')
        if type_ and path:
            start_background_thread(http_downloader, (path, self.source_link))
