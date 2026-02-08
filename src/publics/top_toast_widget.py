from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QTimer, QEvent, QPropertyAnimation, QEasingCurve, QPoint, Qt
from ui import top_toast
import enum
import queue

Y_POS_MOVE_VALUE = 30  # y坐标偏移量
ANIMATION_TIME = 150  # 动画显示时间
ICON_SIZE = 20  # 提示图标大小


class ToastIconType(enum.IntEnum):
    """
    顶部通知消息的图标类型

    Notes:
        NO_ICON 不显示图标\n
        INFORMATION 提示信息图标，即小写'i'图标\n
        ERROR 错误图标\n
        SUCCESS 成功图标
    """
    NO_ICON = 1
    INFORMATION = 2
    ERROR = 3
    SUCCESS = 4


class ToastMessage:
    """
    一个顶部通知消息

    Args:
        title (str): 通知标题
        appear_duration (int): 显示时间 以毫秒为单位
        icon_type (ToastIconType): 左侧显示的图标类型
    """

    def __init__(self,
                 title: str = '',
                 appear_duration: int = 2000,
                 icon_type: ToastIconType = ToastIconType.NO_ICON):
        self.icon_type = icon_type
        self.title = title
        self.appear_duration = appear_duration


class TopToaster(QWidget, top_toast.Ui_Form):
    """顶部消息显示组件"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 始终置顶
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 背景透明
        self.setFixedHeight(32)
        self.init_pixmap_cache()

        self._is_showing = False
        self.toast_queue = queue.Queue()
        self.toast_hide_timer = QTimer(self)
        self.toast_hide_timer.setSingleShot(True)
        self.toast_hide_timer.timeout.connect(self.hideWithAnimation)

        self.init_animation()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Resize and source is self.parent():  # 父组件调整大小
            self._sync_parent_widget_size()
        return super(TopToaster, self).eventFilter(source, event)  # 照常处理事件

    def showWithAnimation(self):
        self.show()
        self._sync_parent_widget_size()
        self._animation_show.setStartValue(QPoint(self._calc_x_pos(), -Y_POS_MOVE_VALUE))
        self._animation_show.setEndValue(QPoint(self._calc_x_pos(), Y_POS_MOVE_VALUE))
        self._animation_show.start()

    def hideWithAnimation(self):
        self._animation_hide.setStartValue(QPoint(self._calc_x_pos(), Y_POS_MOVE_VALUE))
        self._animation_hide.setEndValue(QPoint(self._calc_x_pos(), -Y_POS_MOVE_VALUE))
        self._animation_hide.start()

    def init_animation(self):
        self._animation_show = QPropertyAnimation(self, b"pos")
        self._animation_show.setDuration(ANIMATION_TIME)
        self._animation_show.setEasingCurve(QEasingCurve.OutCubic)  # 弹出时用 OutCubic

        self._animation_hide = QPropertyAnimation(self, b"pos")
        self._animation_hide.setDuration(ANIMATION_TIME)
        self._animation_hide.setEasingCurve(QEasingCurve.InCubic)  # 收回时用 InCubic
        self._animation_hide.finished.connect(self._hide_toast_widget_fully)

    def init_pixmap_cache(self):
        self.success_icon = QPixmap('ui/success.png').scaled(ICON_SIZE, ICON_SIZE,
                                                             transformMode=Qt.SmoothTransformation)
        self.error_icon = QPixmap('ui/error.png').scaled(ICON_SIZE, ICON_SIZE,
                                                         transformMode=Qt.SmoothTransformation)
        self.info_icon = QPixmap('ui/information.png').scaled(ICON_SIZE, ICON_SIZE,
                                                              transformMode=Qt.SmoothTransformation)

    def _calc_x_pos(self):
        if not self.parent():
            return 0
        return int(self.parent().width() / 2 - self.width() / 2)

    def _sync_parent_widget_size(self):
        self.adjustSize()
        self.move(self._calc_x_pos(), self.y())

    def _hide_toast_widget_fully(self):
        self.hide()
        self._is_showing = False
        self._show_one_toast_from_queue()

    def _set_toast_widget(self, toast: ToastMessage):
        self.label_2.setText(toast.title)
        self.label.show()
        if toast.icon_type == ToastIconType.NO_ICON:
            self.label.hide()
        elif toast.icon_type == ToastIconType.SUCCESS:
            self.label.setPixmap(self.success_icon)
        elif toast.icon_type == ToastIconType.ERROR:
            self.label.setPixmap(self.error_icon)
        elif toast.icon_type == ToastIconType.INFORMATION:
            self.label.setPixmap(self.info_icon)

        self.showWithAnimation()
        self.toast_hide_timer.start(toast.appear_duration)

    def _show_one_toast_from_queue(self):
        if not self.toast_queue.empty():
            self._is_showing = True
            toast = self.toast_queue.get()
            self._set_toast_widget(toast)

    def setCoverWidget(self, widget: QWidget):
        self.setParent(widget)
        widget.installEventFilter(self)

        self.pos().setY(-Y_POS_MOVE_VALUE)
        self._sync_parent_widget_size()
        self.hide()

    def showToast(self, toast: ToastMessage):
        self.toast_queue.put(toast)
        if not self._is_showing:
            self._show_one_toast_from_queue()
