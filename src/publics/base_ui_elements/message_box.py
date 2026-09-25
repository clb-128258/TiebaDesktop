"""统一的消息对话框组件"""

import enum
import os

from PyQt5.QtCore import QRect, Qt, QT_VERSION_STR
from PyQt5.QtWidgets import QApplication, QCommandLinkButton, QSizePolicy, QVBoxLayout

from publics import qt_image
from publics.base_ui_elements import base_ui
from ui import messagebox

if os.name == 'nt':
    import win32api
    import win32con


class MessageBoxIcon(enum.IntEnum):
    """消息对话框图标类型"""

    NoIcon = 0
    Information = 1
    Warning = 2
    Critical = 3
    Question = 4


class StandardButton(enum.IntFlag):
    """消息对话框按钮类型"""

    NoButton = 0x00000000
    Ok = 0x00000400
    Save = 0x00000800
    SaveAll = 0x00001000
    Open = 0x00002000
    Yes = 0x00004000
    YesToAll = 0x00008000
    No = 0x00010000
    NoToAll = 0x00020000
    Abort = 0x00040000
    Retry = 0x00080000
    Ignore = 0x00100000
    Close = 0x00200000
    Cancel = 0x00400000
    Discard = 0x00800000
    Help = 0x01000000
    Apply = 0x02000000
    Reset = 0x04000000
    RestoreDefaults = 0x08000000


_BUTTON_ORDER = (
    StandardButton.Help,
    StandardButton.Yes,
    StandardButton.No,
    StandardButton.Ok,
    StandardButton.Cancel,
    StandardButton.Save,
    StandardButton.SaveAll,
    StandardButton.Open,
    StandardButton.Close,
    StandardButton.Retry,
    StandardButton.Ignore,
    StandardButton.Abort,
    StandardButton.Discard,
    StandardButton.Apply,
    StandardButton.Reset,
    StandardButton.RestoreDefaults,
)

_BUTTON_META = {
    StandardButton.Ok: ('确定', '确认并关闭此提示'),
    StandardButton.Yes: ('是', '确认执行当前操作'),
    StandardButton.No: ('否', '取消当前操作'),
    StandardButton.Cancel: ('取消', '关闭当前操作'),
    StandardButton.Help: ('帮助', '打开相关帮助或网页'),
    StandardButton.Save: ('保存', '保存当前更改'),
    StandardButton.SaveAll: ('全部保存', '保存所有未保存的更改'),
    StandardButton.Open: ('打开', '打开所选项目'),
    StandardButton.Close: ('关闭', '关闭当前内容'),
    StandardButton.Retry: ('重试', '重新执行当前操作'),
    StandardButton.Ignore: ('忽略', '忽略当前项目并继续'),
    StandardButton.Abort: ('中止', '中止当前操作'),
    StandardButton.Discard: ('放弃', '放弃未保存的更改'),
    StandardButton.Apply: ('应用', '应用当前更改'),
    StandardButton.Reset: ('重置', '将当前设置恢复为默认值'),
    StandardButton.RestoreDefaults: ('恢复默认值', '恢复默认设置'),
}


