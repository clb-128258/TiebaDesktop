import pathlib
import random
from typing import Callable, Optional
import platform

from PyQt5.QtGui import QIcon

from publics import win8toast, app_logger
import consts

Win10_MIN_VERSION = 10240

IS_WINDOWS = platform.system() == 'Windows'
IS_AT_LEAST_WIN10 = IS_WINDOWS and int(platform.version().split('.')[-1]) >= Win10_MIN_VERSION
IS_WIN8 = IS_WINDOWS and 9200 <= int(platform.version().split('.')[-1]) <= 9600

if IS_WINDOWS:
    import winreg
if IS_AT_LEAST_WIN10:
    from windows_toasts import (InteractableWindowsToaster,
                                Toast, ToastDisplayImage, ToastImagePosition,
                                ToastImage, ToastButton)

    windows_global_toaster = InteractableWindowsToaster('贴吧桌面', consts.WINDOWS_AUMID)


class Button:
    """
    通知中的按钮

    Args:
        text (str): 按钮文本
        callback (Callable): 点击按钮时的回调函数
    """

    def __init__(self, text, callback: Callable = None):
        self.button_text = text
        self.button_id = 'buttonid_' + str(random.randint(1, 10 ** 8))
        self.callback = callback

        if IS_AT_LEAST_WIN10:
            self.toast_button = ToastButton(text, self.button_id)
        else:
            self.toast_button = None


def init_AUMID(appId: str, appName: str, iconPath: Optional[pathlib.Path]):
    if not IS_AT_LEAST_WIN10:
        return

    if iconPath is not None:
        if not iconPath.exists():
            raise ValueError(f"Could not register the application: File {iconPath} does not exist")
        elif iconPath.suffix != ".ico":
            raise ValueError(f"Could not register the application: File {iconPath} must be of type .ico")

    winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
    keyPath = f"SOFTWARE\\Classes\\AppUserModelId\\{appId}"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, keyPath) as masterKey:
        winreg.SetValueEx(masterKey, "DisplayName", 0, winreg.REG_SZ, appName)
        if iconPath is not None:
            winreg.SetValueEx(masterKey, "IconUri", 0, winreg.REG_SZ, str(iconPath.resolve()))


def recursive_delete_key(key_handle, sub_key_name, access=winreg.KEY_WOW64_64KEY):
    """
    递归删除指定的注册表项及其所有子项。

    :param key_handle: 已打开的父项句柄 (例如: HKEY_CURRENT_USER)。
    :param sub_key_name: 要删除的子项名称字符串。
    :param access: 用于 RegDeleteKeyEx 的访问权限，默认为 KEY_WOW64_64KEY。
    """
    try:
        # 尝试打开要删除的子项，用于枚举其子项和值。
        # KEY_ALL_ACCESS 或 KEY_SET_VALUE + KEY_ENUMERATE_SUB_KEYS + KEY_QUERY_VALUE
        # KEY_READ 是用于枚举的最小权限，这里我们用一个能打开的权限。
        key_to_delete = winreg.OpenKey(
            key_handle,
            sub_key_name,
            0,
            winreg.KEY_READ | access
        )
    except FileNotFoundError:
        app_logger.log_INFO(f"Registry key '{sub_key_name}' does not exist, no need to delete.")
        return

    # 1. 递归删除所有子项 (Subkeys)
    while True:
        try:
            # 枚举子项。由于每次删除后索引都会变化，所以总是从索引 0 开始。
            sub_key = winreg.EnumKey(key_to_delete, 0)
            full_path = f"{sub_key_name}\\{sub_key}"

            # 对子项进行递归调用
            # 注意：这里需要传入 key_handle 和 full_path，而不是 key_to_delete。
            # 简化起见，我们直接调用自身来删除 sub_key_name 下的 sub_key
            recursive_delete_key(key_handle, full_path, access)

        except OSError as e:
            # 当没有更多子项时，EnumKey 会抛出 OSError
            # (Python 3.3+ 的 winreg 模块通常将 Windows 错误码转换为 OSError)
            if e.winerror == 259:  # ERROR_NO_MORE_ITEMS
                break
            # 其他 OSError 可能是权限问题等，应该被抛出
            app_logger.log_exception(e)

    # 2. 关闭句柄
    winreg.CloseKey(key_to_delete)

    # 3. 删除父项自身
    app_logger.log_INFO(f"Deleting registry key: {sub_key_name}")
    try:
        # 使用 DeleteKeyEx 来执行实际的删除操作
        winreg.DeleteKeyEx(key_handle, sub_key_name, access)
    except PermissionError as e:
        app_logger.log_WARN(f"Permission error: Unable to delete '{sub_key_name}'. Please run as administrator.")
        app_logger.log_exception(e)
    except OSError as e:
        app_logger.log_WARN(f"Deletion failed (possibly already deleted or other reasons): {sub_key_name} - {e}")
        app_logger.log_exception(e)


