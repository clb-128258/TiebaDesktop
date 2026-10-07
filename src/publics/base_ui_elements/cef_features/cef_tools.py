"""CEF 后端的下载弹窗与任务管理器。

UI 全部接入项目既有的 base_ui 主题系统（背景 / 文字颜色与图标都跟随主题方案），
下载弹窗参考 Chrome 的下载气泡：右上角弹出的浮层，按条目列出下载内容。

- 下载：桥接层通过 CEF_BRIDGE_EVENT_DOWNLOAD 回传下载事件（JSON），这里维护下载列表；
- 任务管理器：CEF 没有开放子进程信息，改用「helper 进程启动时写下自己的命令行」的方式区分
  渲染 / GPU / 网络等进程，再配合系统 API 取内存和 CPU。
"""
import ctypes
import os
import subprocess
import sys
import tempfile

from PyQt5.QtCore import QObject, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QFrame,
                             QGraphicsDropShadowEffect, QHBoxLayout, QHeaderView, QLabel,
                             QProgressBar, QPushButton, QScrollArea, QTableWidget,
                             QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from publics import app_logger, profile_mgr
from publics.base_ui_elements import base_ui
from publics.base_ui_elements.message_box import MessageBox

IS_WINDOWS = os.name == 'nt'


def _bridge_lib():
    # 延迟导入，避免和 cef_webview 形成循环依赖
    from publics.base_ui_elements.cef_features import cef_webview
    return cef_webview._CefBridge.instance().lib()


def is_dark_theme() -> bool:
    return profile_mgr.get_theme_policy() == 2


def theme_icon(name: str) -> QIcon:
    """按当前主题取图标（图标目录为 icon_black / icon_white）。"""
    scheme = profile_mgr.get_theme_policy_string()[1]
    return QIcon(f'ui/icon_{scheme}/{name}.png')


def theme_colors() -> dict:
    """主题相关的几个颜色，供自定义 QSS 使用。"""
    dark = is_dark_theme()
    return {
        'bg': profile_mgr.get_theme_color_string(),
        'fg': profile_mgr.get_theme_font_color_string(),
        'border': '#5f6368' if dark else '#dadce0',
        'hover': 'rgba(255, 255, 255, 30)' if dark else 'rgba(0, 0, 0, 18)',
        'sub': '#9aa0a6' if dark else '#5f6368',
        'accent': '#8ab4f8' if dark else '#1a73e8',
    }


def human_size(num):
    try:
        num = float(num)
    except Exception:
        return '-'
    if num <= 0:
        return '-'
    units = ('B', 'KB', 'MB', 'GB', 'TB')
    index = 0
    while num >= 1024 and index < len(units) - 1:
        num /= 1024.0
        index += 1
    if index == 0:
        return '%d B' % int(num)
    return '%.1f %s' % (num, units[index])


# ---------------------------------------------------------------------- 下载管理

def default_download_dir() -> str:
    """下载目录：优先用系统「下载」目录，取不到就退回临时目录。

    注意必须做 normpath：QStandardPaths 返回的是 "C:/Users/xx/Downloads" 这种正斜杠路径，
    直接和文件名拼接会得到混合分隔符的路径，CEF 会拒绝创建文件导致下载立刻失败。
    """
    path = ''
    try:
        from PyQt5.QtCore import QStandardPaths
        path = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or ''
    except Exception:
        path = ''
    if not path:
        path = os.path.join(os.path.expanduser('~'), 'Downloads')
    path = os.path.normpath(path)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        app_logger.log_exception(e)
        path = os.path.normpath(tempfile.gettempdir())
    return path


def unique_path(directory: str, name: str) -> str:
    """同名文件自动加序号，避免直接覆盖已有文件。"""
    name = os.path.basename(name) or 'download'
    base, ext = os.path.splitext(name)
    candidate = os.path.join(directory, name)
    index = 1
    while os.path.exists(candidate) and index < 1000:
        candidate = os.path.join(directory, '%s (%d)%s' % (base, index, ext))
        index += 1
    return os.path.normpath(candidate)


