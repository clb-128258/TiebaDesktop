"""私信与吧群消息气泡。"""
from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from publics import profile_mgr, qt_image
from publics.base_ui_elements import base_ui
from publics.funcs import show_label_pixmap_with_animation, timestamp_to_string,open_url_in_browser
from subwindow.thread_picture_label import ThreadPictureLabel

from ui import message_item


class ChatMessageWidget(base_ui.InsideWidgetBaseQWidget, message_item.Ui_Form):
    """
    消息气泡组件
    显示文字、图片等消息
    """

    contentSizeChanged = pyqtSignal()

    def __init__(self, message, show_sender=False):
        super().__init__()
        self.setupUi(self)

        self.message = message
        self.show_sender = show_sender
        self._last_height = 62
        self._layout_width = None
        self._image_requested = False

        self.portrait_image = qt_image.MultipleImage()
        self.destroyed.connect(self._cleanup)

        self.label.setFixedSize(38, 38)
        self.label_2.setFixedSize(38, 38)

        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label_2.setTextInteractionFlags(Qt.NoTextInteraction)

        # 昵称显示
        self.label_4.setWordWrap(True)
        self.label_4.setTextFormat(Qt.PlainText)
        self.label_4.setText(message.sender_name if show_sender else '')
        self.label_4.setVisible(bool(show_sender and message.sender_name))
        self.label_4.setAlignment(
            (Qt.AlignRight if message.direction == 'out' else Qt.AlignLeft)
            | Qt.AlignVCenter
        )

        # 消息时间
        self.label_3.setText(timestamp_to_string(message.timestamp or 0))
        self.label_3.setAlignment(
            Qt.AlignRight if message.direction == 'out' else Qt.AlignLeft
        )

        # 文字气泡
        self.bubble = QLabel(message.text or '[暂不支持的消息类型，请用手机贴吧查看]')
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.PlainText)
        self.bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bubble.linkActivated.connect(open_url_in_browser)
        self.bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bubble.customContextMenuRequested.connect(self.show_text_content_menu)

        image_urls = list(message.image_urls or [])
        self.image_label = None
        if image_urls:
            if message.text in ('[图片]', '[图片消息]', ''):
                # 为图片消息时隐藏文本气泡
                self.bubble.hide()

            preview_url = (
                message.image_thumbnail_urls[0]
                if message.image_thumbnail_urls
                else image_urls[0]
            )#小图url
            image_width, image_height = self._calculate_image_size(
                message,
                600,
            )
            self.image_label = ThreadPictureLabel(
                image_width,
                image_height,
                image_urls[0],
                preview_url,
            )
            self.image_label.setScaledContents(True)
            self.image_label.hide()

        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        if self.image_label is not None:
            content_layout.addWidget(self.image_label)
        content_layout.addWidget(self.bubble)

        self.message_layout = QHBoxLayout(self.messageContentWidget)
        self.message_layout.setContentsMargins(0, 0, 0, 0)
        if message.direction == 'out':
            self.message_layout.addStretch(1)
            self.message_layout.addWidget(self.content_container)
            self.label.hide()
            avatar_label = self.label_2
        else:
            self.message_layout.addWidget(self.content_container)
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

    def show_text_content_menu(self):
        menu = base_ui.create_thread_content_menu(self.bubble)
        menu.exec(QCursor.pos())

    def load_images(self):
        """滚动到视口后异步加载消息图片"""
        if self._image_requested or self.image_label is None:
            return
        self.image_label.show()
        self.image_label.load_picture_async()
        self._image_requested = True

    def update_layout_width(self, list_width):
        """使用 QFontMetrics 重新计算文字和图片区域尺寸"""
        list_width = max(120, int(list_width))
        if self._layout_width is not None and abs(self._layout_width - list_width) < 2:
            return self._last_height
        max_width = max(120, int(list_width * 2 / 3))

        bubble_width = 0
        bubble_height = 0
        if not self.bubble.isHidden():
            natural_width = max(
                self._natural_text_width(self.bubble.text()) + 24,
                48,
            )
            bubble_width = min(max_width, natural_width)
            text_width = max(80, bubble_width - 24)
            bubble_height = max(
                self.bubble.fontMetrics().height() + 20,
                self._text_height(self.bubble.text(), text_width) + 20,
            )
            self.bubble.setFixedSize(bubble_width, bubble_height)

        image_width, image_height = self._image_size(max_width)
        if self.image_label is not None:
            self.image_label.setFixedSize(image_width, image_height)
            self.image_label.show()

        content_width = max(
            bubble_width,
            image_width if self.image_label is not None else 0,
        )
        content_height = bubble_height + image_height
        if bubble_width and image_height:
            content_height += self.content_container.layout().spacing()
        content_width = max(48, content_width)
        content_height = max(36, content_height)
        self.content_container.setFixedSize(content_width, content_height)
        self.messageContentWidget.setFixedHeight(content_height)

        sender_height = 0
        if not self.label_4.isHidden():
            sender_width = max(80, content_width)
            sender_height = self._text_height(
                self.label_4.text(),
                sender_width,
                self.label_4.fontMetrics(),
            )
            self.label_4.setFixedHeight(max(20, sender_height + 2))

        margins = (
                self.gridLayout.contentsMargins().top()
                + self.gridLayout.contentsMargins().bottom()
                + self.gridLayout.verticalSpacing() * 2
        )
        total_height = max(
            58,
            margins
            + sender_height
            + content_height
            + self.label_3.sizeHint().height(),
        )
        self._last_height = total_height
        self._layout_width = list_width
        self.setMinimumHeight(total_height)
        self.setMaximumHeight(total_height)
        self.gridLayout.activate()
        return total_height

    def preferred_height(self, available_width=700):
        return self.update_layout_width(available_width)

    def _image_size(self, max_width):
        if self.image_label is None:
            return 0, 0
        return self._calculate_image_size(self.message, max_width)

    @staticmethod
    def _calculate_image_size(message, max_width):
        source_width = int(message.image_width or 0)
        source_height = int(message.image_height or 0)

        if source_width <= 0:
            source_width = 360
            source_height = 201
        elif source_height <= 0:
            source_height = max(1, int(source_width * 0.56))

        scale = min(3.5, max_width / source_width)
        width = max(48, int(source_width * scale))
        height = max(48, int(source_height * scale))
        return width, height

    def _text_height(self, text, width, metrics=None):
        metrics = metrics or self.bubble.fontMetrics()
        rect = metrics.boundingRect(
            QRect(0, 0, max(40, width), 100000),
            Qt.AlignLeft | Qt.TextWordWrap | Qt.TextWrapAnywhere,
            text or '',
        )
        return max(metrics.height(), rect.height())

    def _natural_text_width(self, text):
        lines = (text or '').splitlines() or ['']
        return max(
            self.bubble.fontMetrics().horizontalAdvance(line)
            for line in lines
        )

    def _cleanup(self):
        self.portrait_image.destroyImage()

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
