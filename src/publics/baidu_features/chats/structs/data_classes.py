"""
各类数据体的封装
"""
import secrets
from dataclasses import dataclass, field,asdict
from typing import List

from publics.baidu_features.chats.structs.chatroom_data_parser import *
from publics.baidu_features.chats.structs import models


@dataclass
class WsMessageUser:
    user_id: int = 0
    user_name: str = ''
    portrait: str = ''


@dataclass
class WsMessage:
    msg_id: int = 0
    msg_type: int = 0
    text: str = ''
    user: WsMessageUser = field(default_factory=WsMessageUser)
    create_time: int = 0

    @classmethod
    def from_dict(cls, data):
        return cls(
            int(data.get('msg_id', 0)),
            int(data.get('msg_type', 0)),
            str(data.get('text', '') or ''),
            WsMessageUser(
                int(data.get('user', {}).get('user_id', 0)),
                str(data.get('user', {}).get('user_name', '') or ''),
                str(data.get('user', {}).get('portrait', '') or ''),
            ),
            int(data.get('create_time', 0)),
        )


@dataclass
class WsMsgGroup:
    group_id: int = 0
    group_type: int = 0
    messages: List[WsMessage] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        return cls(
            int(data.get('group_id', 0)),
            int(data.get('group_type', 0)),
            [WsMessage.from_dict(item) for item in data.get('messages', [])],
        )


@dataclass
class WsMsgGroups:
    groups: List[WsMsgGroup] = field(default_factory=list)

    def __iter__(self):
        return iter(self.groups)

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, index):
        return self.groups[index]


@dataclass
class SendMsgResult:
    group_id: int = 0
    local_msg_id: int = 0
    to_user_id: int = 0
    to_user_type: int = 0
    msg_id: int = 0


@dataclass
class SetMsgReadedResult:
    read_msg_id: int = 0
    group_id: int = 0
    to_user_id: int = 0
    to_user_type: int = 0


@dataclass
class RobotSkill:
    type: int = 0
    name: str = ''
    alias: str = ''
    desc: str = ''
    is_show: bool = False
    items: List[dict] = field(default_factory=list)


@dataclass
class Robot:
    user_id: int = 0
    portrait: str = ''
    user_name: str = ''
    name_show: str = ''
    bduk: str = ''
    robot_role: int = 0
    skills: List[RobotSkill] = field(default_factory=list)


@dataclass
class ChatroomDetail:
    fid: int = 0
    fname: str = ''
    room_id: int = 0
    name: str = ''
    avatar: str = ''
    announce: str = ''
    member_num: int = 0
    chat_threshold: int = 0
    robots: List[Robot] = field(default_factory=list)


@dataclass
class ChatroomReplyContent:
    """
    吧群消息引用的被回复内容

    Args:
        user_id (int): 被回消息发送者的用户id
        user_name (str): 被回复者昵称

        text (str): 消息文本内容
        msg_id (int): 被回复消息id
        msg_key (str): 被回复消息key
        msg_type (models.ChatroomMessageType): 被回复消息类型
    """

    user_id: int = 0
    user_name: str = ''

    text: str = ''
    msg_type: models.ChatroomMessageType = 0

    msg_id: int = 0
    msg_key: str = ''

    def to_dict(self):
        return asdict(self)

    @classmethod
    def parse_from_json(cls, value):
        value = json_value(value, value)
        if isinstance(value, str):
            return cls(text=value)
        if not isinstance(value, dict):
            return None

        bduk = value.get('re_baidu_uk')
        user_name = value.get('re_nickname')

        text = get_message_text(value)
        msg_id = int(value.get('re_msg_id'), 0)
        msg_key = str(value.get('re_msg_key', ''))
        msg_type = models.ChatroomMessageType(int(json_value(value.get('re_ext'), {}).get('msg_type', 0)))

        return cls(
            bduk_to_user_id(bduk),
            user_name,
            text,
            msg_type,
            msg_id,
            msg_key
        )


@dataclass
class ChatroomAtUser:
    """吧群消息中的 @ 用户"""

    user_id: int = 0
    user_name: str = ''
    portrait: str = ''
    position: int = 0

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'user_name': self.user_name,
            'portrait': self.portrait,
            'position': self.position,
        }

    @classmethod
    def parse_from_json(cls, value):
        value = json_value(value, [])
        if isinstance(value, dict):
            value = value.get('at_data') or value.get('list') or [value]
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            if not isinstance(item, dict):
                continue

            bduk = item.get('at_baidu_uk')
            user_name = item.get('at_name')
            portrait = item.get('at_portrait', '').split('?', 1)[0]

            try:
                position = int(item.get('position', 0) or 0)
            except (TypeError, ValueError):
                position = 0

            result.append(cls(
                bduk_to_user_id(bduk),
                user_name,
                portrait,
                position,
            ))
        result.sort(key=lambda item: item.position)
        return result


