"""
聊天会话数据模型
"""
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List


class ChatSessionType(str, enum.Enum):
    """会话类型"""

    INTERACTION = 'interaction'
    PRIVATE = 'private'
    CHATROOM = 'chatroom'


@dataclass
class ChatMessage:
    """
    私信与吧群共用的消息容器
    """

    session_key: str = ''
    message_id: int = 0
    sender_id: int = 0
    sender_name: str = ''
    sender_portrait: str = ''
    direction: str = 'in'
    msg_type: int = 1
    text: str = ''
    image_urls: List[str] = field(default_factory=list)
    image_thumbnail_urls: List[str] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    timestamp: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    is_read: bool = False
    notify: bool = True


@dataclass
class InteractionEntry:
    """一条回复、@ 或点赞互动"""

    category: str
    timestamp: int
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatSession:
    """可被左侧列表和详情页共同消费的会话"""

    key: str
    session_type: ChatSessionType
    target_id: int = 0
    title: str = ''
    subtitle: str = ''
    avatar: str = ''
    timestamp: int = 0
    unread_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)
    messages: List[ChatMessage] = field(default_factory=list)

    @property
    def is_interaction(self):
        return self.session_type == ChatSessionType.INTERACTION

    @property
    def is_private(self):
        return self.session_type == ChatSessionType.PRIVATE

    @property
    def is_chatroom(self):
        return self.session_type == ChatSessionType.CHATROOM

    @classmethod
    def interaction_session(
        cls,
        category,
        unread_count=0,
        title='互动消息',
        timestamp=0,
    ):
        return cls(
            key=f'interaction:{category}',
            session_type=ChatSessionType.INTERACTION,
            target_id=0,
            title=title,
            subtitle='',
            timestamp=timestamp,
            unread_count=unread_count,
            extra={'category': category},
        )

    @classmethod
    def private_session(
        cls,
        peer_user_id,
        title,
        subtitle,
        portrait,
        timestamp,
        unread_count,
    ):
        return cls(
            key=f'private:{int(peer_user_id)}',
            session_type=ChatSessionType.PRIVATE,
            target_id=int(peer_user_id),
            title=title or str(peer_user_id),
            subtitle=subtitle,
            avatar=portrait,
            timestamp=int(timestamp or 0),
            unread_count=int(unread_count or 0),
        )

    @classmethod
    def chatroom_session(cls, room):
        room_id = int(room.get('room_id', 0))
        return cls(
            key=f'chatroom:{room_id}',
            session_type=ChatSessionType.CHATROOM,
            target_id=room_id,
            title=str(room.get('name') or room.get('forum_name') or room_id),
            subtitle=str(room.get('last_message') or '暂无消息'),
            avatar=str(room.get('avatar') or ''),
            timestamp=int(room.get('last_time', 0) or 0),
            unread_count=int(room.get('unread_count', 0) or 0),
            extra={
                'fid': int(room.get('fid', 0) or 0),
                'forum_name': str(room.get('forum_name', '') or ''),
                'member_num': int(room.get('member_num', 0) or 0),
            },
        )
