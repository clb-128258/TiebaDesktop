"""Windows 8 系统下的通知工具"""
import os
import subprocess
import threading


def send_msg(title: str, msgitem: str, icon: str = '', callback=None):
    icon_arg = f'-p \"{os.path.abspath(icon)}\"' if icon else ''
    rtv = subprocess.call(
        f'{os.getcwd()}\\dlls\\toast.exe -w -t \"{title}\" -m \"{msgitem}\" {icon_arg}', shell=True)
    if rtv == 0 and callback is not None:
        callback()
    return rtv


def send_msg_async(title: str, msgitem: str, icon: str = '', callback=None):
    t = threading.Thread(target=send_msg, args=(title, msgitem, icon, callback), daemon=True)
    t.start()
