"""贴吧私信与吧群消息 API。

公开接口尽量对齐 aiotieba 4.8.x：

- ``send_msg`` / ``get_group_msg`` / ``set_msg_readed``：私信
- ``get_roomlist_by_fid`` / ``get_chatroom_detail`` / ``get_chatroom_msgs``：吧群
- ``join_chatroom`` / ``send_chatroom_msg``：吧群长连接操作

频繁收发消息时应复用 :class:`TiebaMessageClient`；模块底部的同名函数是一次性
便捷入口，每次调用都会创建并关闭连接。
"""
import asyncio
import binascii
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urlencode

import aiohttp
import aiotieba
from aiotieba.config import ProxyConfig
from aiotieba.helper.crypto import enuid
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_der_public_key

from publics import request_mgr
from . import tieba_message_protocol as protocol
from .tieba_message_network import (
    BlcpNotification,
    MessageConnectionError,
    PrivateMessageConnection,
    BlcpConnection,
    _resolve_proxy,
)

_WS_PUBLIC_KEY = binascii.a2b_base64(
    b'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwQpwBZxXJV/JVRF/uNfyMSdu7YWwRNLM8+2xbniGp2iIQHOikPpTYQjlQgMi1uvq1kZpJ32rHo3hkwjy2l0lFwr3u4Hk2Wk7vnsqYQjAlYlK0TCzjpmiI+OiPOUNVtbWHQiLiVqFtzvpvi4AU7C1iKGvc/4IS45WjHxeScHhnZZ7njS4S1UgNP/GflRIbzgbBhyZ9kEW5/OO5YfG1fy6r4KSlDJw4o/mw5XhftyIpL+5ZBVBC6E1EIiP/dd9AbK62VV1PByfPMHMixpxI3GM2qwcmFsXcCcgvUXJBa9k6zP8dDQ3csCM2QNT+CQAOxthjtp/TFWaD7MzOdsIYb3THwIDAQAB'
)


def _check_response_error(result):
    error = getattr(result, 'err', None)
    if error is not None:
        raise error
    return result


