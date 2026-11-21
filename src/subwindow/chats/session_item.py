"""左侧聊天会话条目"""
from PyQt5.QtCore import Qt

from publics import qt_image
from publics.base_ui_elements import base_ui
from publics.funcs import cut_string, show_label_pixmap_with_animation

from ui import user_chat_session_item

from publics.baidu_features.chats.structs.models import ChatSessionType


class UserChatSessionItem(base_ui.InsideWidgetBaseQWidget, user_chat_session_item.Ui_Form):
    """
    会话用户条目
    显示昵称、最近消息与未读数。
    """

    def __init__(self, session):
        super().__init__()
        self.setupUi(self)
        self.session = session
        self._avatar_key = None
        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label, pixmap)
        )
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
            self.label_4.setText('99+' if session.unread_count > 99 else str(session.unread_count))
            self.label_4.show()
        else:
            self.label_4.hide()

        self._set_avatar(session)

    def _set_avatar(self, session):
        if session.is_interaction:
            avatar_key = ('interaction', session.extra.get('category', ''))
        elif session.is_private:
            avatar_key = (
                'private',
                str(session.avatar or '').split('?', 1)[0],
            )
        elif session.is_chatroom:
            avatar_key = ('chatroom', str(session.avatar or ''))
        else:
            avatar_key = ('unknown', '')
        if avatar_key == self._avatar_key:
            return
        self._avatar_key = avatar_key

        self.portrait_image.destroyImage()
        self.label.clear()
        if session.is_private and avatar_key[1]:
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.TiebaPortrait,
                avatar_key[1],
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        elif session.is_chatroom and avatar_key[1]:
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.HttpLink,
                avatar_key[1],
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        elif session.is_interaction:
            category = session.extra.get('category', '')
            pixmap = qt_image.get_pixmap_icon_from_file(f'ui/{category}me.png', 42)
            self.label.setPixmap(pixmap)
