"""基础 UI 组件库，负责 UI 的主题管理等"""
import ctypes
import enum
from ctypes import wintypes

import yarl
import pyperclip
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu, QAction, QLabel, QWidget, QDialog, QLineEdit, \
    QTextEdit, QPlainTextEdit, QToolButton, QGraphicsDropShadowEffect
from PyQt5.QtGui import QTextDocumentFragment, QColor, QPalette, QIcon

from publics import funcs, profile_mgr, qt_window_mgr, app_logger, request_mgr

# --- Windows API 常量与定义 ---
WM_THEMECHANGED = 0x031A
WM_SETTINGCHANGE = 0x001A
# DWM 属性 ID
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 11/Win10 20H1+
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # 旧版 Win10，从 1809 版本开始

dwmapi = ctypes.WinDLL("dwmapi")

# 标记上一次是否启用深色模式
last_apps_dark_mode = funcs.get_system_dark_mode_status()


def create_thread_content_menu(parent_label: QLabel):
    """创建一个文本右键菜单"""

    def open_search_window(text):
        from subwindow.tieba_search_entry import TiebaSearchWindow
        window = TiebaSearchWindow(profile_mgr.current_bduss, profile_mgr.current_stoken)
        qt_window_mgr.add_window(window)
        window.lineEdit.setText(text)
        window.start_search()

    def get_search_engine_link():
        try:
            settings = profile_mgr.local_config['other_settings']['context_menu_search_engine']
            if settings['preset']:
                return profile_mgr.sep_name_map_inverted[settings['preset']], profile_mgr.search_engine_presets[
                    settings['preset']]
            else:
                return '自定义引擎', settings['custom_url']
        except Exception as e:
            app_logger.log_exception(e)
            return 'Bing', profile_mgr.search_engine_presets['bing']

    selected_text = parent_label.selectedText()
    all_text = QTextDocumentFragment.fromHtml(parent_label.text()).toPlainText() if parent_label.text().startswith(
        '<') else parent_label.text()

    menu = BaseQMenu(parent_label)

    copy_selected = QAction('复制所选', parent_label)
    copy_selected.triggered.connect(lambda: pyperclip.copy(selected_text))
    if not selected_text or selected_text == all_text:
        copy_selected.setVisible(False)
    menu.addAction(copy_selected)

    copy_all = QAction('复制全文', parent_label)
    copy_all.triggered.connect(lambda: pyperclip.copy(all_text))
    menu.addAction(copy_all)

    select_all = QAction('全选文本', parent_label)
    select_all.triggered.connect(lambda: parent_label.setSelection(0, len(all_text)))
    menu.addAction(select_all)

    menu.addSeparator()

    search_tb = QAction(f'在贴吧内搜索“{funcs.cut_string(selected_text, 20)}”', parent_label)
    search_tb.triggered.connect(lambda: open_search_window(selected_text))
    if not selected_text:
        search_tb.setVisible(False)
    menu.addAction(search_tb)

    # 链接直接跳转
    if selected_text.startswith((request_mgr.SCHEME_HTTP, request_mgr.SCHEME_HTTPS)):
        url = yarl.URL(selected_text)
        jump_webpage = QAction(f'跳转到网页 {url.host}', parent_label)
        jump_webpage.triggered.connect(lambda: funcs.open_url_in_browser(selected_text))
        menu.addAction(jump_webpage)

    engine_name, engine_link = get_search_engine_link()
    engine_link = engine_link.replace('[query]', selected_text)
    search_network = QAction(f'在 {engine_name} 中搜索“{funcs.cut_string(selected_text, 20)}”', parent_label)
    search_network.triggered.connect(lambda: funcs.open_url_in_browser(engine_link))
    if not selected_text:
        search_network.setVisible(False)
    menu.addAction(search_network)

    return menu


def set_window_dark_mode(hwnd, enabled: bool):
    """设置窗口标题栏的深色模式"""
    is_dark = ctypes.c_int(1 if enabled else 0)

    # 尝试使用新版 ID
    res = dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(is_dark),
        ctypes.sizeof(is_dark)
    )

    # 如果失败，尝试旧版 ID
    if res != 0:
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(is_dark),
            ctypes.sizeof(is_dark)
        )


def set_widget_dark_mode(widget: QWidget):
    """为 Qt 窗口设置标题栏颜色"""
    if os.name == 'nt' and widget.isWindow():
        is_dark = profile_mgr.get_theme_policy() == 2
        set_window_dark_mode(int(widget.winId()), is_dark)


def update_placeholder_color(parent_widget, color_hex="#808080"):
    """
    递归遍历界面，设置所有输入框的占位符颜色
    :param parent_widget: 顶层窗口或容器 (如 self)
    :param color_hex: 目标占位符颜色的十六进制字符串
    """
    target_color = QColor(color_hex)

    # 查找所有类型的输入框
    input_widgets = parent_widget.findChildren((QLineEdit, QTextEdit, QPlainTextEdit))

    for widget in input_widgets:
        palette = widget.palette()
        # 设置 PlaceholderText 角色
        palette.setColor(QPalette.PlaceholderText, target_color)
        widget.setPalette(palette)


