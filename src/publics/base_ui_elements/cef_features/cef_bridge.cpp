// CEF 原生桥接层实现，详见 cef_bridge.h
#include "cef_bridge.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <vector>
#include <deque>
#include <mutex>

#include <map>
#include <string>

#include "include/cef_download_handler.h"
#include "include/cef_request_handler.h"
#include "include/cef_resource_request_handler.h"
#include "include/cef_response.h"
#include "include/cef_response_filter.h"
#include "include/cef_urlrequest.h"

#include <stdio.h>

#if !defined(_WIN32)
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#include "include/cef_app.h"
#include "include/cef_browser.h"
#include "include/cef_client.h"
#include "include/cef_command_line.h"
#include "include/cef_context_menu_handler.h"
#include "include/cef_cookie.h"
#include "include/cef_frame.h"
#include "include/cef_menu_model.h"
#include "include/cef_values.h"
#include "include/cef_request_context.h"
#include "include/cef_version.h"

#if defined(_WIN32)
#include <windows.h>
// windows.h 会把这些名字定义成宏，导致 CEF 的同名方法（如 CefFrame::LoadString）无法编译
#undef LoadString
#undef LoadImage
#undef GetMessage
#undef CreateWindow
#undef CreateDialog
#undef DrawText
#else
#include <X11/Xlib.h>
#endif

#include <sstream>

namespace {

// ---------------------------------------------------------------- 字符串工具

std::string ToUtf8(const CefString& value) {
  return value.ToString();
}

CefString FromUtf8(const char* text) {
  if (!text)
    return CefString();
#if defined(_WIN32)
  // Windows 下 CefString(const char*) 按本地 ANSI 解释，这里显式做 UTF-8 -> UTF-16
  const int size = ::MultiByteToWideChar(CP_UTF8, 0, text, -1, nullptr, 0);
  if (size <= 0)
    return CefString();
  std::wstring wide(static_cast<size_t>(size - 1), L'\0');
  ::MultiByteToWideChar(CP_UTF8, 0, text, -1, &wide[0], size);
  return CefString(wide.c_str());
#else
  return CefString(std::string(text));
#endif
}

// 用于把 HTML 转成 data: URL（CEF 154 已移除 CefFrame::LoadString）
std::string Base64Encode(const std::string& input) {
  static const char kTable[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string output;
  output.reserve(((input.size() + 2) / 3) * 4);

  size_t i = 0;
  while (i + 2 < input.size()) {
    const uint32_t n = (static_cast<uint8_t>(input[i]) << 16) |
                       (static_cast<uint8_t>(input[i + 1]) << 8) |
                       static_cast<uint8_t>(input[i + 2]);
    output.push_back(kTable[(n >> 18) & 0x3F]);
    output.push_back(kTable[(n >> 12) & 0x3F]);
    output.push_back(kTable[(n >> 6) & 0x3F]);
    output.push_back(kTable[n & 0x3F]);
    i += 3;
  }

  const size_t remain = input.size() - i;
  if (remain == 1) {
    const uint32_t n = static_cast<uint8_t>(input[i]) << 16;
    output.push_back(kTable[(n >> 18) & 0x3F]);
    output.push_back(kTable[(n >> 12) & 0x3F]);
    output.append("==");
  } else if (remain == 2) {
    const uint32_t n = (static_cast<uint8_t>(input[i]) << 16) |
                       (static_cast<uint8_t>(input[i + 1]) << 8);
    output.push_back(kTable[(n >> 18) & 0x3F]);
    output.push_back(kTable[(n >> 12) & 0x3F]);
    output.push_back(kTable[(n >> 6) & 0x3F]);
    output.push_back('=');
  }

  return output;
}

char* AllocUtf8(const std::string& text) {
  char* buffer = static_cast<char*>(malloc(text.size() + 1));
  if (!buffer)
    return nullptr;
  memcpy(buffer, text.c_str(), text.size() + 1);
  return buffer;
}

CefWindowHandle ToWindowHandle(unsigned long long handle) {
#if defined(_WIN32)
  return reinterpret_cast<CefWindowHandle>(static_cast<uintptr_t>(handle));
#else
  return static_cast<CefWindowHandle>(handle);
#endif
}

// ---------------------------------------------------------------- 全局状态

// 事件码由 cef_bridge.h 中的 CEF_BRIDGE_EVENT_* 定义，这里是 Python 侧用到的扩展事件
const int kEventCookies = 13;

cef_bridge_event_cb g_event_cb = nullptr;
cef_bridge_paint_cb g_paint_cb = nullptr;
bool g_initialized = false;
std::map<int, CefRect> g_view_rects;

// 防止消息泵重入：
//   1) CreateBrowserSync / CloseBrowser / CefShutdown 内部会自己泵消息；
//   2) 它们泵到的是 Qt 的定时器消息，于是我们 4ms 的泵会在 CEF 调用内部重入；
//   3) 重入 CefDoMessageLoopWork 会让 Chromium 直接 CHECK 崩溃（STATUS_BREAKPOINT）。
bool g_in_pump = false;
bool g_windowless = false;  // 默认窗口化嵌入（SetAsChild）
bool g_in_cef_call = false;

struct CefCallGuard {
  CefCallGuard() { g_in_cef_call = true; }
  ~CefCallGuard() { g_in_cef_call = false; }
};
std::string g_extra_args;

std::map<int, CefRefPtr<CefBrowser>> g_browsers;
// 宿主 browser_id -> 关联的开发者工具浏览器（不放进 g_browsers，避免抢占 id 映射）
std::map<int, CefRefPtr<CefBrowser>> g_devtools;
std::map<int, std::string> g_bridge_scripts;
std::map<int, std::string> g_titles;

void EmitEvent(int browser_id, int event, const std::string& data) {
  if (g_event_cb)
    g_event_cb(browser_id, event, data.c_str());
}

// 注意：这些辅助函数必须返回 CefRefPtr（强引用）。
// 之前返回裸指针时，临时 CefRefPtr 在返回时析构，调用方拿到的是可能已失效的对象，
// 表现为「一 resize / 一调用 CEF API 就崩溃」。
CefRefPtr<CefBrowser> BrowserById(int browser_id) {
  const auto it = g_browsers.find(browser_id);
  if (it == g_browsers.end())
    return nullptr;
  return it->second;
}

CefRefPtr<CefBrowserHost> HostById(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  return browser ? browser->GetHost() : nullptr;
}

CefRefPtr<CefFrame> MainFrameById(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  return browser ? browser->GetMainFrame() : nullptr;
}

// ---------------------------------------------------------------- 平台窗口操作

#if !defined(_WIN32)
Display* XDisplay() {
  static Display* display = XOpenDisplay(nullptr);
  return display;
}
#endif

// 让消息泵之间插入一点真实等待时间：关闭渲染进程需要时间（IPC + 子进程退出），
// 光靠密集地调用 CefDoMessageLoopWork() 会在子进程真正结束前就退出循环。
void SleepMs(int ms) {
#if defined(_WIN32)
  ::Sleep(static_cast<DWORD>(ms));
#else
  struct timespec ts;
  ts.tv_sec = ms / 1000;
  ts.tv_nsec = static_cast<long>(ms % 1000) * 1000000L;
  nanosleep(&ts, nullptr);
#endif
}
void MoveResizeWindow(CefWindowHandle handle, int x, int y, int width, int height) {
  if (!handle)
    return;
#if defined(_WIN32)
  ::MoveWindow(handle, x, y, width, height, TRUE);
#else
  Display* display = XDisplay();
  if (display) {
    XMoveResizeWindow(display, handle, x, y, width, height);
    XFlush(display);
  }
#endif
}

void ShowHideWindow(CefWindowHandle handle, bool visible) {
  if (!handle)
    return;
#if defined(_WIN32)
  ::ShowWindow(handle, visible ? SW_SHOW : SW_HIDE);
#else
  Display* display = XDisplay();
  if (!display)
    return;
  if (visible)
    XMapWindow(display, handle);
  else
    XUnmapWindow(display, handle);
  XFlush(display);
#endif
}

// ---------------------------------------------------------------- JS 桥

// 页面里的 chrome.webview.postMessage 由注入的 shim 转成带前缀的 console.log，
// 这里再解析出来交回 Python（避免实现 render process 侧的 V8 handler）。
const char kBridgePrefix[] = "__TIEBA_BRIDGE__";

const char kDefaultBridgeScript[] =
    "(function(){"
    "function dispatch(msg){try{console.log('__TIEBA_BRIDGE__'+String(msg));}catch(e){}}"
    "try{if(!window.chrome){window.chrome={};}}catch(e){}"
    "try{window.chrome=window.chrome||{};"
    "window.chrome.webview=window.chrome.webview||{};"
    "window.chrome.webview.postMessage=dispatch;"
    "if(!window.chrome.webview.addEventListener){window.chrome.webview.addEventListener=function(){};}"
    "if(!window.chrome.webview.removeEventListener){window.chrome.webview.removeEventListener=function(){};}"
    "}catch(e){}})();";



// ---------------------------------------------------------------- HTTP 拦截 / 下载状态

// 需要在 UI 线程回调 Python 的请求 / 响应（CEF 的资源回调发生在 IO 线程）
struct PendingHttp {
  int browser_id = 0;
  int kind = 0;  // 1 = 请求，2 = 响应
  std::string url;
  std::string method;
  int status_code = 0;
  std::string headers;
  std::string body;
};

std::mutex g_http_mutex;
std::deque<PendingHttp> g_http_queue;
cef_bridge_http_cb g_http_cb = nullptr;
// browser_id -> 需要拦截的 URL 子串（"*" 表示全部）
std::map<int, std::vector<std::string>> g_http_patterns;

// 下载：OnBeforeDownload 需要同步拿到 Python 决定的保存路径
std::map<uint32, CefRefPtr<CefDownloadItemCallback>> g_download_callbacks;
int g_download_pending_id = -1;
std::string g_download_pending_path;
bool g_download_pending_cancel = false;

// 单次响应最多保留多少字节（避免大文件把内存吃满）
const size_t kMaxResponseBodyBytes = 4u * 1024u * 1024u;

std::string JsonEscape(const std::string& text) {
  std::string out;
  out.reserve(text.size() + 16);
  for (char ch : text) {
    switch (ch) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(ch) < 0x20)
          out += ' ';
        else
          out += ch;
    }
  }
  return out;
}