@dataclass
class ChatroomMsg:
    """
    聊天群消息

    Attributes:
        msg_id (int): 消息id
        msg_key (str): 消息key
        msg_type (models.ChatroomMessageType): 消息类型
        user_id (int): 发送者用户id

        content (dict): 内容json信息
        text (str): 文本内容

        image_url (str): 图片内容链接
        image_thumbnail_url (str): 预览小图链接
        image_width (int): 图片宽度
        image_height (int): 图片高度

        create_time (int): 消息发送时间戳
        is_sys_msg (bool): 是否为系统消息

        reply_content (ChatroomReplyContent | None): 引用的回复内容
        at_users (list[ChatroomAtUser]): 消息艾特的用户
    """
    msg_id: int = 0
    msg_key: str = ''
    msg_type: models.ChatroomMessageType = 0
    user_id: int = 0
    content: dict = field(default_factory=dict)
    text: str = ''
    image_url: str = ''
    image_thumbnail_url: str = ''
    image_width: int = 0
    image_height: int = 0
    create_time: int = 0
    is_sys_msg: bool = False
    reply_content: ChatroomReplyContent = None
    at_users: List[ChatroomAtUser] = field(default_factory=list)

    @classmethod
    def from_json(cls, data):
        text = ''
        image_url = ''
        image_thumbnail_url = ''
        image_width = 0
        image_height = 0

        # 各种解析数据
        content = json_value(data.get('content'), {})
        content_map = content if isinstance(content, dict) else {}
        raw_text = content_map.get('text')
        text_data = json_value(raw_text, {})

        # 还是解析数据，百度的数据体封装好乱，，，
        body = json_value(text_data.get('content_body'), text_data)
        ext_data = json_value(text_data.get('ext'), text_data)

        # 消息类型
        content_type = int(ext_data.get('type') or text_data.get('content_type') or 0)

        # 把百度uk转换成用户id
        baidu_uk = (
                text_data.get('baidu_uk')
                or ext_data.get('baidu_uk')
                or '')
        user_id = bduk_to_user_id(baidu_uk)

        # 是否为系统消息
        sys_value = (
                ext_data.get('is_sys_msg')
                or text_data.get('is_sys_msg')
                or content_map.get('is_sys_msg')
                or 0
        )
        is_sys_msg = bool(int(sys_value))

        # 回复的消息内容
        reply_content = ChatroomReplyContent.parse_from_json(text_data.get('re_data'))

        # at数据
        at_users = ChatroomAtUser.parse_from_json(text_data.get('at_data'))

        # 图片链接提取
        if isinstance(body, dict):
            text = str(body.get('text', ''))
            image_url = str(
                body.get('url')
                or body.get('src')
                or body.get('thumbnail')
                or ''
            )
            image_thumbnail_url = str(
                body.get('thumbnail')
                or body.get('thumb')
                or image_url
            )

            image_content = ext_data.get('content', {})
            image_width, image_height = parse_image_size(
                image_content.get('bsize')
                or image_content.get('big_size')
            )
        elif isinstance(body, str):
            text = body
        elif text_data.get('text'):
            text = str(text_data['text'])

        if not text:
            if content_type in CHATROOM_INVALID_MSG_TYPES:
                pass
            elif content_type == models.ChatroomMessageType.ThreadShare:
                text = '[分享贴子]'
            elif content_type == models.ChatroomMessageType.Image:
                text = '[图片]'
            else:
                text = '[暂不支持的消息类型]'

        if not image_url:
            image_url = str(
                content_map.get('url')
                or content_map.get('src')
                or ''
            )
            if image_url:
                image_thumbnail_url = str(
                    content_map.get('thumbnail')
                    or content_map.get('thumb')
                    or image_url
                )
                if not text:
                    text = '[图片]'
        if not image_width:
            image_width, image_height = parse_image_size(
                content_map.get('bsize')
                or content_map.get('big_size')
                or text_data.get('bsize')
                or text_data.get('big_size')
            )

        if not text and isinstance(raw_text, str):
            text = raw_text

        return cls(
            msg_id=int(data.get('msgid', 0)),
            msg_key=str(data.get('msg_key', '') or ''),
            msg_type=models.ChatroomMessageType(content_type),
            user_id=user_id,
            content=content,
            text=text,
            image_url=image_url,
            image_thumbnail_url=image_thumbnail_url,
            image_width=image_width,
            image_height=image_height,
            create_time=int(data.get('create_time', 0)),
            is_sys_msg=is_sys_msg,
            reply_content=reply_content,
            at_users=at_users,
        )


