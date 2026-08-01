"""基础 UI 组件库，负责 UI 的主题管理等"""
import ctypes
import enum
from ctypes import wintypes
import yarl
import pyperclip
import re

from PyQt5.QtCore import Qt, QTimer, QObject
from PyQt5.QtWidgets import QMenu, QAction, QLabel, QWidget, QDialog, QLineEdit, \
    QTextEdit, QPlainTextEdit, QToolButton, QGraphicsDropShadowEffect, QMainWindow
from PyQt5.QtGui import QTextDocumentFragment, QColor, QPalette, QIcon, QPainter, QPixmap, QPixmapCache

from publics import funcs, profile_mgr, qt_window_mgr, app_logger, request_mgr
from publics.base_ui_elements.windows_features.dwm_visual import WM_SETTINGCHANGE, set_widget_background_mode

# 邮箱判别正则
email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# 标记上一次是否启用深色模式
last_apps_dark_mode = funcs.get_system_dark_mode_status()

background_pixmap = None
background_pixmap_hex = ''


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
                return '自定义搜索引擎', settings['custom_url']
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

    # 邮箱地址识别
    if re.match(email_regex, selected_text):
        jump_mailapp = QAction(f'向 {selected_text} 发送电子邮件', parent_label)
        jump_mailapp.triggered.connect(lambda: funcs.open_url_in_browser('mailto://' + selected_text))
        menu.addAction(jump_mailapp)

    # 链接直接跳转
    if selected_text.startswith((request_mgr.SCHEME_HTTP, request_mgr.SCHEME_HTTPS)):
        url = yarl.URL(selected_text)
        jump_webpage = QAction(f'打开网页 {url.host}', parent_label)
        jump_webpage.triggered.connect(lambda: funcs.open_url_in_browser(selected_text))
        menu.addAction(jump_webpage)

    search_tb = QAction(f'在贴吧内搜索“{funcs.cut_string(selected_text, 20)}”', parent_label)
    search_tb.triggered.connect(lambda: open_search_window(selected_text))
    if not selected_text:
        search_tb.setVisible(False)
    menu.addAction(search_tb)

    engine_name, engine_link = get_search_engine_link()
    engine_link = engine_link.replace('[query]', selected_text)
    search_network = QAction(f'在 {engine_name} 中搜索“{funcs.cut_string(selected_text, 20)}”', parent_label)
    search_network.triggered.connect(lambda: funcs.open_url_in_browser(engine_link))
    if not selected_text:
        search_network.setVisible(False)
    menu.addAction(search_network)

    return menu


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

    def get_bg_color_qss():
        # 处理纯色背景
        bg_config = funcs.get_dict_value_treely(profile_mgr.local_config,
                                                ['theme_settings', 'background'],
                                                profile_mgr.local_config_model['theme_settings']['background'])

        if bg_config['dwm_bg']['enable']:
            return ''
        else:
            bg_color = profile_mgr.get_theme_color_string()
            bg_qss = (f'QMainWindow {{background-color: {bg_color};}}'
                      f'QDialog {{background-color: {bg_color};}}'
                      f'QWidget#Form {{background-color: {bg_color};}}')

            return bg_qss

    qss_list = []
    policy = profile_mgr.get_theme_policy()

    if policy == 1:
        qss_list.append(replace_color_flags(profile_mgr.theme_qss['bright']))
    elif policy == 2:
        qss_list.append(replace_color_flags(profile_mgr.theme_qss['dark']))
    qss_list.append(replace_color_flags(profile_mgr.theme_qss['common']))
    qss_list.append(get_bg_color_qss())

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


def init_bg_pixmap():
    """初始化背景 QPixmap"""

    global background_pixmap, background_pixmap_hex

    bg_config = funcs.get_dict_value_treely(profile_mgr.local_config,
                                            ['theme_settings', 'background'],
                                            profile_mgr.local_config_model['theme_settings']['background'])
    enable = bg_config['common_bg']['bg_picture']['enable'] and not bg_config['dwm_bg']['enable']
    file_path = bg_config['common_bg']['bg_picture']['image_path']
    image_opacity = bg_config['common_bg']['bg_picture']['image_opacity']
    image_hex = f'{file_path}+{image_opacity}'

    position = int(255 * (image_opacity / 100))

    if enable and image_hex != background_pixmap_hex:
        background_pixmap_hex = file_path
        del background_pixmap
        QPixmapCache.clear()

        original_pixmap = QPixmap(background_pixmap_hex)
        if not original_pixmap.isNull():
            background_pixmap = QPixmap(original_pixmap.size())
            background_pixmap.fill(Qt.transparent)

            p1 = QPainter(background_pixmap)
            p1.setCompositionMode(QPainter.CompositionMode_Source)
            p1.drawPixmap(0, 0, original_pixmap)
            p1.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p1.fillRect(background_pixmap.rect(), QColor(0, 0, 0, position))
            p1.end()
        else:
            del original_pixmap
            background_pixmap = None
            background_pixmap_hex = ''
            QPixmapCache.clear()
    elif not enable:
        del background_pixmap
        background_pixmap = None
        background_pixmap_hex = ''
        QPixmapCache.clear()


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


