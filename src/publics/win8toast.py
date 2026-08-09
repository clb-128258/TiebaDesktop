"""Windows 8 系统下的通知工具"""
import os
import subprocess
import threading


def send_msg(title: str, msgitem: str, icon: str = '', callback=None):
    icon_arg = f'-p \"{os.path.abspath(icon)}\"' if icon else ''
    shell = f'\"{os.getcwd()}\\binres\\toast.exe\" -w -t \"{title}\" -m \"{msgitem}\" {icon_arg}'

    process = subprocess.Popen(shell, shell=True)
    try:
        rtv = process.wait(300)
    except subprocess.TimeoutExpired:
        process.kill()
        rtv = -1

    if rtv == 0 and callback is not None:
        callback()
    return rtv


def send_msg_async(title: str, msgitem: str, icon: str = '', callback=None):
    t = threading.Thread(target=send_msg, args=(title, msgitem, icon, callback), daemon=True)
    t.start()
