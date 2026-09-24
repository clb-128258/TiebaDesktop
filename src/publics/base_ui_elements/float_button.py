import enum

from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import QToolButton, QGraphicsDropShadowEffect


class NarrowButtonStatus(enum.Enum):
    ArrowLeft = enum.auto()
    ArrowRight = enum.auto()
    Refresh = enum.auto()
    Add = enum.auto()
    Settings = enum.auto()


class FloatingButton(QToolButton):
    """在 QWidget 上方悬浮的按钮"""

    def __init__(self, parent, moveUpCount=1):
        super().__init__()
        self.setParent(parent)
        self.init_ui()

        self.status = None
        self.moveUpCount = moveUpCount

    def init_ui(self):
        self.setFixedSize(45, 45)

        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(20)  # 阴影模糊半径
        shadow_effect.setColor(QColor(0, 0, 0, 120))  # 阴影颜色和透明度
        shadow_effect.setOffset(4, 4)  # 阴影偏移量
        self.setGraphicsEffect(shadow_effect)

        self.setStyleSheet(f"""QToolButton {{
            background-color: rgba(91, 68, 200, 210);
            border: none;
            border-radius: 22px;
            padding: 4px;
            icon-size: 32px;
        }}
        QToolButton:hover {{
            background-color: #6a50ea;
        }}
        QToolButton:pressed {{
            background-color: #6969ff;
        }}""")

    def set_button_status(self, status: NarrowButtonStatus):
        self.status = status
        icon_path = ''

        tool_tip = '悬浮按钮'
        if status in (NarrowButtonStatus.ArrowRight, NarrowButtonStatus.ArrowLeft):
            tool_tip = '点击切换到另一页面'
        elif status == NarrowButtonStatus.Refresh:
            tool_tip = '刷新'
        elif status == NarrowButtonStatus.Add:
            tool_tip = '添加'
        elif status == NarrowButtonStatus.Settings:
            tool_tip = '管理'
        self.setToolTip(tool_tip)

        if status == NarrowButtonStatus.ArrowRight:
            icon_path = f'ui/icon_white/forward.png'
        elif status == NarrowButtonStatus.ArrowLeft:
            icon_path = f'ui/icon_white/back.png'
        elif status == NarrowButtonStatus.Refresh:
            icon_path = f'ui/icon_white/refresh.png'
        elif status == NarrowButtonStatus.Add:
            icon_path = f'ui/icon_white/add.png'
        elif status == NarrowButtonStatus.Settings:
            icon_path = f'ui/icon_white/settings.png'
        self.setIcon(QIcon(icon_path))

        self.move_button()

    def move_button(self):
        put_left_button_list = [NarrowButtonStatus.ArrowRight, NarrowButtonStatus.Refresh, NarrowButtonStatus.Add,
                                NarrowButtonStatus.Settings]
        put_right_button_list = [NarrowButtonStatus.ArrowLeft]
        move_value = 20
        x, y = 0, 0

        if self.status in put_left_button_list:
            x = self.parent().width() - self.width() - move_value
            y = self.parent().height() - self.moveUpCount * (self.height() + move_value)
        elif self.status in put_right_button_list:
            x = move_value
            y = self.parent().height() - self.moveUpCount * (self.height() + move_value)
        self.move(x, y)
