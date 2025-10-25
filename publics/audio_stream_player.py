"""mp3音频流播放器"""
import pyaudio
import subprocess
import os
import queue
import threading
from aiotieba.logging import get_logger
from PyQt5.QtCore import QObject, pyqtSignal
import time
import enum
import sys

FFMPEG_PATH = os.getcwd().replace("\\", "/") + f'/ffmpeg/ffmpeg.exe'  # 本地ffmpeg路径
FORMAT = pyaudio.paInt16  # 16-bit PCM
CHANNELS = 2  # 立体声
RATE = 44100  # 采样率 44.1kHz
CHUNK = 1024  # 每次读取的字节数


def do_log(info: str):
    get_logger().info("[HTTP Mp3 Play Engine] " + info)


class EventType(enum.IntEnum):
    """事件类型枚举"""
    PAUSE = 1  # 执行暂停
    UNPAUSE = 2  # 解除暂停
    STOP = 3  # 停止播放
    PLAY = 4  # 开始播放


class HttpMp3Player(QObject):
    """
    http协议下的mp3播放器

    Args:
        mp3_url (str): mp3文件链接
        enable_ffmpeg_errinfo (bool): 是否在控制台显示ffmpeg的调试信息
    """
    mp3_url = ''
    enable_ffmpeg_logging = False
    playEvent = pyqtSignal(EventType)
    __is_pausing = False
    __playing = False

    def __init__(self, mp3_url: str = "", enable_ffmpeg_errinfo: bool = False):
        super().__init__()

        self.mp3_url = mp3_url
        self.enable_ffmpeg_logging = enable_ffmpeg_errinfo
        self.__is_pausing = False
        self.__playing = False

        self.__event_queue = queue.Queue()

    def start_play(self):
        if not self.__playing:
            self.__init_pyaudio()
            self.__get_pcm_stream_thread = threading.Thread(target=self.__init_player, daemon=True)
            self.__get_pcm_stream_thread.start()
            self.__playing = True
            self.playEvent.emit(EventType.PLAY)

    def wait_play_finish(self):
        try:
            self.__get_pcm_stream_thread.join()
        except AttributeError:
            raise Exception('play has not started')

    def stop_play(self):
        if self.__playing:
            self.__event_queue.put(EventType.STOP)

    def pause_play(self):
        if not self.__is_pausing:
            self.__event_queue.put(EventType.PAUSE)
            self.__is_pausing = True
            do_log("Playback paused.")

    def unpause_play(self):
        if self.__is_pausing:
            self.__event_queue.put(EventType.UNPAUSE)
            self.__is_pausing = False
            do_log("Playback pause canceled.")

    def is_audio_playing(self):
        return self.__playing

    def is_audio_pause(self):
        return self.__is_pausing

    def __init_player(self):
        cmd = [
            FFMPEG_PATH,
            '-user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            '-i', self.mp3_url,
            '-f', 'wav',  # 输出 WAV 格式（带头部）
            '-acodec', 'pcm_s16le',  # 16-bit 小端 PCM
            '-ar', str(RATE),  # 采样率
            '-ac', str(CHANNELS),  # 声道数
            '-vn', '-sn', '-dn',  # 忽略视频、字幕、数据流
            '-'  # 输出到 stdout
        ]

        do_log("Starting ffmpeg... (Streaming from URL)")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=sys.stderr if self.enable_ffmpeg_logging else subprocess.DEVNULL,
            bufsize=1024,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        try:
            while True:
                # 从队列读取音频数据块
                if not self.__event_queue.empty():
                    event_type = self.__event_queue.get()
                    if event_type == EventType.PAUSE:
                        self.playEvent.emit(EventType.PAUSE)
                        need_stop = self.__handle_pause()
                        if need_stop == EventType.STOP:
                            break
                        elif need_stop == EventType.UNPAUSE:
                            self.playEvent.emit(EventType.UNPAUSE)
                    elif event_type == EventType.STOP:
                        break
                else:
                    data = self.process.stdout.read(CHUNK)
                    if not data:
                        break
                    self.audio_stream.write(data)
        except Exception as e:
            do_log(f"Error during playback: \n{type(e)}\n{e}")
        finally:
            # 清理资源
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.pa_obj.terminate()
            self.process.terminate()
            self.__playing = False
            self.playEvent.emit(EventType.STOP)
            do_log("Playback stopped.")

    def __init_pyaudio(self):
        # 设置音频播放参数（需与 ffmpeg 输出匹配）
        # 初始化 PyAudio
        self.pa_obj = pyaudio.PyAudio()

        # 打开音频输出流
        self.audio_stream = self.pa_obj.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )

    def __handle_pause(self) -> EventType:
        while True:
            if self.__event_queue.empty():
                time.sleep(0.01)
            else:
                event_type = self.__event_queue.get()
                return event_type
