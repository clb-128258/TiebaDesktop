import pathlib
import winreg
import random

from windows_toasts import InteractableWindowsToaster, Toast, ToastDisplayImage, ToastImagePosition, ToastImage, \
    MIN_VERSION, ToastButton
from typing import Callable, Optional
import platform

from publics import win8toast
import consts


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
        self.toast_button = ToastButton(text, self.button_id)


def init_AUMID(appId: str, appName: str, iconPath: Optional[pathlib.Path]):
    if platform.system() == 'Windows':
        if int(platform.version().split('.')[-1]) >= MIN_VERSION:
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


def showMessage(title: str,
                text: str,
                icon='',
                topicon='',
                buttons: list[Button] = None,
                callback: Callable = None,
                lowerText=''):
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

    Notes:
        在 Windows 8.1 系统中会调用 win8toast.send_msg_async 来发送消息，
        此时 topicon 和 buttons 参数是无效的
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
        wintoaster.remove_toast(newToast)

    if platform.system() == 'Windows':
        if int(platform.version().split('.')[-1]) >= MIN_VERSION:
            wintoaster = InteractableWindowsToaster(lowerText, consts.WINDOWS_AUMID)
            newToast = Toast()
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

            wintoaster.show_toast(newToast)
        elif int(platform.version().split('.')[-1]) == 9600:
            win8toast.send_msg_async(title.replace('\n', ' '), text.replace('\n', ' '), icon, callback)
