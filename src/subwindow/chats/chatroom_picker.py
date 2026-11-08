"""吧群订阅选择对话框。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from publics import qt_image
from publics.funcs import cut_string, show_label_pixmap_with_animation
from publics.base_ui_elements import base_ui


class ChatRoomPickerDialog(base_ui.WindowBaseQDialog):
    """展示吧群基础信息和最新消息供用户选择。"""

    def __init__(self, rooms):
        super().__init__()
        self.rooms = rooms
        self._selected_index = -1
        self._image_loaders = []

        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint)
        self.reset_theme()

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowTitle('选择要订阅的吧群')
        self.resize(620, 460)

        layout = QVBoxLayout(self)
        tip = QLabel('请选择要添加到会话列表的吧群：')
        layout.addWidget(tip)

        self.list_widget = QListWidget(self)
        self.list_widget.setFrameShape(QListWidget.NoFrame)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        layout.addWidget(self.list_widget, 1)

        for index, room in enumerate(rooms):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, index)
            widget = self._create_item(room)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _: self.accept())
        self.destroyed.connect(self._cleanup)

    def _create_item(self, room):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(8, 8, 8, 8)

        avatar = QLabel()
        avatar.setFixedSize(48, 48)
        avatar.setAlignment(Qt.AlignCenter)
        row.addWidget(avatar)

        info = QVBoxLayout()
        title = QLabel(room['name'])
        title.setStyleSheet('font-size:13px;font-weight:bold;')
        info.addWidget(title)

        meta_text = room['forum_name'] or f'吧 ID {room["fid"]}'
        if room.get('unread_count'):
            meta_text += f' · {room["unread_count"]} 条未读'
        meta = QLabel(meta_text)
        meta.setStyleSheet('color:grey;')
        info.addWidget(meta)

        latest = QLabel(
            f'最新：{cut_string(room.get("last_message") or "暂无消息", 42)}'
        )
        latest.setStyleSheet('color:grey;')
        info.addWidget(latest)
        row.addLayout(info, 1)

        if room.get('avatar'):
            loader = qt_image.MultipleImage()
            loader.currentPixmapChanged.connect(
                lambda pixmap, label=avatar: show_label_pixmap_with_animation(
                    label,
                    pixmap,
                )
            )
            loader.setImageInfo(
                qt_image.ImageLoadSource.HttpLink,
                room['avatar'],
                qt_image.ImageCoverType.RoundCover,
                (48, 48),
            )
            loader.loadImage()
            self._image_loaders.append(loader)
        return widget

    def _on_current_changed(self, current, previous):
        self.ok_button.setEnabled(current is not None)
        self._selected_index = (
            int(current.data(Qt.UserRole))
            if current is not None
            else -1
        )

    def selected_room(self):
        if 0 <= self._selected_index < len(self.rooms):
            return self.rooms[self._selected_index]
        return None

    def _cleanup(self):
        for loader in self._image_loaders:
            loader.destroyImage()
        self._image_loaders.clear()
