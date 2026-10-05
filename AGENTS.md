# AGENTS.md

本文件面向参与 TiebaDesktop 开发的开发者与 Agent 工具，提供项目概览、常用命令、目录职责和修改注意事项。修改代码前请先阅读本文件，并优先遵循仓库已有模式。

## 项目概览

TiebaDesktop 是一个基于 Python 与 PyQt5 的第三方百度贴吧桌面客户端，支持 Windows 与 Linux（均为 x86_64）。功能包括贴吧内容浏览、登录与多账号管理、签到、互动消息、用户主页、收藏/点赞/浏览历史、通知、内置浏览器与视频播放等，其中部分能力依赖 Windows 原生组件（WebView2、WinRT 分享、系统通知）。

核心入口是 `src/main.py`。应用启动时会初始化用户数据目录、日志、代理、命令行任务、Qt 高 DPI 配置、翻译文件、主题背景、主窗口和系统托盘。Windows 专属步骤（WinRT 分享库、WebView2 检查）会在非 Windows 平台自动跳过；Linux 下会设置 `QT_QPA_PLATFORM=wayland`。

## 技术栈与依赖

- 语言：Python 3.9+
- GUI：PyQt5
- 贴吧 API：`aiotieba==4.6.1`，并配套 `aiotieba-fix-files/` 中的补丁文件
- 网络与解析：`requests`、`beautifulsoup4`
- 加密与音频：`pycryptodome`、`pyaudio`（Linux 需要系统提供 portaudio，如 Debian 系的 `portaudio19-dev`）
- Windows 专用：`pywin32`、`pythonnet`、`windows_toasts`，以及 `src/binres/` 下的 `.exe`/`.dll`（WebView2、toast、ShareBridge 等）
- 打包：PyInstaller、7-Zip；Windows 可选 NSIS，Linux 可选 dpkg-deb 与 rpmbuild

依赖清单按平台拆分：Windows 见 `src/requirements.txt`，Linux 见 `src/requirements-linux.txt`（不含 `pywin32`、`pythonnet`、`windows_toasts` 等 Windows 专用库）。跨平台代码依赖 `os.name`、`sys.platform`、`platform.system()` 做分支判断；Windows 专用库只能在对应分支内导入，否则会破坏 Linux 下的启动。

## 目录地图

- `src/main.py`：程序入口。
- `src/consts.py`：全局常量、版本号、默认用户数据目录、HTTP header、主题色等。
- `src/publics/`：公共逻辑与基础设施。
  - `app_logger.py`：日志。
  - `profile_mgr.py`、`account_mgr.py`、`cache_mgr.py`：用户数据、账号和缓存管理。
  - `cli_feats.py`：命令行启动参数处理。
  - `baidu_features/`：贴吧/百度相关接口封装。
  - `base_ui_elements/`：基础 UI 组件、窗口效果、加载控件等。
  - `winrt_url_share/`：Windows 分享桥接 C++ 代码与构建脚本。
- `src/subwindow/`：业务窗口、页面和主要交互逻辑。
- `src/ui/`：由 Qt `.ui` 文件生成的 Python UI 文件、QSS、图标、表情、播放器静态资源等。
- `src/resf/`：原始 Qt Designer `.ui` 文件、PSD、protobuf 源定义和生成脚本。
- `src/proto/`：由 `.proto` 生成的 Python protobuf 文件。
- `src/binres/`：运行所需二进制资源；Windows 为 `.exe`/`.dll`（WebView2、toast、ShareBridge 等），Linux 为 `.so` 动态库（如内置解码库 `libtieba_audiodec.so`）。
- `aiotieba-fix-files/`：需要覆盖到虚拟环境 `site-packages/aiotieba` 的补丁文件。
- `build-tools/`：构建脚本、PyInstaller 版本信息、NSIS 脚本、Linux deb/rpm 打包逻辑和构建配置示例。
- `docs/`：开发环境、构建、命令行参数说明和应用截图。

## 本地开发

Windows 与 Linux 均可开发与验证，按平台选择对应步骤。

### 1. 创建并激活虚拟环境

Windows：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```powershell
# Windows
pip install -r src\requirements.txt
```

```bash
# Linux
pip install -r src/requirements-linux.txt
```

### 3. 应用 aiotieba 补丁

