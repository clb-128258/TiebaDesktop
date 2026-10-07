# CEF WebView（Windows / Linux 通用）

本目录提供 TiebaDesktop 的 CEF 内核 webview，用于：

- Linux 端的内置浏览器 / 网页登录 / 贴内视频播放；
- Windows 端**没有安装 WebView2** 时的备选方案。

它与 `windows_features/webview2.py` 提供完全一致的调用接口，业务代码统一通过
`publics/base_ui_elements/common_webview.py` 调用，不需要关心底层用的是哪套内核。

## 为什么不用 cefpython3

`cefpython3` 停留在很老的 CEF 版本（CEF 66），音视频支持受限，也无法跟上官方的
安全更新。这里改为**自己写一层很薄的 native 桥接库**（`cef_bridge.cpp`），编译时链接你下载的 CEF 二进制发行版，因此：

- CEF 版本可以自由选择，**尽量用官方最新稳定版**；
- 官方发行版自带 `libffmpeg`（含 H.264 / AAC），**音视频播放可用**；
- 桥接层只暴露一组扁平的 C 函数，Python 侧用 `ctypes` 调用，不需要额外的 Python 依赖。

## 当前使用的 CEF 版本

本仓库编译并验证过的版本是 **CEF 109.1.18（Chromium 109.0.5414.120）**：

- 该发行版仍然兼容 **Windows 7**；
- 自带 `libffmpeg`（H.264 / AAC 等 proprietary codecs），贴内视频可以直接播放。

Windows 下 `run_build.bat` 默认就用这个目录编译桥接层；需要换版本时，在运行前设置环境变量
`CEF_ROOT` 覆盖即可（更新的 CEF 版本同样能编译，只是不再支持 Windows 7）。

## 文件说明

| 文件                                 | 说明                                             |
|------------------------------------|------------------------------------------------|
| `cef_bridge.h` / `cef_bridge.cpp`  | 桥接动态库，封装 CEF 的浏览器、事件、导航、Cookie 等能力             |
| `cef_bridge_helper.cpp`            | CEF 子进程入口（CEF 是多进程架构，需要它来跑渲染/GPU/网络子进程）        |
| `CMakeLists.txt`                   | 桥接库与 helper 的构建配置                              |
| `build_linux.sh` / `run_build.bat` | 一键构建脚本（会编译并拷贝产物到 `src/binres`）                 |
| `cef_webview.py`                   | Python 侧封装：ctypes 绑定 + Qt 控件，接口与 WebView2 版本一致 |

## 依赖

1. **CEF 二进制发行版**：从 <https://cef-builds.spotifycdn.com/index.html> 下载与你平台匹配的
   “Standard Distribution”（Windows 选 windows64，Linux 选 linux64），解压到任意目录。
   建议选择当前最新的 stable 分支。
2. **构建工具**：CMake 3.15+ 与 C++17 编译器（Windows 用 MSVC，Linux 用 gcc/g++）。
3. （Linux）系统需要 `libx11-dev`（桥接层用它管理 CEF 子窗口）。

## 构建桥接层

> 想一次性编译所有 C++ 组件（音频解码库 + CEF 桥接库），可以直接运行
> `src/build-all.sh`（Linux）或 `src\build-all.bat`（Windows）。

### Linux

```bash
cd src/publics/base_ui_elements/cef_features
CEF_ROOT=/opt/cef_binary_xxx_linux64 ./build_linux.sh
```

> 也可以直接 `./build_linux.sh /opt/cef_binary_xxx_linux64` 而不设置 `CEF_ROOT`。

产物：

- `src/binres/cef/libcef_bridge.so`
- `src/binres/cef/cef_bridge_helper`

以及脚本复制来的 Chromium 二进制文件。

### Windows（先执行 `vcvars64.bat`）

```bat
cd src\publics\base_ui_elements\cef_features
set CEF_ROOT=D:\cef_binary_xxx_windows64
run_build.bat
```

> 也可以直接 `run_build.bat D:\cef_binary_xxx_windows64` 而不设置 `CEF_ROOT`。

产物：

- `src\binres\cef\cef_bridge.dll`
- `src\binres\cef\cef_bridge_helper.exe`

以及脚本复制来的 Chromium 二进制文件。

> CEF 的 C++ 封装库（`libcef_dll_wrapper`）由 CMake 脚本自动编译。若你使用的 CEF 版本
> 目录结构与脚本假设不同（例如已自带 `libcef_dll_wrapper.lib`），按报错提示调整
> `CMakeLists.txt` 即可。

## 启用与降级

- 找不到 `binres/cef_bridge*` 或 `binres/cef/libcef*` 时，`isWebViewInstalled()` 返回 `False`，
  程序照常启动（内置浏览器、网页登录降级为二维码登录）。
  也就是说**程序本体可以脱离 CEF 运行**。
- Linux 下 CEF 以子窗口方式嵌入 Qt 需要 X11（Wayland 会话走 XWayland），程序会自动选择 xcb。

## 打包：可选集成 CEF

`build-tools/build_config.json` 中的 `cef_cfg`：

```json
"cef_cfg": {
"bundle_cef": false
}
```

- `bundle_cef = false`：**不集成 CEF**，打包时会主动把 `binres/cef` 从产物里删掉（控制体积），用户端没有 CEF 时自动降级

CEF 运行时有 100~200 MB，是否集成直接决定安装包体积，因此默认是关闭的。

## 与 CEF 版本共存

桥接层直接使用 CEF 的 C++ API，因此必须用**同一份 CEF 发行版的头文件**编译。CEF 的
构建脚本与少数 API 签名会随版本调整，遇到问题时按下面处理：

