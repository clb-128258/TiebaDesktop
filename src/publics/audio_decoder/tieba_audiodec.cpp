/**
 * 内置音频解码库的实现
 *
 * 支持两种输入格式，并在运行时按文件头自动识别：
 *   * MP3    —— 解码内核为 minimp3（CC0 公共领域）；
 *   * AMR-NB —— 解码内核为内嵌的 opencore-amr（Apache-2.0），贴吧语音贴使用的就是该格式。
 *
 * 两种格式共用同一套流式缓冲、重采样与输出逻辑：
 *   * 压缩数据可以任意分块送入，内部自动缓存并整理缓冲区；
 *   * 自动跳过无用的头部（MP3 的 ID3v2 标签、AMR 的 #!AMR 文件头）；
 *   * 输出统一为 44100Hz、双声道、16bit 交错 PCM，可以直接交给播放设备。
 */
#define MINIMP3_IMPLEMENTATION
#include "minimp3.h"

#include "tieba_audiodec.h"
#include "amrnb_dec.h"

#include <cmath>
#include <cstddef>
#include <cstring>
#include <vector>

namespace
{
    // 输出格式
    const int kOutputRate = TIEBA_DEC_OUTPUT_RATE;
    const int kOutputChannels = TIEBA_DEC_OUTPUT_CHANNELS;

    // 单声道升为双声道时的等功率增益（-3dB）
    const double kMonoToStereoGain = 0.7071067811865476;

    // mp3 帧头长度与单帧最大长度
    const int kFrameHeaderSize = 4;
    const int kMaxFrameBytes = 1441;

    // 已消费数据的整理阈值：超过该值就整理一次输入缓冲区
    const size_t kCompactThreshold = 64 * 1024;

    // ID3v2 标签头的长度
    const size_t kID3HeaderSize = 10;

    // AMR-NB：文件头、采样参数与各帧类型的长度（字节，含 TOC）
    const char kAmrMagic[] = "#!AMR\n";
    const size_t kAmrMagicSize = 6;
    const char kAmrWbMagic[] = "#!AMR-WB\n";
    const size_t kAmrWbMagicSize = 9;
    const int kAmrSampleRate = 8000;
    const int kAmrChannels = 1;
    const int kAmrFrameBytes[16] = {13, 14, 16, 18, 20, 21, 27, 32, 6, 1, 1, 1, 1, 1, 1, 1};

    struct Decoder
    {
        // 输入数据与格式识别
        std::vector<uint8_t> input;       // 待解码的压缩数据
        size_t read_pos;                  // input 中已经消费掉的位置
        bool input_end;                   // 是否已经送入全部压缩数据
        int format;                       // TIEBA_DEC_FORMAT_*

        // MP3 专用状态
        mp3dec_t minimp3;
        bool id3_skipped;                 // 开头的 ID3v2 标签是否已经处理过

        // AMR 专用状态
        void* amr;                        // opencore-amr 解码器状态
        bool amr_header_skipped;          // 开头的 #!AMR 文件头是否已经处理过

        // 输出数据
        int source_rate;                  // 源采样率，仅用于日志
        int source_channels;              // 源声道数，仅用于日志
        std::vector<int16_t> frame;       // 当前帧的立体声数据（交错）
        std::vector<int16_t> pcm;         // 重采样后等待取走的 PCM（交错）
        size_t pcm_pos;                   // pcm 中已经取走的位置
        int16_t history[kOutputChannels]; // 上一块的最后一条采样，用于跨块插值
        double phase;                     // 重采样相位，单位为输入采样数
        bool resampler_started;           // 重采样状态是否已经初始化

        Decoder()
            : read_pos(0), input_end(false), format(TIEBA_DEC_FORMAT_UNKNOWN),
              id3_skipped(false), amr(NULL), amr_header_skipped(false),
              source_rate(0), source_channels(0), pcm_pos(0), phase(1.0),
              resampler_started(false)
        {
            std::memset(&minimp3, 0, sizeof(minimp3));
            std::memset(history, 0, sizeof(history));
        }
    };