把 `aiotieba-fix-files/` 目录内的文件复制到虚拟环境的 `site-packages/aiotieba/` 下，并覆盖同名文件（Windows 为 `Lib/site-packages`，Linux 为 `lib/python3.x/site-packages`）。不要把 `aiotieba-fix-files/` 目录本身复制进去。

### 4. 补齐平台二进制依赖

- 音频解码库（语音播放使用，两个平台都需要）：
  - 在 `src/publics/audio_decoder/` 中编译生成 `tieba_audiodec.dll`（Windows）或 `libtieba_audiodec.so`（Linux）到 `src/binres/`。
  - 解码内核为内嵌的 minimp3（MP3，CC0）与 opencore-amr（AMR-NB，Apache-2.0），因此语音播放不再依赖 ffmpeg。
- Windows：
  - 分享功能需要在 `src/publics/winrt_url_share/` 中编译生成 `ShareBridge.dll` 到 `src/binres/`。
  - 登录/内置浏览器相关功能需要系统安装 WebView2 Runtime。
- Linux：
  - 无需 WebView2 与 `ShareBridge.dll`，可跳过上述步骤。

### 5. 运行应用

```bash
cd src
python main.py
```

### 平台差异（重要）

- 内置浏览器、网页登录、贴内视频播放基于 WebView2，目前仅 Windows 可用；`webview2.isWebView2Installed()` 在非 Windows 下固定返回 `False`，Linux 上这些功能不可用。改动相关代码时要确认非 Windows 下的降级行为。
- WinRT 分享、`toast.exe`/`windows_toasts` 通知、Aero/Mica/Acrylic 窗口效果均为 Windows 专用，非 Windows 下应静默跳过。
- 默认用户数据目录：Windows 为 `%USERPROFILE%/AppData/Local/TiebaDesktop`，Linux 为 `~/.local/share/TiebaDesktop`。
- Linux 打包会清理 `work_temp/binres` 中的 `.exe`/`.dll`，只保留 Linux 需要的二进制文件（无后缀名的可执行文件与 `.so` 动态库）。
- 语音播放器 `src/publics/audio_stream_player.py` 支持自由调整进度：`seek_to()` 会重新请求音频数据，
  并在解码器内跳过目标位置之前的 PCM（`tieba_dec_skip_pcm`），因此 mp3 与 amr-nb 都适用；
  播放位置通过 `positionChanged` 上报，界面进度条位于 `src/resf/thread_voice_item.ui`。

## 常用命令

以下命令从仓库根目录执行，先激活对应平台的虚拟环境（Windows：`.\.venv\Scripts\Activate.ps1`；Linux：`source .venv/bin/activate`）。

运行应用：

```bash
cd src
python main.py
```

其它常用启动方式：

```bash
cd src
python main.py --quiet            # 静默启动，仅显示托盘
python main.py --sign-all-forums  # 所有关注吧签到
python main.py --sign-grows       # 成长等级签到
python main.py --set-current-account --userid=YOUR_UID
python main.py --reset-udf --udf-path=YOUR_PATH
```

打包发布：

```powershell
# Windows
cd build-tools
python build.py --makefile .\build_config.json
```

```bash
# Linux
cd build-tools
python build.py --makefile ./build_config.json
```

构建前需要在 `build_config.json` 中把 `src_code_path`、`py_environ_path`、`sevenzip_path` 等路径改成本机实际值。Linux 下 `sevenzip_path` 通常为 `/usr/bin/7z`，应将 `installer_cfg.build_nsis` 设为 `false`，并按需设置 `build_deb`/`build_rpm`（需要系统已安装 `dpkg-deb`、`rpmbuild`）。构建脚本会创建 `build-tools/work_temp` 和 `build-tools/work_out`，Linux 打包时还会使用 `work_linux_temp`，这些目录已被 `.gitignore` 忽略。

## UI 与 protobuf 生成

Qt Designer 源文件位于 `src/resf/*.ui`，生成后的 Python 文件位于 `src/ui/*.py`。

生成 UI 文件（Windows 下用 `cd src\resf` 亦可）：

```bash
cd src/resf
python make.py
```

运行前请先修改 `src/resf/make.py` 中的 `PYUIC_PATH`，指向本机 `pyuic5`。

protobuf 源定义位于 `src/resf/protobuf/proto/`，生成后的 Python 文件位于 `src/proto/`。

生成 protobuf 文件：

```bash
cd src/resf/protobuf
python make.py
```

