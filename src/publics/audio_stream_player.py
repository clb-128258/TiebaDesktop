"""mp3音频流播放器

播放链路：网络上分块读取音频数据 -> 内置解码库（publics/audio_decoder，mp3 使用 minimp3、
amr-nb 使用内嵌的 opencore-amr）解码为 44100Hz 双声道 PCM -> 交给 pyaudio 播放。

除顺序播放外，还支持自由调整播放进度（seek）：定位时在解码器内部快速丢弃目标位置之前的 PCM，
因此对 mp3 与 amr-nb 都适用，也不要求服务端支持 Range 请求。

已下载的音频数据会缓存在内存中（完整下载后还会写入本地缓存文件），
因此重复定位与重复播放时不需要再向服务器请求数据，定位速度只取决于解码速度。
"""
import enum
import queue
import threading
import time

import pyaudio
import requests
from PyQt5.QtCore import QObject, pyqtSignal

from publics import app_logger, cache_mgr, request_mgr
from publics.audio_decoder import decoder as audio_decoder

import consts

# 播放参数（与内置解码库的输出格式保持一致）
FORMAT = pyaudio.paInt16  # 16-bit PCM
CHANNELS = audio_decoder.OUTPUT_CHANNELS  # 立体声
RATE = audio_decoder.OUTPUT_RATE  # 采样率 44.1kHz
CHUNK = 1024  # 每次写入声卡的帧数

PCM_FRAME_BYTES = CHANNELS * audio_decoder.OUTPUT_SAMPLE_WIDTH  # 一条立体声采样的字节数
BYTES_PER_SECOND = RATE * PCM_FRAME_BYTES  # 每秒音频对应的 PCM 字节数
PCM_BUFFER_SIZE = CHUNK * PCM_FRAME_BYTES  # 每次取出的 PCM 字节数
STREAM_READ_SIZE = 16 * 1024  # 每次从网络读取的压缩数据字节数
EVENT_POLL_INTERVAL = 0.01  # 暂停期间的事件轮询间隔（秒）
POSITION_EMIT_INTERVAL = 0.3  # 进度更新的最小间隔（秒）


def do_log(info: str):
    app_logger.log_INFO("[Http Mp3 Play Engine] " + info)


class EventType(enum.IntEnum):
    """事件类型枚举"""
    PAUSE = 1  # 执行暂停
    UNPAUSE = 2  # 解除暂停
    STOP = 3  # 停止播放
    PLAY = 4  # 开始播放
    SEEK = 5  # 调整播放进度


class _Action(enum.IntEnum):
    """播放线程内部的动作"""
    CONTINUE = 0  # 继续当前一轮的播放
    STOP = 1  # 结束播放
    SEEK = 2  # 重新定位，需要开始新一轮解码