class BackgroundImageManager(QObject):
    """背景图片缩放管理器"""

    def __init__(self):
        super().__init__()

        self.cached_pixmap = None  # 用于缓存缩放后的图
        self.cached_x = 0
        self.cached_y = 0

        # 防抖定时器
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(lambda: self.scale_bg_image(True))

    def scale_bg_image(self, use_high_quality=False):
        if background_pixmap is None or background_pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return

        if use_high_quality:
            # 1. 在尺寸改变时，才进行像素缩放
            scaled = background_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )

            # 2. 计算居中偏移
            self.cached_x = (self.width() - scaled.width()) // 2
            self.cached_y = (self.height() - scaled.height()) // 2
        else:
            # 低质量模式下
            scaled = background_pixmap.scaled(
                self.size(),
                Qt.IgnoreAspectRatio,
                Qt.FastTransformation
            )

            # 2. 计算居中偏移
            self.cached_x = self.cached_y = 0

        del self.cached_pixmap
        # 3. 缓存结果
        QPixmapCache.clear()
        self.cached_pixmap = scaled

        if not use_high_quality:
            self.resize_timer.start(300)
        else:
            # 触发一次重绘，无缝变为高清
            self.update()

    def draw_bg_on_painter(self, event):
        if self.cached_pixmap is None or self.cached_pixmap.isNull():
            return

        painter = QPainter(self)

        # 直接使用缓存好的 pixmap，CPU 占用极低
        painter.drawPixmap(self.cached_x, self.cached_y, self.cached_pixmap)


class BaseQMainWindow(QMainWindow, BackgroundImageManager):
    """所有主窗口引用的 QMainWindow 父类"""

    def __init__(self):
        super().__init__()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, qt_window_mgr.refresh_all_windows_theme, eventType, message)
        if is_changed and self not in qt_window_mgr.distributed_window:
            self.reset_theme()
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        self.draw_bg_on_painter(event)
        super().paintEvent(event)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.scale_bg_image()

    def set_theme_qss(self):
        """载入标准样式主题，同时为窗口背景设置颜色"""
        set_theme_qss_as_cfg(self)
        set_widget_background_mode(self)
        self.scale_bg_image()

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class WindowBaseQWidget(QWidget, BackgroundImageManager):
    """所有独立窗口引用的 QWidget 父类"""

    def __init__(self):
        super().__init__()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, qt_window_mgr.refresh_all_windows_theme, eventType, message)
        if is_changed and self not in qt_window_mgr.distributed_window:
            self.reset_theme()
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        self.draw_bg_on_painter(event)
        super().paintEvent(event)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.scale_bg_image()

    def set_theme_qss(self):
        """载入标准样式主题，同时为窗口背景设置颜色"""
        set_theme_qss_as_cfg(self)
        set_widget_background_mode(self)
        self.scale_bg_image()

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class InsideWidgetBaseQWidget(QWidget):
    """所有嵌入组件引用的 QWidget 父类"""

    def __init__(self):
        super().__init__()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, qt_window_mgr.refresh_all_windows_theme, eventType, message)
        if is_changed and self not in qt_window_mgr.distributed_window:
            self.reset_theme()
        return super().nativeEvent(eventType, message)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)

    def set_theme_qss(self):
        """载入标准样式主题"""
        set_theme_qss_as_cfg(self)

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()


class WindowBaseQDialog(QDialog, BackgroundImageManager):
    """所有独立模态窗口引用的 QDialog 父类"""

    def __init__(self):
        super().__init__()

    def nativeEvent(self, eventType, message):
        is_changed = handle_native_event(self, qt_window_mgr.refresh_all_windows_theme, eventType, message)
        if is_changed and self not in qt_window_mgr.distributed_window:
            self.reset_theme()
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        self.draw_bg_on_painter(event)
        super().paintEvent(event)

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self.scale_bg_image()

    def set_theme_qss(self):
        """载入标准样式主题，同时为窗口背景设置颜色"""
        set_theme_qss_as_cfg(self)
        set_widget_background_mode(self)
        self.scale_bg_image()

    def add_extend_qss(self, qss):
        """在标准主题上添加自定义样式表"""
        self.setStyleSheet(self.styleSheet() + '\n' + qss)

    def reset_theme(self):
        """动态重载主题/使用自定义主题 时应当调用此方法"""
        self.set_theme_qss()
