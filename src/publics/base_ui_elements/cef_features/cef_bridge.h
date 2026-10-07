// TiebaDesktop 的 CEF 原生桥接层（C ABI）。
//
// 这一层只做一件事：把 CEF 的 C++ API 包成一组扁平的 C 函数，
// 让 Python 侧（ctypes）可以驱动窗口化的 CEF 浏览器。
//
// 之所以不直接用 cefpython3：cefpython3 停留在很老的 CEF 版本且音视频支持受限，
// 而这里编译时链接的是你下载的 CEF 二进制发行版（版本可自由选择、尽量新）。
#ifndef TIEBADESKTOP_CEF_BRIDGE_H_
#define TIEBADESKTOP_CEF_BRIDGE_H_

#if defined(_WIN32)
#define CEF_BRIDGE_API extern "C" __declspec(dllexport)
#else
#define CEF_BRIDGE_API extern "C" __attribute__((visibility("default")))
#endif

// 事件类型，必须与 Python 侧 cef_webview.py 中的 CefEventType 保持一致
enum {
    CEF_BRIDGE_EVENT_CREATED = 1,        // 浏览器创建完成
    CEF_BRIDGE_EVENT_CLOSE = 2,          // 浏览器即将关闭
    CEF_BRIDGE_EVENT_LOAD_START = 3,     // 开始加载
    CEF_BRIDGE_EVENT_LOAD_END = 4,       // 加载完成
    CEF_BRIDGE_EVENT_LOAD_ERROR = 5,     // 加载失败，data 为错误描述
    CEF_BRIDGE_EVENT_TITLE = 6,          // 标题变化，data 为新标题
    CEF_BRIDGE_EVENT_URL = 7,            // 地址变化，data 为新地址
    CEF_BRIDGE_EVENT_STATUS = 8,         // 状态栏文本
    CEF_BRIDGE_EVENT_BRIDGE_MESSAGE = 9, // 页面通过 JS 桥发来的消息
    CEF_BRIDGE_EVENT_NEW_TAB = 10,       // 页面请求打开新窗口，data 为目标地址
    CEF_BRIDGE_EVENT_FULLSCREEN = 11,    // 全屏状态变化，data 为 "1"/"0"
    CEF_BRIDGE_EVENT_CONSOLE = 12,       // 页面控制台消息
    CEF_BRIDGE_EVENT_DEVTOOLS_CREATED = 14, // 开发者工具浏览器已创建
    CEF_BRIDGE_EVENT_DEVTOOLS_CLOSED = 15,  // 开发者工具浏览器已关闭

    CEF_BRIDGE_EVENT_FAVICON_URL = 16,      // favicon 地址变化，data 为图标 URL（空串表示没有图标）
    CEF_BRIDGE_EVENT_FAVICON_DATA = 17,     // cef_bridge_fetch_icon 的结果，data 为 base64 图标数据
    CEF_BRIDGE_EVENT_DOWNLOAD = 18,         // 下载事件，data 为 JSON（字段含义见 cef_webview.py）
};

// 事件回调：browser_id 为创建时传入的 id，event 为上面的枚举，data 为 UTF-8 字符串
typedef void (*cef_bridge_event_cb)(int browser_id, int event, const char* data);

// 初始化 CEF。返回 1 表示成功，0 表示失败。
//   cache_path      用户数据 / 缓存目录（UTF-8）
//   log_file        cef 日志文件路径，可为 NULL
//   resources_dir   资源目录（cef.pak 等），可为 NULL 表示与库同目录
//   locales_dir     locales 目录，可为 NULL
//   subprocess_path 子进程 helper 可执行文件路径，可为 NULL
//   user_agent      自定义 UA，可为 NULL
//   extra_args      追加到 CEF 命令行的参数（空格分隔），可为 NULL
CEF_BRIDGE_API int cef_bridge_init(const char* cache_path,
                                   const char* log_file,
                                   const char* resources_dir,
                                   const char* locales_dir,
                                   const char* subprocess_path,
                                   const char* user_agent,
                                   const char* extra_args);

