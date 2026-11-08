"""私信与吧群消息气泡。"""
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy

from publics import profile_mgr, qt_image
from publics.base_ui_elements import base_ui
from publics.funcs import show_label_pixmap_with_animation, timestamp_to_string

from ui import message_item


class ChatMessageWidget(base_ui.InsideWidgetBaseQWidget, message_item.Ui_Form):
    """统一显示私信、吧群消息。"""

    def __init__(self, message, show_sender=False):
        super().__init__()
        self.setupUi(self)
        self.message = message
        self.show_sender = show_sender
        self._last_height = 62
        self.portrait_image = qt_image.MultipleImage()
        self.destroyed.connect(self.portrait_image.destroyImage)

        self.gridLayout.setContentsMargins(8, 6, 8, 6)
        self.gridLayout.setVerticalSpacing(4)
        self.gridLayout.setRowStretch(0, 0)
        self.gridLayout.setRowStretch(1, 0)
        self.gridLayout.setRowStretch(2, 0)

        self.label.setFixedSize(38, 38)
        self.label_2.setFixedSize(38, 38)
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label_2.setTextInteractionFlags(Qt.NoTextInteraction)

        self.label_4.setWordWrap(True)
        self.label_4.setTextFormat(Qt.PlainText)
        self.label_4.setText(message.sender_name if show_sender else '')
        self.label_4.setVisible(bool(show_sender and message.sender_name))
        if message.direction == 'out':
            self.label_4.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        else:
            self.label_4.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.label_3.setText(timestamp_to_string(message.timestamp or 0))
        self.label_3.setAlignment(
            Qt.AlignRight if message.direction == 'out' else Qt.AlignLeft
        )

        self.bubble = QLabel(message.text or '[非文本消息]')
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.PlainText)
        self.bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.message_layout = QHBoxLayout(self.messageContentWidget)
        self.message_layout.setContentsMargins(0, 0, 0, 0)
        if message.direction == 'out':
            self.message_layout.addStretch(1)
            self.message_layout.addWidget(self.bubble)
            self.label.hide()
            avatar_label = self.label_2
        else:
            self.message_layout.addWidget(self.bubble)
            self.message_layout.addStretch(1)
            self.label_2.hide()
            avatar_label = self.label

        if message.sender_portrait:
            self.portrait_image.currentPixmapChanged.connect(
                lambda pixmap: show_label_pixmap_with_animation(avatar_label, pixmap)
            )
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.TiebaPortrait,
                message.sender_portrait.split('?', 1)[0],
                qt_image.ImageCoverType.RoundCover,
                (38, 38),
            )
            self.portrait_image.loadImage()
        else:
            avatar_label.clear()

        self.reset_theme()
        self.update_layout_width(900)

    def update_layout_width(self, list_width):
        """按列表宽度重新排版，返回条目总高度。"""
        list_width = max(120, int(list_width))
        bubble_width = max(120, int(list_width * 2 / 3))
        text_width = max(80, bubble_width - 20)

        self.bubble.setFixedWidth(bubble_width)
        text_height = self._text_height(self.bubble.text(), text_width)
        bubble_height = max(36, text_height + 20)
        self.bubble.setFixedHeight(bubble_height)
        self.messageContentWidget.setMinimumHeight(bubble_height)
        self.messageContentWidget.setMaximumHeight(bubble_height)

        sender_height = 0
        if not self.label_4.isHidden():
            sender_height = self._text_height(
                self.label_4.text(),
                bubble_width,
            )
            self.label_4.setFixedHeight(max(20, sender_height + 2))

        time_height = 20
        margins = (
            self.gridLayout.contentsMargins().top()
            + self.gridLayout.contentsMargins().bottom()
            + self.gridLayout.verticalSpacing() * 2
        )
        total_height = max(
            58,
            margins + sender_height + bubble_height + time_height,
        )
        self._last_height = total_height
        self.setMinimumHeight(total_height)
        self.setMaximumHeight(total_height)
        self.gridLayout.activate()
        return total_height

    def preferred_height(self, available_width=700):
        return self.update_layout_width(available_width)

    def _text_height(self, text, width):
        metrics = self.bubble.fontMetrics()
        rect = metrics.boundingRect(
            QRect(0, 0, max(40, width), 100000),
            Qt.AlignLeft | Qt.TextWordWrap | Qt.TextWrapAnywhere,
            text or '',
        )
        return max(18, rect.height())

    def reset_theme(self):
        super().reset_theme()
        if self.message.direction == 'out':
            bg_color = '#4f83cc'
            text_color = '#ffffff'
        else:
            bg_color = '#e8e8e8' if profile_mgr.get_theme_policy() == 1 else '#343434'
            text_color = profile_mgr.get_theme_font_color_string()
        self.bubble.setStyleSheet(
            f'QLabel{{background-color:{bg_color};color:{text_color};'
            'border-radius:8px;padding:8px 10px;}}'
        )