std::string SerializeHeaderMap(const CefRequest::HeaderMap& headers) {
  std::string out;
  for (const auto& kv : headers) {
    out += ToUtf8(kv.first);
    out += ": ";
    out += ToUtf8(kv.second);
    out += '\n';
  }
  return out;
}

bool ShouldIntercept(int browser_id, const std::string& url) {
  const auto it = g_http_patterns.find(browser_id);
  if (it == g_http_patterns.end())
    return false;
  for (const std::string& pattern : it->second) {
    if (pattern == "*" || (!pattern.empty() && url.find(pattern) != std::string::npos))
      return true;
  }
  return false;
}

void EnqueueHttp(PendingHttp&& item) {
  std::lock_guard<std::mutex> lock(g_http_mutex);
  // 兜底：极端情况下（大量请求）避免无限堆积
  if (g_http_queue.size() > 512)
    g_http_queue.pop_front();
  g_http_queue.push_back(std::move(item));
}

void DrainHttpQueue() {
  for (int i = 0; i < 8; ++i) {
    PendingHttp item;
    {
      std::lock_guard<std::mutex> lock(g_http_mutex);
      if (g_http_queue.empty())
        return;
      item = std::move(g_http_queue.front());
      g_http_queue.pop_front();
    }
    if (!g_http_cb)
      continue;
    const void* body = item.body.empty() ? nullptr : item.body.data();
    g_http_cb(item.browser_id, item.kind, item.url.c_str(), item.method.c_str(),
              item.status_code, item.headers.c_str(), body,
              static_cast<int>(item.body.size()));
  }
}

// ---------------------------------------------------------------- HTTP 拦截

// 响应体过滤器：把响应原样放行，同时抄一份内容交给上层（CEF 的响应回调在 IO 线程）
class BridgeHttpResponseFilter : public CefResponseFilter {
 public:
  BridgeHttpResponseFilter(int browser_id,
                           const std::string& url,
                           CefRefPtr<CefResponse> response)
      : browser_id_(browser_id), url_(url) {
    if (response) {
      status_code_ = response->GetStatus();
      CefResponse::HeaderMap headers;
      response->GetHeaderMap(headers);
      headers_ = SerializeHeaderMap(headers);
    }
  }

  bool InitFilter() override { return true; }

  FilterStatus Filter(void* data_in,
                      size_t data_in_size,
                      size_t& data_in_read,
                      void* data_out,
                      size_t data_out_size,
                      size_t& data_out_written) override {
    data_in_read = 0;
    data_out_written = 0;

    if (data_in && data_in_size > 0) {
      // 输入必须全部读走（CEF 的约定）
      data_in_read = data_in_size;
      const char* chunk = static_cast<const char*>(data_in);
      if (body_.size() < kMaxResponseBodyBytes) {
        const size_t room = kMaxResponseBodyBytes - body_.size();
        body_.append(chunk, data_in_size < room ? data_in_size : room);
      }
      pending_.append(chunk, data_in_size);
    }

    if (pending_offset_ < pending_.size() && data_out && data_out_size > 0) {
      const size_t available = pending_.size() - pending_offset_;
      const size_t count = available < data_out_size ? available : data_out_size;
      memcpy(data_out, pending_.data() + pending_offset_, count);
      data_out_written = count;
      pending_offset_ += count;
      if (pending_offset_ >= pending_.size()) {
        pending_.clear();
        pending_offset_ = 0;
      }
    }

    if (pending_offset_ < pending_.size())
      return RESPONSE_FILTER_NEED_MORE_DATA;

    if (!data_in) {
      // data_in 为空表示响应已经全部到达：这里把结果交给上层
      PendingHttp item;
      item.browser_id = browser_id_;
      item.kind = 2;
      item.url = url_;
      item.status_code = status_code_;
      item.headers = headers_;
      item.body = body_;
      EnqueueHttp(std::move(item));
      return RESPONSE_FILTER_DONE;
    }

    return RESPONSE_FILTER_NEED_MORE_DATA;
  }

