// CEF 子进程 helper。
//
// CEF 是多进程架构：主进程会把渲染 / GPU / 网络等任务交给子进程执行，
// 子进程以 `--type=xxx` 启动。因为宿主进程是 Python，不方便让 Python 再来一次
// CEF 引导，所以这里编译一个极小的可执行文件，
// 由 CefSettings.browser_subprocess_path 指定给 CEF。
#include "cef_bridge.h"

#if defined(_WIN32)
#include <windows.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE prev_instance, LPWSTR cmd_line, int show) {
  return cef_bridge_execute_process(0, nullptr);
}
#else
int main(int argc, char** argv) {
  return cef_bridge_execute_process(argc, argv);
}
#endif
