/**
 * 内置音频解码库的 C 接口
 *
 * 该库把 minimp3（MP3，CC0 公共领域）与 opencore-amr（AMR-NB，Apache-2.0）封装为一组
 * 稳定的 C 函数，供 Python 侧通过 ctypes 调用，用于取代体积庞大的 ffmpeg 二进制文件。
 *
 * 使用方式：送入任意分块的压缩数据（例如网络流），取出解码后的 PCM。
 * 输入格式（MP3 / AMR-NB）由库内部按文件头自动识别，调用方无需关心；
 * 输出的 PCM 固定为 44100Hz、双声道、16bit 小端交错格式。
 */
#ifndef TIEBA_AUDIODEC_H
#define TIEBA_AUDIODEC_H

#include <stdint.h>

#if defined(_WIN32)
#  if defined(TIEBA_AUDIODEC_EXPORTS)
#    define TIEBA_DEC_API __declspec(dllexport)
#  else
#    define TIEBA_DEC_API __declspec(dllimport)
#  endif
#  define TIEBA_DEC_CALL __cdecl
#else
#  define TIEBA_DEC_API __attribute__((visibility("default")))
#  define TIEBA_DEC_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

/** 解码输出的采样率（Hz） */
#define TIEBA_DEC_OUTPUT_RATE 44100

/** 解码输出的声道数 */
#define TIEBA_DEC_OUTPUT_CHANNELS 2

/** 音频格式，通过 tieba_dec_format 获取 */
enum
{
    TIEBA_DEC_FORMAT_UNSUPPORTED = -1, /* 识别出格式但当前不支持（例如 AMR-WB） */
    TIEBA_DEC_FORMAT_UNKNOWN = 0,      /* 还没有识别出格式 */
    TIEBA_DEC_FORMAT_MP3 = 1,
    TIEBA_DEC_FORMAT_AMR_NB = 2
};

/** 解码器句柄，由 tieba_dec_create 创建 */
typedef void* tieba_dec_handle;

/**
 * 创建解码器实例
 *
 * @return 解码器句柄，失败时返回 NULL
 */
TIEBA_DEC_API tieba_dec_handle TIEBA_DEC_CALL tieba_dec_create(void);

/**
 * 销毁解码器实例
 *
 * @param handle 解码器句柄，可以为 NULL
 */
TIEBA_DEC_API void TIEBA_DEC_CALL tieba_dec_destroy(tieba_dec_handle handle);

/**
 * 送入一段压缩数据，内部会追加到待解码缓冲区
 *
 * @param handle 解码器句柄
 * @param data 压缩数据，可以为 NULL（此时相当于无事发生）
 * @param size 压缩数据字节数
 * @return 0 表示成功，-1 表示参数错误，-2 表示内存不足
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_feed(tieba_dec_handle handle, const uint8_t* data, int size);

/**
 * 声明压缩数据已经全部送入，之后不会再有新数据
 *
 * @param handle 解码器句柄
 */
TIEBA_DEC_API void TIEBA_DEC_CALL tieba_dec_set_input_end(tieba_dec_handle handle);

/**
 * 取出解码后的 PCM 数据
 *
 * 返回值可能小于 max_bytes，返回 0 表示当前没有可用的数据
 * （可能是需要继续送入压缩数据，也可能是数据已经全部解码完）。
 *
 * @param handle 解码器句柄
 * @param out 输出缓冲区
 * @param max_bytes 输出缓冲区的最大字节数，建议为 4 的整数倍
 * @return 实际写入的字节数，参数错误时返回 -1
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_read_pcm(tieba_dec_handle handle, uint8_t* out, int max_bytes);

/**
 * 解码并丢弃指定字节数的 PCM，用于跳转到指定播放位置
 *
 * 内部会持续解码直到跳过足够的数据，或缓冲区中暂时没有可解码的数据；
 * 跳过的长度按 16bit 交错立体声计算，且始终是完整立体声采样。
 *
 * @param handle 解码器句柄
 * @param bytes 需要跳过的 PCM 字节数
 * @return 实际跳过的字节数，参数错误时返回 -1
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_skip_pcm(tieba_dec_handle handle, int bytes);

/**
 * 判断是否已经解码完毕
 *
 * @param handle 解码器句柄
 * @return 已经送入全部数据且缓冲区中不再有可解码的数据时返回 1，否则返回 0
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_is_drained(tieba_dec_handle handle);

/**
 * 获取识别出的输入格式（TIEBA_DEC_FORMAT_*），主要用于日志与错误提示
 *
 * @param handle 解码器句柄
 * @return 输入格式
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_format(tieba_dec_handle handle);

/**
 * 获取源音频的采样率，仅用于日志与调试
 *
 * @param handle 解码器句柄
 * @return 源采样率（Hz），尚未解出任何帧时返回 0
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_source_rate(tieba_dec_handle handle);

/**
 * 获取源音频的声道数，仅用于日志与调试
 *
 * @param handle 解码器句柄
 * @return 源声道数，尚未解出任何帧时返回 0
 */
TIEBA_DEC_API int TIEBA_DEC_CALL tieba_dec_source_channels(tieba_dec_handle handle);

#ifdef __cplusplus
}
#endif

#endif /* TIEBA_AUDIODEC_H */