def _json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _parse_image_size(value):
    """
    解析接口中的 `bsize` 尺寸字段

    Return:
        (width, height)
    """
    if isinstance(value, dict):
        width = value.get('width') or value.get('w')
        height = value.get('height') or value.get('h')
        try:
            return int(width), int(height)
        except (TypeError, ValueError):
            return 0, 0
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return 0, 0
    if value is None:
        return 0, 0

    text = str(value).strip().lower()
    for separator in (',', 'x', '×', '*'):
        if separator in text:
            parts = text.split(separator, 1)
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except (TypeError, ValueError):
                return 0, 0
    return 0, 0


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
class ChatroomMsg:
    """
    聊天群消息

    Attributes:
        msg_id (int): 消息id
        msg_key (str): 消息key
        msg_type (int): 消息类型
        user_id (int): 发送者用户id

        content (dict): 内容json信息
        text (str): 文本内容
        image_url (str): 图片内容链接
        image_thumbnail_url (str): 预览小图链接
        image_width (int): 图片宽度
        image_height (int): 图片高度
        create_time (int): 消息发送时间戳
    """
    msg_id: int = 0
    msg_key: str = ''
    msg_type: int = 0
    user_id: int = 0
    content: dict = field(default_factory=dict)
    text: str = ''
    image_url: str = ''
    image_thumbnail_url: str = ''
    image_width: int = 0
    image_height: int = 0
    create_time: int = 0

    @classmethod
    def from_json(cls, data):
        text = ''
        image_url = ''
        image_thumbnail_url = ''
        image_width = 0
        image_height = 0

        content = _json_value(data.get('content'), {})
        content_map = content if isinstance(content, dict) else {}
        raw_text = content_map.get('text')
        text_data = _json_value(raw_text, {})
        parsed_raw_text = _json_value(raw_text, None)

        if isinstance(text_data, dict):
            body = _json_value(text_data.get('content_body'), text_data)
            ext_data=_json_value(text_data.get('ext'), text_data)
            if isinstance(body, dict):
                text = str(body.get('text', '') or '')
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
                image_width, image_height = _parse_image_size(
                    image_content.get('bsize')
                    or image_content.get('big_size')
                )
            elif isinstance(body, str):
                text = body
            elif text_data.get('text'):
                text = str(text_data['text'])

            if not text:
                content_type = str(text_data.get('content_type', '') or '')
                if content_type == '1':
                    text = '[图片]'
                else:
                    text = '[暂不支持的消息类型，请用手机贴吧查看]'
                    print(data)

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
            image_width, image_height = _parse_image_size(
                content_map.get('bsize')
                or content_map.get('big_size')
                or text_data.get('bsize')
                or text_data.get('big_size')
            )
        if (
                not text
                and isinstance(raw_text, str)
                and not isinstance(parsed_raw_text, (dict, list))
        ):
            text = raw_text

        return cls(
            int(data.get('msgid', 0)),
            str(data.get('msg_key', '') or ''),
            int(data.get('type', 0)),
            int(data.get('from_user', 0) or 0),
            content,
            text,
            image_url,
            image_thumbnail_url,
            image_width,
            image_height,
            int(data.get('create_time', 0)),
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


class _MsgIDManager:
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


class _MessageAccount:
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


class TiebaMessageClient:
    """可复用的贴吧私信与吧群消息客户端。"""

    def __init__(self, account, proxy=True):
        if isinstance(account, str):
            account = aiotieba.Account(account)
        if not isinstance(account, aiotieba.Account):
            raise TypeError('account 必须是 aiotieba.Account 或 BDUSS 字符串')

        self._account = _MessageAccount(account)
        self._proxy = proxy
        self._session = None
        self._private = None
        self._blcp = None
        self._chat_message_queue = asyncio.Queue(maxsize=100)
        self._private_forwarder = None
        self._message_ids = _MsgIDManager()
        self._private_group_ids = set()
        self._is_closed = False
        self.private_message_queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, exc_tb=None):
        await self.close()

    async def start(self, private=True, chatroom=True):
        """提前初始化连接。未调用时各方法也会按需初始化。"""
        if private:
            await self._ensure_private()
        if chatroom:
            await self._ensure_chatroom()
        return self

    async def close(self):
        if self._is_closed:
            return
        self._is_closed = True

        if self._private is not None:
            await self._private.close()
            self._private = None
        if self._blcp is not None:
            await self._blcp.close()
            self._blcp = None
        await self._stop_private_forwarder()
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _stop_private_forwarder(self):
        if self._private_forwarder is None:
            return
        self._private_forwarder.cancel()
        try:
            await self._private_forwarder
        except asyncio.CancelledError:
            pass
        self._private_forwarder = None

    async def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12),
                trust_env=self._proxy is True,
            )
        return self._session

    def _proxy_kwargs(self):
        proxy_url, proxy_auth = _resolve_proxy(self._proxy)
        kwargs = {}
        if proxy_url:
            kwargs['proxy'] = proxy_url
        if proxy_auth is not None:
            kwargs['proxy_auth'] = proxy_auth
        return kwargs

    def _legacy_proxy(self):
        if isinstance(self._proxy, str):
            return ProxyConfig(self._proxy)
        return self._proxy

    async def _request(self, method, url, **kwargs):
        session = await self._get_session()
        kwargs.setdefault('ssl', request_mgr.is_ssl_required())
        kwargs.update(self._proxy_kwargs())
        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            return await response.read(), response

    async def _ensure_profile(self):
        if self._account.user_id and self._account.nick_name:
            return

        async with aiotieba.Client(
                account=self._account.source,
                proxy=self._legacy_proxy(),
        ) as client:
            user = await client.get_self_info()
            _check_response_error(user)
            self._account.set_user(user)

            http_core = client._http_core
            tasks = []
            if not self._account.zid:
                tasks.append(aiotieba.init_z_id.request(http_core))
            if not self._account.client_id or not self._account.sample_id:
                tasks.append(aiotieba.sync.request(http_core))
            results = await asyncio.gather(*tasks)

            index = 0
            if not self._account.zid:
                if hasattr(self._account.source, 'z_id'):
                    self._account.source.z_id = results[index]
                else:
                    self._account.source.zid = results[index]
                index += 1
            if not self._account.client_id or not self._account.sample_id:
                client_id, sample_id = results[index]
                self._account.source.client_id = client_id
                self._account.source.sample_id = sample_id

    async def _ensure_private(self):
        if self._private is not None and self._private.is_open:
            return
        if self._is_closed:
            raise MessageConnectionError('message client is closed')

        if self._private is not None:
            await self._private.close()
            self._private = None
        await self._stop_private_forwarder()

        await self._ensure_profile()

        private = PrivateMessageConnection(
            self._account.ws_sec_key,
            proxy=self._proxy,
        )
        await private.connect()

        try:
            device = {
                '_client_type': '2',
                '_client_version': protocol.MESSAGE_CLIENT_VERSION,
            }
            rsa_cipher = load_der_public_key(_WS_PUBLIC_KEY)
            secret_key = rsa_cipher.encrypt(self._account.ws_sec_key, PKCS1v15())
            request_body = protocol.pack_update_client_info_req(
                self._account.bduss,
                device,
                secret_key,
                cuid=f'-|com.baidu.tieba{protocol.MESSAGE_CLIENT_VERSION}',
            )
            response_body = await private.send(
                request_body,
                protocol.CMD_INIT_WS,
                encrypt=False,
            )
            result = protocol.parse_update_client_info_res(response_body)

            user = result['user']
            user_id = int(user.get('user_id', 0))
            available = int(result.get('is_user_available', 0))
            if not user_id or available != user_id:
                raise aiotieba.exception.TiebaValueError(
                    f'isUserAvailable({available}) userId({user_id})'
                )

            self._account.user_id = self._account.user_id or user_id
            self._account.user_name = self._account.user_name or user.get('user_name', '')
            self._account.portrait = self._account.portrait or user.get('portrait', '')
            self._account.nick_name = (
                    self._account.nick_name
                    or self._account.user_name
                    or str(user_id)
            )
            self._account.bduk = protocol.user_id2bduk(self._account.user_id)

            for group in result['groups']:
                group_id = int(group['group_id'])
            if int(group['group_type']) == protocol.GROUP_TYPE_PRIVATE_MSG:
                self._message_ids.priv_gid = group_id
                self._private_group_ids.add(group_id)
                self._message_ids.update_msg_id(group_id, int(group['last_msg_id']))
        except BaseException:
            await private.close()
            raise

        self._private = private
        self._private_forwarder = asyncio.create_task(self._forward_private_messages())

    async def _forward_private_messages(self):
        private = self._private
        while private is not None:
            groups = await private.message_queue.get()
            self._track_private_groups(groups)
            await self.private_message_queue.put(WsMsgGroups([
                WsMsgGroup.from_dict(group) for group in groups
            ]))

    def _track_private_groups(self, groups):
        for group in groups:
            group_id = int(group['group_id'])
            if int(group['group_type']) == protocol.GROUP_TYPE_PRIVATE_MSG:
                if not self._message_ids.priv_gid:
                    self._message_ids.priv_gid = group_id
            else:
                continue

            for message in group['messages']:
                user_id = int(message['user']['user_id'])
                if not user_id:
                    continue
                self._message_ids.update_pulled_msg_id(user_id, int(message['msg_id']))
                if int(message['msg_type']) != protocol.MSG_TYPE_READED:
                    continue
                content = _json_value(message['text'], {})
                if content.get('eventId') != 22001:
                    continue
                read_msg_id = content.get('eventParam', {}).get('readMsgId', 0)
                if read_msg_id:
                    self._message_ids.update_read_msg_id(user_id, int(read_msg_id))

    async def _get_lcm_token(self):
        cuid = self._account.cuid_galaxy2
        timestamp = int(time.time() * 1000)
        data = [
            ('app_id', str(protocol.CHAT_APPID)),
            ('app_version', protocol.MESSAGE_CLIENT_VERSION),
            ('cuid', cuid),
            ('device_type', 'android'),
            ('manufacture', ''),
            ('model_type', ''),
            ('request_id', str(timestamp)),
            ('sdk_version', protocol.BLCP_SDK_VERSION),
            (
                'sign',
                hashlib.md5(
                    f'{protocol.CHAT_APPID}{cuid}android{timestamp}'.encode()
                ).hexdigest(),
            ),
            ('ts', timestamp),
            ('user_key', ''),
        ]
        body, _ = await self._request(
            'POST',
            'https://pim.baidu.com/rest/5.0/generate_lcm_token',
            headers={
                'Accept-Encoding': 'gzip',
                'User-Agent': 'aiotieba/4.8.4',
            },
            json=dict(data),
        )
        result = json.loads(body.decode('utf-8'))
        if int(result.get('err_code', 0) or 0):
            raise aiotieba.exception.TiebaServerError(
                int(result['err_code']),
                str(result.get('err_msg', '')),
            )
        token = result.get('token') or result.get('data', {}).get('token')
        if not token:
            raise aiotieba.exception.TiebaValueError('Missing LCM token')
        return token

    async def _ensure_chatroom(self):
        if self._blcp is not None and self._blcp.is_open:
            return
        if self._is_closed:
            raise MessageConnectionError('message client is closed')

        if self._blcp is not None:
            await self._blcp.close()
            self._blcp = None

        await self._ensure_profile()
        token = await self._get_lcm_token()

        blcp = BlcpConnection(message_queue=self._chat_message_queue)
        await blcp.connect()

        try:
            correlation_id = protocol.new_correlation_id()
            body = protocol.pack_lcm_login_req(
                token,
                correlation_id,
                self._account.cuid_galaxy2,
            )
            response = await blcp.request(
                protocol.BLCP_SERVICE_LCM,
                protocol.BLCP_METHOD_LOGIN,
                body,
                correlation_id,
            )
            if not response.ok or response.payload['error_code']:
                raise aiotieba.exception.TiebaServerError(
                    response.payload['error_code'],
                    response.payload['error_msg'],
                )
            blcp.start_heartbeat(response.payload['next_interval_ms'])

            cloud_request = {
                'params': {
                    'appname': 'tieba',
                    'sid': self._account.sample_id,
                    'ua': f'900_1600_android_{protocol.MESSAGE_CLIENT_VERSION}_240',
                    'uid': enuid(self._account.cuid_galaxy2),
                    'cfrom': '1008550l',
                    'from': '1008550l',
                    'network': '1_-1',
                    'p_sv': '32',
                    'mps': '',
                    'mpv': '1',
                    'c3_aid': self._account.c3_aid,
                    'type_id': '0',
                },
                'filter': {
                    'aps': {'cpu_abi': 'armeabi-v7a'},
                    'command': {'step': '0'},
                },
            }
            response = await blcp.request(
                protocol.BLCP_SERVICE_CLOUD_CONTROL,
                protocol.BLCP_METHOD_LOGIN,
                cloud_request,
            )
            if not response.ok or int(response.payload.get('errno', 0)):
                raise aiotieba.exception.TiebaServerError(
                    response.error_code or int(response.payload.get('errno', 0)),
                    response.error_text or 'cloud control login failed',
                )

            im_request = {
                'method': protocol.BLCP_METHOD_LOGIN_BY_TOKEN,
                'appid': protocol.CHAT_APPID,
                'device_id': 'android_' + self._account.cuid_galaxy2,
                'account_type': 1,
                'token': self._account.bduss,
                'version': 4,
                'sdk_version': protocol.CHAT_SDK_VERSION,
                'app_version': protocol.MESSAGE_CLIENT_VERSION,
                'app_open_type': 0,
                'client_identifier': json.dumps({'zid': '', 'version_code': ''}),
                'tail': 0,
                'timeout': 10,
                'cookie': '',
                'device_info': {
                    'app_version': protocol.MESSAGE_CLIENT_VERSION,
                    'os_version': '32',
                    'platform': 'android',
                    'appid': str(protocol.CHAT_APPID),
                    'from': '1008550l',
                    'cfrom': '1008550l',
                },
                'rpc': json.dumps({'rpc_retry_time': 0}),
                'user_type': 0,
                'client_logid': int(time.time() * 1_000_000),
            }
            response = await blcp.request(
                protocol.BLCP_SERVICE_IM,
                protocol.BLCP_METHOD_LOGIN_BY_TOKEN,
                im_request,
            )
            if not response.ok or int(response.payload.get('err_code', 0)):
                raise aiotieba.exception.TiebaServerError(
                    response.error_code or int(response.payload.get('err_code', 0)),
                    response.error_text or str(response.payload.get('err_msg', '')),
                )

            self._account.trigger_id = int(response.payload['trigger_id'][0])
            self._account.uk = int(response.payload['uk'])
            self._account.user_id = int(response.payload.get('bd_uid') or self._account.user_id)
            self._account.bduk = protocol.user_id2bduk(self._account.user_id)
        except BaseException:
            await blcp.close()
            raise

        self._blcp = blcp

    async def _get_forum_level(self, fid):
        async with aiotieba.Client(
                account=self._account.source,
                proxy=self._legacy_proxy(),
        ) as client:
            level_info = await client.get_forum_level(fid)
            _check_response_error(level_info)
            return int(level_info.user_level)

    async def _build_at_data(self, at_user_ids):
        if not at_user_ids:
            return []

        at_data = []
        async with aiotieba.Client(
                account=self._account.source,
                proxy=self._legacy_proxy(),
        ) as client:
            for count, user_id in enumerate(at_user_ids):
                user = await client.get_user_info(
                    int(user_id),
                    aiotieba.ReqUInfo.NICK_NAME | aiotieba.ReqUInfo.PORTRAIT,
                )
                _check_response_error(user)
                at_data.append({
                    'at_type': 'user',
                    'at_baidu_uk': protocol.user_id2bduk(int(user_id)),
                    'at_name': user.nick_name,
                    'at_portrait': user.portrait,
                    'position': str(count),
                })
        return at_data

    async def _resolve_user_id(self, id_):
        if isinstance(id_, int):
            return id_
        async with aiotieba.Client(
                account=self._account.source,
                proxy=self._legacy_proxy(),
        ) as client:
            user = await client.get_user_info(id_, aiotieba.ReqUInfo.USER_ID)
            _check_response_error(user)
            return int(user.user_id)

    async def send_msg(self, id_, content):
        """发送私信。"""
        await self._ensure_private()
        user_id = await self._resolve_user_id(id_)
        local_msg_id = self._message_ids.get_local_msg_id(user_id)
        request_body = protocol.pack_send_private_msg_req(
            user_id,
            str(content),
            local_msg_id,
        )
        response_body = await self._private.send(
            request_body,
            protocol.CMD_SEND_PRIVATE_MSG,
        )
        data = protocol.parse_send_private_msg_res(response_body)

        target_user_id = data['to_user_id'] or user_id
        self._message_ids.update_local_msg_id(target_user_id, data['local_msg_id'])
        if data['group_id'] and not data['to_user_type']:
            self._message_ids.priv_gid = data['group_id']
            self._private_group_ids.add(data['group_id'])
        return SendMsgResult(
            data['group_id'],
            data['local_msg_id'],
            data['to_user_id'],
            data['to_user_type'],
            data['msg_id'],
        )

    async def get_group_msg(self, group_ids, get_type=1, from_start=False):
        """获取私信分组消息。"""
        await self._ensure_private()
        if group_ids is None:
            group_ids = [self._message_ids.priv_gid]
        group_ids = [int(group_id) for group_id in group_ids]
        if not group_ids or not all(group_ids):
            raise aiotieba.exception.TiebaValueError('private message group id is unavailable')
        msg_ids = [
            0 if from_start else self._message_ids.get_msg_id(group_id)
            for group_id in group_ids
        ]
        request_body = protocol.pack_get_group_msg_req(
            group_ids,
            msg_ids,
            get_type,
            cuid=f'{self._account.source.cuid}|com.baidu.tieba{protocol.MESSAGE_CLIENT_VERSION}',
        )
        response_body = await self._private.send(
            request_body,
            protocol.CMD_GET_GROUP_MSG,
        )
        groups = protocol.parse_get_group_msg_res(response_body)
        for group in groups:
            if int(group['group_type']) == protocol.GROUP_TYPE_PRIVATE_MSG:
                group_id = int(group['group_id'])
                self._private_group_ids.add(group_id)
                if group['messages']:
                    self._message_ids.set_msg_id(
                        group_id,
                        max(int(message['msg_id']) for message in group['messages']),
                    )
        self._track_private_groups(groups)

        return WsMsgGroups([WsMsgGroup.from_dict(group) for group in groups])

    async def set_msg_readed(self, message, group_id=None):
        """上报一条收到的私信为已读。"""
        await self._ensure_private()
        user_id = int(message.user.user_id)
        request_body = protocol.pack_set_msg_readed_req(
            user_id,
            int(group_id or self._message_ids.priv_gid),
            int(message.msg_id),
        )
        response_body = await self._private.send(
            request_body,
            protocol.CMD_SET_MSG_READED,
        )
        data = protocol.parse_set_msg_readed_res(response_body)
        target_user_id = data['to_user_id'] or user_id
        if data['read_msg_id']:
            self._message_ids.update_sent_msg_id(target_user_id, data['read_msg_id'])
        if data['group_id'] and not data['to_user_type']:
            self._message_ids.priv_gid = data['group_id']
        return SetMsgReadedResult(
            data['read_msg_id'],
            data['group_id'],
            data['to_user_id'],
            data['to_user_type'],
        )

    async def get_roomlist_by_fid(self, fid):
        """获取某个吧的所有吧群。"""
        params = protocol.sign_params([
            ('BDUSS', self._account.bduss),
            ('_client_version', protocol.MESSAGE_CLIENT_VERSION),
            ('fid', int(fid)),
        ])
        body, _ = await self._request(
            'POST',
            'https://tiebac.baidu.com/c/f/chat/getRoomListByFid',
            headers={
                'User-Agent': 'aiotieba/4.8.4',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            cookies={'BDUSS': self._account.bduss},
            data=urlencode(params).encode(),
        )
        result = json.loads(body.decode('utf-8'))
        if int(result.get('error_code', 0)):
            raise aiotieba.exception.TiebaServerError(
                int(result['error_code']),
                str(result.get('error_msg', '')),
            )

        room_list = []
        for item in (result.get('data') or {}).get('list', []):
            room_list.extend(item.get('room_list', []))
        return RoomList(room_list)

    async def get_chatroom_detail(self, chatroom_id, last_msg_id=0, last_time=0):
        """获取吧群详情。"""
        params = [
            ('_client_version', protocol.MESSAGE_CLIENT_VERSION),
            ('chatroom_id', str(int(chatroom_id))),
        ]
        if last_msg_id:
            params.append(('last_msg_id', str(int(last_msg_id))))
        if last_time:
            params.append(('last_time', str(int(last_time))))
        params = protocol.sign_params(params)

        body, _ = await self._request(
            'GET',
            'https://tiebac.baidu.com/c/f/chat/getChatRoomDetail',
            headers={
                'User-Agent': 'aiotieba/4.8.4',
                'Accept-Encoding': 'gzip',
            },
            cookies={
                'BDUSS': self._account.bduss,
                'STOKEN': self._account.stoken,
            },
            params=params,
        )
        result = json.loads(body.decode('utf-8'))
        if int(result.get('error_code', 0)):
            raise aiotieba.exception.TiebaServerError(
                int(result['error_code']),
                str(result.get('error_msg', '')),
            )

        data = result.get('data') or {}
        basic = data.get('basic_info') or {}
        extra = data.get('extra_info') or {}
        bots = (data.get('bots') or {}).get('bot_list', [])
        robots = []
        for bot in bots:
            user = bot.get('user') or {}
            bduk = str(user.get('uk', '') or '')
            try:
                user_id = protocol.bduk2user_id(bduk)
            except (ValueError, TypeError):
                user_id = 0
            skills = [
                RobotSkill(
                    int(skill.get('type', 0)),
                    str(skill.get('name', '') or ''),
                    str(skill.get('alias', '') or ''),
                    str(skill.get('desc', '') or ''),
                    bool(int(skill.get('is_show', 0))),
                    skill.get('items', []),
                )
                for skill in bot.get('skill', [])
            ]
            robots.append(Robot(
                user_id,
                str(user.get('portrait', '') or ''),
                str(user.get('name', '') or ''),
                str(user.get('name_show', '') or ''),
                bduk,
                int(user.get('robot_role', 0) or 0),
                skills,
            ))

        return ChatroomDetail(
            int(basic.get('forum_id', 0)),
            str(basic.get('forum_name', '') or ''),
            int(basic.get('id', 0)),
            str(basic.get('name', '') or ''),
            str(basic.get('avatar', '') or ''),
            str(extra.get('announce', '') or ''),
            int(basic.get('discuss_num', 0)),
            int(extra.get('talk_threshold_level', 0)),
            robots,
        )

    async def get_chatroom_msgs(self, chatroom_id):
        """获取吧群最近 60 条消息。"""
        params = protocol.sign_params([
            ('appid', str(protocol.CHAT_APPID)),
            ('mcast_id', int(chatroom_id)),
            ('msgid_end', protocol.LONG_MAX),
            ('count', -60),
            ('category', 4),
            ('app_version', protocol.MESSAGE_CLIENT_VERSION),
            ('sdk_version', protocol.CHAT_SDK_VERSION),
            ('device_id', self._account.cuid_galaxy2),
            ('timestamp', int(time.time())),
        ], salt=b'')
        body, _ = await self._request(
            'POST',
            'https://pim.baidu.com/rest/3.0/im/fetch_mcast_msg_client',
            headers={
                'Accept-Encoding': 'gzip',
                'User-Agent': 'aiotieba/4.8.4',
            },
            cookies={'BDUSS': self._account.bduss},
            json=dict(params),
        )
        result = json.loads(body.decode('utf-8'))
        if int(result.get('err_code', 0)):
            raise aiotieba.exception.TiebaServerError(
                int(result['err_code']),
                str(result.get('err_msg', '')),
            )
        return ChatroomMsgs([
            ChatroomMsg.from_json(item)
            for item in result.get('messages', [])
        ])

    async def join_chatroom(self, chatroom_id):
        """加入吧群消息通道并预取最近消息。"""
        await self._ensure_chatroom()
        response = await self._blcp.request(
            protocol.BLCP_SERVICE_MCAST,
            protocol.BLCP_METHOD_JOIN_CAST,
            {
                'method': protocol.BLCP_METHOD_JOIN_CAST,
                'mcast_id': int(chatroom_id),
                'appid': protocol.CHAT_APPID,
                'uk': self._account.uk,
            },
        )
        err_code = int(response.payload.get('err_code', 0) or 0)
        if not response.ok or err_code:
            raise aiotieba.exception.TiebaServerError(
                response.error_code or err_code,
                response.error_text or 'failed to join chatroom',
            )
        await self.get_chatroom_msgs(chatroom_id)
        return True

    async def send_chatroom_msg(
            self,
            chatroom_id,
            fid,
            text,
            at_user_ids=None,
            robot=-1,
    ):
        """向吧群发送纯文本消息。"""
        await self._ensure_chatroom()
        level = await self._get_forum_level(fid)
        at_data = await self._build_at_data(at_user_ids)
        timestamp = int(time.time())
        portrait = self._account.portrait
        user_name = self._account.nick_name or self._account.user_name

        content_text = {
            'room_id': str(int(chatroom_id)),
            'type': '0',
            'to_uid': '0',
            'vip': str(int(self._account.is_vip)),
            'name': user_name,
            'portrait': portrait + '?t=' + str(timestamp),
            'content_type': '0',
            'content_body': json.dumps({'text': str(text)}, ensure_ascii=False),
            'src': '',
            'baidu_uk': self._account.bduk,
            'ext': {},
        }

        main_data = []
        if self._account.is_vip:
            main_data.append({
                'icon': {
                    'height': 75,
                    'priority': 2,
                    'schema': 'https://tieba.baidu.com/mo/q/hybrid-business-vip/tbvip?customfullscreen=1&nonavigationbar=1',
                    'type': '1',
                    'url': 'https://tieba-ares.cdn.bcebos.com/mis/2023-7/1689061482682/13afea50121d.png',
                    'width': 75,
                },
                'type': 2,
            })

        namedata = {
            'text': {
                'short_enable': 1,
                'short_length': 5,
                'short_priority': 1,
                'priority': 1,
                'str': user_name,
                'suffix': '...',
                'type': '1',
            },
            'type': 1,
        }
        if self._account.is_vip:
            namedata['text']['text_color'] = {
                'day': 'CAM_X0301',
                'night': 'CAM_X0301',
                'type': 2,
            }
        main_data.extend((
            namedata,
            {
                'icon': {
                    'height': 15,
                    'priority': 5,
                    'schema': 'https://tieba.baidu.com/mo/q/hybrid-main-user/taskCenter?customfullscreen=1&nonavigationbar=1',
                    'type': '3',
                    'url': f'local://icon/icon_mask_level_usergrouth_{self._account.glevel}?type=webp',
                    'width': 24,
                },
                'type': 2,
            },
            {
                'icon': {
                    'height': 12,
                    'priority': 2,
                    'schema': (
                        'https://tieba.baidu.com/mo/q/wise-bawu-core/forum-level'
                        f'?customfullscreen=1&forum_id={int(fid)}&nonavigationbar=1'
                        f'&obj_locate=5&portrait={portrait}?t={timestamp}'
                    ),
                    'type': '4',
                    'url': f'local://icon/icon_level_{level:02d}?type=webp',
                    'width': 16,
                },
                'type': 2,
            },
        ))

        ext_data = {
            'main_data': main_data,
            'is_sys_msg': 0,
            'version': '',
            'portrait': portrait + '?t=' + str(timestamp),
            'robot_role': 0,
            'role': 0,
            'send_status': 0,
            'from': 'android',
            'session_id': int(chatroom_id),
            'type': 1,
            'user_name': user_name,
        }
        content_text['ext'].update(ext_data)
        content_text['ext']['content'] = (
            {}
            if int(robot) == -1
            else {'robot_params': {'scene': 'tieba_group_chat', 'type': int(robot)}}
        )
        content_text['ext']['level'] = level
        content_text['ext']['forum_id'] = int(fid)
        if at_data:
            content_text['at_data'] = at_data
        content_text['ext'] = json.dumps(content_text['ext'], ensure_ascii=False)
        content_text = json.dumps(content_text, ensure_ascii=False)

        request_data = {
            'method': protocol.BLCP_METHOD_SEND_MCAST_MSG,
            'mcast_id': int(chatroom_id),
            'role': 3,
            'token': self._account.bduss,
            'appid': protocol.CHAT_APPID,
            'uk': self._account.uk,
            'origin_id': self._account.trigger_id,
            'type': 81,
            'app_safe_ext': json.dumps(
                {'haotianjing': {'zid': self._account.zid}},
                ensure_ascii=False,
            ),
            'content': json.dumps({'text': content_text}, ensure_ascii=False),
            'msg_key': protocol.compute_msg_key(self._account.bduk),
            'account_type': 1,
            'sdk_version': protocol.CHAT_SDK_VERSION,
            'event_list': [
                {'event': 'CClickSendBegin', 'timestamp_ms': 0},
                {'event': 'CSendBegin', 'timestamp_ms': 0},
                {'event': 'CIMSendBegin', 'timestamp_ms': int(time.time() * 1000)},
            ],
            'client_logid': int(time.time() * 1_000_000),
            'rpc': '{"rpc_retry_time":0}',
        }
        response = await self._blcp.request(
            protocol.BLCP_SERVICE_MCAST,
            protocol.BLCP_METHOD_SEND_MCAST_MSG,
            request_data,
        )
        err_code = int(response.payload.get('err_code', 0) or 0)
        if not response.ok or err_code:
            raise aiotieba.exception.TiebaServerError(
                response.error_code or err_code,
                response.error_text or str(response.payload.get('msg', '')),
            )
        return True

    def get_private_message_queue(self):
        """返回私信推送队列，元素类型为 :class:`WsMsgGroups`。"""
        return self.private_message_queue

    def get_private_notification_queue(self):
        """返回私信 WebSocket 推送提示队列。"""
        if self._private is None:
            return asyncio.Queue()
        return self._private.notify_queue

    @property
    def private_group_id(self):
        """当前账号的私信消息组 ID，未完成私信初始化时为 0。"""
        return self._message_ids.priv_gid

    @property
    def private_group_ids(self):
        return sorted(self._private_group_ids)

    @property
    def user_id(self):
        return self._account.user_id

    @property
    def user_name(self):
        return self._account.nick_name or self._account.user_name

    @property
    def portrait(self):
        return self._account.portrait

    def get_chat_message_queue(self):
        """返回吧群推送队列，元素类型为 :class:`BlcpNotification`。"""
        return self._chat_message_queue


def _coerce_account(account):
    if hasattr(account, 'aiotieba_account'):
        return account.aiotieba_account
    return account


def get_message_client(account, proxy=True):
    """从 TiebaAccount、aiotieba.Account 或 BDUSS 创建消息客户端。"""
    return TiebaMessageClient(_coerce_account(account), proxy=proxy)


async def send_msg(account, id_, content, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.send_msg(id_, content)
    finally:
        await client.close()


async def get_group_msg(account, group_ids, get_type=1, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.get_group_msg(group_ids, get_type=get_type)
    finally:
        await client.close()


async def set_msg_readed(account, message, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.set_msg_readed(message)
    finally:
        await client.close()


async def get_roomlist_by_fid(account, fid, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.get_roomlist_by_fid(fid)
    finally:
        await client.close()


async def get_chatroom_detail(account, chatroom_id, last_msg_id=0, last_time=0, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.get_chatroom_detail(
            chatroom_id,
            last_msg_id=last_msg_id,
            last_time=last_time,
        )
    finally:
        await client.close()


async def get_chatroom_msgs(account, chatroom_id, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.get_chatroom_msgs(chatroom_id)
    finally:
        await client.close()


async def join_chatroom(account, chatroom_id, proxy=True):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.join_chatroom(chatroom_id)
    finally:
        await client.close()


async def send_chatroom_msg(
        account,
        chatroom_id,
        fid,
        text,
        at_user_ids=None,
        robot=-1,
        proxy=True,
):
    client = get_message_client(account, proxy=proxy)
    try:
        return await client.send_chatroom_msg(
            chatroom_id,
            fid,
            text,
            at_user_ids=at_user_ids,
            robot=robot,
        )
    finally:
        await client.close()
