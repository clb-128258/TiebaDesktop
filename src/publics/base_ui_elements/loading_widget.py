from PyQt5.QtCore import Qt, QByteArray, QSize, QEvent
from PyQt5.QtGui import QPainter, QColor, QMovie

from publics.base_ui_elements import base_ui
from publics.base_ui_elements.windows_features import dwm_visual
from publics import profile_mgr
from ui import loading_amt


class LoadingFlashWidget(base_ui.InsideWidgetBaseQWidget, loading_amt.Ui_loadFlashForm):
    """覆盖在其它widget上层的加载动画组件"""

    need_clean_bottom_rect = True
    is_full_color=False

    def __init__(self, show_caption=True, caption=''):
        super().__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # 背景透明
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 始终置顶
        self.reset_theme()

        self.set_caption(show_caption, caption)
        self.init_load_flash()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.need_clean_bottom_rect and not self.is_full_color:
            painter = QPainter(self)
            # 1. 设置混合模式为 Clear (擦除模式)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            # 2. 填充整个 c 组件的区域，使其 Alpha 变为 0
            painter.fillRect(self.parent().rect(), QColor(0, 0, 0, 0))
            # 3. 恢复正常绘制模式 (如果 c 里面还要画文字或图标)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def reset_theme(self):
        super().reset_theme()

        color = profile_mgr.get_theme_color_string()

        # 处理纯色背景
        self.is_full_color = not dwm_visual.is_dwm_bg_enabled()
        final_bg_color = color if self.is_full_color else 'transparent'

        self.add_extend_qss(f"""
            QWidget{{background-color: {final_bg_color}; border-radius: 10px;}}
        """)

    def set_caption(self, show_caption=True, caption=''):
        if show_caption:
            self.label_17.show()
            if caption:
                self.label_17.setText(caption)
            else:
                self.label_17.setText('数据正在赶来的路上...')
        else:
            self.label_17.hide()

    def init_load_flash(self):
        def set_pixmap():
            pixmap = self.show_movie.currentPixmap()
            pixmap.setDevicePixelRatio(self.devicePixelRatioF())
            self.label_18.setPixmap(pixmap)

        self.show_movie = QMovie('ui/loading_new.gif', QByteArray(b'gif'))
        self.show_movie.setScaledSize(QSize(int(120 * self.devicePixelRatioF()),
                                            int(120 * self.devicePixelRatioF())
                                            )
                                      )
        self.show_movie.frameChanged.connect(set_pixmap)
        self.destroyed.connect(self.show_movie.deleteLater)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Resize and source is self.parent():  # 父组件调整大小
            self.sync_parent_widget_size()
        return super(LoadingFlashWidget, self).eventFilter(source, event)  # 照常处理事件

    def closeEvent(self, a0):
        self.show_movie.stop()
        a0.accept()

    def hideEvent(self, a0):
        self.show_movie.stop()
        a0.accept()

    def showEvent(self, a0):
        super().showEvent(a0)
        self.show_movie.start()
        a0.accept()

    def sync_parent_widget_size(self):
        self.resize(self.parent().size())

    def cover_widget(self, widget, enable_filler=True):
        self.setParent(widget)
        if enable_filler:
            widget.installEventFilter(self)

        self.raise_()
        self.sync_parent_widget_size()