def delete_AUMID(appId: str):
    if not IS_AT_LEAST_WIN10:
        return

    key_type = winreg.HKEY_CURRENT_USER
    keyPath = f"SOFTWARE\\Classes\\AppUserModelId\\{appId}"

    recursive_delete_key(key_type, keyPath)


def showMessageInTrayIcon(title: str,
                          text: str,
                          callback: Callable,
                          icon='', ):
    """
    通过全局共用的托盘图标，发送气球通知
    """
    from subwindow.main_ui_elements import tray_icon_instance
    tray_icon_instance.show_balloon_message(title, text, QIcon(icon), callback)


def showMessage(title: str,
                text: str,
                icon='',
                topicon='',
                buttons: list[Button] = None,
                callback: Callable = None,
                group: str = 'default',
                lowerText: str = ''):
    """
    显示通知消息

    Args:
        title (str): 标题文本
        text (str): 正文内容
        icon (str): 左侧显示图标的文件路径
        topicon (str): 顶部显示图片的文件路径
        buttons (list[Button]): 按钮列表
        callback (Callable): 点击通知时的回调函数
        lowerText (str): 在正文下方显示的浅色文本
        group (str): 消息所在组名称

    Notes:
        在 Windows 8.1 系统中会调用 win8toast.send_msg_async 来发送消息，
        此时 topicon 和 buttons 参数是无效的; \n
        在 Win7 及以下版本系统或非 Windows 系统下，会调用托盘图标发送气球通知。
    """
    buttons = buttons if buttons else []

    def handle_msg_click_winrt(event_args):
        is_button = False
        for b in buttons:
            if event_args.arguments == b.button_id and b.callback:
                is_button = True
                if b.callback: b.callback()
        if not is_button:
            if callback: callback()
        windows_global_toaster.remove_toast(newToast)

    if IS_WINDOWS:
        if IS_AT_LEAST_WIN10:
            newToast = Toast()
            newToast.group = group
            newToast.attribution_text = lowerText
            newToast.text_fields = [title, text]
            newToast.on_activated = lambda event_args: handle_msg_click_winrt(event_args)

            if icon:
                toastImage = ToastImage(icon)
                toastDP = ToastDisplayImage(toastImage, position=ToastImagePosition.AppLogo)
                newToast.AddImage(toastDP)
            if topicon:
                toastTopImage = ToastImage(topicon)
                toastTopDP = ToastDisplayImage(toastTopImage, position=ToastImagePosition.Hero)
                newToast.AddImage(toastTopDP)
            if buttons:
                for i in buttons:
                    newToast.AddAction(i.toast_button)

            windows_global_toaster.show_toast(newToast)
        elif IS_WIN8:
            win8toast.send_msg_async(title.replace('\n', ' '), text.replace('\n', ' '), icon, callback)
        else:
            showMessageInTrayIcon(title, text, callback, icon)
    else:
        showMessageInTrayIcon(title, text, callback, icon)
