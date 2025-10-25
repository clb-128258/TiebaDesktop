from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget

from publics import audio_stream_player
from publics.funcs import format_second
from ui import thread_voice_item


class ThreadVoiceItem(QWidget, thread_voice_item.Ui_Form):
    """嵌入在列表的语音贴播放组件"""
    source_link = ''
    length = 0
    play_engine = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.play_engine = audio_stream_player.HttpMp3Player()
        self.label.setPixmap(QPixmap('ui/voice_icon.png').scaled(20, 20, transformMode=Qt.SmoothTransformation))
        self.pushButton_2.hide()

        self.play_engine.playEvent.connect(self.handle_events)
        self.pushButton.clicked.connect(self.start_pause_audio)
        self.pushButton_2.clicked.connect(self.play_engine.stop_play)

        self.destroyed.connect(self.play_engine.stop_play)

    def start_pause_audio(self):
        if not self.play_engine.is_audio_playing():
            self.play_engine.start_play()
        elif not self.play_engine.is_audio_pause():
            self.play_engine.pause_play()
        elif self.play_engine.is_audio_pause():
            self.play_engine.unpause_play()

    def handle_events(self, type_):
        if type_ == audio_stream_player.EventType.PLAY:
            self.pushButton.setText('暂停')
            self.pushButton_2.show()
        elif type_ == audio_stream_player.EventType.PAUSE:
            self.pushButton.setText('继续播放')
        elif type_ == audio_stream_player.EventType.UNPAUSE:
            self.pushButton.setText('暂停')
        elif type_ == audio_stream_player.EventType.STOP:
            self.pushButton.setText('播放')
            self.pushButton_2.hide()

    def setdatas(self, src, len_):
        self.source_link = src
        self.play_engine.mp3_url = src
        self.length = len_
        self.label_3.setText(f'这是一条语音 [时长 {format_second(len_)}]')
