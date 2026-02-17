from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QWidget
import gc
from publics import profile_mgr

distributed_window = []


def add_window(widget: QWidget, showAfterAdd=True):
    distributed_window.append(widget)
    window_rect = profile_mgr.get_window_rects(type(widget))
    if window_rect and not window_rect[4]:
        widget.setGeometry(window_rect[0],
                           window_rect[1],
                           window_rect[2],
                           window_rect[3])

    if showAfterAdd and window_rect and window_rect[4]:
        widget.showMaximized()
    elif showAfterAdd:
        widget.show()


def del_window(widget: QWidget):
    global distributed_window
    if widget in distributed_window:
        widget.hide()
        profile_mgr.add_window_rects(type(widget),
                                     widget.x(), widget.y() + 32,  # 算上标题栏的高度
                                     widget.width(), widget.height(),
                                     widget.isMaximized())

        # 清理内存
        distributed_window.remove(widget)
        widget.deleteLater()
        del widget
        QPixmapCache.clear()
        gc.collect()


def clear_windows():
    global distributed_window
    while distributed_window:
        del_window(distributed_window[0])