class DownloadItem:
    def __init__(self, download_id: int, url: str, name: str, path: str, total: int):
        self.download_id = download_id
        self.url = url
        self.name = name
        self.path = path
        self.total = total
        self.received = 0
        self.percent = -1
        self.speed = 0
        self.state = 'progress'
        self.paused = False

    def state_text(self) -> str:
        if self.state == 'done':
            return '已下载'
        if self.state == 'canceled':
            return '已取消'
        if self.state == 'failed':
            return '下载失败'
        if self.paused:
            return '已暂停'
        return '正在下载'

    def detail_text(self) -> str:
        """Chrome 那样的第二行：大小 / 速度或完成状态。"""
        parts = []
        if self.state == 'done':
            parts.append('已下载')
            parts.append(human_size(self.received if self.received > 0 else self.total))
        elif self.state == 'canceled':
            parts.append('已取消')
        elif self.state == 'failed':
            parts.append('下载失败')
        else:
            if self.total > 0:
                parts.append('%s / %s' % (human_size(self.received), human_size(self.total)))
            else:
                parts.append(human_size(self.received))
            if self.paused:
                parts.append('已暂停')
            elif self.speed > 0:
                parts.append('%s/s' % human_size(self.speed))
        return ' · '.join(parts)

    def progress_value(self) -> int:
        if self.state == 'done':
            return 100
        if self.percent >= 0:
            return max(0, min(self.percent, 100))
        if self.total > 0:
            return int(self.received * 100 / self.total)
        return 0


