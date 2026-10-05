# amrnb

内嵌的 AMR-NB 解码器，用于播放贴吧语音贴（服务端返回的语音是 AMR-NB 格式）。

## 第三方代码

本目录下的 `amrnb` 代码来自 **opencore-amr**：

* 项目主页：<https://sourceforge.net/projects/opencore-amr/>
* 本仓库使用的镜像：<https://github.com/BelledonneCommunications/opencore-amr>
* 使用的提交：`3b67218fb8efb776bcd79e7445774e02d778321d`
* 许可证：Apache License 2.0（完整文本见 `LICENSE.txt`），其中的 AMR 代码源自 3GPP TS 26.073 参考实现

为保证体积与依赖可控，只保留了 **AMR-NB 解码** 所需的文件：

| 目录 | 说明 |
| --- | --- |
| `dec/src` | AMR-NB 解码器实现 |
| `dec/include` | 解码器接口头文件 |
| `common/src` | 解码所需的公共实现与码表 |
| `common/include` | 公共头文件与码表声明 |
| `common/dec/include` | 输入格式（bitstream_format）定义 |
| `oscl` | 上游使用的少量平台宏 |

编码器（`enc`）、AMR-WB（`amrwb`）与 mp4 相关代码均未包含。上游以 C++ 方式编译这些文件，
但它们实际是 C 风格代码（使用了 C 的 `register` 关键字），因此本项目的构建脚本把它们按 **C** 编译
（见 `../CMakeLists.txt`）。

本目录内容除本说明外均为第三方代码，请勿直接修改；如需升级，请整体替换为对应版本的原始文件。