 private:
  const int browser_id_;
  const std::string url_;
  int status_code_ = 0;
  std::string headers_;
  std::string body_;
  std::string pending_;
  size_t pending_offset_ = 0;

  IMPLEMENT_REFCOUNTING(BridgeHttpResponseFilter);
  DISALLOW_COPY_AND_ASSIGN(BridgeHttpResponseFilter);
};

// 抓取 favicon：用浏览器自己的请求上下文发起一次 GET，把结果回调给上层
class BridgeIconRequestClient : public CefURLRequestClient {
 public:
  BridgeIconRequestClient(int browser_id, const std::string& url)
      : browser_id_(browser_id), url_(url) {}

  void OnRequestComplete(CefRefPtr<CefURLRequest> request) override {
    if (body_.empty() || body_.size() > kMaxResponseBodyBytes) {
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_FAVICON_DATA, "");
      return;
    }
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_FAVICON_DATA, Base64Encode(body_));
  }

  void OnUploadProgress(CefRefPtr<CefURLRequest> request,
                        int64 current,
                        int64 total) override {}

  void OnDownloadProgress(CefRefPtr<CefURLRequest> request,
                          int64 current,
                          int64 total) override {}

  void OnDownloadData(CefRefPtr<CefURLRequest> request,
                      const void* data,
                      size_t data_length) override {
    if (body_.size() >= kMaxResponseBodyBytes)
      return;
    body_.append(static_cast<const char*>(data), data_length);
  }

  bool GetAuthCredentials(bool isProxy,
                          const CefString& host,
                          int port,
                          const CefString& realm,
                          const CefString& scheme,
                          CefRefPtr<CefAuthCallback> callback) override {
    return false;
  }

 private:
  const int browser_id_;
  const std::string url_;
  std::string body_;

  IMPLEMENT_REFCOUNTING(BridgeIconRequestClient);
  DISALLOW_COPY_AND_ASSIGN(BridgeIconRequestClient);
};
// ---------------------------------------------------------------- Cookie 访问器

class BridgeCookieVisitor : public CefCookieVisitor {
 public:
  explicit BridgeCookieVisitor(int browser_id) : browser_id_(browser_id) {}

  bool Visit(const CefCookie& cookie,
             int count,
             int total,
             bool& delete_cookie) override {
    if (count > 0)
      cookies_ += "; ";
    cookies_ += ToUtf8(CefString(&cookie.name));
    cookies_ += "=";
    cookies_ += ToUtf8(CefString(&cookie.value));
    if (count + 1 >= total)
      EmitEvent(browser_id_, kEventCookies, cookies_);
    return true;
  }

 private:
  const int browser_id_;
  std::string cookies_;

  IMPLEMENT_REFCOUNTING(BridgeCookieVisitor);
  DISALLOW_COPY_AND_ASSIGN(BridgeCookieVisitor);
};

// ---------------------------------------------------------------- CefClient