class DownloadManager(QObject):
    """全局下载列表（所有标签页共用一个下载弹窗）。"""

    changed = pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls) -> 'DownloadManager':
        if cls._instance is None:
            cls._instance = DownloadManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.items = []
        self.panel = None
        self._by_id = {}

    # ------------------------------------------------------------ 桥接层事件
    def handle_bridge_event(self, browser_id: int, payload: dict, anchor=None):
        state = int(payload.get('state', 2))
        download_id = int(payload.get('id', 0))
        if state == 1:
            self.__begin(download_id, payload, anchor)
        else:
            self.__update(download_id, payload)

    def __begin(self, download_id: int, payload: dict, anchor=None):
        url = payload.get('url') or ''
        name = os.path.basename(payload.get('name') or '') or 'download'
        directory = default_download_dir()
        path = unique_path(directory, name)
        total = int(payload.get('total') or -1)
        item = DownloadItem(download_id, url, name, path, total)
        self.items.append(item)
        self._by_id[download_id] = item

        lib = _bridge_lib()
        if lib is None:
            return
        try:
            # 必须在桥接层的这次回调里同步回话，否则下载会被取消
            lib.cef_bridge_download_continue(download_id, path.encode('utf-8'))
        except Exception as e:
            app_logger.log_exception(e)
        app_logger.log_INFO(f'cef download start: {name} -> {path}')
        self.changed.emit()
        self.show_panel(anchor)

    def __update(self, download_id: int, payload: dict):
        item = self._by_id.get(download_id)
        if item is None:
            return
        state = int(payload.get('state', 2))
        # 进度只允许前进：CEF 在收尾时会再发一次 received/percent 归零的事件
        received = int(payload.get('received') or 0)
        percent = int(payload.get('percent') or -1)
        if received >= item.received:
            item.received = received
        if percent >= item.percent:
            item.percent = percent
        total = int(payload.get('total') or -1)
        if total > 0:
            item.total = total
        item.speed = int(payload.get('speed') or 0)
        if payload.get('path'):
            item.path = os.path.normpath(payload['path'])
        if state == 3:
            item.state = 'done'
            if item.received <= 0 and item.total > 0:
                item.received = item.total
            item.percent = 100
            item.speed = 0
            app_logger.log_INFO(f'cef download finished: {item.path}')
        elif state == 4:
            item.state = 'canceled'
            item.speed = 0
        elif state == 5 and item.state == 'progress':
            item.state = 'failed'
            item.speed = 0
            app_logger.log_WARN(f'cef download failed: {item.url}')
        self.changed.emit()

    # ------------------------------------------------------------ 操作
    def open_file(self, item: 'DownloadItem'):
        if not item.path or not os.path.isfile(item.path):
            MessageBox.warning(self.panel, '文件不存在', '下载尚未完成或文件已被移动。')
            return
        try:
            if IS_WINDOWS:
                os.startfile(item.path)  # Windows 专用
            else:
                subprocess.Popen(['xdg-open', item.path])
        except Exception as e:
            app_logger.log_exception(e)
            MessageBox.warning(self.panel, '打开失败', str(e))

    def show_in_folder(self, item: 'DownloadItem'):
        target = item.path if item.path else default_download_dir()
        try:
            if IS_WINDOWS:
                if os.path.isfile(target):
                    subprocess.Popen(['explorer', '/select,', os.path.normpath(target)])
                else:
                    subprocess.Popen(['explorer', os.path.dirname(target) or target])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', target])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(target) or target])
        except Exception as e:
            app_logger.log_exception(e)

    def open_download_dir(self):
        directory = default_download_dir()
        try:
            if IS_WINDOWS:
                subprocess.Popen(['explorer', directory])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', directory])
            else:
                subprocess.Popen(['xdg-open', directory])
        except Exception as e:
            app_logger.log_exception(e)

    def set_paused(self, item: 'DownloadItem', paused: bool):
        lib = _bridge_lib()
        if lib is None:
            return
        try:
            lib.cef_bridge_download_set_paused(item.download_id, 1 if paused else 0)
            item.paused = bool(paused)
        except Exception as e:
            app_logger.log_exception(e)
        self.changed.emit()

    def cancel(self, item: 'DownloadItem'):
        if item.state != 'progress':
            self.remove(item)
            return
        lib = _bridge_lib()
        if lib is not None:
            try:
                lib.cef_bridge_download_cancel_by_id(item.download_id)
            except Exception as e:
                app_logger.log_exception(e)
        item.state = 'canceled'
        item.speed = 0
        self.changed.emit()

    def remove(self, item: 'DownloadItem'):
        if item in self.items:
            self.items.remove(item)
        self._by_id.pop(item.download_id, None)
        self.changed.emit()

    def clear_finished(self):
        for item in list(self.items):
            if item.state in ('done', 'canceled', 'failed'):
                self.remove(item)

    def show_panel(self, anchor=None):
        if self.panel is None:
            self.panel = DownloadPopup(self)
        self.panel.refresh()
        self.panel.show_near(anchor)


class _DownloadRow(QFrame):
    """下载气泡里的一行：图标 + 文件名 + 状态 + 进度条 + 操作按钮。"""

    def __init__(self, popup: 'DownloadPopup', item: 'DownloadItem'):
        super().__init__(popup)
        self.setObjectName('downloadRow')
        self.setCursor(Qt.PointingHandCursor)
        self._popup = popup
        self.item = item

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 4, 6)
        layout.setSpacing(10)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(24, 24)
        layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(2)
        self.name_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.detail_label.setObjectName('downloadDetail')
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        center.addWidget(self.name_label)
        center.addWidget(self.detail_label)
        center.addWidget(self.progress)
        layout.addLayout(center, 1)

        self.pause_button = QToolButton(self)
        self.close_button = QToolButton(self)
        for button in (self.pause_button, self.close_button):
            button.setAutoRaise(True)
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(26, 26)
        layout.addWidget(self.pause_button, 0, Qt.AlignTop)
        layout.addWidget(self.close_button, 0, Qt.AlignTop)

        self.pause_button.clicked.connect(self.__toggle_pause)
        self.close_button.clicked.connect(self.__close_clicked)

    def refresh(self, item: 'DownloadItem'):
        self.item = item
        self.icon_label.setPixmap(theme_icon('page.png').pixmap(20, 20))
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(item.name, Qt.ElideMiddle, 210))
        self.name_label.setToolTip(item.path or item.url)
        self.detail_label.setText(item.detail_text())

        in_progress = item.state == 'progress'
        self.progress.setVisible(in_progress)
        self.progress.setValue(item.progress_value())
        self.pause_button.setVisible(in_progress)
        self.pause_button.setIcon(theme_icon('play_arrow.png' if item.paused else 'pause.png'))
        self.pause_button.setToolTip('继续' if item.paused else '暂停')
        self.close_button.setIcon(theme_icon('close.png'))
        self.close_button.setToolTip('取消下载' if in_progress else '从列表中移除')

    def __toggle_pause(self):
        if self.item.state == 'progress':
            self._popup.manager.set_paused(self.item, not self.item.paused)

    def __close_clicked(self):
        self._popup.manager.cancel(self.item)

    def mousePressEvent(self, a0):
        if a0.button() == Qt.LeftButton and self.item.state == 'done':
            self._popup.manager.open_file(self.item)
        super().mousePressEvent(a0)