CEF_BRIDGE_API int cef_bridge_is_initialized();

// 选择嵌入方式：1 = OSR 离屏渲染；0 = 原生子窗口（默认，需在 cef_bridge_init 之前调用）
CEF_BRIDGE_API void cef_bridge_set_windowless(int enabled);

CEF_BRIDGE_API void cef_bridge_set_event_callback(cef_bridge_event_cb cb);

// 驱动一次 CEF 消息循环（配合 CefSettings.external_message_pump 使用）
CEF_BRIDGE_API void cef_bridge_do_work();

// 关闭 CEF（进程退出前调用）
CEF_BRIDGE_API void cef_bridge_shutdown();

// 创建一个窗口化的浏览器，parent_handle 为宿主窗口句柄
// （Windows: HWND；Linux: X11 Window id，两者都取自 Qt 控件的 winId()）
// parent_handle 用 64 位，Windows 下 HWND 是 64 位，不能用 unsigned long 截断
CEF_BRIDGE_API int cef_bridge_create_browser(int browser_id,
                                             unsigned long long parent_handle,
                                             const char* url,
                                             int x, int y, int width, int height,
                                             const char* js_bridge_script,
                                             const char* user_agent);

CEF_BRIDGE_API void cef_bridge_resize(int browser_id, int x, int y, int width, int height);
CEF_BRIDGE_API void cef_bridge_set_visible(int browser_id, int visible);
CEF_BRIDGE_API void cef_bridge_load(int browser_id, const char* url);
CEF_BRIDGE_API void cef_bridge_load_string(int browser_id, const char* html, const char* url);
CEF_BRIDGE_API void cef_bridge_go_back(int browser_id);
CEF_BRIDGE_API void cef_bridge_go_forward(int browser_id);
CEF_BRIDGE_API int cef_bridge_can_go_back(int browser_id);
CEF_BRIDGE_API int cef_bridge_can_go_forward(int browser_id);
CEF_BRIDGE_API void cef_bridge_reload(int browser_id);
CEF_BRIDGE_API void cef_bridge_stop_load(int browser_id);
CEF_BRIDGE_API void cef_bridge_set_zoom(int browser_id, double level);
CEF_BRIDGE_API double cef_bridge_get_zoom(int browser_id);
CEF_BRIDGE_API void cef_bridge_set_muted(int browser_id, int muted);
CEF_BRIDGE_API int cef_bridge_is_muted(int browser_id);
CEF_BRIDGE_API void cef_bridge_execute_js(int browser_id, const char* code);
// 打开开发者工具。
// parent_handle 非 0 时把 devtools 浏览器以原生子窗口方式嵌入该句柄（推荐，
// 与主浏览器同一条已经验证过的渲染路径）；为 0 时退化成 CEF 自己创建的顶层弹窗。
// 返回 1 表示已发起创建，2 表示已经打开，0 表示失败。
CEF_BRIDGE_API int cef_bridge_open_devtools(int browser_id,
                                            unsigned long long parent_handle,
                                            int x, int y, int width, int height);
CEF_BRIDGE_API void cef_bridge_resize_devtools(int browser_id, int x, int y,
                                               int width, int height);
CEF_BRIDGE_API void cef_bridge_close_devtools(int browser_id);
CEF_BRIDGE_API int cef_bridge_has_devtools(int browser_id);

// ---------------------------------------------------------------- HTTP 请求 / 响应拦截
//
// 观察浏览器的请求与响应。kind：1 = 请求、2 = 响应；headers 为 "Name: Value\n" 逐行文本；
// body 只在本次回调期间有效（需要保留请自行复制）。
//
// 注意：CEF 的资源请求回调发生在 IO 线程，桥接层会把它排进队列、在 UI 线程（cef_bridge_do_work
// 的调用线程）再回调，因此 Python 侧可以安全地操作 Qt 对象；代价是「重写请求」不会被应用，
// 只能观察（与 Windows 端 onResponseCaught 的既有约定一致）。
typedef void (*cef_bridge_http_cb)(int browser_id, int kind, const char* url,
                                   const char* method, int status_code,
                                   const char* headers, const void* body, int body_len);