class BridgeClient : public CefClient,
                     public CefLifeSpanHandler,
                     public CefLoadHandler,
                     public CefDisplayHandler,
                     public CefContextMenuHandler,
                     public CefRenderHandler,
                     public CefRequestHandler,
                     public CefResourceRequestHandler,
                     public CefDownloadHandler {
 public:
  explicit BridgeClient(int browser_id) : browser_id_(browser_id) {}

  CefRefPtr<CefLifeSpanHandler> GetLifeSpanHandler() override { return this; }
  CefRefPtr<CefLoadHandler> GetLoadHandler() override { return this; }
  CefRefPtr<CefDisplayHandler> GetDisplayHandler() override { return this; }
  CefRefPtr<CefContextMenuHandler> GetContextMenuHandler() override { return this; }
  CefRefPtr<CefRenderHandler> GetRenderHandler() override { return this; }
  CefRefPtr<CefRequestHandler> GetRequestHandler() override { return this; }
  CefRefPtr<CefDownloadHandler> GetDownloadHandler() override { return this; }

  // ---- CefRenderHandler（OSR）
  void GetViewRect(CefRefPtr<CefBrowser> browser, CefRect& rect) override {
    const auto it = g_view_rects.find(browser_id_);
    rect = (it != g_view_rects.end()) ? it->second : CefRect(0, 0, 800, 600);
  }

  void OnPaint(CefRefPtr<CefBrowser> browser,
               PaintElementType type,
               const RectList& dirty_rects,
               const void* buffer,
               int width,
               int height) override {
    if (type != PET_VIEW || !buffer || !g_paint_cb)
      return;
    g_paint_cb(browser_id_, buffer, width, height);
  }

  // ---- CefLifeSpanHandler
  bool OnBeforePopup(CefRefPtr<CefBrowser> browser,
                     CefRefPtr<CefFrame> frame,
#if CEF_VERSION_MAJOR >= 120
                     int popup_id,
#endif
                     const CefString& target_url,
                     const CefString& target_frame_name,
                     CefLifeSpanHandler::WindowOpenDisposition target_disposition,
                     bool user_gesture,
                     const CefPopupFeatures& popup_features,
                     CefWindowInfo& window_info,
                     CefRefPtr<CefClient>& client,
                     CefBrowserSettings& settings,
                     CefRefPtr<CefDictionaryValue>& extra_info,
                     bool* no_javascript_access) override {
    // 新窗口请求交给上层（对应 webview2 的 handle_newtab_byuser）
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_NEW_TAB, ToUtf8(target_url));
    return true;  // 阻止 CEF 自己弹窗
  }

  void OnAfterCreated(CefRefPtr<CefBrowser> browser) override {

    g_browsers[browser_id_] = browser;
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_CREATED, "");
  }

  void OnBeforeClose(CefRefPtr<CefBrowser> browser) override {

    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_CLOSE, "");
    g_browsers.erase(browser_id_);
  }

  // ---- CefLoadHandler
  void OnLoadStart(CefRefPtr<CefBrowser> browser,
                   CefRefPtr<CefFrame> frame,
                   TransitionType transition_type) override {
    if (frame && frame->IsMain())
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_LOAD_START, ToUtf8(frame->GetURL()));
  }

  void OnLoadEnd(CefRefPtr<CefBrowser> browser,
                 CefRefPtr<CefFrame> frame,
                 int http_status_code) override {
    if (!frame || !frame->IsMain())
      return;
    InjectBridgeScript(frame);
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_LOAD_END, ToUtf8(frame->GetURL()));
  }

  void OnLoadError(CefRefPtr<CefBrowser> browser,
                   CefRefPtr<CefFrame> frame,
                   ErrorCode error_code,
                   const CefString& error_text,
                   const CefString& failed_url) override {
    if (frame && frame->IsMain())
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_LOAD_ERROR, ToUtf8(error_text));
  }

  // ---- CefDisplayHandler
  void OnTitleChange(CefRefPtr<CefBrowser> browser, const CefString& title) override {
    g_titles[browser_id_] = ToUtf8(title);
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_TITLE, g_titles[browser_id_]);
  }

  void OnAddressChange(CefRefPtr<CefBrowser> browser,
                       CefRefPtr<CefFrame> frame,
                       const CefString& url) override {
    if (frame && frame->IsMain())
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_URL, ToUtf8(url));
  }

  void OnFullscreenModeChange(CefRefPtr<CefBrowser> browser, bool fullscreen) override {
    // 网页进入/退出 HTML 全屏时通知上层（视频播放器需要它来切换窗口全屏）
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_FULLSCREEN, fullscreen ? "1" : "0");
  }

  void OnStatusMessage(CefRefPtr<CefBrowser> browser, const CefString& value) override {
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_STATUS, ToUtf8(value));
  }

  bool OnConsoleMessage(CefRefPtr<CefBrowser> browser,
                        cef_log_severity_t level,
                        const CefString& message,
                        const CefString& source,
                        int line) override {
    const std::string text = ToUtf8(message);
    const size_t prefix_len = sizeof(kBridgePrefix) - 1;
    if (text.size() >= prefix_len && text.compare(0, prefix_len, kBridgePrefix) == 0)
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_BRIDGE_MESSAGE, text.substr(prefix_len));
    else
      EmitEvent(browser_id_, CEF_BRIDGE_EVENT_CONSOLE, text);
    return true;
  }

  void OnFaviconURLChange(CefRefPtr<CefBrowser> browser,
                          const std::vector<CefString>& icon_urls) override {
    // 上层拿到 URL 后会调用 cef_bridge_fetch_icon 取二进制
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_FAVICON_URL,
              icon_urls.empty() ? "" : ToUtf8(icon_urls[icon_urls.size() - 1]));
  }
  // ---- CefContextMenuHandler（使用 CEF 内置命令 id，由 CEF 自己执行）
  void OnBeforeContextMenu(CefRefPtr<CefBrowser> browser,
                           CefRefPtr<CefFrame> frame,
                           CefRefPtr<CefContextMenuParams> params,
                           CefRefPtr<CefMenuModel> model) override {
    if (model->GetCount() > 0)
      model->AddSeparator();
    model->AddItem(MENU_ID_BACK, "后退");
    model->AddItem(MENU_ID_FORWARD, "前进");
    model->AddItem(MENU_ID_RELOAD, "刷新");
    model->AddSeparator();
    model->AddItem(MENU_ID_COPY, "复制");
    model->AddItem(MENU_ID_PASTE, "粘贴");
    model->AddItem(MENU_ID_SELECT_ALL, "全选");
  }

  // ---- CefRequestHandler（IO 线程：只做筛选，真正的回调排队到 UI 线程）
  CefRefPtr<CefResourceRequestHandler> GetResourceRequestHandler(
      CefRefPtr<CefBrowser> browser,
      CefRefPtr<CefFrame> frame,
      CefRefPtr<CefRequest> request,
      bool is_navigation,
      bool is_download,
      const CefString& request_initiator,
      bool& disable_default_handling) override {
    if (!g_http_cb || !request)
      return nullptr;
    return ShouldIntercept(browser_id_, ToUtf8(request->GetURL())) ? this : nullptr;
  }

  // ---- CefResourceRequestHandler
  ReturnValue OnBeforeResourceLoad(CefRefPtr<CefBrowser> browser,
                                   CefRefPtr<CefFrame> frame,
                                   CefRefPtr<CefRequest> request,
                                   CefRefPtr<CefCallback> callback) override {
    if (request) {
      PendingHttp item;
      item.browser_id = browser_id_;
      item.kind = 1;
      item.url = ToUtf8(request->GetURL());
      item.method = ToUtf8(request->GetMethod());
      CefRequest::HeaderMap headers;
      request->GetHeaderMap(headers);
      item.headers = SerializeHeaderMap(headers);
      CefRefPtr<CefPostData> post_data = request->GetPostData();
      if (post_data) {
        std::vector<CefRefPtr<CefPostDataElement>> elements;
        post_data->GetElements(elements);
        for (const auto& element : elements) {
          if (!element || element->GetType() != PDE_TYPE_BYTES)
            continue;
          const size_t size = element->GetBytesCount();
          if (size == 0)
            continue;
          std::string buffer(size, '\0');
          element->GetBytes(size, &buffer[0]);
          item.body += buffer;
        }
      }
      EnqueueHttp(std::move(item));
    }
    return RV_CONTINUE;
  }

  CefRefPtr<CefResponseFilter> GetResourceResponseFilter(
      CefRefPtr<CefBrowser> browser,
      CefRefPtr<CefFrame> frame,
      CefRefPtr<CefRequest> request,
      CefRefPtr<CefResponse> response) override {
    if (!request)
      return nullptr;
    return new BridgeHttpResponseFilter(browser_id_, ToUtf8(request->GetURL()), response);
  }

  // ---- CefDownloadHandler（UI 线程）
  bool CanDownload(CefRefPtr<CefBrowser> browser,
                   const CefString& url,
                   const CefString& request_method) override {
    return true;
  }

  void OnBeforeDownload(CefRefPtr<CefBrowser> browser,
                        CefRefPtr<CefDownloadItem> download_item,
                        const CefString& suggested_name,
                        CefRefPtr<CefBeforeDownloadCallback> callback) override {
    if (!download_item || !callback)
      return;
    const uint32 download_id = download_item->GetId();
    {
      std::lock_guard<std::mutex> lock(g_http_mutex);
      g_download_pending_id = static_cast<int>(download_id);
      g_download_pending_path.clear();
      g_download_pending_cancel = false;
    }

    const std::string url = ToUtf8(download_item->GetURL());
    const std::string name = ToUtf8(suggested_name);
    const int64 total = download_item->GetTotalBytes();
    std::string json = "{\"state\":1,\"id\":" + std::to_string(download_id) +
                       ",\"url\":\"" + JsonEscape(url) +
                       "\",\"name\":\"" + JsonEscape(name) +
                       "\",\"total\":" + std::to_string(total) + "}";
    // 同步询问上层：它会在回调里调用 cef_bridge_download_continue / cancel
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_DOWNLOAD, json);

    std::string path;
    bool cancel = false;
    {
      std::lock_guard<std::mutex> lock(g_http_mutex);
      if (g_download_pending_id == static_cast<int>(download_id)) {
        path = g_download_pending_path;
        cancel = g_download_pending_cancel;
        g_download_pending_id = -1;
      }
    }
    if (cancel) {
      // 不调用 Continue：CEF 会把这次下载取消掉
      return;
    }
    callback->Continue(FromUtf8(path.c_str()), false);
  }

  void OnDownloadUpdated(CefRefPtr<CefBrowser> browser,
                         CefRefPtr<CefDownloadItem> download_item,
                         CefRefPtr<CefDownloadItemCallback> callback) override {
    if (!download_item || !download_item->IsValid())
      return;
    const uint32 download_id = download_item->GetId();
    const bool done = download_item->IsComplete() || download_item->IsCanceled();
    {
      std::lock_guard<std::mutex> lock(g_http_mutex);
      if (callback && !done)
        g_download_callbacks[download_id] = callback;
      else
        g_download_callbacks.erase(download_id);
    }

    int state = 2;
    if (download_item->IsComplete())
      state = 3;
    else if (download_item->IsCanceled())
      state = 4;
    else if (!download_item->IsInProgress())
      state = 5;
    std::string json =
        "{\"state\":" + std::to_string(state) +
        ",\"id\":" + std::to_string(download_id) +
        ",\"url\":\"" + JsonEscape(ToUtf8(download_item->GetURL())) +
        "\",\"name\":\"" + JsonEscape(ToUtf8(download_item->GetSuggestedFileName())) +
        "\",\"path\":\"" + JsonEscape(ToUtf8(download_item->GetFullPath())) +
        "\",\"received\":" + std::to_string(download_item->GetReceivedBytes()) +
        ",\"total\":" + std::to_string(download_item->GetTotalBytes()) +
        ",\"percent\":" + std::to_string(download_item->GetPercentComplete()) +
        ",\"speed\":" + std::to_string(download_item->GetCurrentSpeed()) +
        ",\"in_progress\":" + (download_item->IsInProgress() ? "true" : "false") +
        "}";
    EmitEvent(browser_id_, CEF_BRIDGE_EVENT_DOWNLOAD, json);
  }
 private:
  void InjectBridgeScript(CefRefPtr<CefFrame> frame) {
    if (!frame)
      return;
    std::string script = kDefaultBridgeScript;
    const auto it = g_bridge_scripts.find(browser_id_);
    if (it != g_bridge_scripts.end() && !it->second.empty())
      script = it->second;
    frame->ExecuteJavaScript(script, frame->GetURL(), 0);
  }

  const int browser_id_;

  IMPLEMENT_REFCOUNTING(BridgeClient);
  DISALLOW_COPY_AND_ASSIGN(BridgeClient);
};


