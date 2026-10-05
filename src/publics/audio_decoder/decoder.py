"""内置音频解码库的 Python 封装

底层是 publics/audio_decoder 下的 C++ 动态库：MP3 使用 minimp3、AMR-NB 使用内嵌的
opencore-amr。输入格式由底层按文件头自动识别，对外统一输出 44100Hz、双声道、
16bit 交错 PCM，因此本模块不需要再做格式转换。
"""
import ctypes
import os
import platform

from publics import app_logger

# 解码输出的固定参数，与底层解码库保持一致
OUTPUT_RATE = 44100
OUTPUT_CHANNELS = 2
OUTPUT_SAMPLE_WIDTH = 2

# 与底层 tieba_audiodec.h 中的 TIEBA_DEC_FORMAT_* 对应
FORMAT_UNSUPPORTED = -1
FORMAT_UNKNOWN = 0
FORMAT_MP3 = 1
FORMAT_AMR_NB = 2

FORMAT_NAMES = {FORMAT_UNSUPPORTED: 'unsupported',
                FORMAT_UNKNOWN: 'unknown',
                FORMAT_MP3: 'mp3',
                FORMAT_AMR_NB: 'amr-nb'}

# 各平台对应的解码库文件名
LIBRARY_NAMES = {'Windows': 'tieba_audiodec.dll',
                 'Linux': 'libtieba_audiodec.so'}

_library = None


def get_library_path():
    """获取解码库在当前平台下的路径

    Returns:
        str: 解码库的绝对路径

    Raises:
        OSError: 当前平台没有对应的解码库
    """
    library_name = LIBRARY_NAMES.get(platform.system())
    if library_name is None:
        raise OSError(f'audio decoder library does not support {platform.system()} yet')

    return os.path.abspath(os.path.join('binres', library_name))


def load_library():
    """加载解码库，重复调用只会真正加载一次

    Returns:
        ctypes.CDLL: 已加载并配置好函数签名的解码库

    Raises:
        FileNotFoundError: 解码库文件不存在（还没有编译）
    """
    global _library
    if _library is not None:
        return _library

    library_path = get_library_path()
    if not os.path.isfile(library_path):
        raise FileNotFoundError(f'audio decoder library was not found: {library_path}. '
                                f'Please build it first, see publics/audio_decoder/README.md')

    library = ctypes.CDLL(library_path)
    library.tieba_dec_create.restype = ctypes.c_void_p
    library.tieba_dec_create.argtypes = []
    library.tieba_dec_destroy.restype = None
    library.tieba_dec_destroy.argtypes = [ctypes.c_void_p]
    library.tieba_dec_feed.restype = ctypes.c_int
    library.tieba_dec_feed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    library.tieba_dec_set_input_end.restype = None
    library.tieba_dec_set_input_end.argtypes = [ctypes.c_void_p]
    library.tieba_dec_read_pcm.restype = ctypes.c_int
    library.tieba_dec_read_pcm.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.tieba_dec_skip_pcm.restype = ctypes.c_int
    library.tieba_dec_skip_pcm.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.tieba_dec_is_drained.restype = ctypes.c_int
    library.tieba_dec_is_drained.argtypes = [ctypes.c_void_p]
    library.tieba_dec_format.restype = ctypes.c_int
    library.tieba_dec_format.argtypes = [ctypes.c_void_p]
    library.tieba_dec_source_rate.restype = ctypes.c_int
    library.tieba_dec_source_rate.argtypes = [ctypes.c_void_p]
    library.tieba_dec_source_channels.restype = ctypes.c_int
    library.tieba_dec_source_channels.argtypes = [ctypes.c_void_p]

    _library = library
    app_logger.log_INFO(f'[Audio decoder] library loaded from {library_path}')
    return library


def format_name(fmt: int) -> str:
    """把格式编号转换成便于阅读的名称"""
    return FORMAT_NAMES.get(fmt, f'unknown({fmt})')


