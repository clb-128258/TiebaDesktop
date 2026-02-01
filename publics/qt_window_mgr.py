from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QWidget
import gc

distributed_window = []


def add_window(widget: QWidget, showAfterAdd=True):
    distributed_window.append(widget)
    if showAfterAdd:
        widget.show()


def del_window(widget: QWidget):
    global distributed_window
    if widget in distributed_window:
        widget.hide()

        # 清理内存
        distributed_window.remove(widget)
        widget.destroy()
        widget.deleteLater()
        del widget
        QPixmapCache.clear()
        gc.collect()


def clear_windows():
    global distributed_window
    while distributed_window:
        del_window(distributed_window[0])
