# 主程序构建指南

## 前期准备

### 准备虚拟环境

在构建之前，需要先准备好开发环境，具体可参阅 [如何配置贴吧桌面的开发环境](https://github.com/clb-128258/TiebaDesktop/blob/main/docs/how-to-set-up-env.md)  
在准备好开发环境后，还需要在虚拟环境下安装 `pyinstaller` 以用于打包，进入虚拟环境执行以下命令即可：

```commandline
pip install pyinstaller
```

### 准备依赖工具

除了虚拟环境，还需要准备以下工具:

* 7-Zip 解压缩工具（用于生成发行压缩包）
* Windows：NSIS 安装程序管理系统（可选，用于构建发行安装程序）
* Linux：dpkg-deb 与 rpmbuild（可选，分别用于构建 deb 与 rpm 安装包）

7-Zip 与 NSIS 请到网络上自行下载，Linux 下的两个打包工具可以用发行版的包管理器安装：

```commandline
# Debian / Ubuntu
sudo apt install dpkg rpm

# Fedora / RHEL
sudo dnf install dpkg rpm-build

# openSUSE
sudo zypper install dpkg rpm-build
```

其中 dpkg-deb 由 dpkg 软件包提供，rpmbuild 由 rpm / rpm-build 软件包提供。
脚本只会构建当前系统上已安装对应工具的那一种安装包，缺少工具时会输出提示并跳过，不会影响其它产物的构建。

## 设置构建配置文件

执行构建脚本 `build.py` 需要传入一个 `makefile`，用于指定各种配置选项，具体可以参考 `build_config.json` 文件。  
**注意**：构建配置文件的 JSON 架构需要与 `build_config.json` 的一样。  
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
    // 是否执行安装包构建，如果为 false 则无需关心 makensis_path 字段的值，且无需安装 NSIS 环境
    "build_nsis": true,
    // 如果执行安装包构建，请在这里指定 NSIS 安装目录下 makensis.exe 的路径
    "makensis_path": "makensis.exe path",
    // Linux 下是否构建 deb 安装包，需要系统内已安装 dpkg-deb，不填时默认为 true
    "build_deb": true,
    // Linux 下是否构建 rpm 安装包，需要系统内已安装 rpmbuild，不填时默认为 true
    "build_rpm": true,
    // Linux 安装包的维护者信息，会写入 deb 的 Maintainer 字段与 rpm 的 changelog
    "linux_maintainer": "CLB <clb-128258@users.noreply.github.com>"
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
    ]
  }
}
```

建议：指定路径时，**建议使用绝对路径**，以避免相对路径带来的各种问题。

## 启动构建

假设你的构建配置文件为 `.\build_config.json`，在终端执行以下命令，启动构建过程：

```commandline
cd project\build-tools
python build.py --makefile .\build_config.json
```

当终端输出 `All processes were GONE. Everything is OK.` 字样时，代表构建工作已经成功。

构建成功后，可以在 work_out 目录下找到发行文件：

| 产物 | 说明 |
| --- | --- |
| `TiebaDesktop-<版本>-win64.zip` / `TiebaDesktop-<版本>-linux64.zip` | 含可执行文件的发行压缩包 |
| `TiebaDesktop-nsis-installer-<版本>-win64.exe` | Windows 安装程序（需要 NSIS） |
| `TiebaDesktop-<版本>-linux64.deb` | Debian / Ubuntu 安装包（需要 dpkg-deb） |
| `TiebaDesktop-<版本>-linux64.rpm` | Fedora / RHEL / openSUSE 安装包（需要 rpmbuild） |

生成的 work_temp 目录是用于暂存构建文件的，构建脚本会复制一份源代码到此目录，并执行 pyinstaller 的打包操作。构建最终完成时，work_temp
下存储的应当为原始的程序可执行文件。Linux 安装包所使用的 `work_linux_temp` 目录会在构建结束后自动删除。

## Linux 安装包

在 Linux 下构建时，脚本会把 pyinstaller 生成的程序目录整理成标准的系统安装结构，再调用系统自带的打包工具生成 deb 与 rpm 安装包。
安装包内的文件布局如下：

| 安装路径 | 说明 |
| --- | --- |
| `/opt/TiebaDesktop/` | 程序本体（可执行文件与其依赖文件） |
| `/usr/bin/tiebadesktop` | 启动脚本，用于从终端或应用菜单启动程序 |
| `/usr/share/applications/tiebadesktop.desktop` | 桌面菜单入口 |
| `/usr/share/icons/hicolor/512x512/apps/tiebadesktop.png` | 应用图标 |
| `/usr/share/pixmaps/tiebadesktop.png` | 应用图标（兼容旧环境） |
| `/usr/share/doc/tiebadesktop/copyright` | 版权信息 |

打包前脚本会自动清理 `work_temp/binres` 目录：Windows 专属的依赖文件（`ffmpeg.exe`、`toast.exe`、
WebView2 与 ShareBridge 的 `.dll` 文件等）在 Linux 下不会被使用，会被删除，只保留没有后缀名的 linux 二进制文件
（例如音频播放器使用的 `binres/ffmpeg`），清理后产生的空目录也会一并删除。因此 deb、rpm 与发行压缩包都不会
再携带这些文件，可以省下可观的体积。

用户可以像安装其它软件一样安装与卸载本程序：

```commandline
# Debian / Ubuntu
sudo apt install ./TiebaDesktop-<版本>-linux64.deb
sudo apt remove tiebadesktop