运行前请先修改 `src/resf/protobuf/make.py` 中的 `PROTOC_PATH`。

## 命令行参数行为

命令行功能集中在 `src/publics/cli_feats.py`：

- 第一层参数会影响内部配置，例如 `--reset-udf --udf-path=...`。
- 第二层参数执行写入性任务，并在完成后退出，例如 `--set-current-account`、`--uninstall-cleanup`。
- 第三层参数执行普通任务，并在完成后退出，例如 `--sign-all-forums`、`--sign-grows`。
- `--quiet` 是标记参数，可叠加使用；单独使用时会进入 GUI 模式但不弹出主窗口，仅创建托盘。

修改命令行任务时，要确认是否应该阻止 GUI 启动，并留意涉及账号、本地数据删除和系统弹窗的行为。注意 Windows 下提示与确认使用 `win32api.MessageBox`；非 Windows 下 `msgbox` 不会弹窗、`msgbox_ask` 固定返回 `False`（等同拒绝），改动交互逻辑时要留意这一差异。

## 数据与隐私

默认用户数据目录在 `src/consts.py` 中定义：

- Windows：`%USERPROFILE%/AppData/Local/TiebaDesktop`
- Linux：`$HOME/.local/share/TiebaDesktop`
- 其他系统：`./TiebaDesktop_UserData`

账号、登录态、偏好、缓存、历史记录等都属于敏感本地数据。开发和调试时不要提交真实用户数据，不要在日志、测试数据或 issue 输出中暴露 BDUSS、STOKEN、UID、Cookie、用户私密内容等信息。

## 代码修改指南

- 优先沿用现有代码风格和目录职责，避免把业务逻辑放进生成的 UI 文件。
- 修改界面结构时优先改 `src/resf/*.ui`，再生成 `src/ui/*.py`；如果只修生成文件，后续重新生成可能覆盖改动。
- `src/ui/` 内含大量资源文件和生成代码，改动前确认它是源文件还是生成产物。
- 网络请求相关改动优先放在 `src/publics/baidu_features/` 或既有 API 封装附近。
- 用户数据读写优先复用 `profile_mgr.py`、`account_mgr.py`、`cache_mgr.py` 等现有管理器。
- Windows 专有能力（WebView2、WinRT 分享、toast 通知、Aero/Mica/Acrylic 效果）必须保留平台判断，避免破坏 Linux 下的基本导入和运行；新增 Windows 专用依赖时只在 `os.name == 'nt'` 分支内导入。
- 调整依赖时同步检查 `src/requirements.txt` 与 `src/requirements-linux.txt`，不要把 Windows 专用库写进 Linux 清单。
- 修改 `build-tools/build.py` 的打包流程或 `binres` 清理规则时，确认 Windows 与 Linux 两条路径仍然可用。
- 不要随意更改 `consts.encrypt_key`、默认数据目录、账号数据结构和 protobuf 生成文件，除非同步处理迁移与兼容。
- 不要提交本地构建产物、虚拟环境、IDE 配置、`ShareBridge.dll`、`tieba_audiodec.dll`/`libtieba_audiodec.so` 或用户数据。
- 当前仓库未见统一测试套件；修改后至少运行受影响路径的应用入口或脚本，能做静态导入检查时也一并执行。

## Agent 工作建议

- 开始任务前先看 `git status --short`，保护用户已有改动。
- 搜索文件优先使用 `rg` 或 `rg --files`。
- 涉及运行应用、打包、安装依赖、下载文件或编译 C++ 时，先说明影响和本机依赖。
- 涉及删除用户数据、构建目录、生成文件或覆盖补丁文件时，先确认目标路径。
- 跨平台改动尽量在 Windows 与 Linux 上都验证；本地只有单一平台时，至少做静态导入检查，并在回复中说明未验证的平台。
- 修改 UI、protobuf 或构建配置后，在最终回复中明确说明是否重新生成、是否运行验证命令。
- 如果终端中文显示乱码，不要据此改写源码注释或文档编码；优先使用编辑器或 UTF-8 方式确认原文。

## 参考文档

- `README.md`：项目介绍、功能列表和目录概览。
- `docs/how-to-set-up-env.md`：开发环境配置。
- `docs/build-guide.md`：主程序构建指南（含 Linux deb/rpm 打包说明）。
- `docs/command-usages.md`：命令行启动参数说明。
