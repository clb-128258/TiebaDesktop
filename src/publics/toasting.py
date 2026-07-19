import pathlib
import random
from typing import Callable, Optional
import platform
import threading

from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer

from publics import win8toast
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
    if IS_AT_LEAST_WIN10:
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
