"""
各类数据体的封装
"""
import secrets
from dataclasses import dataclass, field, asdict
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
    """私信消息"""
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
class ChatroomThreadShare:
    """吧群消息中的转发贴子"""

    thread_id: int = 0
    title: str = ''
    forum_id: int = 0
    forum_name: str = ''
    forum_avatar: str = ''
    author_id: int = 0
    author_name: str = ''
    author_portrait: str = ''
    abstract: str = ''
    image_urls: List[str] = field(default_factory=list)
    video_url: str = ''
    video_duration: int = 0
    video_play_count: int = 0
    show_content: str = ''

    def to_dict(self):
        return asdict(self)

    @classmethod
    def parse_from_json(cls, service_info):
        thread_info = service_info.get('thread_info')
        if not isinstance(thread_info, dict):
            return None

        author = thread_info.get('author', {})
        forum_info = thread_info.get('forumInfo', {})
        rich_abstract = thread_info.get('richAbstract', [])
        video_info = thread_info.get('videoInfo', {})
        if not isinstance(rich_abstract, list):
            rich_abstract = []
        abstract_parts = []
        image_urls = []
        video_url = str(video_info.get('videoUrl', ''))
        video_duration = int(video_info.get('videoDuration', 0))
        video_play_count = int(video_info.get('playCount', 0))
        video_thumbnail_url = video_info.get('thumbnailUrl')
        if video_thumbnail_url:
            image_urls.append(str(video_thumbnail_url))
        for part in rich_abstract:
            if not isinstance(part, dict):
                continue
            if int(part.get('type', 0)) == 0:
                text = ' '.join(str(part.get('text', '')).split())
                abstract_parts.append(text)
            else:
                part_type = int(part.get('type', 0))
                if part_type == 5:
                    video_url = video_url or str(part.get('link', ''))
                    video_duration = (
                            video_duration
                            or int(part.get('during_time', 0))
                    )
                    if not video_thumbnail_url:
                        image_url = part.get('src')
                        if image_url:
                            image_urls.append(str(image_url))
                else:
                    image_url = (
                            part.get('src')
                            or part.get('url')
                            or part.get('small_pic')
                            or ''
                    )
                    if image_url:
                        image_urls.append(image_url)

        media_list = thread_info.get('media', [])
        if isinstance(media_list, dict):
            media_list = [media_list]
        for media in media_list:
            if not isinstance(media, dict):
                continue
            image_url = media.get('url') or media.get('small_pic')
            if image_url:
                image_urls.append(str(image_url))

        return cls(
            thread_id=int(thread_info.get('id', 0)),
            title=str(thread_info.get('title', '')),
            forum_id=int(
                forum_info.get('id')
                or forum_info.get('fid')
                or 0
            ),
            forum_name=str(forum_info.get('name', '')),
            forum_avatar=str(forum_info.get('avatar', '')),
            author_id=int(author.get('id', 0)),
            author_name=str(author.get('nameShow') or author.get('name', '')),
            author_portrait=str(author.get('portrait', '')).split('?', 1)[0],
            abstract='\n'.join(abstract_parts),
            image_urls=list(dict.fromkeys(image_urls))[:3],
            video_url=video_url,
            video_duration=video_duration,
            video_play_count=video_play_count,
            show_content=str(
                service_info.get('msg_conf', {}).get('show_content', '')
            ),
        )


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
        extra_info (dict): 额外的消息体json信息
        text (str): 文本内容

        image_url (str): 图片内容链接
        image_thumbnail_url (str): 预览小图链接
        image_width (int): 图片宽度
        image_height (int): 图片高度

        voice_url (str): 语言url
        voice_duration (int): 语音长度

        create_time (int): 消息发送时间戳
        is_sys_msg (bool): 是否为系统消息
        from_client (models.ChatroomMessageFromType): 发送来源客户端

        reply_content (ChatroomReplyContent | None): 引用的回复内容
        at_users (list[ChatroomAtUser]): 消息艾特的用户
        thread_share (ChatroomThreadShare | None): 转发贴子信息
    """
    msg_id: int = 0
    msg_key: str = ''
    msg_type: models.ChatroomMessageType = 0
    user_id: int = 0

    content: dict = field(default_factory=dict)
    extra_info: dict = field(default_factory=dict)
    text: str = ''

    image_url: str = ''
    image_thumbnail_url: str = ''
    image_width: int = 0
    image_height: int = 0

    voice_url: str = ''
    voice_duration: int = 0

    create_time: int = 0
    is_sys_msg: bool = False
    from_client: models.ChatroomMessageFromType = ''

    reply_content: ChatroomReplyContent = None
    at_users: List[ChatroomAtUser] = field(default_factory=list)
    thread_share: ChatroomThreadShare = None

    @classmethod
    def from_json(cls, data):
        text = ''
        thread_share = None

        image_url = ''
        image_thumbnail_url = ''
        image_width = 0
        image_height = 0

        voice_url = ''
        voice_duration = 0

        # 各种解析数据，百度的数据体封装好乱，，，
        content = json_value(data.get('content'), {})
        text_data = json_value(content.get('text'), {})
        body = json_value(text_data.get('content_body'), {})
        ext_data = json_value(text_data.get('ext'), text_data.get('data', {}))

        # 消息类型
        content_type = int(
            ext_data.get('type') or
            ext_data.get('service_info', {}).get('msg_type') or
            text_data.get('content_type') or
            text_data.get('type') or
            0
        )

        # 来自哪个客户端
        from_client = ext_data.get('from')

        # 把百度uk转换成用户id
        baidu_uk = text_data.get('baidu_uk', '')
        user_id = bduk_to_user_id(baidu_uk)

        # 是否为系统消息
        sys_value = ext_data.get('is_sys_msg', 0)
        is_sys_msg = bool(int(sys_value)) or models.ChatroomMessageType(content_type).is_sys_msg()

        # 回复的消息内容
        reply_content = ChatroomReplyContent.parse_from_json(text_data.get('re_data'))

        # at数据
        at_users = ChatroomAtUser.parse_from_json(text_data.get('at_data'))

        # 富媒体内容获取
        if content_type == models.ChatroomMessageType.Text:
            # 纯文本消息
            text = body.get('text', '')
        elif content_type in (models.ChatroomMessageType.Image, models.ChatroomMessageType.MemeImage):
            # 图片链接提取
            image_url = body.get('url', '')
            image_thumbnail_url = body.get('thumbnail', '')

            image_content = ext_data.get('content', {})
            image_width, image_height = parse_image_size(
                image_content.get('bsize')
                or image_content.get('big_size')
            )
        elif content_type == models.ChatroomMessageType.Voice:
            # 语音数据
            voice_url = body.get('url', '')
            voice_duration = int(body.get('duration', 0))
        elif content_type == models.ChatroomMessageType.ThreadShare:
            service_info = ext_data.get('service_info', {})
            thread_share = ChatroomThreadShare.parse_from_json(service_info)
            if thread_share is not None:
                text = thread_share.title or thread_share.show_content
            else:
                text = '[分享贴子]'
        elif service_info := ext_data.get('service_info'):
            # service_info 类信息获取
            text = service_info['msg_conf']['show_content']
        else:
            if content_type in CHATROOM_INVALID_MSG_TYPES:
                pass
            elif content_type_string := models.ChatroomMsgTypeStringMap.get(content_type):
                text = content_type_string
            else:
                text = '[暂不支持的消息类型]'

        return cls(
            msg_id=int(data.get('msgid', 0)),
            msg_key=str(data.get('msg_key', '') or ''),
            msg_type=models.ChatroomMessageType(content_type),
            user_id=user_id,
            content=text_data,
            extra_info=ext_data,
            text=text,
            image_url=image_url,
            image_thumbnail_url=image_thumbnail_url,
            image_width=image_width,
            image_height=image_height,
            voice_url=voice_url,
            voice_duration=voice_duration,
            create_time=int(data.get('create_time', 0)),
            is_sys_msg=is_sys_msg,
            from_client=models.ChatroomMessageFromType(from_client),
            reply_content=reply_content,
            at_users=at_users,
            thread_share=thread_share,
        )

    def to_json(self):
        return asdict(self)

    def to_normal_msg(self):
        chatroom_id = int(self.extra_info.get('session_id') or self.content.get('room_id') or 0)
        service_info = self.extra_info.get('service_info')
        if not isinstance(service_info, dict):
            service_info = self.extra_info
        user_from = service_info.get('user_from', {})
        user_name = (
                user_from.get('username')
                or self.extra_info.get('user_name', '')
        )
        portrait = (
                user_from.get('avatar')
                or self.extra_info.get('portrait', '')
        ).split('?', 1)[0]

        return models.ChatMessage(
            session_key=f'chatroom:{chatroom_id}',
            message_id=self.msg_id,
            sender_id=self.user_id,
            sender_name=user_name,
            sender_portrait=portrait,
            msg_type=self.msg_type,
            text=self.text,
            image_urls=[self.image_url] if self.image_url else [],
            image_thumbnail_urls=(
                [self.image_thumbnail_url]
                if self.image_thumbnail_url
                else []
            ),
            image_width=int(self.image_width),
            image_height=int(self.image_height),
            timestamp=int(self.create_time),
            payload=self.content,
            is_read=True,
            reply_content=(
                self.reply_content.to_dict()
                if self.reply_content is not None
                else {}
            ),
            at_users=[
                user.to_dict()
                for user in self.at_users
            ],
            thread_share=(
                self.thread_share.to_dict()
                if self.thread_share is not None
                else {}
            ),
            is_system=self.is_sys_msg,
            origin_msg=self
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