// ---------------------------------------------------------------- 开发者工具

// 开发者工具浏览器使用独立的 client：
//   1) 不能复用 BridgeClient——它的 OnAfterCreated 会把 devtools 浏览器写进
//      g_browsers，从而顶替宿主浏览器的 id 映射；
//   2) 单独记录 devtools 浏览器，关闭标签页 / 退出进程时才能先把它关掉，
//      否则 CefShutdown 会以 access violation（reading 0x10）崩溃。
class BridgeDevToolsClient : public CefClient, public CefLifeSpanHandler {
 public:
  explicit BridgeDevToolsClient(int owner_id) : owner_id_(owner_id) {}

  CefRefPtr<CefLifeSpanHandler> GetLifeSpanHandler() override { return this; }

  void OnAfterCreated(CefRefPtr<CefBrowser> browser) override {
    g_devtools[owner_id_] = browser;
    EmitEvent(owner_id_, CEF_BRIDGE_EVENT_DEVTOOLS_CREATED, "");
  }

  void OnBeforeClose(CefRefPtr<CefBrowser> browser) override {
    const auto it = g_devtools.find(owner_id_);
    if (it != g_devtools.end() && it->second && it->second->IsSame(browser))
      g_devtools.erase(it);
    EmitEvent(owner_id_, CEF_BRIDGE_EVENT_DEVTOOLS_CLOSED, "");
  }

 private:
  const int owner_id_;

  IMPLEMENT_REFCOUNTING(BridgeDevToolsClient);
  DISALLOW_COPY_AND_ASSIGN(BridgeDevToolsClient);
};

// ---------------------------------------------------------------- CefApp

class BridgeApp : public CefApp, public CefBrowserProcessHandler {
 public:
  CefRefPtr<CefBrowserProcessHandler> GetBrowserProcessHandler() override { return this; }

  void OnBeforeCommandLineProcessing(const CefString& process_type,
                                     CefRefPtr<CefCommandLine> command_line) override {
    if (!process_type.empty())
      return;
    // Linux 下我们不会安装 setuid 的 chrome-sandbox，直接关闭沙箱
#if !defined(_WIN32)
    command_line->AppendSwitch("no-sandbox");
#endif
    if (!g_extra_args.empty()) {
      std::istringstream stream(g_extra_args);
      std::string token;
      while (stream >> token) {
        if (token.rfind("--", 0) != 0)
          continue;
        const std::string name = token.substr(2);
        const size_t pos = name.find('=');
        if (pos == std::string::npos)
          command_line->AppendSwitch(CefString(name));
        else
          command_line->AppendSwitchWithValue(CefString(name.substr(0, pos)),
                                              CefString(name.substr(pos + 1)));
      }
    }
  }

 private:
  IMPLEMENT_REFCOUNTING(BridgeApp);
};

// ---------------------------------------------------------------- 子进程类型标记

// 把子进程自己的命令行写到 <临时目录>/TiebaDesktopCefProcesses/<pid>.txt。
// CEF 没有公开「哪个子进程是渲染 / GPU / 网络进程」，任务管理器靠这个文件区分。
std::string TempDirPath() {
#if defined(_WIN32)
  wchar_t buffer[MAX_PATH + 1] = {0};
  if (::GetTempPathW(MAX_PATH, buffer) == 0)
    return std::string();
  return ToUtf8(CefString(buffer));
#else
  const char* env = getenv("TMPDIR");
  if (env && *env)
    return std::string(env);
  return std::string("/tmp");
#endif
}

void WriteProcessTypeMarker(const std::string& command_line) {
  std::string dir = TempDirPath();
  if (dir.empty())
    return;
  if (dir.back() != '/' && dir.back() != '\\')
    dir += '/';
  dir += "TiebaDesktopCefProcesses";
#if defined(_WIN32)
  ::CreateDirectoryW(CefString(dir).ToWString().c_str(), nullptr);
  const unsigned long pid = ::GetCurrentProcessId();
#else
  mkdir(dir.c_str(), 0755);
  const unsigned long pid = static_cast<unsigned long>(getpid());
#endif
  const std::string path = dir + "/" + std::to_string(pid) + ".txt";
  FILE* file = fopen(path.c_str(), "wb");
  if (!file)
    return;
  fwrite(command_line.c_str(), 1, command_line.size(), file);
  fclose(file);
}
}  // namespace

// ---------------------------------------------------------------- 导出接口

CEF_BRIDGE_API int cef_bridge_execute_process(int argc, char** argv) {
#if defined(_WIN32)
  CefMainArgs main_args(::GetModuleHandle(nullptr));
  WriteProcessTypeMarker(ToUtf8(CefString(::GetCommandLineW())));
#else
  CefMainArgs main_args(argc, argv);
  {
    std::string command_line;
    for (int i = 0; i < argc; ++i) {
      if (i > 0)
        command_line += ' ';
      if (argv[i])
        command_line += argv[i];
    }
    WriteProcessTypeMarker(command_line);
  }
#endif
  CefRefPtr<BridgeApp> app(new BridgeApp());
  return CefExecuteProcess(main_args, app.get(), nullptr);
}

CEF_BRIDGE_API int cef_bridge_init(const char* cache_path,
                                   const char* log_file,
                                   const char* resources_dir,
                                   const char* locales_dir,
                                   const char* subprocess_path,
                                   const char* user_agent,
                                   const char* extra_args) {
  if (g_initialized)
    return 1;

  if (extra_args)
    g_extra_args = extra_args;

  CefSettings settings;
  settings.no_sandbox = true;
  settings.multi_threaded_message_loop = false;
  settings.external_message_pump = true;
  settings.windowless_rendering_enabled = g_windowless;
  settings.log_severity = LOGSEVERITY_WARNING;

  if (cache_path)
    CefString(&settings.cache_path) = FromUtf8(cache_path);
  if (log_file)
    CefString(&settings.log_file) = FromUtf8(log_file);
  if (resources_dir)
    CefString(&settings.resources_dir_path) = FromUtf8(resources_dir);
  if (locales_dir)
    CefString(&settings.locales_dir_path) = FromUtf8(locales_dir);
  if (subprocess_path)
    CefString(&settings.browser_subprocess_path) = FromUtf8(subprocess_path);
  if (user_agent)
    CefString(&settings.user_agent) = FromUtf8(user_agent);

#if defined(_WIN32)
  CefMainArgs main_args(::GetModuleHandle(nullptr));
#else
  CefMainArgs main_args(0, nullptr);
#endif
  CefRefPtr<BridgeApp> app(new BridgeApp());
  if (!CefInitialize(main_args, settings, app.get(), nullptr))
    return 0;

  g_initialized = true;
  return 1;
}

