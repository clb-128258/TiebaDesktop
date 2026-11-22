"""
聊天会话数据模型
"""
import enum
import strenum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

from publics import account_mgr


class ChatSessionType(str, enum.Enum):
    """会话类型"""

    INTERACTION = 'interaction'
    PRIVATE = 'private'
    CHATROOM = 'chatroom'


class ChatroomMessageFromType(strenum.StrEnum):
    """
    聊天群消息发送来源

    Attributes:
        Ios: ios端贴吧
        Android: 安卓端贴吧

        Unknown: 未知客户端
    """
    Ios = 'ios'
    Android = 'android'

    Unknown = 'Unknown'

    @classmethod
    def _missing_(cls, value):
        return cls.Unknown


class ChatroomMessageType(enum.IntEnum):
    """
    聊天群消息类型

    Attributes:
        Text: 纯文本消息
        Image: 图片消息
        Voice: 语音消息
        MemeImage: 表情包图片
        ThreadShare: 转发贴子
        OnlineUsersCountUpdate: 群聊在线人数更新
        RecallNotice: 撤回系统提示

        CloudCallUnknown: [106] 作用未知，可能与云控相关
        Unknown: 未知类型
    """
    Text = 1
    Image = 2
    Voice = 3
    MemeImage = 4
    ThreadShare = 7010
    OnlineUsersCountUpdate = 101
    CloudCallUnknown = 106
    RecallNotice = 7002

    Unknown = 0

    @classmethod
    def _missing_(cls, value):
        return cls.Unknown

    def is_sys_msg(self):
        sys_msg_types = [self.RecallNotice]
        return self.value in sys_msg_types


@dataclass
class ChatMessage:
    """
    统一的消息容器
    """

    session_key: str = ''
    message_id: int = 0

    sender_id: int = 0
    sender_name: str = ''
    sender_portrait: str = ''

    msg_type: int = 1
    text: str = ''

    image_urls: List[str] = field(default_factory=list)
    image_thumbnail_urls: List[str] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0

    timestamp: int = 0
    is_read: bool = False
    notify: bool = True
    is_system: bool = False

    reply_content: Dict[str, Any] = field(default_factory=dict)
    at_users: List[Dict[str, Any]] = field(default_factory=list)
    thread_share: Dict[str, Any] = field(default_factory=dict)

    payload: Dict[str, Any] = field(default_factory=dict)
    origin_msg: Any = None

    @property
    def direction(self):
        """
        消息的发送方向
        """
        current_uid = account_mgr.GlobalAccountContainer.get_current_account().uid
        current_portrait = account_mgr.GlobalAccountContainer.get_current_account().portrait
        return 'out' if self.sender_id == current_uid or self.sender_portrait == current_portrait else 'in'

    def to_dict(self):
        return asdict(self)


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


ChatroomMsgTypeStringMap = {
    ChatroomMessageType.Text: '[文本]',
    ChatroomMessageType.Image: '[图片]',
    ChatroomMessageType.MemeImage: '[表情]',
    ChatroomMessageType.Voice: '[语音]',
    ChatroomMessageType.ThreadShare: '[分享贴子]',
}