class DownloadPopup(QWidget):
    """Chrome 风格的下载气泡：Qt.Popup，点击其它地方自动关闭。"""

    def __init__(self, manager: 'DownloadManager'):
        super().__init__(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.manager = manager
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(390)
        self._rows = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)  # 给阴影留出空间
        self.card = QFrame(self)
        self.card.setObjectName('downloadCard')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(8, 2, 2, 2)
        self.title_label = QLabel('下载内容', self.card)
        self.title_label.setObjectName('downloadTitle')
        self.close_button = QToolButton(self.card)
        self.close_button.setAutoRaise(True)
        self.close_button.setIconSize(QSize(16, 16))
        self.close_button.setFixedSize(26, 26)
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        card_layout.addLayout(header)

        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_host = QWidget()
        list_host.setObjectName('downloadList')
        self._list_layout = QVBoxLayout(list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)
        self.scroll.setWidget(list_host)
        card_layout.addWidget(self.scroll)

        self.empty_label = QLabel('暂无下载内容', self.card)
        self.empty_label.setObjectName('downloadEmpty')
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setMinimumHeight(90)
        card_layout.addWidget(self.empty_label)

        footer = QHBoxLayout()
        footer.setContentsMargins(6, 2, 6, 2)
        self.folder_button = QPushButton('打开下载文件夹', self.card)
        self.folder_button.setObjectName('linkButton')
        self.folder_button.setCursor(Qt.PointingHandCursor)
        self.folder_button.clicked.connect(self.manager.open_download_dir)
        self.clear_button = QPushButton('清除已结束的下载', self.card)
        self.clear_button.setObjectName('linkButton')
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.manager.clear_finished)
        footer.addWidget(self.folder_button)
        footer.addStretch(1)
        footer.addWidget(self.clear_button)
        card_layout.addLayout(footer)

        self.manager.changed.connect(self.refresh)
        self.reset_theme()
        self.refresh()

    # ------------------------------------------------------------ 主题
    def reset_theme(self):
        """接入 base_ui 的主题系统：背景、文字、悬停色都跟随当前主题方案。"""
        base_ui.set_theme_qss_as_cfg(self)
        color = theme_colors()
        self.setStyleSheet(self.styleSheet() + f'''
QFrame#downloadCard {{background-color: {color['bg']}; border: 1px solid {color['border']};
    border-radius: 10px;}}
QFrame#downloadCard QLabel {{color: {color['fg']}; background: transparent;}}
QLabel#downloadTitle {{font-size: 14px; font-weight: 600; padding: 4px 2px;}}
QLabel#downloadDetail, QLabel#downloadEmpty {{color: {color['sub']}; font-size: 12px;}}
QFrame#downloadRow {{background-color: transparent; border-radius: 6px;}}
QFrame#downloadRow:hover {{background-color: {color['hover']};}}
QToolButton {{border: none; background: transparent; border-radius: 13px;}}
QToolButton:hover {{background-color: {color['hover']};}}
QScrollArea, QWidget#downloadList {{background: transparent; border: none;}}
QProgressBar {{border: none; background-color: {color['hover']}; border-radius: 2px;}}
QProgressBar::chunk {{background-color: {color['accent']}; border-radius: 2px;}}
QPushButton#linkButton {{border: none; background: transparent; color: {color['accent']};
    font-size: 12px; padding: 3px 4px;}}
QPushButton#linkButton:hover {{text-decoration: underline;}}
QPushButton#linkButton:disabled {{color: {color['sub']};}}
''')
        self.close_button.setIcon(theme_icon('close.png'))

    # ------------------------------------------------------------ 列表
    def refresh(self):
        items = self.manager.items
        alive = set()
        for item in items:
            alive.add(item.download_id)
            row = self._rows.get(item.download_id)
            if row is None:
                row = _DownloadRow(self, item)
                self._rows[item.download_id] = row
                self._list_layout.insertWidget(0, row)  # 最新的排在最上面
            row.refresh(item)

        for download_id in list(self._rows):
            if download_id in alive:
                continue
            row = self._rows.pop(download_id)
            self._list_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()

        has_items = bool(items)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)
        self.clear_button.setEnabled(
            any(i.state in ('done', 'canceled', 'failed') for i in items))

        host = self.scroll.widget()
        height = min(max(host.sizeHint().height(), 70), 330)
        self.scroll.setFixedHeight(height)
        self.adjustSize()

    # ------------------------------------------------------------ 定位显示
    def show_near(self, anchor=None):
        self.reset_theme()
        self.adjustSize()
        if anchor is not None:
            corner = anchor.mapToGlobal(QPoint(anchor.width(), 0))
            x = corner.x() - self.width() - 6
            y = corner.y() + 6
        else:
            area = QApplication.primaryScreen().availableGeometry()
            x = area.right() - self.width() - 16
            y = area.top() + 72
        screen = QApplication.screenAt(QPoint(x, y)) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(x, area.left() + 4), area.right() - self.width() - 4)
        y = min(max(y, area.top() + 4), area.bottom() - self.height() - 4)
        self.move(x, y)
        self.show()
        self.raise_()


