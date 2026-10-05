/**
 * AMR-NB 解码器的 C 接口
 *
 * 对内嵌的 opencore-amr（amrnb 目录，Apache-2.0）做一层极薄的封装，
 * 供 tieba_audiodec.cpp 调用，避免 C++ 代码直接包含第三方头文件。
 */
#ifndef TIEBA_AMRNB_DEC_H
#define TIEBA_AMRNB_DEC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** 每帧解码出的采样点数（8kHz、20ms） */
#define TIEBA_AMRNB_FRAME_SAMPLES 160

/**
 * 创建 AMR-NB 解码器
 *
 * @return 解码器状态，失败时返回 NULL
 */
void* tieba_amrnb_create(void);

/**
 * 销毁 AMR-NB 解码器
 *
 * @param state 解码器状态，可以为 NULL
 */
void tieba_amrnb_destroy(void* state);

/**
 * 解码一帧 AMR-NB 数据（包含 TOC 字节）
 *
 * @param state 解码器状态
 * @param frame 一帧数据，首字节为 TOC
 * @param frame_bytes 该帧的字节数（含 TOC）
 * @param out 输出缓冲区，至少可以容纳 TIEBA_AMRNB_FRAME_SAMPLES 个采样
 * @return 写入的采样点数，失败时返回 -1
 */
int tieba_amrnb_decode(void* state, const uint8_t* frame, int frame_bytes, int16_t* out);

#ifdef __cplusplus
}
#endif

#endif /* TIEBA_AMRNB_DEC_H */