CEF_BRIDGE_API int cef_bridge_is_initialized() { return g_initialized ? 1 : 0; }

CEF_BRIDGE_API void cef_bridge_set_windowless(int enabled) {
  g_windowless = (enabled != 0);
}

CEF_BRIDGE_API void cef_bridge_set_event_callback(cef_bridge_event_cb cb) {
  g_event_cb = cb;
}

CEF_BRIDGE_API void cef_bridge_do_work() {
  // 正在执行其它 CEF 调用或已在泵内时直接返回，避免重入
  if (!g_initialized || g_in_pump || g_in_cef_call)
    return;
  g_in_pump = true;
  CefDoMessageLoopWork();
  g_in_pump = false;
  // 把 IO 线程攒下的请求 / 响应回调切回 UI 线程（Python 侧要安全访问 Qt）
  DrainHttpQueue();
}

CEF_BRIDGE_API void cef_bridge_shutdown() {
  if (!g_initialized)
    return;

  // 必须先把所有浏览器关掉：带着存活的浏览器直接 CefShutdown 会触发
  // "Check failed: observers_.empty()" 之类的断言从而导致进程异常退出。
  CefCallGuard guard;
  {
    std::vector<CefRefPtr<CefBrowser>> browsers;
    for (auto& kv : g_browsers)
      if (kv.second)
        browsers.push_back(kv.second);
    for (auto& browser : browsers) {
      CefRefPtr<CefBrowserHost> host = browser->GetHost();
      if (host && host->HasDevTools())
        host->CloseDevTools();
    }
    // 我们记录的 devtools 浏览器必须直接关闭并释放引用：只靠 CloseDevTools 它们会
    // 一直存活，带着存活的 devtools 浏览器直接 CefShutdown 会触发
    // access violation（reading 0x10）让进程异常退出。
    std::vector<CefRefPtr<CefBrowser>> devtools;
    for (auto& kv : g_devtools)
      if (kv.second)
        devtools.push_back(kv.second);
    g_devtools.clear();
    for (auto& browser : devtools) {
      CefRefPtr<CefBrowserHost> devtools_host = browser->GetHost();
      if (devtools_host)
        devtools_host->CloseBrowser(true);
    }
    devtools.clear();
    for (auto& browser : browsers)      browser->GetHost()->CloseBrowser(true);
  }
  // 泵到所有浏览器真正析构（OnBeforeClose 会把自己从表里移除）为止
  for (int i = 0; i < 1000 && (!g_browsers.empty() || !g_devtools.empty()); ++i)
    CefDoMessageLoopWork();
  // 渲染进程退出需要一点真实时间，这里再等一会儿（最多 1s）
  for (int i = 0; i < 200 && (!g_browsers.empty() || !g_devtools.empty()); ++i) {
    CefDoMessageLoopWork();
    SleepMs(5);
  }
  for (int i = 0; i < 50; ++i)
    CefDoMessageLoopWork();

  g_browsers.clear();
  g_devtools.clear();
  g_bridge_scripts.clear();
  g_http_patterns.clear();
  g_download_callbacks.clear();
  g_http_cb = nullptr;
  g_titles.clear();
  g_event_cb = nullptr;
  CefShutdown();
  g_initialized = false;
}

CEF_BRIDGE_API int cef_bridge_create_browser(int browser_id,
                                             unsigned long long parent_handle,
                                             const char* url,
                                             int x, int y, int width, int height,
                                             const char* js_bridge_script,
                                             const char* user_agent) {
  if (!g_initialized)
    return 0;

  CefCallGuard guard;

  if (js_bridge_script)
    g_bridge_scripts[browser_id] = js_bridge_script;

  g_view_rects[browser_id] =
      CefRect(0, 0, width > 0 ? width : 800, height > 0 ? height : 600);

  CefWindowInfo window_info;
  if (g_windowless) {
    // 离屏（OSR）渲染：不创建原生窗口，画面由 CefRenderHandler::OnPaint 回传
    window_info.SetAsWindowless(ToWindowHandle(parent_handle));
  } else {
    // 默认：原生子窗口嵌入（与 cefpython examples/qt.py 的做法一致）
    window_info.SetAsChild(ToWindowHandle(parent_handle), CefRect(x, y, width, height));
#if CEF_VERSION_MAJOR >= 120
    // 只有 Alloy 风格支持「客户端提供父窗口」的子窗口；
    // CEF 109 等老版本没有 runtime_style（默认就是 Alloy），这里按版本编译。
    window_info.runtime_style = CEF_RUNTIME_STYLE_ALLOY;
#endif
  }

  CefBrowserSettings browser_settings;
  CefRefPtr<BridgeClient> client(new BridgeClient(browser_id));
  const CefString target = url ? FromUtf8(url) : FromUtf8("about:blank");

  CefRefPtr<CefBrowser> browser = CefBrowserHost::CreateBrowserSync(
      window_info, client.get(), target, browser_settings,
      CefRefPtr<CefDictionaryValue>(), CefRefPtr<CefRequestContext>());
  if (!browser)
    return 0;

  g_browsers[browser_id] = browser;
  return 1;
}

CEF_BRIDGE_API void cef_bridge_resize(int browser_id, int x, int y, int width, int height) {
  if (width <= 0 || height <= 0)
    return;

  // OSR 用它作为取景矩形，窗口化模式用它来调整 CEF 子窗体
  g_view_rects[browser_id] = CefRect(0, 0, width, height);

  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;

  if (!g_windowless) {
    // 关键：窗口化模式必须把 CEF 的子窗口一起调整到控件大小，
    // 否则只有外层窗口变了、网页不会重排（右键菜单还能点在空白区域）。
    CefWindowHandle handle = host->GetWindowHandle();
    if (handle)
      MoveResizeWindow(handle, x, y, width, height);
  }
  host->NotifyMoveOrResizeStarted();
  host->WasResized();
}

CEF_BRIDGE_API void cef_bridge_set_visible(int browser_id, int visible) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;
  // OSR 下没有原生窗口，只需通知可见性
  host->WasHidden(visible == 0);
}

CEF_BRIDGE_API void cef_bridge_load(int browser_id, const char* url) {
  CefRefPtr<CefFrame> frame = MainFrameById(browser_id);
  if (frame && url)
    frame->LoadURL(FromUtf8(url));
}