# ---------------------------------------------------------------------- 任务管理器

_UTILITY_LABELS = {
    'network.mojom.NetworkService': '网络服务',
    'storage.mojom.StorageService': '存储服务',
    'audio.mojom.AudioService': '音频服务',
    'device.mojom.DeviceService': '设备服务',
    'data_decoder.mojom.DataDecoderService': '数据解码服务',
    'tracing.mojom.TracingService': '追踪服务',
    'unzip.mojom.Unzipper': '解压服务',
}

_TYPE_LABELS = {
    'renderer': '渲染进程',
    'gpu-process': 'GPU 进程',
    'utility': '实用工具进程',
    'crashpad-handler': '崩溃处理器',
    'zygote': 'Zygote 进程',
}


def marker_dir() -> str:
    return os.path.join(tempfile.gettempdir(), 'TiebaDesktopCefProcesses')


def _process_type(pid: int):
    """读取 helper 进程启动时写下的命令行，解析出进程类型。"""
    path = os.path.join(marker_dir(), '%d.txt' % pid)
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as file:
            command_line = file.read()
    except Exception:
        return '', ''
    ptype = ''
    note = ''
    for token in command_line.replace('"', ' ').split():
        if token.startswith('--type='):
            ptype = token[len('--type='):]
        elif token.startswith('--utility-sub-type='):
            note = token[len('--utility-sub-type='):]
    return ptype, note


def _type_text(ptype: str, note: str) -> str:
    if not ptype:
        return '子进程'
    if ptype == 'utility' and note:
        return _UTILITY_LABELS.get(note, '实用工具: %s' % note)
    return _TYPE_LABELS.get(ptype, ptype)


