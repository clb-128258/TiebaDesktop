# 贡献指南

感谢你愿意参与 TiebaDesktop 的开发。为了让项目保持稳定、易维护，也方便作者和其他贡献者 review，请在提交 issue、PR 或使用 agent 修改代码前阅读本指南。

## 参与前须知

- 提交 Bug 前，请先确认问题没有被他人反馈过，并尽量使用最新版本复现。
- 提交功能建议前，请先确认类似需求没有被提出过，并说明使用场景和预期效果。
- 进行代码贡献前，建议先阅读仓库根目录的 `AGENT.md`、`README.md` 以及 `docs/` 下的开发与构建文档。
- 本项目主要面向 Windows 桌面环境开发。涉及系统能力、通知、WebView2、WinRT 分享、路径和进程控制时，请特别注意平台兼容。

## 开发环境

推荐使用 Python 3.9+ 和 Windows 环境。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r src\requirements.txt
```

Linux 环境可使用：

```bash
pip install -r src/requirements-linux.txt
```

安装依赖后，需要将 `aiotieba-fix-files/` 中的内容复制到虚拟环境的 `Lib/site-packages/aiotieba/`，用本仓库补丁覆盖同名文件。不要提交虚拟环境、site-packages、本地账号数据或构建产物。

部分功能还需要本地补齐：

- 用真实 `ffmpeg.exe` 替换 `src/binres/ffmpeg.exe` 占位文件。
- Windows 分享功能需要编译 `src/publics/winrt_url_share/`，生成 `src/binres/ShareBridge.dll`。
- 登录和内置浏览器相关功能依赖 WebView2 Runtime。

## 分支与提交

- 请从最新主分支创建功能分支后再开发。
- 一次 PR 聚焦一个问题或一个功能，避免混合重构、格式化和无关改动。
- 提交信息应简洁说明改动目的，例如 `fix: 修复签到失败提示`、`feat: 增加帖子筛选选项`。
- 不要提交 `.venv/`、`.idea/`、`.vscode/`、`build-tools/work_temp/`、`build-tools/work_out/`、`ShareBridge.dll`、真实 `ffmpeg.exe`、用户数据、日志或账号凭据。

## 代码规范

- 优先沿用现有代码风格、命名方式和模块边界，具体包括：
  - Python 文件、函数、变量、模块名使用现有的 `snake_case` 风格，例如 `tieba_apis.py`、`get_current_user()`、`signed_count`。
  - 类名使用 `PascalCase`，并尽量延续已有语义命名，例如 `MainWindow`、`TrayIcon`、`CliFunctions`、各类页面和 item 组件。
  - 常量放在 `src/consts.py` 或就近模块顶部，使用大写或项目已有命名方式；不要把全局配置散落到业务函数中。
  - UI 类、窗口类、业务页面类继续放在 `src/subwindow/` 或既有同类文件中；公共工具、数据管理、系统集成能力放在 `src/publics/`。
  - 贴吧/百度接口封装放在 `src/publics/baidu_features/`，不要在 UI 事件处理函数中直接堆叠复杂 HTTP 请求逻辑。
  - 账号、配置、缓存、日志、代理、通知等横向能力应复用现有 manager/helper，不要新增平行的数据存储方案。
  - 文件命名尽量与功能对象一致：窗口/页面使用业务名，列表项使用 `*_item.py`，详情页使用 `*_detail*.py`，选择器使用 `*_selector.py`。
  - 新增代码应保持当前项目“函数直接、模块清楚”的风格；只有在能明显减少重复或隔离复杂状态时再抽象新类或新层。
- 业务逻辑应放在 `src/subwindow/`、`src/publics/` 或既有业务模块中，不要写进由 Qt 生成的 UI 文件。
- 网络请求与贴吧/百度接口相关改动，优先放在 `src/publics/baidu_features/` 或已有封装附近。
- 用户数据、账号、缓存读写优先复用 `profile_mgr.py`、`account_mgr.py`、`cache_mgr.py` 等现有管理器。
- Windows 专用代码必须加平台判断，避免在非 Windows 平台导入时直接失败。
- 异步接口调用应保持现有 `asyncio` 与 `aiotieba.Client` 用法，不要在 UI 线程中加入长时间阻塞操作。
- 日志用于定位问题，但不要记录 BDUSS、STOKEN、Cookie、私信、用户隐私内容或其他敏感信息。
- 不要随意修改 `src/consts.py` 中的数据目录、加密 key、版本号和请求 header；如确需修改，请说明兼容性影响。

## UI 与资源修改

- Qt Designer 源文件位于 `src/resf/*.ui`，生成后的 Python UI 文件位于 `src/ui/*.py`。
- 修改界面结构时，优先修改 `.ui` 源文件，并运行生成脚本：

  ```powershell
  cd src\resf
  python make.py
  ```

- 运行前请根据本机环境修改 `src/resf/make.py` 中的 `PYUIC_PATH`。
- 如果只修改 `src/ui/*.py`，请在 PR 中说明原因，因为后续重新生成可能覆盖这些改动。
- 添加图片、图标、表情、QSS 或播放器资源时，请放在现有资源目录内，并避免引入未经授权或体积过大的文件。

## protobuf 修改

protobuf 源定义位于 `src/resf/protobuf/proto/`，生成文件位于 `src/proto/`。

修改 `.proto` 后运行：

```powershell
cd src\resf\protobuf
python make.py
```

运行前请根据本机环境修改 `src/resf/protobuf/make.py` 中的 `PROTOC_PATH`。提交 PR 时，请同时提交源 `.proto` 与生成后的 Python 文件，并说明兼容性影响。

## 命令行功能

命令行参数处理集中在 `src/publics/cli_feats.py`。新增或修改参数时请注意：

- 写入性任务执行后通常应阻止 GUI 启动并退出进程。
- `--quiet` 是标记参数，可与其他参数叠加。
- 涉及账号切换、用户数据删除、签到、系统弹窗的行为必须清晰、可预期。
- 删除数据、结束进程等高风险操作必须保留确认或明确触发条件。

## 构建与验证

本地运行：

```powershell
cd src
python main.py
```

打包构建：

```powershell
cd build-tools
python build.py --makefile .\build_config.json
```

打包前请确认 `build-tools/build_config.json` 中的路径适配本机环境。构建会生成 `build-tools/work_temp/` 与 `build-tools/work_out/`，不要提交这些目录。

项目目前未提供统一自动化测试套件。提交前请至少完成与改动相关的手工验证，并在 PR 中说明验证方式。建议包括：

- 应用能从 `src/main.py` 正常启动。
- 修改过的页面、按钮、弹窗、托盘或命令行参数能按预期工作。
- 涉及登录、发帖、签到、删除数据、系统通知等功能时，已验证失败路径和提示文案。
- 涉及构建脚本或二进制依赖时，说明是否执行过打包构建。

## Pull Request 要求

PR 描述建议包含：

- 改动目的：修复了什么问题或增加了什么能力。
- 主要改动：列出关键文件或模块。
- 验证方式：写明运行过的命令、手工测试路径和结果。
- 风险与兼容性：说明是否影响账号数据、配置格式、缓存、构建流程或平台兼容。
- 截图或录屏：涉及 UI 改动时请尽量提供。

请保持 diff 聚焦、可 review。若 PR 中包含生成文件，请说明对应源文件和生成命令。

## Issue 提交规范

Bug 报告请尽量提供：

- 复现步骤和预期行为。
- 最新日志文件：主窗口右上角 -> 软件设置 -> 调试诊断 -> 打开日志文件夹。
- 诊断信息截图：主窗口右上角 -> 软件设置 -> 调试诊断 -> 诊断信息。
- 操作系统版本、TiebaDesktop 版本、WebView2/.NET 等相关运行库版本。
- 必要的截图或录屏。

功能建议请说明：

- 该功能解决什么实际问题。
- 期望的交互或使用流程。
- 是否有替代方案。
- 是否涉及贴吧账号安全、隐私、自动化操作或平台规则风险。

## 安全与隐私

- 不要上传 BDUSS、STOKEN、Cookie、账号导出文件、日志中的敏感片段、私信或用户隐私内容。
- 不要把本地用户数据目录作为测试样例提交。
- 涉及自动签到、发帖、用户管理、数据清理等功能时，应谨慎处理错误提示、频率控制和用户确认。
- 如发现安全问题，请优先用私密渠道联系维护者，不要在公开 issue 中披露可被滥用的细节。

## Agent 使用规范

如果使用 agent 辅助开发：

- 修改前先检查 `git status --short`，不要覆盖他人或用户已有改动。
- 优先阅读相关文件和 `AGENT.md`，再做最小必要修改。
- 文件搜索优先使用 `rg` 或 `rg --files`。
- 不要擅自运行会删除数据、覆盖依赖、安装软件、下载文件或触发账号操作的命令。
- 修改 UI/protobuf 后，明确说明是否重新生成。
- 最终说明应包含改动摘要和已执行的验证命令。