    inline Decoder* as_decoder(tieba_dec_handle handle)
    {
        return static_cast<Decoder*>(handle);
    }

    /** 读取源音频中的一条采样
     *
     * index 是虚拟输入序列的下标：下标 0 表示上一块的最后一条采样，
     * 下标 n (n >= 1) 表示当前块的第 n - 1 条采样。
     */
    inline int16_t sample_at(const Decoder* decoder, const std::vector<int16_t>& frame,
                             int frame_samples, int index, int channel)
    {
        if (index <= 0)
        {
            return decoder->history[channel];
        }
        if (index > frame_samples)
        {
            index = frame_samples;
        }
        return frame[(size_t)(index - 1) * kOutputChannels + channel];
    }

    /** 把一条输出采样限制在 16bit 范围内 */
    inline int16_t clamp_sample(double value)
    {
        if (value > 32767.0)
        {
            return 32767;
        }
        if (value < -32768.0)
        {
            return -32768;
        }
        return (int16_t)std::lrint(value);
    }

    /** 把当前帧转换为 44100Hz 双声道并追加到 pcm 缓冲区 */
    void append_frame(Decoder* decoder, const int16_t* src, int samples, int src_rate, int src_channels)
    {
        decoder->frame.resize((size_t)samples * kOutputChannels);
        for (int i = 0; i < samples; i++)
        {
            for (int channel = 0; channel < kOutputChannels; channel++)
            {
                if (src_channels == 1)
                {
                    // 单声道升为双声道时按等功率原则衰减 3dB，
                    // 这样播放电平与原先 ffmpeg 的处理链路保持一致
                    decoder->frame[(size_t)i * kOutputChannels + channel] =
                        clamp_sample(src[i] * kMonoToStereoGain);
                }
                else
                {
                    decoder->frame[(size_t)i * kOutputChannels + channel] =
                        src[(size_t)i * src_channels + channel];
                }
            }
        }

        const std::vector<int16_t>& frame = decoder->frame;

        // 采样率一致时直接透传，不做任何插值
        if (src_rate <= 0 || src_rate == kOutputRate)
        {
            decoder->resampler_started = false;
            decoder->pcm.insert(decoder->pcm.end(), frame.begin(), frame.end());
            return;
        }

        if (!decoder->resampler_started)
        {
            // 第一块数据：让第一个输出采样正好对应第一条输入采样
            for (int channel = 0; channel < kOutputChannels; channel++)
            {
                decoder->history[channel] = frame[channel];
            }
            decoder->phase = 1.0;
            decoder->resampler_started = true;
        }

        const double step = (double)src_rate / (double)kOutputRate;
        // 降采样时用相邻采样的均值做简单的抗混叠，升采样时用线性插值
        const bool down_sampling = step > 1.0;
        const int taps = (int)std::ceil(step);

        while (decoder->phase < (double)samples)
        {
            const int base = (int)std::floor(decoder->phase);
            const double frac = decoder->phase - (double)base;

            for (int channel = 0; channel < kOutputChannels; channel++)
            {
                double value;
                if (down_sampling)
                {
                    double sum = 0;
                    for (int k = 0; k < taps; k++)
                    {
                        sum += sample_at(decoder, frame, samples, base + k, channel);
                    }
                    value = sum / taps;
                }
                else
                {
                    const double v0 = sample_at(decoder, frame, samples, base, channel);
                    const double v1 = sample_at(decoder, frame, samples, base + 1, channel);
                    value = v0 + (v1 - v0) * frac;
                }
                decoder->pcm.push_back(clamp_sample(value));
            }

            decoder->phase += step;
        }

        decoder->phase -= (double)samples;
        for (int channel = 0; channel < kOutputChannels; channel++)
        {
            decoder->history[channel] = frame[(size_t)(samples - 1) * kOutputChannels + channel];
        }
    }