if IS_WINDOWS:
    import ctypes.wintypes as wt

    TH32CS_SNAPPROCESS = 0x00000002
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_TERMINATE = 0x0001


    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wt.DWORD),
            ('cntUsage', wt.DWORD),
            ('th32ProcessID', wt.DWORD),
            ('th32DefaultHeapID', ctypes.c_void_p),
            ('th32ModuleID', wt.DWORD),
            ('cntThreads', wt.DWORD),
            ('th32ParentProcessID', wt.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wt.DWORD),
            ('szExeFile', ctypes.c_char * 260),
        ]


    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('cb', wt.DWORD),
            ('PageFaultCount', wt.DWORD),
            ('PeakWorkingSetSize', ctypes.c_size_t),
            ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t),
            ('PeakPagefileUsage', ctypes.c_size_t),
        ]


    def _child_pids(parent_pid: int):
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == -1:
            return []
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        result = []
        try:
            ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
            while ok:
                if entry.th32ParentProcessID == parent_pid:
                    result.append(int(entry.th32ProcessID))
                ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return result


    def _filetime_seconds(value):
        return ((value.dwHighDateTime << 32) | value.dwLowDateTime) / 1e7


    def _process_stats(pid: int):
        """返回 (内存字节数, 累计 CPU 秒数)，取不到返回 (0, 0.0)。"""
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return 0, 0.0
        try:
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            memory = 0
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                memory = int(counters.WorkingSetSize)
            creation = wt.FILETIME()
            exit_time = wt.FILETIME()
            kernel_time = wt.FILETIME()
            user_time = wt.FILETIME()
            cpu = 0.0
            if kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                        ctypes.byref(exit_time),
                                        ctypes.byref(kernel_time),
                                        ctypes.byref(user_time)):
                cpu = _filetime_seconds(kernel_time) + _filetime_seconds(user_time)
            return memory, cpu
        finally:
            kernel32.CloseHandle(handle)


    def _process_alive(pid: int) -> bool:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True


    def _terminate_process(pid: int) -> bool:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            kernel32.TerminateProcess(handle, 1)
        finally:
            kernel32.CloseHandle(handle)
        return True

else:
    SC_CLK_TCK = os.sysconf('SC_CLK_TCK')


    def _parse_stat(pid: int):
        with open('/proc/%d/stat' % pid, 'r') as file:
            stat = file.read()
        # comm 字段可能包含空格和括号，从最后一个 ')' 之后开始切分
        return stat[stat.rindex(')') + 2:].split()


    def _child_pids(parent_pid: int):
        result = []
        for name in os.listdir('/proc'):
            if not name.isdigit():
                continue
            try:
                fields = _parse_stat(int(name))
                if int(fields[1]) == parent_pid:
                    result.append(int(name))
            except Exception:
                continue
        return result


    def _process_stats(pid: int):
        memory = 0
        cpu = 0.0
        try:
            fields = _parse_stat(pid)
            # utime(14) / stime(15) 换算成秒
            cpu = (int(fields[11]) + int(fields[12])) / float(SC_CLK_TCK)
        except Exception:
            pass
        try:
            with open('/proc/%d/status' % pid, 'r') as file:
                for line in file:
                    if line.startswith('VmRSS:'):
                        memory = int(line.split()[1]) * 1024
                        break
        except Exception:
            pass
        return memory, cpu


    def _process_alive(pid: int) -> bool:
        return os.path.isdir('/proc/%d' % pid)


    def _terminate_process(pid: int) -> bool:
        try:
            os.kill(pid, 9)
            return True
        except Exception:
            return False


def list_cef_processes():
    """列出浏览器进程与它的 CEF 子进程。

    返回 [(pid, 类型文本, 内存字节, 累计 CPU 秒)]，第一项是本进程（浏览器进程）。
    """
    own_pid = os.getpid()
    rows = [(own_pid, '浏览器进程（本程序）') + _process_stats(own_pid)]
    for pid in _child_pids(own_pid):
        ptype, note = _process_type(pid)
        rows.append((pid, _type_text(ptype, note)) + _process_stats(pid))
    rows.sort(key=lambda row: -row[2])
    return rows


