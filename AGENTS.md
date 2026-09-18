# AGENT.md

本文件面向参与 TiebaDesktop 开发的开发者与 Agent 工具，提供项目概览、常用命令、目录职责和修改注意事项。修改代码前请先阅读本文件，并优先遵循仓库已有模式。

## 项目概览

TiebaDesktop 是一个基于 Python 与 PyQt5 的第三方百度贴吧桌面客户端，主要面向 Windows 桌面体验。项目包含贴吧内容浏览、登录与多账号管理、签到、互动消息、用户主页、收藏/点赞/浏览历史、通知、内置浏览器、视频播放和若干 Windows 原生能力集成。

核心入口是 `src/main.py`。应用启动时会初始化用户数据目录、日志、代理、命令行任务、Qt 高 DPI 配置、翻译文件、WebView2 检查、WinRT 分享库、主题背景、主窗口和系统托盘。

## 技术栈与依赖

- 语言：Python 3.9+
- GUI：PyQt5
- 贴吧 API：`aiotieba==4.6.1`，并配套 `aiotieba-fix-files/` 中的补丁文件
- 网络与解析：`requests`、`beautifulsoup4`
- 加密与系统能力：`pycryptodome`、`pywin32`、`pythonnet`
- 音频与媒体：`pyaudio`、`src/binres/` 下的二进制资源
- Windows 通知：`windows_toasts`、`src/binres/toast.exe`
- 内置网页/登录相关：WebView2 运行时及 `src/binres/Microsoft.Web.WebView2.*.dll`
- 打包：PyInstaller、7-Zip，可选 NSIS

Windows 依赖见 `src/requirements.txt`，Linux 依赖见 `src/requirements-linux.txt`。本项目主要在 Windows 上开发，跨平台代码需要特别注意 `os.name` 判断和 Windows 专用依赖隔离。

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
- `src/binres/`：运行所需二进制资源，例如 WebView2、toast、ffmpeg 占位文件等。
- `aiotieba-fix-files/`：需要覆盖到虚拟环境 `site-packages/aiotieba` 的补丁文件。
- `build-tools/`：构建脚本、PyInstaller 版本信息、NSIS 脚本和构建配置示例。
- `docs/`：开发环境、构建、命令行参数说明和应用截图。

## 本地开发

推荐在 Windows 上开发与验证。

1. 创建虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. 安装依赖：

   ```powershell
   pip install -r src\requirements.txt
   ```

   Linux 环境使用：

   ```bash
   pip install -r src/requirements-linux.txt
   ```

3. 应用 `aiotieba` 补丁：

   将 `aiotieba-fix-files/` 目录内的文件复制到虚拟环境中的 `Lib/site-packages/aiotieba/`，遇到同名文件时以本仓库补丁文件覆盖。不要把 `aiotieba-fix-files/` 目录本身复制进去。

4. 补齐本地二进制依赖：

   - 用真实 `ffmpeg.exe` 替换 `src/binres/ffmpeg.exe` 占位文件。
   - Windows 分享功能需要在 `src/publics/winrt_url_share/` 中编译生成 `ShareBridge.dll` 到 `src/binres/`。非 Windows 平台可跳过。
   - 登录/内置浏览器相关功能需要系统安装 WebView2 Runtime。

5. 运行应用：

   ```powershell
   cd src
   python main.py
   ```

## 常用命令

从仓库根目录执行：

```powershell
.\.venv\Scripts\Activate.ps1
cd src
python main.py
```

静默启动 GUI，仅显示托盘：

```powershell
cd src
python main.py --quiet
```

执行所有关注吧签到：

```powershell
cd src
python main.py --sign-all-forums
```

执行成长等级签到：

```powershell
cd src
python main.py --sign-grows
```

切换当前账号：

```powershell
cd src
python main.py --set-current-account --userid=YOUR_UID
```

重定向用户数据目录：

```powershell
cd src
python main.py --reset-udf --udf-path=YOUR_PATH
```

打包发布：

```powershell
cd build-tools
python build.py --makefile .\build_config.json
```

