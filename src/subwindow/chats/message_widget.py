"""私信与吧群消息气泡"""
import html

from PyQt5.QtCore import QRect, Qt, pyqtSignal, QEvent
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from publics import account_mgr, profile_mgr, qt_image
from publics.baidu_features.chats.structs.models import ChatroomMessageType
from publics.base_ui_elements import base_ui
from publics.funcs import (
    large_num_to_string,
    open_url_in_browser,
    show_label_pixmap_with_animation,
    timestamp_to_string,
    format_second
)
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

        self.destroyed.connect(self._cleanup)

        self.label.setFixedSize(38, 38)
        self.label_2.setFixedSize(38, 38)

        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.label_2.setTextInteractionFlags(Qt.NoTextInteraction)

        self.portrait_image = qt_image.MultipleImage()
        self.image_label = None
        self.thread_share_container = None
        self.thread_share_view = None
        self.init_message_elements()

        # 重写事件过滤器
        self.label.installEventFilter(self)
        self.label_4.installEventFilter(self)
        self.label_2.installEventFilter(self)

        self.reset_theme()
        self.update_layout_width(900)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if source in (self.label, self.label_4, self.label_2):
                open_url_in_browser(f'user://{self.message.sender_id}')

        return super(ChatMessageWidget, self).eventFilter(source, event)  # 照常处理事件

    def show_text_content_menu(self, label):
        menu = base_ui.create_thread_content_menu(label)
        menu.exec(QCursor.pos())

    def load_images(self):
        """滚动到视口后异步加载消息图片"""
        if self._image_requested:
            return

        if self.portrait_image.isImageInfoValid():
            self.portrait_image.loadImage()
        if self.image_label:
            self.image_label.show()
            self.image_label.load_picture_async()
        if self.thread_share_view is not None:
            self.thread_share_view.load_all_AsyncImage()

        self._image_requested = True

    def init_message_elements(self):
        # 昵称显示
        self.label_4.setTextFormat(Qt.PlainText)
        sender_visible = bool(
            self.show_sender
            and self.message.sender_name
            and not self.message.is_system
        )
        self.label_4.setText(self.message.sender_name if sender_visible else '')
        self.label_4.setVisible(sender_visible)
        self.label_4.setAlignment(
            (Qt.AlignRight if self.message.direction == 'out' else Qt.AlignLeft)
            | Qt.AlignVCenter
        )

        # 消息时间
        message_time_text = f'{timestamp_to_string(self.message.timestamp)}'
        self.label_3.setText(message_time_text)
        self.label_3.setAlignment(
            Qt.AlignCenter
            if self.message.is_system
            else (
                Qt.AlignRight
                if self.message.direction == 'out'
                else Qt.AlignLeft
            )
        )

        # 文字气泡
        self._bubble_plain_text = self.message.text or '[该消息没有文字内容]'
        self.bubble = QLabel(self.messageContentWidget)
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.RichText)
        self.bubble.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        self.bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.bubble.setOpenExternalLinks(False)
        self.bubble.linkActivated.connect(open_url_in_browser)
        self.bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bubble.customContextMenuRequested.connect(lambda: self.show_text_content_menu(self.bubble))
        self._set_bubble_text(self.message)

        # 回复消息标签
        self.reply_label = QLabel(self.messageContentWidget)
        self.reply_label.setWordWrap(True)
        self.reply_label.setTextFormat(Qt.PlainText)
        self.reply_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.reply_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.reply_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reply_label.customContextMenuRequested.connect(lambda: self.show_text_content_menu(self.reply_label))
        self.reply_label.hide()
        self._set_auxiliary_content(self.message)

        # 图片内容
        image_urls = list(self.message.image_urls or [])
        if image_urls:
            self.bubble.hide()

            preview_url = (
                self.message.image_thumbnail_urls[0]
                if self.message.image_thumbnail_urls
                else image_urls[0]
            )  # 小图url
            image_width, image_height = self._calculate_image_size(
                self.message,
                600,
            )

            self.image_label = ThreadPictureLabel(
                image_width,
                image_height,
                image_urls[0],
                preview_url,
            )

            self.image_label.setParent(self.messageContentWidget)
            self.image_label.hide()

        if (
                self.message.msg_type == ChatroomMessageType.ThreadShare
                and self.message.thread_share
        ):
            # 转发贴子
            self._init_thread_share(self.message.thread_share)
            self.bubble.hide()

        # 内容布局管理器
        self.content_container = QWidget(self.messageContentWidget)
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(7)
        content_layout.addWidget(self.reply_label)
        if self.thread_share_container is not None:
            content_layout.addWidget(self.thread_share_container)
        if self.image_label is not None:
            content_layout.addWidget(self.image_label)
        content_layout.addWidget(self.bubble)

        # 消息内容布局
        self.message_layout = QHBoxLayout(self.messageContentWidget)
        self.message_layout.setSpacing(7)
        self.message_layout.setContentsMargins(0, 0, 0, 0)
        if self.message.is_system:
            self.message_layout.addStretch(1)
            self.message_layout.addWidget(self.content_container)
            self.message_layout.addStretch(1)
            self.label.hide()
            self.label_2.hide()
            avatar_label = None
        elif self.message.direction == 'out':
            self.message_layout.addStretch(1)
            self.message_layout.addWidget(self.content_container)
            self.label.hide()
            avatar_label = self.label_2
        else:
            self.message_layout.addWidget(self.content_container)
            self.message_layout.addStretch(1)
            self.label_2.hide()
            avatar_label = self.label

        # 用户头像
        if avatar_label is not None:
            avatar_label.clear()
        if self.message.sender_portrait and not self.message.is_system:
            self.portrait_image.currentPixmapChanged.connect(
                lambda pixmap: show_label_pixmap_with_animation(avatar_label, pixmap)
            )
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.TiebaPortrait,
                self.message.sender_portrait.split('?', 1)[0],
                qt_image.ImageCoverType.RoundCover,
                (38, 38),
            )

    def _init_thread_share(self, thread_share):
        from subwindow.thread_preview_item import AsyncLoadImage, ThreadView

        account = account_mgr.GlobalAccountContainer.get_current_account()
        thread_id = int(thread_share.get('thread_id', 0))
        forum_id = int(thread_share.get('forum_id', 0))
        author_portrait = thread_share.get('author_portrait', '')

        self.thread_share_view = ThreadView(
            account.bduss,
            thread_id,
            forum_id,
            account.stoken,
            author_portrait,
        )
        self.thread_share_view.load_by_callback = True
        self.thread_share_view.allow_open_home_page = bool(author_portrait)
        abstract = thread_share.get('abstract', '')
        video_text = self._thread_share_video_text(thread_share)
        if video_text:
            abstract = '\n'.join(filter(None, (abstract, video_text)))
        self.thread_share_view.set_infos(
            author_portrait or None,
            thread_share.get('author_name', ''),
            thread_share.get('title', ''),
            abstract,
            thread_share.get('forum_avatar') or None,
            thread_share.get('forum_name', ''),
        )
        pictures = [
            AsyncLoadImage(url)
            for url in thread_share.get('image_urls', [])
        ]
        self.thread_share_view.set_picture(pictures)
        self.thread_share_view.toolButton.hide()
        self.thread_share_view.pushButton_2.setVisible(bool(thread_id))
        self.thread_share_view.pushButton_3.setVisible(bool(forum_id))

        self.thread_share_container = QFrame(self.messageContentWidget)
        self.thread_share_container.setObjectName('threadShareCard')
        card_layout = QVBoxLayout(self.thread_share_container)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(5)
        card_title = QLabel('分享贴子', self.thread_share_container)
        card_title.setStyleSheet('QLabel{color:#888888;font-size:8pt;}')
        card_layout.addWidget(card_title)
        card_layout.addWidget(self.thread_share_view)

    @staticmethod
    def _thread_share_video_text(thread_share):
        duration = int(thread_share.get('video_duration', 0))
        play_count = int(thread_share.get('video_play_count', 0))
        text = f'[视频] 时长 {format_second(duration)} | {large_num_to_string(play_count, endspace=True)}次浏览'
        return text if duration and play_count else ''

    def _set_auxiliary_content(self, message):
        reply = message.reply_content or {}
        reply_text = reply.get('text', '')
        reply_name = reply.get('user_name', '')
        if message.is_system or not (reply_text or reply_name):
            self.reply_label.clear()
            self.reply_label.hide()
        else:
            self.reply_label.setText(reply_text)
            self.reply_label.show()

    def _set_bubble_text(self, message):
        rich_text = html.escape(self._bubble_plain_text)
        mentions = []
        for user in message.at_users or []:
            name = str(user.get('user_name') or '')
            target = user.get('user_id') or user.get('portrait') or ''
            token = f'@{name}' if name else ''
            if token and target:
                mentions.append((token, str(target)))
        mentions.sort(key=lambda item: len(item[0]), reverse=True)
        for token, target in mentions:
            escaped_token = html.escape(token)
            link = (
                f'<a href="user://{html.escape(target)}" '
                f'style="text-decoration:underline;">'
                f'{escaped_token}</a>'
            )
            rich_text = rich_text.replace(escaped_token, link)
        self.bubble.setText(rich_text)

    def update_layout_width(self, list_width):
        """使用 QFontMetrics 重新计算文字和图片区域尺寸"""
        list_width = max(120, int(list_width))
        if self._layout_width is not None and abs(self._layout_width - list_width) < 2:
            return self._last_height
        max_width = max(120, int(list_width * 2 / 3))
        message_area_width = self._message_area_width(list_width)
        self.gridLayout.setColumnMinimumWidth(0, 38)
        self.gridLayout.setColumnMinimumWidth(2, 38)
        self.messageContentWidget.setFixedWidth(message_area_width)

        auxiliary_sizes = self._update_auxiliary_sizes(max_width)
        bubble_width = 0
        bubble_height = 0
        if not self.bubble.isHidden():
            natural_width = max(
                self._natural_text_width(self._bubble_plain_text) + 24,
                48,
            )
            bubble_width = min(max_width, natural_width)
            text_width = max(80, bubble_width - 24)
            bubble_height = max(
                self.bubble.fontMetrics().height() + 20,
                self._text_height(
                    self._bubble_plain_text,
                    text_width,
                ) + 20,
            )
            self.bubble.setFixedSize(bubble_width, bubble_height)

        thread_share_width, thread_share_height = (
            self._update_thread_share_size(max_width)
        )

        image_width, image_height = self._image_size(max_width)
        if self.image_label is not None:
            self.image_label.setFixedSize(image_width, image_height)
            self.image_label.show()

        content_width = max(
            bubble_width,
            thread_share_width,
            image_width if self.image_label is not None else 0,
            max((size[0] for size in auxiliary_sizes), default=0),
        )
        visible_sizes = list(auxiliary_sizes)
        if bubble_width:
            visible_sizes.append((bubble_width, bubble_height))
        if thread_share_height:
            visible_sizes.append((thread_share_width, thread_share_height))
        if image_width:
            visible_sizes.append((image_width, image_height))
        content_height = sum(size[1] for size in visible_sizes)
        if len(visible_sizes) > 1:
            content_height += (
                    self.content_container.layout().spacing()
                    * (len(visible_sizes) - 1)
            )
        content_width = max(48, content_width)
        content_height = max(36, content_height)
        self.content_container.setFixedSize(content_width, content_height)
        self.messageContentWidget.setFixedHeight(content_height)

        sender_height = 0
        if not self.label_4.isHidden():
            sender_height = self._text_height(
                self.label_4.text(),
                message_area_width,
                self.label_4.fontMetrics(),
            )
            self.label_4.setFixedSize(
                message_area_width,
                max(20, sender_height + 2),
            )
            self.label_3.setFixedWidth(message_area_width)
        else:
            self.label_3.setFixedWidth(message_area_width)

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
        self.setMinimumWidth(list_width)
        self.setMaximumWidth(list_width)
        self.setMinimumHeight(total_height)
        self.setMaximumHeight(total_height)
        self.message_layout.activate()
        self.gridLayout.activate()
        return total_height

    def _message_area_width(self, list_width):
        margins = self.gridLayout.contentsMargins()
        spacing = max(0, self.gridLayout.horizontalSpacing())
        available = (
                list_width
                - margins.left()
                - margins.right()
                - 38 * 2
                - spacing * 2
        )
        return max(80, available)

    def _update_thread_share_size(self, max_width):
        if self.thread_share_container is None:
            return 0, 0

        card_width = max(160, int(max_width))
        card_layout = self.thread_share_container.layout()
        margins = card_layout.contentsMargins()
        inner_width = max(
            120,
            card_width - margins.left() - margins.right(),
        )
        self.thread_share_container.setFixedWidth(card_width)
        self.thread_share_view.setFixedWidth(inner_width)

        layouts = self.thread_share_view.findChildren(QLayout)
        for _ in range(2):
            for layout in layouts:
                layout.invalidate()
            for layout in reversed(layouts):
                layout.activate()
            self.thread_share_view.adjustSize()

        card_layout.invalidate()
        card_layout.activate()
        height = max(
            self.thread_share_container.sizeHint().height(),
            card_layout.heightForWidth(card_width),
        )
        height = max(50, height)
        self.thread_share_container.setFixedHeight(height)
        return card_width, height

    def _update_auxiliary_sizes(self, max_width):
        sizes = []
        labels = (
            (self.reply_label, self.reply_label.text()),
        )
        for label, text in labels:
            if not text or label.isHidden():
                continue
            natural_width = max(
                self._natural_text_width(text, label.fontMetrics()) + 18,
                96,
            )
            width = min(max_width, natural_width)
            height = max(
                label.fontMetrics().height() + 10,
                self._text_height(
                    text,
                    width - 18,
                    label.fontMetrics(),
                ) + 10,
            )
            label.setFixedSize(width, height)
            sizes.append((width, height))
        return sizes

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

        scale = min(2, max_width / source_width)
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

    def _natural_text_width(self, text, metrics=None):
        metrics = metrics or self.bubble.fontMetrics()
        lines = (text or '').splitlines() or ['']
        return max(
            metrics.horizontalAdvance(line)
            for line in lines
        )

    def _cleanup(self):
        self.portrait_image.destroyImage()

    def reset_theme(self):
        super().reset_theme()

        if self.message.is_system:
            bg_color = 'rgba(127,127,127,28)'
            text_color = '#777777'
        elif self.message.direction == 'out':
            bg_color = '#4f83cc'
            text_color = '#ffffff'
        else:
            bg_color = '#e8e8e8' if profile_mgr.get_theme_policy() == 1 else '#343434'
            text_color = profile_mgr.get_theme_font_color_string()
        self.bubble.setStyleSheet(
            f'QLabel{{'
            f'background-color:{bg_color};'
            f'color:{text_color};'
            'border-radius:8px;'
            'padding:6px 8px;'
            f'font-size: 10pt;}}'
        )
        self.reply_label.setStyleSheet(
            'QLabel{'
            'background-color:rgba(127,127,127,50);'
            'color:#777777;'
            'border-left:3px solid #7a9cc6;'
            'border-radius:4px;'
            'padding:4px 6px;'
            'font-size:9pt;}'
        )
        if self.thread_share_container is not None:
            if profile_mgr.get_theme_policy() == 1:
                card_bg = 'rgba(0,0,0,10)'
                card_border = 'rgba(0,0,0,30)'
            else:
                card_bg = 'rgba(255,255,255,12)'
                card_border = 'rgba(255,255,255,35)'
            self.thread_share_container.setStyleSheet(
                'QFrame#threadShareCard{'
                f'background-color:{card_bg};'
                f'border:1px solid {card_border};'
                'border-radius:8px;}'
            )
            self.thread_share_view.setStyleSheet(
                self.thread_share_view.styleSheet()
                + '\nQWidget#Form{background-color:transparent;}'
            )
