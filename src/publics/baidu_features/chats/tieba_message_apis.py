"""贴吧私信与吧群消息 API"""
import asyncio
import time

from aiotieba.config import ProxyConfig
from aiotieba.helper.crypto import enuid
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_der_public_key

from publics.baidu_features import tieba_apis as chat_http
from publics.baidu_features.chats.structs import chatroom_data_parser as chat_http_parsers
from publics.baidu_features.chats.network.tieba_message_network import (
    MessageConnectionError,
    PrivateMessageConnection,
    BlcpConnection,
)
from publics.baidu_features.chats.structs.data_classes import *
from publics.baidu_features.chats.network.tieba_message_protocol import WS_PUBLIC_KEY


def _check_response_error(result):
    error = getattr(result, 'err', None)
    if error is not None:
        raise error
    return result


async def _run_sync_http(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


class TiebaMessageClient:
    """可复用的贴吧私信与吧群消息客户端"""

    def __init__(self, account, proxy=True):
        if isinstance(account, str):
            account = aiotieba.Account(account)
        if not isinstance(account, aiotieba.Account):
            raise TypeError('account 必须是 aiotieba.Account 或 BDUSS 字符串')

        self._account = PrivateMessageAccount(account)
        self._proxy = proxy
        self._private = None
        self._blcp = None
        self._chat_message_queue = asyncio.Queue(maxsize=100)
        self._private_forwarder = None
        self._message_ids = PrivateMsgIDManager()
        self._private_group_ids = set()
        self._is_closed = False
        self.private_message_queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, exc_tb=None):
        await self.close()

    async def start(self, private=True, chatroom=True):
        """
        初始化连接
        未调用时各方法也会按需初始化

        Args:
            private (bool): 是否初始化私信连接
            chatroom (bool): 是否初始化聊天室 BLCP 连接
        """
        if private:
            await self._ensure_private()
        if chatroom:
            await self._ensure_chatroom()

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

    async def _stop_private_forwarder(self):
        if self._private_forwarder is None:
            return
        self._private_forwarder.cancel()
        try:
            await self._private_forwarder
        except asyncio.CancelledError:
            pass
        self._private_forwarder = None

    def _legacy_proxy(self):
        if isinstance(self._proxy, str):
            return ProxyConfig(self._proxy)
        return self._proxy

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
            rsa_cipher = load_der_public_key(WS_PUBLIC_KEY)
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
                content = json_value(message['text'], {})
                if content.get('eventId') != 22001:
                    continue
                read_msg_id = content.get('eventParam', {}).get('readMsgId', 0)
                if read_msg_id:
                    self._message_ids.update_read_msg_id(user_id, int(read_msg_id))

    async def _get_lcm_token(self):
        content = await _run_sync_http(
            chat_http.get_lcm_token,
            self._account.cuid_galaxy2,
        )
        return chat_http_parsers.parse_lcm_token(content)

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
        content = await _run_sync_http(
            chat_http.get_roomlist_by_fid,
            self._account.bduss,
            self._account.stoken,
            int(fid),
        )
        return chat_http_parsers.parse_roomlist_by_fid(content, default_fid=fid)

    async def get_chatroom_detail(self, chatroom_id, last_msg_id=0, last_time=0):
        """获取吧群详情"""
        content = await _run_sync_http(
            chat_http.get_chatroom_detail,
            self._account.bduss,
            self._account.stoken,
            int(chatroom_id),
            last_msg_id,
            last_time,
        )
        return chat_http_parsers.parse_chatroom_detail(content)

    async def get_chatroom_msgs(
            self,
            chatroom_id,
            count=-60,
            msgid_end=protocol.LONG_MAX,
    ):
        """获取吧群消息"""
        content = await _run_sync_http(
            chat_http.get_chatroom_msgs,
            self._account.bduss,
            self._account.stoken,
            self._account.cuid_galaxy2,
            int(chatroom_id),
            count,
            msgid_end,
        )
        return chat_http_parsers.parse_chatroom_msgs(content)

    @staticmethod
    def _check_mcast_response(response, action):
        err_code = int(response.payload.get('err_code', 0) or 0)
        if not response.ok or err_code:
            raise aiotieba.exception.TiebaServerError(
                response.error_code or err_code,
                response.error_text or f'failed to {action}',
            )
        return response.payload

    async def join_chatroom_group(self, chatroom_id):
        """加入贴吧吧群分组，与官方客户端保持一致。"""
        await self._ensure_chatroom()
        response = await self._blcp.request(
            protocol.BLCP_SERVICE_MCAST,
            protocol.BLCP_METHOD_JOIN_CHATROOM_GROUP,
            {
                'method': protocol.BLCP_METHOD_JOIN_CHATROOM_GROUP,
                'appid': protocol.CHAT_APPID,
                'app_version': protocol.MESSAGE_CLIENT_VERSION,
                'sdk_version': protocol.CHAT_SDK_VERSION,
                'device_id': self._account.cuid_galaxy2,
                'uk': self._account.uk,
                'room_type': protocol.TIEBA_CHATROOM_ROOM_TYPE,
                'batch_type': protocol.TIEBA_CHATROOM_BATCH_TYPE,
                'chatroom_group_id': protocol.TIEBA_CHATROOM_GROUP_ID,
            },
        )
        return self._check_mcast_response(response, 'join chatroom group')

    async def join_chatroom(self, chatroom_id):
        """加入吧群分组和具体消息通道。"""
        await self._ensure_chatroom()
        await self.join_chatroom_group(chatroom_id)
        response = await self._blcp.request(
            protocol.BLCP_SERVICE_MCAST,
            protocol.BLCP_METHOD_JOIN_CAST,
            {
                'method': protocol.BLCP_METHOD_JOIN_CAST,
                'mcast_id': int(chatroom_id),
                'appid': protocol.CHAT_APPID,
                'uk': self._account.uk,
                'origin_id': self._account.trigger_id,
                'msg_key': protocol.new_cast_msg_key(),
                'sdk_version': protocol.CHAT_SDK_VERSION,
                'is_reliable': False,
            },
        )
        return self._check_mcast_response(response, 'join chatroom')

    async def send_chatroom_msg(
            self,
            chatroom_id,
            fid,
            text,
            at_user_ids=None,
            robot=-1,
    ):
        """向吧群发送消息"""
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

    @property
    def is_chatroom_connected(self):
        return self._blcp is not None and self._blcp.is_open

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