- **需要 C++20**：CEF 的头文件使用了 `std::convertible_to` 等 C++20 concepts，用 C++17 编译会报
  `<concepts> 只 … C++20 起可用` / `convertible_to` 语法错误。本目录的 `CMakeLists.txt` 已设置
  `CMAKE_CXX_STANDARD 20`；若你使用的 CEF 版本还要更新（用到 C++23 特性），把它改成 `23` 即可。
- 配置阶段报 `Use find_package(CEF) to load this file.`：说明 CEF 版本较新，本目录的
  `CMakeLists.txt` 已经改用 `find_package(CEF REQUIRED)`，保持这样即可；
- 报找不到 `libcef_dll_wrapper`：确认 `CEF_ROOT` 指向解压后的 CEF 根目录，脚本会自动
  在 `libcef_dll/` 与 `libcef_dll/libcef_dll_wrapper/` 两种布局中查找；
- 编译期报某个 handler 函数「does not override」：说明该版本调整了虚函数签名，按编译器
  提示修正 `cef_bridge.cpp` 中对应函数的参数列表即可（常见于 `OnBeforePopup`、
  `ShowDevTools` 这类接口）。

## 嵌入方式与子进程

- **子进程必须使用独立的 `cef_bridge_helper.exe`**（`cef_bridge_init` 的 `subprocess_path`）。
  如果把该参数留空让 CEF 复用主程序，CEF 会以 `python.exe --type=renderer` 之类的形式拉子进程，
  而 `python.exe` 会在解析命令行时直接报 `unknown option --type=...` 退出，
  Chromium 随即 `FATAL: GPU process isn't usable. Goodbye.` 让整个进程崩溃（退出码 0x80000003）。
- 嵌入方式默认是**窗口化**（`CefWindowInfo::SetAsChild` + Alloy 风格，与 cefpython `examples/qt.py` 一致）；
  需要离屏渲染时设置环境变量 `TIEBADESKTOP_CEF_OSR=1`（走 `CefRenderHandler::OnPaint` + 输入转发）。
- 窗口化嵌入要求控件**先 show 出来**再创建浏览器（原生窗口句柄稳定之后），
  因此业务代码应先 `add_widget/show`，再调用 `initRender()`。

## 开发者工具（DevTools）

`openDevtoolsWindow()` **不使用** CEF 自带的 devtools 弹窗（`ShowDevTools` + `SetAsPopup`）：
那套窗口在部分 Windows 环境下只会显示一片空白（窗口能右键、能点到关闭按钮，但没有任何内容）。

现在的做法是：由 Qt 提供一个顶层窗口，再把 devtools 浏览器以**原生子窗口**（`SetAsChild`）
的方式嵌进去，和主浏览器走完全相同的渲染路径，因此不会再白屏，窗口缩放也会同步。

另外要注意一个 CEF 的行为：**devtools 浏览器只有在承载它的原生窗口被销毁后才会真正关闭**。
只调用 `CloseDevTools()` / `CloseBrowser()` 时它会一直存活（`HasDevTools()` 始终为 true），
最终让 `CefShutdown()` 以 `access violation (reading 0x10)` 崩溃，进程异常退出。
因此承载 devtools 的 Qt 窗口带 `WA_DeleteOnClose`，关闭即销毁窗口，CEF 随之完成清理；
`__teardown_partial()` 里也一定先销毁该窗口，再销毁宿主浏览器。

## 内置浏览器能力

- **favicon**：`OnFaviconURLChange` 拿到图标地址后，桥接层用浏览器自己的请求上下文抓二进制，
  Python 侧转成 `QIcon`；`iconChanged` / `iconUrlChanged` 与 Windows 端行为一致；
- **HTTP 观察**：`profile.http_rewriter` 里登记的 URL 会被桥接层拦截，请求（带真实 `Cookie`
  请求头）与响应（状态码 / 响应头 / 响应体）都会回调到 `onRequestCaught` / `onResponseCaught`，
  登录取 token、发贴验证码都依赖它；
- **下载**：点击下载链接会从右上角弹出 Chrome 风格的下载气泡（默认下载到系统「下载」目录），
  按条目显示文件名 / 进度 / 大小 / 状态，支持打开 / 定位 / 暂停 / 取消 / 清除已结束；
- **任务管理器**：右键菜单里的「任务管理器」会列出本程序与全部 CEF 子进程（类型 / PID / 内存 / CPU），
  可以结束单个子进程；
- 上面两个窗口都接入了项目的 base_ui 主题系统（背景 / 文字 / 图标随主题方案变化），
  任务管理器与其它窗口一样继承 `base_ui.WindowBaseQDialog`；
- **另存为网页**：把当前页面的 HTML 源码保存到本地。

## 已知限制

- 「另存为网页」保存的是当前页面的 HTML 源码（`document.documentElement.outerHTML`），
  不会把图片 / CSS 等子资源一起打包（CEF 没有提供 Chromium 那套「保存完整网页」的能力）；
- `HttpDataRewriter` 的返回值不会用来重写请求 / 响应，只能用来观察：CEF 的资源回调发生在 IO
  线程，桥接层把回调切回 UI 线程时请求 / 响应已经发出。响应体最多保留 4MB；
- 任务管理器只能按系统进程列出 CEF 子进程（CEF 没有公开「标签页 ↔ 渲染进程」的对应关系），
  因此看不到每个标签页的标题；
- 各账号的 webview 数据目录暂时共用一份 CEF 缓存（`profile.data_folder`），
  多账号之间的浏览器登录态未做隔离；
- 「清理 webview 缓存」在 CEF 后端下暂为空实现（CefRequestContext::ClearHttpCache 的签名随版本变化），清理 Cookie / DOM 存储仍然有效。