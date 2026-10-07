# 如何配置贴吧桌面的开发环境

## 前期准备

本软件理论上兼容 Windows/MacOS/Linux 系统，但本软件主要是在 Windows 上开发的，因此在 Windows 下的工作效果最好。  
文档主要以 Windows 环境为例展开讲述，与其他系统的语法可能有一些不相通之处。

在部署本项目前，请先准备以下必要开发组件：

* Python 解释器 (至少 3.9 版本)
* CMake (需要设置到系统环境变量中)
* MSVC 编译器 (建议 2022 版本)
* Windows SDK 10+ 版本

除此之外，建议开发过程中使用：
* 6 核以上的 CPU、16G 以上内存的电脑
* Win10 或以上系统（或是相对主流、版本较新的 Linux 发行版）

> [!note]
>
> 安装以上组件时，请使用与你系统架构相同的版本进行安装，否则可能会产生兼容性问题。

处理好依赖工具后，先创建一个文件夹，用于存放项目源代码和 python 虚拟环境。  
这里假定存放项目的文件夹名称为 `project`，存放虚拟环境的文件夹为 `project/venv`。

## 克隆项目

```commandline
cd project
git clone https://github.com/clb-128258/TiebaDesktop.git
```


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

## 编译 C++ 组件

本项目使用了多个 C++ 桥接库（WinrtShareBridge、音频解码库、CEF 等）。  
为方便部署，执行 `build-all` 脚本即可直接编译所有 C++ 依赖。

> [!important]
>
> 有关 CEF：构建可选，需要提供已编译好的 CEF 文件，详情参见 [CEF 集成说明](https://github.com/clb-128258/TiebaDesktop/blob/main/src/publics/base_ui_elements/cef_features/README.md)  
> 如果不需要编译 CEF，下文中的 `CEF_PATH` 参数在实际执行时不传入即可。

Windows：

1) 在 `project/src` 目录下打开命令提示符
2) 初始化 MSVC 编译器环境：
    ```commandline
    VS_INSTDIR\VC\Auxiliary\Build\vcvarsARCH.bat
    ```
   其中 `VS_INSTDIR` 为你的 Visual Studio 安装目录，`ARCH` 为你的系统架构（如`64` `32`等），请根据实际情况进行修改。
3) 运行编译脚本：
    ```commandline
    build-all.bat CEF_PATH
    ```
    其中 `CEF_PATH` 为你的 CEF 二进制发行版路径，可不传。
4) 编译完成后，`project/src/binres` 目录下应当出现   
`tieba_audiodec.dll` `ShareBridge.dll` `cef/*.dll` 等文件，  
如果没有则是编译出了问题。

Linux：

1) 在终端运行编译脚本：
    ```commandline
    cd project/src
    bash build-all.sh CEF_PATH
    ```
    其中 `CEF_PATH` 为你的 CEF 二进制发行版路径，可不传。
2) 编译完成后，`project/src/binres` 目录下应当出现   
`libtieba_audiodec.so` `cef/*.so` 等文件，  
如果没有则是编译出了问题。

至此，本项目的环境全部配置完成。

## 最后一步 - 运行！

在终端执行：

```commandline
project/venv/scripts/activate
cd project/src
python main.py
```

如果配置正常，你应该能看见贴吧桌面的主窗口弹出。