CEF_BRIDGE_API void cef_bridge_load_string(int browser_id, const char* html, const char* url) {
  // CEF 154 起已移除 CefFrame::LoadString，这里改用 base64 编码的 data: URL；
  // 参数 url 在 data: URL 方案下无法作为 base URL 使用，忽略。
  (void)url;
  CefRefPtr<CefFrame> frame = MainFrameById(browser_id);
  if (!frame || !html)
    return;
  const std::string data_url =
      "data:text/html;charset=utf-8;base64," + Base64Encode(std::string(html));
  frame->LoadURL(CefString(data_url));
}

CEF_BRIDGE_API void cef_bridge_go_back(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  if (browser)
    browser->GoBack();
}

CEF_BRIDGE_API void cef_bridge_go_forward(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  if (browser)
    browser->GoForward();
}

CEF_BRIDGE_API int cef_bridge_can_go_back(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  return (browser && browser->CanGoBack()) ? 1 : 0;
}

CEF_BRIDGE_API int cef_bridge_can_go_forward(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  return (browser && browser->CanGoForward()) ? 1 : 0;
}

CEF_BRIDGE_API void cef_bridge_reload(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  if (browser)
    browser->Reload();
}

CEF_BRIDGE_API void cef_bridge_stop_load(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  if (browser)
    browser->StopLoad();
}

CEF_BRIDGE_API void cef_bridge_set_zoom(int browser_id, double level) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host)
    host->SetZoomLevel(level);
}

CEF_BRIDGE_API double cef_bridge_get_zoom(int browser_id) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  return host ? host->GetZoomLevel() : 1.0;
}

CEF_BRIDGE_API void cef_bridge_set_muted(int browser_id, int muted) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host)
    host->SetAudioMuted(muted != 0);
}

CEF_BRIDGE_API int cef_bridge_is_muted(int browser_id) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  return (host && host->IsAudioMuted()) ? 1 : 0;
}

CEF_BRIDGE_API void cef_bridge_execute_js(int browser_id, const char* code) {
  CefRefPtr<CefFrame> frame = MainFrameById(browser_id);
  if (frame && code)
    frame->ExecuteJavaScript(FromUtf8(code), frame->GetURL(), 0);
}

CEF_BRIDGE_API int cef_bridge_open_devtools(int browser_id,
                                            unsigned long long parent_handle,
                                            int x, int y, int width, int height) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return 0;
  if (host->HasDevTools())
    return 2;

  CefCallGuard guard;

  CefWindowInfo window_info;
  if (parent_handle) {
    // 默认：让 devtools 作为宿主 Qt 窗口的原生子窗口渲染。
    // 这条路径与主浏览器完全一致（SetAsChild），是已经在各平台验证过的渲染方式；
    // 而 CEF 自己创建的 devtools 弹窗（SetAsPopup）在部分 Windows 环境下只会
    // 显示一片空白（能右键、能点到关闭按钮，但没有任何内容）。
    window_info.SetAsChild(ToWindowHandle(parent_handle),
                           CefRect(x, y,
                                   width > 0 ? width : 800,
                                   height > 0 ? height : 600));
  } else {
    // 兜底：没有可用的父窗口时交给 CEF 自己弹一个顶层窗口
    window_info.SetAsPopup(nullptr, "DevTools");
  }

  CefRefPtr<BridgeDevToolsClient> client(new BridgeDevToolsClient(browser_id));
  host->ShowDevTools(window_info, client.get(), CefBrowserSettings(), CefPoint());
  return 1;
}

CEF_BRIDGE_API void cef_bridge_resize_devtools(int browser_id, int x, int y,
                                               int width, int height) {
  if (width <= 0 || height <= 0)
    return;
  const auto it = g_devtools.find(browser_id);
  if (it == g_devtools.end() || !it->second)
    return;
  CefRefPtr<CefBrowserHost> host = it->second->GetHost();
  if (!host)
    return;
  CefWindowHandle handle = host->GetWindowHandle();
  if (handle)
    MoveResizeWindow(handle, x, y, width, height);
  host->NotifyMoveOrResizeStarted();
  host->WasResized();
}

CEF_BRIDGE_API void cef_bridge_close_devtools(int browser_id) {
  // 先把我们记录的 devtools 浏览器取出来、并摘掉表里的引用：g_devtools 里的强引用
  // 会让浏览器一直无法析构（CEF 只有在最后一个引用释放后才会真正销毁浏览器窗口）。
  std::vector<CefRefPtr<CefBrowser>> devtools;
  const auto it = g_devtools.find(browser_id);
  if (it != g_devtools.end()) {
    if (it->second)
      devtools.push_back(it->second);
    g_devtools.erase(it);
  }

  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host && host->HasDevTools())
    host->CloseDevTools();

  // 再直接关掉 devtools 浏览器本身：只调用 CloseDevTools 时，这套 CEF 只会把前端
  // 从宿主上摘下来，并不会真正销毁它（表现为 HasDevTools() 一直为 true）。
  for (auto& browser : devtools) {
    CefRefPtr<CefBrowserHost> devtools_host = browser->GetHost();
    if (devtools_host)
      devtools_host->CloseBrowser(true);
  }
  devtools.clear();

  // 泵到 CEF 的 devtools 关联解除为止（渲染进程退出需要一点真实时间）
  CefCallGuard guard;
  for (int i = 0; i < 300; ++i) {
    if (host && !host->HasDevTools())
      break;
    if (!host && i >= 20)
      break;
    CefDoMessageLoopWork();
    SleepMs(5);
  }
}

CEF_BRIDGE_API int cef_bridge_has_devtools(int browser_id) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  return (host && host->HasDevTools()) ? 1 : 0;
}

CEF_BRIDGE_API void cef_bridge_set_http_callback(cef_bridge_http_cb cb) {
  g_http_cb = cb;
}

CEF_BRIDGE_API void cef_bridge_set_http_patterns(int browser_id, const char* patterns) {
  std::vector<std::string> list;
  if (patterns) {
    std::string text(patterns);
    size_t start = 0;
    while (start <= text.size()) {
      const size_t pos = text.find('|', start);
      const std::string item =
          text.substr(start, pos == std::string::npos ? std::string::npos : pos - start);
      if (!item.empty())
        list.push_back(item);
      if (pos == std::string::npos)
        break;
      start = pos + 1;
    }
  }
  if (list.empty()) {
    g_http_patterns.erase(browser_id);
    return;
  }
  g_http_patterns[browser_id] = list;
}

CEF_BRIDGE_API void cef_bridge_fetch_icon(int browser_id, const char* icon_url) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host || !icon_url || !*icon_url)
    return;
  CefRefPtr<CefRequest> request = CefRequest::Create();
  request->SetURL(FromUtf8(icon_url));
  request->SetMethod(CefString("GET"));
  CefRefPtr<BridgeIconRequestClient> client(new BridgeIconRequestClient(
      browser_id, std::string(icon_url)));
  CefURLRequest::Create(request, client.get(), host->GetRequestContext());
}

CEF_BRIDGE_API void cef_bridge_download_continue(int download_id, const char* path) {
  std::lock_guard<std::mutex> lock(g_http_mutex);
  if (g_download_pending_id != download_id)
    return;
  g_download_pending_path = path ? path : "";
  g_download_pending_cancel = false;
}

CEF_BRIDGE_API void cef_bridge_download_cancel(int download_id) {
  std::lock_guard<std::mutex> lock(g_http_mutex);
  if (g_download_pending_id != download_id)
    return;
  g_download_pending_path.clear();
  g_download_pending_cancel = true;
}