class MessageBox(base_ui.WindowBaseQDialog, messagebox.Ui_messageBox):
    """基于 QCommandLinkButton 的现代化消息对话框"""

    NoButton = StandardButton.NoButton
    Ok = StandardButton.Ok
    Save = StandardButton.Save
    SaveAll = StandardButton.SaveAll
    Open = StandardButton.Open
    Yes = StandardButton.Yes
    YesToAll = StandardButton.YesToAll
    No = StandardButton.No
    NoToAll = StandardButton.NoToAll
    Abort = StandardButton.Abort
    Retry = StandardButton.Retry
    Ignore = StandardButton.Ignore
    Close = StandardButton.Close
    Cancel = StandardButton.Cancel
    Discard = StandardButton.Discard
    Help = StandardButton.Help
    Apply = StandardButton.Apply
    Reset = StandardButton.Reset
    RestoreDefaults = StandardButton.RestoreDefaults

    NoIcon = MessageBoxIcon.NoIcon
    Information = MessageBoxIcon.Information
    Warning = MessageBoxIcon.Warning
    Critical = MessageBoxIcon.Critical
    Question = MessageBoxIcon.Question

    def __init__(self,
                 icon: int = MessageBoxIcon.Information,
                 title: str = '',
                 text: str = '',
                 buttons: int = StandardButton.NoButton,
                 parent=None,
                 defaultButton: int = StandardButton.NoButton):
        super().__init__()

        self._parent = parent
        self._icon_type = MessageBoxIcon(icon)
        self._sound_played = False
        self._size_fixed = False
        self._buttons = {}
        self._default_button = None
        self._init_ui(title, text, icon)
        self.setStandardButtons(buttons)
        self.setDefaultButton(defaultButton)
        self.reset_theme()

    def _init_ui(self, title: str, text: str, icon: int):
        self.setupUi(self)

        if self._parent is not None:
            self.setParent(self._parent)

        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setSizeGripEnabled(False)
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)

        self.messageBoxTitle.setText(title)
        self.messageBoxTitle.setVisible(bool(title))
        self.messageBoxText.setText(text)
        self.messageBoxText.setVisible(bool(text))
        self.messageBoxIcon.clear()
        self._set_icon(icon)

        self._button_layout = QVBoxLayout(self.messageBoxButtons)
        self._button_layout.setContentsMargins(0, 0, 0, 0)
        self._button_layout.setSpacing(8)

        self.verticalLayout_2.setStretch(1, 0)
        self.messageBoxText.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        if self.verticalLayout.count() > 1:
            self.verticalLayout.removeItem(self.verticalLayout.itemAt(1))
        self.verticalLayout.addStretch(1)

    def _set_icon(self, icon: int):
        icon = MessageBoxIcon(icon)
        if icon == MessageBoxIcon.NoIcon:
            self.messageBoxIcon.hide()
            return

        self.messageBoxIcon.show()
        if icon == MessageBoxIcon.Warning:
            icon_file = 'ui/warning.png'
        elif icon == MessageBoxIcon.Critical:
            icon_file = 'ui/error.png'
        else:
            icon_file = 'ui/information.png'
        self.messageBoxIcon.setPixmap(qt_image.get_pixmap_icon_from_file(icon_file, 30))

    def setStandardButtons(self, buttons: int):
        """重新设置对话框底部的标准按钮"""
        buttons = StandardButton(buttons)

        while self._button_layout.count():
            layout_item = self._button_layout.takeAt(0)
            button = layout_item.widget()
            if button is not None:
                button.deleteLater()
        self._buttons.clear()
        self._default_button = None

        first_button = None
        for standard_button in _BUTTON_ORDER:
            if not (buttons & standard_button):
                continue

            button_text, description = _BUTTON_META[standard_button]
            button = QCommandLinkButton(button_text, description, self.messageBoxButtons)
            button.setObjectName('messageBoxButton')
            button.setCursor(Qt.PointingHandCursor)
            button.setFlat(False)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, value=standard_button: self.done(int(value)))
            self._button_layout.addWidget(button)
            self._buttons[standard_button] = button
            if first_button is None:
                first_button = standard_button

        if first_button is not None:
            self.setDefaultButton(first_button)

    def button(self, which: int):
        """获取指定标准按钮对应的 QCommandLinkButton"""
        return self._buttons.get(StandardButton(which))

    def setDefaultButton(self, button: int):
        """设置默认聚焦并按回车触发的按钮"""
        standard_button = StandardButton(button)
        target_button = self._buttons.get(standard_button)
        if target_button is None:
            return

        if self._default_button is not None:
            self._default_button.setDefault(False)
        target_button.setDefault(True)
        target_button.setFocus(Qt.OtherFocusReason)
        self._default_button = target_button

    def done(self, result: int):
        super().done(int(result))

    def reject(self):
        for standard_button in (StandardButton.Cancel, StandardButton.No, StandardButton.Ok):
            if standard_button in self._buttons:
                self.done(int(standard_button))
                return
        super().reject()

    def showEvent(self, a0):
        if not self._size_fixed:
            self._apply_optimal_fixed_size()
        super().showEvent(a0)
        if not self._sound_played:
            self._sound_played = True
            self._play_prompt_sound()

    def _apply_optimal_fixed_size(self):
        """在显示前根据当前内容确定最佳尺寸并固定窗口大小"""
        self.ensurePolished()
        for button in self._buttons.values():
            button.setFixedHeight(
                max(button.minimumSizeHint().height(), button.sizeHint().height() - 5))

        if self.layout() is not None:
            self.layout().activate()
        self.adjustSize()

        if self.messageBoxText.text():
            for _ in range(2):
                if self.layout() is not None:
                    self.layout().activate()

                text_width = max(1, self.messageBoxText.width())
                text_height = self.messageBoxText.fontMetrics().boundingRect(
                    QRect(0, 0, text_width, 100000),
                    Qt.TextWordWrap | Qt.AlignLeft,
                    self.messageBoxText.text(),
                ).height()

                if text_height > 0:
                    self.messageBoxText.setFixedHeight(text_height)

                if self.layout() is not None:
                    self.layout().activate()
                self.adjustSize()

        if self.messageBoxTitle.text():
            for _ in range(2):
                if self.layout() is not None:
                    self.layout().activate()

                text_width = max(1, self.messageBoxTitle.width())
                text_height = self.messageBoxTitle.fontMetrics().boundingRect(
                    QRect(0, 0, text_width, 100000),
                    Qt.TextWordWrap | Qt.AlignLeft,
                    self.messageBoxTitle.text(),
                ).height()

                if text_height > 0:
                    self.messageBoxTitle.setFixedHeight(text_height)

                if self.layout() is not None:
                    self.layout().activate()
                self.adjustSize()

        self.setFixedSize(self.size())
        self._size_fixed = True

    def _play_prompt_sound(self):
        """根据消息类型播放对应的系统提示音"""
        if os.name != 'nt':
            QApplication.beep()
            return

        sound_map = {
            MessageBoxIcon.NoIcon: win32con.MB_OK,
            MessageBoxIcon.Information: win32con.MB_ICONASTERISK,
            MessageBoxIcon.Warning: win32con.MB_ICONEXCLAMATION,
            MessageBoxIcon.Critical: win32con.MB_ICONHAND,
            MessageBoxIcon.Question: win32con.MB_ICONQUESTION,
        }
        win32api.MessageBeep(sound_map.get(self._icon_type, win32con.MB_OK))

    def set_theme_qss(self):
        """应用项目通用主题样式"""
        super().set_theme_qss()

    @classmethod
    def information(cls, parent, title: str, text: str,
                    buttons: int = StandardButton.Ok,
                    defaultButton: int = StandardButton.NoButton):
        return cls._show(parent, MessageBoxIcon.Information, title, text, buttons, defaultButton)

    @classmethod
    def warning(cls, parent, title: str, text: str,
                buttons: int = StandardButton.Ok,
                defaultButton: int = StandardButton.NoButton):
        return cls._show(parent, MessageBoxIcon.Warning, title, text, buttons, defaultButton)

    @classmethod
    def critical(cls, parent, title: str, text: str,
                 buttons: int = StandardButton.Ok,
                 defaultButton: int = StandardButton.NoButton):
        return cls._show(parent, MessageBoxIcon.Critical, title, text, buttons, defaultButton)

    @classmethod
    def question(cls, parent, title: str, text: str,
                 buttons: int = StandardButton.Yes | StandardButton.No,
                 defaultButton: int = StandardButton.NoButton):
        return cls._show(parent, MessageBoxIcon.Question, title, text, buttons, defaultButton)

    @classmethod
    def aboutQt(cls, parent, title: str = '关于 Qt'):
        text = (f'当前程序使用 Qt {QT_VERSION_STR} 构建。\n'
                'Qt 是一个跨平台应用程序开发框架。\n'
                '本程序遵循 Qt 的开源许可协议进行使用。')
        return cls.information(parent, title, text, StandardButton.Ok)

    @classmethod
    def _show(cls, parent, icon: int, title: str, text: str, buttons: int, defaultButton: int):
        message_box = cls(icon, title, text, buttons, parent, defaultButton)

        result = message_box.exec()
        message_box.deleteLater()
        return result