class HttpMp3Player(QObject):
    """
    http协议下的音频流播放器

    解码使用内置的解码库（支持 mp3 与 amr-nb），不再依赖 ffmpeg 二进制文件。

    Args:
        mp3_url (str): 音频文件链接
        enable_decoder_errinfo (bool): 是否在控制台显示解码相关的调试信息
    """
    mp3_url = ''
    enable_decoder_logging = False
    playEvent = pyqtSignal(EventType)
    positionChanged = pyqtSignal(float)  # 播放位置变化（单位：秒）
    __is_pausing = False
    __playing = False

    def __init__(self, mp3_url: str = "", enable_decoder_errinfo: bool = False):
        super().__init__()

        self.mp3_url = mp3_url
        self.enable_decoder_logging = enable_decoder_errinfo
        self.__is_pausing = False
        self.__playing = False

        self.__event_queue = queue.Queue()
        self.__play_thread = None
        self.__source_logged = False
        self.__written_bytes = 0

        # 播放进度相关（单位：秒）
        self.__duration = 0.0  # 音频总时长，由界面告知
        self.__position = 0.0  # 当前播放位置
        self.__seek_target = 0.0  # 本轮解码的起始位置
        self.__position_base = 0.0  # 本轮开始写入时的位置
        self.__last_position_emit = 0.0

        # 当前一轮使用的网络响应
        self.__response = None
        self.__data_over = False

        # 本地缓存（压缩数据）：优先从这里取数据，避免重复下载
        self.__cache_url = None  # 当前缓存对应的链接
        self.__cache = bytearray()  # 已经获取到的压缩数据
        self.__cache_pos = 0  # 本轮已经从缓存中取走的位置
        self.__cache_complete = False  # 是否已经拿到完整音频
        self.__network_skip = 0  # 网络流中需要跳过的、本地已缓存过的字节数

        self.audio_stream = None
        self.pa_obj = None
        self.decoder = None

    # ---------------------------------------------------------------- 播放控制
    def start_play(self):
        if not self.__playing:
            self.__init_pyaudio()
            self.__written_bytes = 0
            self.__source_logged = False
            self.__play_thread = threading.Thread(target=self.__play_thread_func, daemon=True)
            self.__play_thread.start()
            self.__playing = True
            self.playEvent.emit(EventType.PLAY)

    def wait_play_finish(self):
        try:
            self.__play_thread.join()
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

    # ---------------------------------------------------------------- 播放进度
    def set_duration(self, seconds: float):
        """设置音频总时长（秒），用于限制定位范围与界面显示

        Args:
            seconds (float): 音频总时长，界面可从接口数据中获取
        """
        self.__duration = max(0.0, float(seconds))

    def get_duration(self) -> float:
        """获取音频总时长（秒），未知时返回 0"""
        return self.__duration

    def get_position(self) -> float:
        """获取当前播放位置（秒）"""
        return self.__position

    def seek_to(self, seconds: float):
        """把播放位置调整到指定秒数（超出范围会自动截断）

        播放中调用会立即重新定位；未播放时调用，则下次开始播放时从该位置开始。

        Args:
            seconds (float): 目标位置（秒）
        """
        seconds = max(0.0, float(seconds))
        if self.__duration > 0:
            seconds = min(seconds, self.__duration)

        self.__seek_target = seconds
        self.__position = seconds
        self.__written_bytes = 0
        self.__emit_position(force=True)

        if self.__playing:
            self.__event_queue.put(EventType.SEEK)

    def __emit_position(self, force=False):
        """上报当前播放位置（做了节流，避免过于频繁地刷新界面）"""
        now = time.time()
        if not force and now - self.__last_position_emit < POSITION_EMIT_INTERVAL:
            return

        self.__last_position_emit = now
        self.positionChanged.emit(self.__position)

    def __reset_position(self):
        """播放结束时把进度复位，便于下次从头播放"""
        self.__position = 0.0
        self.__seek_target = 0.0
        self.__position_base = 0.0
        self.__written_bytes = 0
        self.__emit_position(force=True)

    # ---------------------------------------------------------------- 内部实现
    def __init_pyaudio(self):
        """初始化声卡相关的资源（必须在播放线程启动前调用）"""
        self.pa_obj = pyaudio.PyAudio()
        self.audio_stream = self.pa_obj.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK
        )

    def __play_thread_func(self):
        """播放线程：边从网络读取音频数据，边解码并写入声卡"""
        try:
            do_log("Starting playback... (streaming from url)")
            while self.__play_round():
                # 收到定位请求，重新开始一轮解码
                do_log("Seek to %.2fs" % self.__seek_target)
        except Exception as e:
            do_log(f"Error during playback: \n{type(e)}\n{e}")
            if self.enable_decoder_logging:
                app_logger.log_exception(e)
        finally:
            self.__release_audio()
            self.decoder = None
            self.__response = None
            self.__playing = False
            self.__is_pausing = False
            self.playEvent.emit(EventType.STOP)
            do_log("Playback stopped.")

    def __play_round(self) -> bool:
        """执行一轮「定位 + 播放」

        Returns:
            bool: 返回 True 表示收到了定位请求，需要重新开始一轮；返回 False 表示播放结束
        """
        self.__load_cache()

        stream_decoder = audio_decoder.AudioDecoder()
        self.decoder = stream_decoder
        self.__data_over = False
        self.__cache_pos = 0
        self.__network_skip = 0

        try:
            if self.__cache_complete:
                # 本地缓存里已经是完整音频，直接用缓存定位与播放，不需要再请求服务器
                return self.__play_with_decoder(stream_decoder)

            with requests.get(self.mp3_url,
                              headers=consts.http_header,
                              stream=True,
                              timeout=consts.HTTP_TIMEOUT,
                              verify=request_mgr.is_ssl_required()) as response:
                response.raise_for_status()
                self.__response = response

                # 服务器不支持 Range，网络数据总是从 0 开始，因此先跳过本地已经缓存过的部分
                self.__network_skip = len(self.__cache)
                return self.__play_with_decoder(stream_decoder)
        finally:
            stream_decoder.close()
            self.decoder = None
            self.__response = None

    def __play_with_decoder(self, stream_decoder) -> bool:
        """一轮播放的实际流程（数据来源由 __read_stream 决定：本地缓存优先）"""
        # 1) 先丢弃目标位置之前的数据
        action = self.__skip_to_target(stream_decoder)
        if action != _Action.CONTINUE:
            if action == _Action.STOP:
                self.__reset_position()
            return action == _Action.SEEK

        # 2) 顺序播放
        while True:
            action = self.__process_events()
            if action != _Action.CONTINUE:
                if action == _Action.STOP:
                    self.__reset_position()
                return action == _Action.SEEK

            data = self.__read_stream()
            if data:
                stream_decoder.feed(data)
            else:
                stream_decoder.set_input_end()

            wrote = self.__write_pcm(stream_decoder)
            if wrote == 0 and self.__data_over:
                if self.__written_bytes == 0:
                    # 一帧都没有解出来时给出明确提示，便于定位格式不支持或数据异常
                    do_log('No audio data was decoded. detected format: '
                           f'{audio_decoder.format_name(stream_decoder.format())}')
                else:
                    do_log("All data has been played.")
                self.__reset_position()
                return False

    def __skip_to_target(self, stream_decoder) -> _Action:
        """丢弃本轮起点之前的 PCM，返回下一步动作"""
        target_bytes = int(self.__seek_target * BYTES_PER_SECOND)
        target_bytes -= target_bytes % PCM_FRAME_BYTES

        skipped = 0
        while skipped < target_bytes:
            action = self.__process_events()
            if action != _Action.CONTINUE:
                return action

            data = self.__read_stream()
            if data:
                stream_decoder.feed(data)
            else:
                # 数据已经结束，无法再往后跳，就从当前位置开始播放
                stream_decoder.set_input_end()
                break

            skipped += stream_decoder.skip_pcm(target_bytes - skipped)

        self.__position_base = skipped / BYTES_PER_SECOND
        self.__written_bytes = 0
        self.__position = self.__position_base
        self.__emit_position(force=True)
        return _Action.CONTINUE

    def __read_stream(self) -> bytes:
        """读取一块压缩数据

        优先使用本地缓存；缓存用完后才继续从网络读取（并跳过本地已经缓存过的部分）。
        返回空字节串表示数据已经结束。
        """
        # 1) 本地缓存
        if self.__cache_pos < len(self.__cache):
            data = bytes(self.__cache[self.__cache_pos:self.__cache_pos + STREAM_READ_SIZE])
            self.__cache_pos += len(data)
            return data

        # 2) 整个音频都已经在缓存里，数据到此为止
        if self.__cache_complete:
            self.__data_over = True
            return b''

        # 3) 继续从网络读取
        if self.__data_over or self.__response is None:
            return b''

        # 服务器不支持 Range，网络数据总是从 0 开始，先丢掉本地已经缓存过的那部分
        while self.__network_skip > 0:
            skipped = self.__response.raw.read(min(STREAM_READ_SIZE, self.__network_skip))
            if not skipped:
                self.__data_over = True
                self.__save_cache()
                return b''
            self.__network_skip -= len(skipped)

        data = self.__response.raw.read(STREAM_READ_SIZE)
        if not data:
            self.__data_over = True
            self.__save_cache()
            return b''

        # 新数据同时写入缓存并直接交给解码器，因此缓存读取位置要一起推进
        self.__cache.extend(data)
        self.__cache_pos += len(data)
        return data

    def __load_cache(self):
        """载入本地缓存（同一个链接只会尝试一次）"""
        if self.__cache_url == self.mp3_url:
            return

        self.__cache_url = self.mp3_url
        self.__cache = bytearray()
        self.__cache_pos = 0
        self.__cache_complete = False
        self.__network_skip = 0

        try:
            cached = cache_mgr.get_voice_cache(self.mp3_url)
        except Exception as e:
            app_logger.log_exception(e)
            cached = b''

        if cached:
            self.__cache = bytearray(cached)
            self.__cache_complete = True
            do_log(f"Voice cache loaded: {len(cached)} bytes")

    def __save_cache(self):
        """网络数据读取完毕：把完整的音频写入本地缓存文件"""
        if self.__cache_complete or not self.__cache:
            return

        self.__cache_complete = True
        try:
            cache_mgr.save_voice_cache(self.mp3_url, bytes(self.__cache))
            do_log(f"Voice cache saved: {len(self.__cache)} bytes")
        except Exception as e:
            app_logger.log_exception(e)

    def __write_pcm(self, stream_decoder) -> int:
        """把解码好的 PCM 写入声卡，返回本次写入的字节数

        暂停或收到新事件时会提前返回，交由 __process_events 处理。
        """
        current_total_written = 0
        while not self.__is_pausing and self.__event_queue.empty() and self.__playing:
            pcm = stream_decoder.read_pcm(PCM_BUFFER_SIZE)
            if not pcm:
                break

            if not self.__source_logged:
                source_hz, source_channels = stream_decoder.source_format()
                if source_hz:
                    do_log(f"Decoded source: {audio_decoder.format_name(stream_decoder.format())} "
                           f"{source_hz}Hz/{source_channels}ch -> {RATE}Hz/{CHANNELS}ch")
                    self.__source_logged = True

            self.audio_stream.write(pcm)

            block_length = len(pcm)
            if block_length > 0:
                current_total_written += block_length
                self.__written_bytes += block_length
                self.__position = self.__position_base + self.__written_bytes / BYTES_PER_SECOND
                self.__emit_position()

        return current_total_written

    def __process_events(self) -> _Action:
        """处理事件队列

        Returns:
            _Action: 下一步动作；暂停时会阻塞在这里等待继续播放或停止
        """
        while True:
            try:
                event_type = self.__event_queue.get_nowait()
            except queue.Empty:
                if self.__is_pausing:
                    time.sleep(EVENT_POLL_INTERVAL)
                    continue
                return _Action.CONTINUE

            if event_type == EventType.STOP:
                self.__is_pausing = False
                return _Action.STOP
            elif event_type == EventType.SEEK:
                return _Action.SEEK
            elif event_type == EventType.PAUSE:
                self.playEvent.emit(EventType.PAUSE)
            elif event_type == EventType.UNPAUSE:
                self.playEvent.emit(EventType.UNPAUSE)

    def __release_audio(self):
        """释放声卡相关的资源"""
        try:
            if self.audio_stream is not None:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
        except Exception as e:
            app_logger.log_exception(e)
        finally:
            self.audio_stream = None

        try:
            if self.pa_obj is not None:
                self.pa_obj.terminate()
        except Exception as e:
            app_logger.log_exception(e)
        finally:
            self.pa_obj = None
