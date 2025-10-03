# 如何配置贴吧桌面的开发环境

## 前期准备

系统里需要安装 python 解释器，建议使用 3.9 版本的。  
先创建一个文件夹，用于存放项目源代码和 python 虚拟环境。  
这里假定存放项目的文件夹名称为 project，存放虚拟环境的文件夹为 project/venv。

## 克隆项目

在 project 目录下执行命令 `git clone https://github.com/clb-128258/TiebaDesktop.git `。  
如果没有 git，也可以直接从 github 下载源代码的 zip 压缩包，并解压到 project 文件夹下。

## 创建并配置虚拟环境

下列命令将创建虚拟环境并安装依赖。

```commandline
python -m venv project/venv  // 创建虚拟环境
project/venv/scripts/activate   // 激活虚拟环境
pip install -r project/env_docs/requirements.txt   // 安装依赖
```

安装完依赖后，把 project/env_docs/aiotieba-fix-files 下的所有文件（不包括这个文件夹本身）全都复制到
project/venv/Lib/site-packages/aiotieba 中，并用前者中的文件**替换**掉后者中出现冲突的文件。

至此，本项目的环境全部配置完成。

## 最后一步 - 运行！

在终端执行：

```commandline
project/venv/scripts/activate   // 激活虚拟环境
cd project  // 切换到项目目录
python main.py   // 启动程序
```

如果配置正常，你应该能看见贴吧桌面的主窗口弹出。
