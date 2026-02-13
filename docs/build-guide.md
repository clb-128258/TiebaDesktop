# 主程序编译指南

## 前期准备

### 准备虚拟环境

在编译之前，需要先准备好开发环境，具体可参阅 [如何配置贴吧桌面的开发环境](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/how-to-set-up-env.md)  
在准备好开发环境后，还需要在虚拟环境下安装 `pyinstaller` 以用于打包，进入虚拟环境执行以下命令即可：

```commandline
pip install pyinstaller
```

### 准备依赖工具

除了虚拟环境，还需要准备以下工具:

* 7-Zip 解压缩工具（用于生成发行压缩包）
* NSIS 安装程序管理系统（可选，用于编译发行安装程序）

以上工具请到网络上自行下载。

## 设置编译配置文件

执行编译脚本 `build.py` 需要传入一个 `makefile`，用于指定各种配置选项，具体可以参考 `build_config.json` 文件。  
**注意**：编译配置文件的 JSON 架构需要与 `build_config.json` 的一样。  
以下为对配置文件的具体说明：

```json lines
{
  // 源代码目录，即本仓库的 src 文件夹
  "src_code_path": "source code path",
  // python 虚拟环境目录，目录下有 script/Lib/include 等文件夹
  "py_environ_path": "virtual environment path",
  // 7-zip 命令行工具的路径，注意是 7z.exe，不是那个带 GUI 的文件管理器 7zfm.exe
  "sevenzip_path": "7z.exe path",
  "installer_cfg": {
    // 是否执行安装包编译，如果为 false 则无需关心 makensis_path 字段的值，且无需安装 NSIS 环境
    "build_nsis": true,
    // 如果执行安装包编译，请在这里指定 NSIS 安装目录下 makensis.exe 的路径
    "makensis_path": "makensis.exe path"
  },
  // 版本信息
  "version": {
    // 版本信息字符串，可从 src/consts.py 复制出来
    "version_string": "1.2.2-beta",
    // 版本信息数组，前三项分别填入 (大版本号, 小版本号, 修订号)，最后一位留 0
    "version_array": [
      1,
      2,
      2,
      0
    ],
    // 编译前的最后一次 git 提交 hash，可以在 github 的提交记录页面找到
    "git_last_commit_hash": "b7521348"
  }
}
```

建议：指定路径时，**建议使用绝对路径**，以避免相对路径带来的各种问题。

## 启动编译

假设你的编译配置文件为 `.\build_config.json`，在终端执行以下命令，启动编译过程：

```commandline
cd project\build-tools
python build.py --makefile .\build_config.json
```

当终端输出 `All processes were GONE. Everything is OK.` 字样时，代表编译工作已经成功。

编译成功后，可以在 work_out 目录下找到发行文件，包括压缩包和安装程序。  
生成的 work_temp 目录是用于暂存编译文件的，编译脚本会复制一份源代码到此目录，并执行 pyinstaller 的打包操作。编译最终完成时，work_temp
下存储的应当为原始的程序可执行文件。

## 常见问题

1) 当执行编译时终端抛出错误 `work_temp tree is existing. Make sure the dir does not exist.` 时，代表在执行编译前已经有
   work_temp 文件夹，请先删除这个文件夹再进行编译。
2) 当控制台抛出错误 `pyinstaller process failed!` 时，代表 `pyinstaller` 进程执行失败，退出码不是
   0。此时需要检查编译配置文件是否正确，路径指定是否有问题。`pyinstaller` 在控制台输出的信息也许有助于解决问题。