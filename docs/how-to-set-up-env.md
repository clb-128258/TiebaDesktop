# 如何配置贴吧桌面的开发环境

## 前期准备

本软件理论上兼容 Windows/MacOS/Linux 系统，但本软件主要是在 Windows 上开发的，因此在 Windows 下的工作效果最好。  
本教程将以 Windows 环境为例展开讲述。

在部署本项目前，请先准备以下必要开发组件：

* Python 解释器 (至少 3.9 版本)
* CMake (需要设置到系统环境变量中)
* MSVC 编译器 (建议 2022 版本)
* Windows SDK 10+ 版本

> [!note]
>
> 安装以上组件时，请使用与你系统架构相同的版本进行安装，否则可能会产生兼容性问题。

处理好依赖工具后，先创建一个文件夹，用于存放项目源代码和 python 虚拟环境。  
这里假定存放项目的文件夹名称为 `project`，存放虚拟环境的文件夹为 `project/venv`。

## 克隆项目

在 `project` 目录下执行命令 `git clone https://github.com/clb-128258/TiebaDesktop.git`.  
如果没有 git，也可以直接从 github 下载源代码的 zip 压缩包，并解压到 `project` 文件夹下。

## 创建并配置虚拟环境

下列命令将创建虚拟环境并安装 Python 依赖。

```commandline
python -m venv project/venv  // 创建虚拟环境
project/venv/scripts/activate   // 激活虚拟环境
pip install -r project/src/requirements.txt   // 安装依赖
```

## 修补 aiotieba

安装完依赖后，把 `project/aiotieba-fix-files` 下的所有文件（不包括这个文件夹本身）  
全都复制到`project/venv/Lib/site-packages/aiotieba` 中，  
并用前者中的文件**替换**掉后者中出现冲突的文件。

## 配置 ffmpeg

下载 ffmpeg 的二进制文件，  
并使用下载到的 `ffmpeg.exe` 替换掉项目中的的占位文件 `project/src/binres/ffmpeg.exe`。

至此，本项目的环境全部配置完成。

## 编译 WinrtShareBridge

> [!note]
>
> 如果你使用的系统不是 Windows，则无需进行此步骤。

`WinrtShareBridge` 是本项目内用于调起 Windows 分享的 C++ 动态链接库。  
为保证各个平台的通用性，本项目不提供 `ShareBridge.dll` 的二进制版本，你需要自行编译。  
以下是编译方法：

1) 在 `project/src/publics/winrt_url_share` 目录下打开终端（命令提示符）
2) 初始化 MSVC 编译器环境：
    ```commandline
    VS_INSTDIR\VC\Auxiliary\Build\vcvarsARCH.bat
    ```
   其中 `VS_INSTDIR` 为你的 Visual Studio 安装目录，`ARCH` 为你的系统架构（如`64` `32`等），请根据实际情况进行修改。
3) 运行编译批处理：
    ```commandline
    run_build.bat
    ```
   编译过程会自动开始。
4) 编译完成后，`project/src/binres` 目录下应当出现 `ShareBridge.dll` 文件，如果没有则是编译出了问题。

> [!warning]
>
> 如果 `project/src/publics/winrt_url_share/build` 目录存在，请先删掉这个目录，否则编译会出错。

## 最后一步 - 运行！

在终端执行：

```commandline
project/venv/scripts/activate
cd project/src
python main.py
```

如果配置正常，你应该能看见贴吧桌面的主窗口弹出。
