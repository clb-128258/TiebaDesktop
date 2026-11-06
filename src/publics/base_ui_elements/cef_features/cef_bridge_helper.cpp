// CEF 子进程 helper。
//
// CEF 是多进程架构：主进程会把渲染 / GPU / 网络等任务交给子进程执行，
// 子进程以 `--type=xxx` 启动。因为宿主进程是 Python，不方便让 Python 再来一次
// CEF 引导，所以这里编译一个极小的可执行文件，
// 由 CefSettings.browser_subprocess_path 指定给 CEF。
#include "cef_bridge.h"

#if defined(_WIN32)
#include <windows.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE prev_instance, LPWSTR cmd_line, int show)
{
  if (cmd_line[0] == L'\0')
  {
    // 直接点开程序时显示消息框提示
    MessageBox(NULL,
               "这是贴吧桌面的 CEF 子进程外壳程序，用于运行 Chromium 子进程，直接双击打开是没有任何作用的。",
               "提示",
               MB_OK | MB_ICONINFORMATION);
  }
  return cef_bridge_execute_process(0, nullptr);
}
#else
int main(int argc, char **argv)
{
  return cef_bridge_execute_process(argc, argv);
}
#endif