    /** 整理输入缓冲区，丢弃已经消费掉的数据 */
    void compact_input(Decoder* decoder)
    {
        if (decoder->read_pos == 0)
        {
            return;
        }
        if (decoder->read_pos < kCompactThreshold && decoder->read_pos < decoder->input.size())
        {
            return;
        }

        decoder->input.erase(decoder->input.begin(),
                             decoder->input.begin() + (std::ptrdiff_t)decoder->read_pos);
        decoder->read_pos = 0;
    }

    /** 按文件头识别输入格式 */
    void detect_format(Decoder* decoder)
    {
        if (decoder->format != TIEBA_DEC_FORMAT_UNKNOWN)
        {
            return;
        }

        const size_t available = decoder->input.size() - decoder->read_pos;
        if (available < kAmrMagicSize)
        {
            return;                       // 数据还不足以判断
        }

        const uint8_t* data = decoder->input.data() + decoder->read_pos;
        if (std::memcmp(data, kAmrMagic, kAmrMagicSize) == 0)
        {
            decoder->amr = tieba_amrnb_create();
            decoder->format = (decoder->amr != NULL) ? TIEBA_DEC_FORMAT_AMR_NB
                                                     : TIEBA_DEC_FORMAT_UNSUPPORTED;
            return;
        }
        if (available >= kAmrWbMagicSize && std::memcmp(data, kAmrWbMagic, kAmrWbMagicSize) == 0)
        {
            decoder->format = TIEBA_DEC_FORMAT_UNSUPPORTED;   // 暂不支持 AMR-WB
            return;
        }
        if (std::memcmp(data, kAmrWbMagic, kAmrMagicSize) == 0)
        {
            return;                       // 可能是 AMR-WB，等待更多数据
        }

        decoder->format = TIEBA_DEC_FORMAT_MP3;
    }

    /** 处理 mp3 开头的 ID3v2 标签，返回 false 表示数据还不够 */
    bool skip_id3v2(Decoder* decoder)
    {
        if (decoder->id3_skipped)
        {
            return true;
        }

        const size_t available = decoder->input.size() - decoder->read_pos;
        const uint8_t* data = decoder->input.data() + decoder->read_pos;

        if (available < 3)
        {
            return false;                        // 数据太少，等收齐后判断
        }
        if (std::memcmp(data, "ID3", 3) != 0)
        {
            decoder->id3_skipped = true;         // 开头不是 ID3v2 标签
            return true;
        }
        if (available < kID3HeaderSize)
        {
            return false;                        // 等待标签头收齐
        }

        // 标签长度使用 synchsafe 整数，每字节只使用低 7 位
        const size_t tag_size = ((size_t)(data[6] & 0x7F) << 21) |
                                ((size_t)(data[7] & 0x7F) << 14) |
                                ((size_t)(data[8] & 0x7F) << 7) |
                                ((size_t)(data[9] & 0x7F));
        size_t total_size = kID3HeaderSize + tag_size;
        if ((data[5] & 0x10) != 0)
        {
            total_size += kID3HeaderSize;        // 存在标签尾
        }
        if (available < total_size)
        {
            return false;                        // 等待标签数据收齐
        }

        decoder->read_pos += total_size;
        decoder->id3_skipped = true;
        return true;
    }