class AudioDecoder:
    """流式音频解码器

    送入的压缩数据可以是任意大小的分块（例如网络流的分片），支持 mp3 与 amr-nb，
    格式由底层自动识别；取出的 PCM 固定为 44100Hz 双声道 16bit 交错格式。
    """

    def __init__(self):
        self._lib = load_library()
        self._handle = self._lib.tieba_dec_create()
        if not self._handle:
            raise MemoryError('failed to create the audio decoder')

    def feed(self, data: bytes):
        """送入一段压缩数据

        Args:
            data (bytes): 压缩数据，可以为空
        """
        if not data:
            return

        result = self._lib.tieba_dec_feed(self._handle, data, len(data))
        if result != 0:
            raise MemoryError(f'failed to feed the audio decoder, error code {result}')

    def set_input_end(self):
        """声明压缩数据已经全部送入"""
        self._lib.tieba_dec_set_input_end(self._handle)

    def read_pcm(self, max_bytes: int = 8192) -> bytes:
        """取出解码好的 PCM 数据

        Args:
            max_bytes (int): 本次最多取出的字节数

        Returns:
            bytes: 16bit 交错立体声 PCM 数据，长度为 0 时表示当前没有数据可取
        """
        output = ctypes.create_string_buffer(max_bytes)
        written = self._lib.tieba_dec_read_pcm(self._handle, ctypes.cast(output, ctypes.c_void_p), max_bytes)
        if written < 0:
            raise RuntimeError(f'failed to read pcm data from the audio decoder, error code {written}')

        return output.raw[:written]

    def skip_pcm(self, bytes_count: int) -> int:
        """解码并丢弃指定字节数的 PCM，用于跳转到指定播放位置

        Args:
            bytes_count (int): 需要跳过的 PCM 字节数（16bit 交错立体声）

        Returns:
            int: 实际跳过的字节数，可能小于请求值（表示还需要更多压缩数据）
        """
        if bytes_count <= 0:
            return 0

        skipped = self._lib.tieba_dec_skip_pcm(self._handle, bytes_count)
        if skipped < 0:
            raise RuntimeError(f'failed to skip pcm data, error code {skipped}')

        return skipped

    def is_drained(self) -> bool:
        """判断是否已经解码完毕

        Returns:
            bool: 已经送入全部数据且缓冲区中没有剩余数据时返回 True
        """
        return bool(self._lib.tieba_dec_is_drained(self._handle))

    def format(self) -> int:
        """获取识别出的输入格式（FORMAT_*）"""
        return self._lib.tieba_dec_format(self._handle)

    def source_format(self):
        """获取源音频的格式，仅用于日志与调试

        Returns:
            tuple: (采样率, 声道数)，尚未解出任何帧时返回 (0, 0)
        """
        return (self._lib.tieba_dec_source_rate(self._handle),
                self._lib.tieba_dec_source_channels(self._handle))

    def close(self):
        """释放解码器，允许重复调用"""
        if self._handle:
            self._lib.tieba_dec_destroy(self._handle)
            self._handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def decode_all(data: bytes, chunk_size: int = 16384) -> bytes:
    """一次性解码整段音频数据，主要用于测试与本地调试

    Args:
        data (bytes): 完整的音频文件数据（mp3 或 amr-nb）
        chunk_size (int): 模拟分块送数据的块大小

    Returns:
        bytes: 解码出的 PCM 数据
    """
    stream_decoder = AudioDecoder()
    try:
        chunks = []
        for offset in range(0, len(data), chunk_size):
            stream_decoder.feed(data[offset:offset + chunk_size])
            while True:
                pcm = stream_decoder.read_pcm()
                if not pcm:
                    break
                chunks.append(pcm)

        stream_decoder.set_input_end()
        while True:
            pcm = stream_decoder.read_pcm()
            if not pcm:
                break
            chunks.append(pcm)

        return b''.join(chunks)
    finally:
        stream_decoder.close()