CEF_BRIDGE_API void cef_bridge_download_set_paused(int download_id, int paused) {
  CefRefPtr<CefDownloadItemCallback> callback;
  {
    std::lock_guard<std::mutex> lock(g_http_mutex);
    const auto it = g_download_callbacks.find(static_cast<uint32>(download_id));
    if (it != g_download_callbacks.end())
      callback = it->second;
  }
  if (!callback)
    return;
  if (paused)
    callback->Pause();
  else
    callback->Resume();
}

CEF_BRIDGE_API void cef_bridge_download_cancel_by_id(int download_id) {
  CefRefPtr<CefDownloadItemCallback> callback;
  {
    std::lock_guard<std::mutex> lock(g_http_mutex);
    const auto it = g_download_callbacks.find(static_cast<uint32>(download_id));
    if (it != g_download_callbacks.end())
      callback = it->second;
  }
  if (callback)
    callback->Cancel();
}
CEF_BRIDGE_API void cef_bridge_print(int browser_id) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host)
    host->Print();
}

CEF_BRIDGE_API void cef_bridge_clear_cache(int browser_id) {
  // NOTE: CefRequestContext::ClearHttpCache 的参数列表在较新的 CEF 中发生了变化，
  // 为避免与具体版本强绑定，这里不做处理；清除 Cookie 依然有效（见 cef_bridge_clear_cookies）。
  (void)browser_id;
}

CEF_BRIDGE_API void cef_bridge_clear_cookies(int browser_id) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host || !host->GetRequestContext())
    return;
  CefRefPtr<CefCookieManager> manager =
      host->GetRequestContext()->GetCookieManager(CefRefPtr<CefCompletionCallback>());
  if (manager)
    manager->DeleteCookies(CefString(), CefString(), CefRefPtr<CefDeleteCookiesCallback>());
}

// 读取指定 URL 上的 Cookie（含 HttpOnly），完成后通过事件回传。
// 登录流程依赖它获取 BDUSS / STOKEN。
CEF_BRIDGE_API void cef_bridge_get_cookies(int browser_id, const char* url) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host || !url || !host->GetRequestContext())
    return;
  CefRefPtr<CefCookieManager> manager =
      host->GetRequestContext()->GetCookieManager(CefRefPtr<CefCompletionCallback>());
  if (!manager)
    return;
  CefRefPtr<BridgeCookieVisitor> visitor(new BridgeCookieVisitor(browser_id));
  manager->VisitUrlCookies(FromUtf8(url), true, visitor.get());
}

CEF_BRIDGE_API char* cef_bridge_get_url(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  if (!browser || !browser->GetMainFrame())
    return nullptr;
  return AllocUtf8(ToUtf8(browser->GetMainFrame()->GetURL()));
}

CEF_BRIDGE_API char* cef_bridge_get_title(int browser_id) {
  const auto it = g_titles.find(browser_id);
  return it == g_titles.end() ? nullptr : AllocUtf8(it->second);
}

CEF_BRIDGE_API int cef_bridge_get_pid(int browser_id) {
  CefRefPtr<CefBrowser> browser = BrowserById(browser_id);
  return browser ? browser->GetIdentifier() : -1;
}

CEF_BRIDGE_API void cef_bridge_free_string(char* text) {
  free(text);
}

CEF_BRIDGE_API void cef_bridge_destroy_browser(int browser_id, int force_close) {
  // 先把浏览器从表里摘出来并握住强引用：
  // CloseBrowser 会同步触发 OnBeforeClose，若此时表里的最后一个引用被释放，
  // 会在 CloseBrowser 内部把对象析构掉，造成 use-after-free 崩溃。
  CefRefPtr<CefBrowser> browser;
  const auto it = g_browsers.find(browser_id);
  if (it != g_browsers.end()) {
    browser = it->second;
    g_browsers.erase(it);
  }
  g_bridge_scripts.erase(browser_id);
  g_titles.erase(browser_id);
  g_http_patterns.erase(browser_id);

  if (!browser)
    return;

  CefCallGuard guard;
  CefRefPtr<CefBrowserHost> host = browser->GetHost();
  if (host) {
    // 先关掉关联的开发者工具：它以子窗口方式嵌在宿主窗口上，
    // 宿主先销毁会让 devtools 的子窗口句柄悬空。
    if (host->HasDevTools())
      cef_bridge_close_devtools(browser_id);
    host->CloseBrowser(force_close != 0);
  }
  // 给 CEF 机会把 OnBeforeClose 跑完
  for (int i = 0; i < 20; ++i)
    CefDoMessageLoopWork();
  g_devtools.erase(browser_id);
}

CEF_BRIDGE_API void cef_bridge_set_paint_callback(cef_bridge_paint_cb cb) {
  g_paint_cb = cb;
}

CEF_BRIDGE_API void cef_bridge_set_view_size(int browser_id, int width, int height) {
  if (width <= 0 || height <= 0)
    return;
  g_view_rects[browser_id] = CefRect(0, 0, width, height);
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host)
    host->WasResized();
}

CEF_BRIDGE_API void cef_bridge_set_focus(int browser_id, int focused) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (host)
    host->SetFocus(focused != 0);
}

CEF_BRIDGE_API void cef_bridge_mouse_move(int browser_id, int x, int y, int modifiers, int leave) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;
  CefMouseEvent event;
  event.x = x;
  event.y = y;
  event.modifiers = modifiers;
  host->SendMouseMoveEvent(event, leave != 0);
}

CEF_BRIDGE_API void cef_bridge_mouse_click(int browser_id, int x, int y, int modifiers,
                                           int button, int mouse_up, int click_count) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;
  CefMouseEvent event;
  event.x = x;
  event.y = y;
  event.modifiers = modifiers;
  cef_mouse_button_type_t type = MBT_LEFT;
  if (button == 1)
    type = MBT_MIDDLE;
  else if (button == 2)
    type = MBT_RIGHT;
  host->SendMouseClickEvent(event, type, mouse_up != 0, click_count);
}

CEF_BRIDGE_API void cef_bridge_mouse_wheel(int browser_id, int x, int y, int modifiers,
                                           int delta_x, int delta_y) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;
  CefMouseEvent event;
  event.x = x;
  event.y = y;
  event.modifiers = modifiers;
  host->SendMouseWheelEvent(event, delta_x, delta_y);
}

CEF_BRIDGE_API void cef_bridge_key(int browser_id, int type, int key_code, int native_key_code,
                                   int modifiers, int is_system_key, int character) {
  CefRefPtr<CefBrowserHost> host = HostById(browser_id);
  if (!host)
    return;
  CefKeyEvent event;
  event.type = static_cast<cef_key_event_type_t>(type);
  event.windows_key_code = key_code;
  event.native_key_code = native_key_code;
  event.modifiers = modifiers;
  event.is_system_key = is_system_key != 0;
  event.character = static_cast<char16_t>(character);
  event.unmodified_character = static_cast<char16_t>(character);
  event.focus_on_editable_field = false;
  host->SendKeyEvent(event);
}

CEF_BRIDGE_API const char* cef_bridge_version() {
  return CEF_VERSION;
}