    /** 解码一帧 mp3 数据，成功产出 PCM 时返回 true */
    bool decode_mp3_frame(Decoder* decoder)
    {
        while (true)
        {
            if (!skip_id3v2(decoder))
            {
                return false;
            }
            if (decoder->read_pos >= decoder->input.size())
            {
                return false;                    // 没有待解码的数据了
            }

            const uint8_t* data = decoder->input.data() + decoder->read_pos;
            const int available = (int)(decoder->input.size() - decoder->read_pos);

            // 流式解码的关键：minimp3 只有在缓冲区里能顺带验证下一帧帧头时，
            // 才会沿用内部的比特池直接解码；一旦数据不够，它会重新同步并清空
            // 比特池，导致后续这些帧全部解不出来（表现为播放中途静音）。
            // 因此这里先攒够「最大帧长 + 帧头」的数据，数据送入结束时再放宽该限制。
            if (!decoder->input_end && available < kMaxFrameBytes + kFrameHeaderSize)
            {
                return false;
            }

            int16_t samples[MINIMP3_MAX_SAMPLES_PER_FRAME];
            mp3dec_frame_info_t info;
            std::memset(&info, 0, sizeof(info));

            const int decoded = mp3dec_decode_frame(&decoder->minimp3, data, available, samples, &info);
            const int frame_bytes = info.frame_bytes;

            if (decoded <= 0)
            {
                // 没有解出数据时，minimp3 会把 frame_bytes 设为「整个缓冲区长度」，
                // 表示缓冲区里还没有完整的一帧（此时必须保留数据等待后续输入，
                // 否则会把尚未解码完整的帧丢掉），而小于缓冲区长度时表示前面有一段
                // 可以安全丢弃的噪声数据。
                if (frame_bytes <= 0 || frame_bytes >= available)
                {
                    return false;
                }
                decoder->read_pos += (size_t)frame_bytes;
                continue;
            }

            decoder->read_pos += (size_t)frame_bytes;

            if (info.hz > 0)
            {
                decoder->source_rate = info.hz;
            }
            if (info.channels > 0)
            {
                decoder->source_channels = info.channels;
            }

            append_frame(decoder, samples, decoded, info.hz, info.channels);
            return true;
        }
    }

    /** 解码一帧 AMR-NB 数据，成功产出 PCM 时返回 true */
    bool decode_amr_frame(Decoder* decoder)
    {
        // 跳过 AMR 文件头
        if (!decoder->amr_header_skipped)
        {
            const size_t available = decoder->input.size() - decoder->read_pos;
            if (available < kAmrMagicSize)
            {
                return false;
            }

            const uint8_t* data = decoder->input.data() + decoder->read_pos;
            if (std::memcmp(data, kAmrMagic, kAmrMagicSize) == 0)
            {
                decoder->read_pos += kAmrMagicSize;
            }
            decoder->amr_header_skipped = true;
        }

        const size_t available = decoder->input.size() - decoder->read_pos;
        if (available < 1)
        {
            return false;                        // 没有待解码的数据了
        }

        // AMR-NB 每帧固定 20ms，帧长度由 TOC 中的帧类型决定
        const uint8_t* data = decoder->input.data() + decoder->read_pos;
        const int frame_type = (data[0] >> 3) & 0x0F;
        const int frame_bytes = kAmrFrameBytes[frame_type];
        if ((int)available < frame_bytes)
        {
            return false;                        // 等待收齐完整的一帧
        }

        int16_t samples[TIEBA_AMRNB_FRAME_SAMPLES];
        if (tieba_amrnb_decode(decoder->amr, data, frame_bytes, samples) < 0)
        {
            decoder->read_pos += (size_t)frame_bytes;
            return false;
        }
        decoder->read_pos += (size_t)frame_bytes;

        decoder->source_rate = kAmrSampleRate;
        decoder->source_channels = kAmrChannels;
        append_frame(decoder, samples, TIEBA_AMRNB_FRAME_SAMPLES, kAmrSampleRate, kAmrChannels);
        return true;
    }

    /** 解码一帧数据（自动按格式分发），成功产出 PCM 时返回 true */
    bool decode_one_frame(Decoder* decoder)
    {
        if (decoder->format == TIEBA_DEC_FORMAT_MP3)
        {
            return decode_mp3_frame(decoder);
        }
        if (decoder->format == TIEBA_DEC_FORMAT_AMR_NB)
        {
            return decode_amr_frame(decoder);
        }

        return false;                            // 未知格式或暂不支持的格式
    }
}

tieba_dec_handle TIEBA_DEC_CALL tieba_dec_create(void)
{
    try
    {
        Decoder* decoder = new Decoder();
        mp3dec_init(&decoder->minimp3);
        return decoder;
    }
    catch (...)
    {
        return NULL;
    }
}

void TIEBA_DEC_CALL tieba_dec_destroy(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder == NULL)
    {
        return;
    }

    if (decoder->amr != NULL)
    {
        tieba_amrnb_destroy(decoder->amr);
    }
    delete decoder;
}