打包前需要确认 `build-tools/build_config.json` 中的路径适配本机环境。构建脚本会创建 `build-tools/work_temp` 和 `build-tools/work_out`，这两个目录已被 `.gitignore` 忽略。

## UI 与 protobuf 生成

Qt Designer 源文件位于 `src/resf/*.ui`，生成后的 Python 文件位于 `src/ui/*.py`。

生成 UI 文件：

```powershell
cd src\resf
python make.py
```

运行前请先修改 `src/resf/make.py` 中的 `PYUIC_PATH`，指向本机 `pyuic5`。

protobuf 源定义位于 `src/resf/protobuf/proto/`，生成后的 Python 文件位于 `src/proto/`。

生成 protobuf 文件：

```powershell
cd src\resf\protobuf
python make.py
```

运行前请先修改 `src/resf/protobuf/make.py` 中的 `PROTOC_PATH`。

## 命令行参数行为

命令行功能集中在 `src/publics/cli_feats.py`：

- 第一层参数会影响内部配置，例如 `--reset-udf --udf-path=...`。
- 第二层参数执行写入性任务，并在完成后退出，例如 `--set-current-account`、`--uninstall-cleanup`。
- 第三层参数执行普通任务，并在完成后退出，例如 `--sign-all-forums`、`--sign-grows`。
- `--quiet` 是标记参数，可叠加使用；单独使用时会进入 GUI 模式但不弹出主窗口，仅创建托盘。

修改命令行任务时，要确认是否应该阻止 GUI 启动，并留意涉及账号、本地数据删除和系统弹窗的行为。

## 数据与隐私

默认用户数据目录在 `src/consts.py` 中定义：

- Windows：`%USERPROFILE%/AppData/Local/TiebaDesktop`
- 其他系统：`./TiebaDesktop_UserData`

账号、登录态、偏好、缓存、历史记录等都属于敏感本地数据。开发和调试时不要提交真实用户数据，不要在日志、测试数据或 issue 输出中暴露 BDUSS、STOKEN、UID、Cookie、用户私密内容等信息。

## 代码修改指南

- 优先沿用现有代码风格和目录职责，避免把业务逻辑放进生成的 UI 文件。
- 修改界面结构时优先改 `src/resf/*.ui`，再生成 `src/ui/*.py`；如果只修生成文件，后续重新生成可能覆盖改动。
- `src/ui/` 内含大量资源文件和生成代码，改动前确认它是源文件还是生成产物。
- 网络请求相关改动优先放在 `src/publics/baidu_features/` 或既有 API 封装附近。
- 用户数据读写优先复用 `profile_mgr.py`、`account_mgr.py`、`cache_mgr.py` 等现有管理器。
- Windows 专有能力必须保留平台判断，避免破坏 Linux/macOS 下的基本导入和运行。
- 不要随意更改 `consts.encrypt_key`、默认数据目录、账号数据结构和 protobuf 生成文件，除非同步处理迁移与兼容。
- 不要提交本地构建产物、虚拟环境、IDE 配置、`ShareBridge.dll`、真实 `ffmpeg.exe` 或用户数据。
- 当前仓库未见统一测试套件；修改后至少运行受影响路径的应用入口或脚本，能做静态导入检查时也一并执行。

## Agent 工作建议

- 开始任务前先看 `git status --short`，保护用户已有改动。
- 搜索文件优先使用 `rg` 或 `rg --files`。
- 涉及运行应用、打包、安装依赖、下载文件或编译 C++ 时，先说明影响和本机依赖。
- 涉及删除用户数据、构建目录、生成文件或覆盖补丁文件时，先确认目标路径。
- 修改 UI、protobuf 或构建配置后，在最终回复中明确说明是否重新生成、是否运行验证命令。
- 如果终端中文显示乱码，不要据此改写源码注释或文档编码；优先使用编辑器或 UTF-8 方式确认原文。

## 参考文档

- `README.md`：项目介绍、功能列表和目录概览。
- `docs/how-to-set-up-env.md`：开发环境配置。
- `docs/build-guide.md`：主程序构建指南。
- `docs/command-usages.md`：命令行启动参数说明。