@dataclass
class ChatroomMsgs:
    messages: List[ChatroomMsg] = field(default_factory=list)

    def __iter__(self):
        return iter(self.messages)

    def __len__(self):
        return len(self.messages)

    def __getitem__(self, index):
        return self.messages[index]


@dataclass
class RoomList:
    room_list: List[dict] = field(default_factory=list)


class _MsgIDPair:
    def __init__(self, msg_id=0):
        self.last_id = msg_id
        self.curr_id = msg_id

    def update(self, msg_id):
        self.last_id = self.curr_id
        self.curr_id = msg_id


class _PrivateCursors:
    def __init__(self):
        self.local_msg_id = 0
        self.pulled_msg_id = 0
        self.sent_msg_id = 0
        self.read_msg_id = 0


class PrivateMsgIDManager:
    def __init__(self):
        self.priv_gid = 0
        self._gid2mid = {0: _MsgIDPair()}
        self._uid2cursors = {}

    def update_msg_id(self, group_id, msg_id):
        pair = self._gid2mid.get(group_id)
        if pair is None:
            self._gid2mid[group_id] = _MsgIDPair(msg_id)
        else:
            pair.update(msg_id)

    def get_msg_id(self, group_id):
        return self._gid2mid.get(group_id, _MsgIDPair()).last_id

    def set_msg_id(self, group_id, msg_id):
        self._gid2mid[group_id] = _MsgIDPair(msg_id)

    def get_local_msg_id(self, user_id):
        cursors = self._get_cursors(user_id)
        return max(cursors.local_msg_id, cursors.pulled_msg_id * 100) + 1

    def update_local_msg_id(self, user_id, msg_id):
        cursors = self._get_cursors(user_id)
        cursors.local_msg_id = max(cursors.local_msg_id, msg_id)

    def update_pulled_msg_id(self, user_id, msg_id):
        cursors = self._get_cursors(user_id)
        cursors.pulled_msg_id = max(cursors.pulled_msg_id, msg_id)

    def update_sent_msg_id(self, user_id, msg_id):
        cursors = self._get_cursors(user_id)
        cursors.sent_msg_id = max(cursors.sent_msg_id, msg_id)

    def update_read_msg_id(self, user_id, msg_id):
        cursors = self._get_cursors(user_id)
        cursors.read_msg_id = max(cursors.read_msg_id, msg_id)

    def _get_cursors(self, user_id):
        cursors = self._uid2cursors.get(user_id)
        if cursors is None:
            cursors = _PrivateCursors()
            self._uid2cursors[user_id] = cursors
        return cursors


class PrivateMessageAccount:
    def __init__(self, account):
        self.source = account
        self.ws_sec_key = secrets.token_bytes(31)
        source_user = getattr(account, 'user', None)
        self.user_id = int(getattr(source_user, 'user_id', 0) or 0)
        self.user_name = ''
        self.nick_name = ''
        self.portrait = str(getattr(source_user, 'portrait', '') or '')
        self.is_vip = bool(getattr(source_user, 'is_vip', False))
        self.glevel = int(getattr(source_user, 'glevel', 0) or 0)
        self.uk = int(getattr(source_user, 'uk', 0) or 0)
        self.trigger_id = int(getattr(source_user, 'trigger_id', 0) or 0)
        self.bduk = ''

    @property
    def bduss(self):
        return self.source.BDUSS

    @property
    def stoken(self):
        return self.source.STOKEN

    @property
    def cuid_galaxy2(self):
        return self.source.cuid_galaxy2

    @property
    def c3_aid(self):
        return self.source.c3_aid

    @property
    def zid(self):
        return (
                getattr(self.source, 'z_id', None)
                or getattr(self.source, 'zid', None)
                or ''
        )

    @property
    def sample_id(self):
        return self.source.sample_id or ''

    @property
    def client_id(self):
        return self.source.client_id or ''

    def set_user(self, user):
        self.user_id = int(getattr(user, 'user_id', 0) or self.user_id)
        self.user_name = str(getattr(user, 'user_name', '') or self.user_name)
        self.nick_name = str(
            getattr(user, 'nick_name', '')
            or getattr(user, 'show_name', '')
            or self.nick_name
            or self.user_name
        )
        portrait = str(getattr(user, 'portrait', '') or self.portrait)
        self.portrait = portrait.split('?', 1)[0]
        self.is_vip = bool(getattr(user, 'is_vip', self.is_vip))
        self.glevel = int(getattr(user, 'glevel', self.glevel) or self.glevel)
        self.uk = int(getattr(user, 'uk', self.uk) or self.uk)
        self.trigger_id = int(getattr(user, 'trigger_id', self.trigger_id) or self.trigger_id)
        if self.user_id:
            self.bduk = protocol.user_id2bduk(self.user_id)