int TIEBA_DEC_CALL tieba_dec_feed(tieba_dec_handle handle, const uint8_t* data, int size)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder == NULL)
    {
        return -1;
    }
    if (data == NULL || size <= 0)
    {
        return 0;
    }

    try
    {
        compact_input(decoder);
        decoder->input.insert(decoder->input.end(), data, data + size);
        detect_format(decoder);
    }
    catch (...)
    {
        return -2;
    }

    return 0;
}

void TIEBA_DEC_CALL tieba_dec_set_input_end(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder != NULL)
    {
        decoder->input_end = true;
    }
}

int TIEBA_DEC_CALL tieba_dec_read_pcm(tieba_dec_handle handle, uint8_t* out, int max_bytes)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder == NULL || out == NULL || max_bytes <= 0)
    {
        return -1;
    }

    const size_t unit = sizeof(int16_t) * (size_t)kOutputChannels;
    int written = 0;

    try
    {
        // 按整条立体声采样为单位拷贝，避免声道错位
        while ((size_t)(max_bytes - written) >= unit)
        {
            if (decoder->pcm_pos >= decoder->pcm.size())
            {
                decoder->pcm.clear();
                decoder->pcm_pos = 0;
                if (!decode_one_frame(decoder))
                {
                    break;                       // 需要更多压缩数据，或数据已经解完
                }
            }

            size_t copy_size = (size_t)(max_bytes - written);
            const size_t available = (decoder->pcm.size() - decoder->pcm_pos) * sizeof(int16_t);
            if (copy_size > available)
            {
                copy_size = available;
            }
            copy_size -= copy_size % unit;

            std::memcpy(out + written, decoder->pcm.data() + decoder->pcm_pos, copy_size);
            decoder->pcm_pos += copy_size / sizeof(int16_t);
            written += (int)copy_size;
        }

        compact_input(decoder);
    }
    catch (...)
    {
        return -1;
    }

    return written;
}

int TIEBA_DEC_CALL tieba_dec_skip_pcm(tieba_dec_handle handle, int bytes)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder == NULL || bytes < 0)
    {
        return -1;
    }

    const size_t unit = sizeof(int16_t) * (size_t)kOutputChannels;
    int skipped = 0;

    try
    {
        while ((size_t)(bytes - skipped) >= unit)
        {
            if (decoder->pcm_pos >= decoder->pcm.size())
            {
                decoder->pcm.clear();
                decoder->pcm_pos = 0;
                if (!decode_one_frame(decoder))
                {
                    break;                       // 需要更多压缩数据，或数据已经解完
                }
            }

            size_t drop = (decoder->pcm.size() - decoder->pcm_pos) * sizeof(int16_t);
            const size_t want = (size_t)(bytes - skipped);
            if (drop > want)
            {
                drop = want;
            }
            drop -= drop % unit;                 // 保持立体声采样对齐

            decoder->pcm_pos += drop / sizeof(int16_t);
            skipped += (int)drop;
        }

        compact_input(decoder);
    }
    catch (...)
    {
        return -1;
    }

    return skipped;
}

int TIEBA_DEC_CALL tieba_dec_is_drained(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    if (decoder == NULL)
    {
        return 1;
    }
    if (!decoder->input_end || decoder->pcm_pos < decoder->pcm.size())
    {
        return 0;
    }

    try
    {
        // 输入已经结束，若还能解出数据，说明尚未解码完毕
        return decode_one_frame(decoder) ? 0 : 1;
    }
    catch (...)
    {
        return 1;
    }
}

int TIEBA_DEC_CALL tieba_dec_format(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    return decoder == NULL ? TIEBA_DEC_FORMAT_UNKNOWN : decoder->format;
}

int TIEBA_DEC_CALL tieba_dec_source_rate(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    return decoder == NULL ? 0 : decoder->source_rate;
}

int TIEBA_DEC_CALL tieba_dec_source_channels(tieba_dec_handle handle)
{
    Decoder* decoder = as_decoder(handle);
    return decoder == NULL ? 0 : decoder->source_channels;
}