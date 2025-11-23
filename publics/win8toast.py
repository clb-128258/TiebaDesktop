import os
import subprocess
import threading


def send_msg(title: str, msgitem: str, icon: str = '', callback=None):
    rtv = subprocess.call(
        f'{os.getcwd()}\\dlls\\toast.exe -t \"{title}\" -m \"{msgitem}\" -w -p \"{os.path.abspath(icon)}\"', shell=True)
    if rtv == 0 and callback is not None:
        callback()
    return rtv


def send_msg_async(title: str, msgitem: str, icon: str = '', callback=None):
    t = threading.Thread(target=send_msg, args=(title, msgitem, icon, callback), daemon=True)
    t.start()