def set_theme_qss_as_cfg(widget, extended_qss=''):
    def replace_color_flags(qss: str):
        bg_color = profile_mgr.get_theme_color_string()
        font_color = profile_mgr.get_theme_font_color_string()

        qss = qss.replace('BG_COLOR', bg_color)
        qss = qss.replace('FONT_COLOR', font_color)

        return qss

    qss_list = []
    policy = profile_mgr.get_theme_policy()

    if policy == 1:
        qss_list.append(replace_color_flags(profile_mgr.theme_qss['bright']))
    elif policy == 2:
        qss_list.append(replace_color_flags(profile_mgr.theme_qss['dark']))
    qss_list.append(replace_color_flags(profile_mgr.theme_qss['common']))

    widget.setStyleSheet('\n'.join(qss_list) + extended_qss)
    update_placeholder_color(widget, '#666666' if policy == 2 else '#abb2bf')  # 为输入框专门设置占位符颜色


def handle_native_event(widget, refreshThemeFunc, eventType, message):
    """
    处理系统原生事件，并同步主题设置

    Args:
        widget (QWidget): 接收到事件的Widget
        refreshThemeFunc (Callable): 在需要刷新主题时，调用的方法
        eventType: 从 nativeEvent 事件中获取
        message: 从 nativeEvent 事件中获取
    Notes:
        该函数仅供顶级窗口使用
    """
    global last_apps_dark_mode
    if eventType == b'windows_generic_MSG':
        # 将指针转换为 MSG 结构体
        msg = wintypes.MSG.from_address(int(message))

        # 获取 lParam
        try:
            change_area = ctypes.wstring_at(msg.lParam)
        except:
            change_area = ""

        # 监听是否修改系统设置
        if msg.message == WM_SETTINGCHANGE and change_area == "ImmersiveColorSet":
            # 在修改了颜色设置时，才读取各种设置，避免不必要性能开销
            paths = ['theme_settings', 'bright_dark_policy']
            follow_sys_theme = funcs.get_dict_value_treely(profile_mgr.local_config, paths, 0) == 0
            is_darkmode = funcs.get_system_dark_mode_status()

            if follow_sys_theme and is_darkmode != last_apps_dark_mode:
                # 执行主题切换
                last_apps_dark_mode = is_darkmode
                refreshThemeFunc()
                return True

    return False


class NarrowButtonStatus(enum.Enum):
    ArrowLeft = enum.auto()
    ArrowRight = enum.auto()


class BaseQMenu(QMenu):
    """所有上下文菜单引用的 QMenu 父类"""

    def __init__(self, parent=None):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | Qt.NoDropShadowWindowHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.set_theme_qss()

    def set_theme_qss(self):
        """载入标准样式主题"""
        set_theme_qss_as_cfg(self)

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class WindowBaseQWidget(QWidget):
    """所有 独立窗口/嵌入组件 引用的 QWidget 父类"""

    def __init__(self):
        super().__init__()
        self.isWindowShowed = False

    def showEvent(self, a0):
        a0.accept()
        if not self.isWindowShowed:
            self.isWindowShowed = True
            self.reset_theme()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, self.reset_theme, eventType, message)
        if is_changed:
            qt_window_mgr.refresh_all_windows_theme()
        return super().nativeEvent(eventType, message)

    def set_theme_qss(self):
        """载入标准样式主题，同时为窗口标题栏设置颜色"""
        set_theme_qss_as_cfg(self)
        set_widget_dark_mode(self)

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class WindowBaseQDialog(QDialog):
    """所有独立模态窗口引用的 QDialog 父类"""

    def __init__(self):
        super().__init__()
        self.isWindowShowed = False

    def showEvent(self, a0):
        a0.accept()
        if not self.isWindowShowed:
            self.isWindowShowed = True
            self.reset_theme()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, self.reset_theme, eventType, message)
        if is_changed:
            qt_window_mgr.refresh_all_windows_theme()
        return super().nativeEvent(eventType, message)

    def set_theme_qss(self):
        """载入标准样式主题，同时为窗口标题栏设置颜色"""
        set_theme_qss_as_cfg(self)
        set_widget_dark_mode(self)

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class FloatingNarrowButton(QToolButton):
    """在 QWidget 上方悬浮的导航按钮"""

    def __init__(self, parent):
        super().__init__()
        self.setParent(parent)

        self.setToolTip('点击切换到另一页面')
        self.init_ui()

    def init_ui(self):
        self.setFixedSize(39, 39)

        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(30)  # 阴影模糊半径
        shadow_effect.setColor(QColor(0, 0, 0, 50))  # 阴影颜色和透明度
        shadow_effect.setOffset(2, 2)  # 阴影偏移量
        self.setGraphicsEffect(shadow_effect)

        self.setStyleSheet(f"""QToolButton {{
            background-color: #5b44c8;
            border: none;
            border-radius: 19px;
            padding: 4px;
            icon-size: 30px;
        }}
        QToolButton:hover {{
            background-color: #6a50ea;
        }}
        QToolButton:pressed {{
            background-color: #6969ff;
        }}""")

    def set_button_status(self, status: NarrowButtonStatus):
        icon_path = ''
        move_value = 20
        x, y = 0, 0

        if status == NarrowButtonStatus.ArrowRight:
            icon_path = f'ui/icon_white/forward.png'
        elif status == NarrowButtonStatus.ArrowLeft:
            icon_path = f'ui/icon_white/back.png'
        self.setIcon(QIcon(icon_path))

        if status == NarrowButtonStatus.ArrowRight:
            x = self.parent().width() - self.width() - move_value
            y = self.parent().height() - self.height() - move_value
        elif status == NarrowButtonStatus.ArrowLeft:
            x = move_value
            y = self.parent().height() - self.height() - move_value
        self.move(x, y)
