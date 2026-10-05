# audio_decoder

贴吧桌面的内置音频解码组件，用于替代体积庞大的 ffmpeg 二进制文件：
把网络上的音频流解码为 PCM 数据，直接交给 pyaudio 播放。

支持两种输入格式，格式在运行时按文件头自动识别，调用方无需关心：

| 格式 | 解码内核 | 说明 |
| --- | --- | --- |
| MP3 | minimp3（CC0 公共领域） | 单头文件解码器 |
| AMR-NB | opencore-amr（Apache-2.0） | 贴吧语音贴返回的就是该格式 |

## 构成

| 文件 | 说明 |
| --- | --- |
| `tieba_audiodec.h` | 本组件对外暴露的 C 接口 |
| `tieba_audiodec.cpp` | 本组件的实现：格式识别、流式缓冲、重采样与格式归一 |
| `decoder.py` | Python 侧封装，通过 ctypes 加载编译好的动态库 |
| `amrnb_dec.h` / `amrnb_dec.c` | 对 AMR-NB 解码内核的薄封装 |
| `minimp3.h` | MP3 解码内核（第三方） |
| `minimp3.LICENSE.txt` | minimp3 的 CC0 许可文本 |
| `amrnb/` | AMR-NB 解码内核（第三方，内含 `README.md` 与 `LICENSE.txt`） |
| `CMakeLists.txt` | 构建配置 |
| `run_build.bat` | Windows 构建脚本（需要先在 MSVC 命令行环境中执行） |
| `build_linux.sh` | Linux 构建脚本（优先使用 cmake，没有 cmake 时回退到 gcc/g++） |

## 构建

Windows（在 VS 开发者命令行中执行）：

```commandline
cd src\publics\audio_decoder
run_build.bat
```

Linux：

```bash
cd src/publics/audio_decoder
bash build_linux.sh
```

构建产物会被拷贝到 `src/binres/` 目录下：

* Windows：`tieba_audiodec.dll`
* Linux：`libtieba_audiodec.so`

这两个文件属于构建产物，不提交到仓库，打包脚本会检查它们是否存在。

## 接口说明

解码库对外只有一个固定格式：**44100Hz、双声道、16bit 小端交错 PCM**，
与播放设备使用的声音参数保持一致，因此 Python 侧不需要再做任何格式转换。

* `tieba_dec_feed`：送入任意大小的压缩数据（网络流的分块数据）。
* `tieba_dec_read_pcm`：取出解码好的 PCM，返回 0 表示暂时没有数据。
* `tieba_dec_set_input_end` / `tieba_dec_is_drained`：用于判断网络流是否已经播放完毕。
* `tieba_dec_format`：获取识别出的输入格式（mp3 / amr-nb），便于日志与排错。
* `tieba_dec_skip_pcm`：解码并丢弃指定字节数的 PCM，用于跳转到指定播放位置。

单声道源（AMR-NB、单声道 MP3）在升为双声道时会按等功率原则衰减 3dB，
采样率不一致时会重采样到 44100Hz，以保证播放电平与设备参数一致。

## 第三方代码

| 目录/文件 | 来源 | 许可证 |
| --- | --- | --- |
| `minimp3.h` | <https://github.com/lieff/minimp3> | CC0 1.0（`minimp3.LICENSE.txt`） |
| `amrnb/` | <https://github.com/BelledonneCommunications/opencore-amr>（SourceForge opencore-amr 镜像） | Apache-2.0（`amrnb/LICENSE.txt`），AMR 代码源自 3GPP TS 26.073 |

`minimp3.h` 的 SHA256 为
`57E437C5C1F0E8B243885D3929C8973B5E6C778451E0100AB4251D19915CB3AD`；
opencore-amr 使用的提交为 `3b67218fb8efb776bcd79e7445774e02d778321d`。