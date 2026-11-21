"""
贴吧群聊天数据的业务解析
"""
import json
import aiotieba

from publics.baidu_features.chats.network import tieba_message_protocol as protocol
from publics.baidu_features.chats.structs.models import normalize_chatroom_room

CHATROOM_INVALID_MSG_TYPES = [101]


def json_value(value, default):
    if isinstance(value, (dict, list)):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _decode_response(content):
    if isinstance(content, dict):
        return content
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError as error:
            raise aiotieba.exception.TiebaValueError(
                '聊天接口返回了无效 JSON'
            ) from error
    if not isinstance(content, dict):
        raise aiotieba.exception.TiebaValueError(
            '聊天接口返回结构不是 JSON 对象'
        )
    return content


def _raise_response_error(result):
    code = result.get(
        'error_code',
        result.get('err_code', result.get('error', 0)),
    )
    try:
        code = int(code or 0)
    except (TypeError, ValueError):
        code = 0
    if code:
        message = (
                result.get('error_msg')
                or result.get('err_msg')
                or result.get('msg')
                or ''
        )
        raise aiotieba.exception.TiebaServerError(code, str(message))
    return result


def _collect_room_items(value):
    """递归提取不同版本群列表响应中的群条目。"""
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_collect_room_items(item))
        return result
    if not isinstance(value, dict):
        return []

    room_info = value.get('room_info')
    room_id = (
            value.get('room_id')
            or (room_info or {}).get('room_id')
            or (room_info or {}).get('id')
    )
    if room_id and (
            isinstance(room_info, dict)
            or value.get('msg_info')
            or value.get('name')
    ):
        return [value]

    result = []
    for key in (
            'list',
            'room_list',
            'rooms',
            'subscribe_list',
            'subscribed_list',
    ):
        if key in value:
            result.extend(_collect_room_items(value[key]))
    if result:
        return result
    for item in value.values():
        if isinstance(item, (dict, list)):
            result.extend(_collect_room_items(item))
    return result


def parse_chat_subscription_list(content):
    from publics.baidu_features.chats.tieba_message_apis import RoomList

    result = _raise_response_error(_decode_response(content))
    rooms = [
        normalize_chatroom_room(room)
        for room in _collect_room_items(result.get('data') or {})
    ]
    return RoomList([room for room in rooms if room['room_id']])


def parse_chatroom_subscription_operation(content):
    return _raise_response_error(_decode_response(content))


def parse_roomlist_by_fid(content, default_fid=0):
    from publics.baidu_features.chats.tieba_message_apis import RoomList

    result = _raise_response_error(_decode_response(content))
    rooms = [
        normalize_chatroom_room(room, default_fid=default_fid)
        for room in _collect_room_items(result.get('data') or {})
    ]
    return RoomList([room for room in rooms if room['room_id']])


def parse_chatroom_detail(content):
    from publics.baidu_features.chats.tieba_message_apis import (
        ChatroomDetail,
        Robot,
        RobotSkill,
    )

    result = _raise_response_error(_decode_response(content))
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


def parse_chatroom_msgs(content):
    from publics.baidu_features.chats.structs.data_classes import (
        ChatroomMsg,
        ChatroomMsgs,
    )

    result = _raise_response_error(_decode_response(content))
    return ChatroomMsgs([
        ChatroomMsg.from_json(item)
        for item in result.get('messages', [])
    ])


def parse_lcm_token(content):
    result = _raise_response_error(_decode_response(content))
    token = result.get('token') or (result.get('data') or {}).get('token')
    if not token:
        raise aiotieba.exception.TiebaValueError('Missing LCM token')
    return token


def parse_message_content(content):
    if not isinstance(content, dict):
        return {}, {}
    text_data = content.get('text', {})
    if isinstance(text_data, str):
        try:
            text_data = json.loads(text_data)
        except ValueError:
            text_data = {}
    if not isinstance(text_data, dict):
        return {}, {}
    ext = text_data.get('ext', {})
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except ValueError:
            ext = {}
    return text_data, ext if isinstance(ext, dict) else {}


def parse_image_size(value):
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


def bduk_to_user_id(value):
    bduk = str(value or '')
    if not bduk:
        return 0
    try:
        return protocol.bduk2user_id(bduk)
    except (TypeError, ValueError):
        return 0


def get_message_text(value):
    """从消息 body 或嵌套 JSON 中提取纯文本"""
    value = json_value(value, value)
    if isinstance(value, str):
        parsed = json_value(value, None)
        if isinstance(parsed, (dict, list)):
            return get_message_text(parsed)
        return value
    if isinstance(value, dict):
        body = value.get('content_body') or value.get('re_content_body')
        if body is not None:
            return get_message_text(body)
        text = value.get('text')
        if isinstance(text, (dict, list)):
            return get_message_text(text)
        return str(text or '')
    return ''
