"""左侧聊天会话条目。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from publics import profile_mgr, qt_image
from publics.base_ui_elements import base_ui
from publics.funcs import cut_string, show_label_pixmap_with_animation

from ui import user_chat_session_item

from .models import ChatSessionType


class UserChatSessionItem(base_ui.InsideWidgetBaseQWidget, user_chat_session_item.Ui_Form):
    """
    会话用户条目
    显示昵称、最近消息与未读数。
    """

    def __init__(self, session):
        super().__init__()
        self.setupUi(self)
        self.session = session
        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label, pixmap)
        )
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.set_session(session)
        self.reset_theme()

    def set_session(self, session):
        self.session = session
        self.label_2.setText(cut_string(session.title or '未命名会话', 10))
        self.label_2.setToolTip(session.title or '')

        if session.session_type == ChatSessionType.INTERACTION:
            self.label_3.clear()
            self.label_3.hide()
        else:
            self.label_3.setText(cut_string(session.subtitle or '暂无消息', 15))
            self.label_3.setToolTip(session.subtitle or '')
            self.label_3.show()

        if session.unread_count > 0:
            self.label_4.setText('999+' if session.unread_count > 999 else str(session.unread_count))
            self.label_4.show()
        else:
            self.label_4.hide()

        self._set_avatar(session)

    def _set_avatar(self, session):
        self.portrait_image.destroyImage()
        if session.session_type == ChatSessionType.PRIVATE and session.avatar:
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.TiebaPortrait,
                session.avatar.split('?', 1)[0],
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        elif session.session_type == ChatSessionType.CHATROOM and session.avatar:
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.HttpLink,
                session.avatar,
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        else:
            icon_policy = profile_mgr.get_theme_policy_string()[1]
            icon = QPixmap(f'ui/icon_{icon_policy}/comment.png')
            icon.setDevicePixelRatio(qt_image.get_screen_ratio())
            self.label.setPixmap(icon.scaled(
                30,
                30,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            ))

    def reset_theme(self):
        super().reset_theme()
        color = profile_mgr.get_theme_font_color_string()
        self.label_2.setStyleSheet(f'QLabel{{color:{color};}}')
        self.label_3.setStyleSheet('QLabel{color:grey;}')
        self.label_4.setStyleSheet(
            'QLabel{background-color:#e5484d;color:white;'
            'border-radius:9px;padding-left:5px;padding-right:5px;}'
        )