CEF_BRIDGE_API void cef_bridge_set_http_callback(cef_bridge_http_cb cb);
// 注册需要拦截的 URL 子串（用 '|' 分隔，'*' 表示拦截全部），需在 create_browser 之前调用
CEF_BRIDGE_API void cef_bridge_set_http_patterns(int browser_id, const char* patterns);

// ---------------------------------------------------------------- favicon
// 抓取图标二进制，完成后通过 CEF_BRIDGE_EVENT_FAVICON_DATA（base64）回传
CEF_BRIDGE_API void cef_bridge_fetch_icon(int browser_id, const char* icon_url);

// ---------------------------------------------------------------- 下载
// 下载事件通过 CEF_BRIDGE_EVENT_DOWNLOAD 回传（data 为 JSON）。
// 收到 state=1 时，必须在同一次回调里调用 download_continue 或 download_cancel 之一。
CEF_BRIDGE_API void cef_bridge_download_continue(int download_id, const char* path);
CEF_BRIDGE_API void cef_bridge_download_cancel(int download_id);
CEF_BRIDGE_API void cef_bridge_download_set_paused(int download_id, int paused);
CEF_BRIDGE_API void cef_bridge_download_cancel_by_id(int download_id);
CEF_BRIDGE_API void cef_bridge_print(int browser_id);
CEF_BRIDGE_API void cef_bridge_clear_cache(int browser_id);
CEF_BRIDGE_API void cef_bridge_clear_cookies(int browser_id);
CEF_BRIDGE_API char* cef_bridge_get_url(int browser_id);   // 需调用 cef_bridge_free_string 释放
CEF_BRIDGE_API char* cef_bridge_get_title(int browser_id);
CEF_BRIDGE_API int cef_bridge_get_pid(int browser_id);
CEF_BRIDGE_API void cef_bridge_free_string(char* text);
CEF_BRIDGE_API void cef_bridge_destroy_browser(int browser_id, int force_close);

// ---------------------------------------------------------------- OSR（离屏渲染）
//
// 浏览器以 windowless 模式创建，画面通过 paint 回调回传到上层（BGRA、物理像素），
// 输入事件通过下面的 mouse_*/key/set_focus 转发进去。
// 这样完全不涉及原生窗口句柄，Qt 侧怎么 reparent 控件都不会影响浏览器。
typedef void (*cef_bridge_paint_cb)(int browser_id, const void* buffer, int width, int height);

CEF_BRIDGE_API void cef_bridge_set_paint_callback(cef_bridge_paint_cb cb);
CEF_BRIDGE_API void cef_bridge_set_view_size(int browser_id, int width, int height);
CEF_BRIDGE_API void cef_bridge_set_focus(int browser_id, int focused);
CEF_BRIDGE_API void cef_bridge_mouse_move(int browser_id, int x, int y, int modifiers, int leave);
CEF_BRIDGE_API void cef_bridge_mouse_click(int browser_id, int x, int y, int modifiers,
                                           int button, int mouse_up, int click_count);
CEF_BRIDGE_API void cef_bridge_mouse_wheel(int browser_id, int x, int y, int modifiers,
                                           int delta_x, int delta_y);
CEF_BRIDGE_API void cef_bridge_key(int browser_id, int type, int key_code, int native_key_code,
                                   int modifiers, int is_system_key, int character);

// 子进程入口：当以 --type=xxx 启动时必须先调用（返回进程退出码）
CEF_BRIDGE_API int cef_bridge_execute_process(int argc, char** argv);

CEF_BRIDGE_API const char* cef_bridge_version();

#endif  // TIEBADESKTOP_CEF_BRIDGE_H_