# Fedora / RHEL / openSUSE
sudo dnf install ./TiebaDesktop-<版本>-linux64.rpm
sudo dnf remove tiebadesktop
```

安装包中的运行依赖来自 deb 的 Depends 字段与 rpm 的 Requires 字段，默认值写在 `build.py` 的 `DEFAULT_DEB_DEPENDS`
与 `DEFAULT_RPM_REQUIRES` 中。如果目标系统的依赖包名与默认值不一致，可以在构建配置的 `installer_cfg` 中覆盖：

```json lines
{
  "installer_cfg": {
    "deb_depends": "libc6, libgcc-s1, libstdc++6, ...",
    "rpm_requires": "glibc, libgcc, libstdc++, ..."
  }
}
```

用户数据（登录信息、偏好选项、历史记录等）保存在用户主目录下的 `~/.local/share/TiebaDesktop`，
安装与卸载安装包都不会删除这些数据，需要清理时可以手动删除该目录。

## 常见问题

1) 当执行构建时终端抛出错误 `work_temp tree is existing. Make sure the dir does not exist.` 时，代表在执行构建前已经有
   work_temp 文件夹，请先删除这个文件夹再进行构建。
2) 当控制台抛出错误 `pyinstaller process failed!` 时，代表 `pyinstaller` 进程执行失败，退出码不是
   0。此时需要检查构建配置文件是否正确，路径指定是否有问题。`pyinstaller` 在控制台输出的信息也许有助于解决问题。
3) 当控制台输出 `dpkg-deb was not found` 或 `rpmbuild was not found` 时，代表系统内没有安装对应的打包工具，
   脚本会跳过这种安装包的构建。按照本文档的说明安装对应工具后重新构建即可。
4) 当控制台抛出错误 `dpkg-deb process failed!` 或 `rpmbuild process failed!` 时，代表打包工具执行失败，
   终端中打包工具自身输出的信息有助于定位问题。
5) rpm 的 `Version` 字段不允许出现 `-`，因此脚本会在版本号的第一个 `-` 处拆分，把之后的部分写入 rpm 的
   `Release` 字段（其中的 `-` 会被替换为 `.`）。例如版本号 `1.3.3-release` 会生成名为
   `tiebadesktop-1.3.3-release.x86_64.rpm` 的软件包，而 CI 使用的 `1.3.3-release-github-actions` 会生成
   `tiebadesktop-1.3.3-release.github.actions.x86_64.rpm`。