def cleanup_stale_markers():
    """删掉已经退出的 helper 进程留下的类型标记文件。"""
    directory = marker_dir()
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        if not name.endswith('.txt') or not name[:-4].isdigit():
            continue
        if not _process_alive(int(name[:-4])):
            try:
                os.remove(os.path.join(directory, name))
            except Exception:
                pass


class CefTaskManagerWindow(base_ui.WindowBaseQDialog):
    """任务管理器：样式与项目内其它窗口一致（base_ui.WindowBaseQDialog）。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('任务管理器')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.resize(720, 460)
        self._last_cpu = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title_label = QLabel('任务管理器', self)
        self.title_label.setObjectName('taskTitle')
        self.hint_label = QLabel('列出本程序与全部 CEF 子进程（浏览器 / GPU / 渲染 / 网络等）', self)
        self.hint_label.setObjectName('taskHint')
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(['类型', 'PID', '内存', 'CPU'])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setHighlightSections(False)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton('刷新', self)
        self.refresh_button.setIcon(theme_icon('refresh.png'))
        self.end_button = QPushButton('结束进程', self)
        self.end_button.setIcon(theme_icon('close.png'))
        close_button = QPushButton('关闭', self)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.end_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(self.refresh)
        self.end_button.clicked.connect(self.__end_process)
        close_button.clicked.connect(self.hide)

        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.set_theme_qss()
        self.refresh()

    def set_theme_qss(self):
        super().set_theme_qss()
        color = theme_colors()
        self.add_extend_qss(f'''
QLabel#taskTitle {{font-size: 15px; font-weight: 600; color: {color['fg']};}}
QLabel#taskHint {{color: {color['sub']}; font-size: 12px;}}
QTableWidget {{background-color: transparent; color: {color['fg']};
    border: 1px solid {color['border']};
    border-radius: 6px;}}
QTableWidget::item {{padding: 3px 6px;}}
QTableWidget::item:selected {{background-color: {color['accent']}; color: #ffffff;}}
QHeaderView::section {{background-color: transparent; color: {color['sub']};
    border: none; border-bottom: 1px solid {color['border']}; padding: 5px;}}
QPushButton {{padding: 4px 14px;}}
''')

    def refresh(self):
        import time
        try:
            rows = list_cef_processes()
        except Exception as e:
            app_logger.log_exception(e)
            return
        now = time.monotonic()
        self.table.setRowCount(len(rows))
        for index, (pid, type_text, memory, cpu) in enumerate(rows):
            self.table.setItem(index, 0, QTableWidgetItem(type_text))
            pid_item = QTableWidgetItem(str(pid))
            pid_item.setData(Qt.UserRole, pid)
            self.table.setItem(index, 1, pid_item)
            memory_item = QTableWidgetItem(human_size(memory))
            memory_item.setData(Qt.UserRole, memory)
            self.table.setItem(index, 2, memory_item)

            cpu_text = '-'
            previous = self._last_cpu.get(pid)
            if previous is not None and now > previous[1]:
                delta_cpu = max(0.0, cpu - previous[0])
                cpu_text = '%.1f%%' % (delta_cpu / (now - previous[1]) * 100.0)
            self._last_cpu[pid] = (cpu, now)
            self.table.setItem(index, 3, QTableWidgetItem(cpu_text))

    def __end_process(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pid_item = self.table.item(row, 1)
        if pid_item is None:
            return
        pid = pid_item.data(Qt.UserRole)
        if not pid:
            return
        pid = int(pid)
        if pid == os.getpid():
            MessageBox.critical(self, '任务管理器', '不能结束本程序自己的进程。')
            return
        if MessageBox.information(
                self, '确定要结束 PID %d 吗？' % pid,
                '对应网页可能会崩溃。',
                MessageBox.Yes | MessageBox.No) != MessageBox.Yes:
            return
        if not _terminate_process(pid):
            MessageBox.critical(self, '结束进程失败', '权限可能不足。')
        QTimer.singleShot(300, self.refresh)
