"""贴吧私信与吧群消息的底层协议编解码。

该模块参照 aiotieba 4.8.x 的消息实现，但不依赖其 Python 3.10+ 类型语法。
仅处理消息链路所需的 protobuf wire 格式、WebSocket 加密和 BLCP 报文，
业务入口见 ``tieba_message_apis``。
"""
import base64
import gzip
import hashlib
import json
import random
import time
from sys import maxsize as LONG_MAX

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import aiotieba


MESSAGE_CLIENT_VERSION = '22.13.1.0'
CHAT_APPID = 10773430
CHAT_SDK_VERSION = 11250036
BLCP_SDK_VERSION = '3460016'

APP_SALT = b'tiebaclient!!!'
WS_KDF_SALT = b'\xa4\x0b\xc8\x34\xd6\x95\xf3\x13'
BLCP_FRAME_PREFIX = b'lcp\x01'

CMD_INIT_WS = 1001
CMD_GET_GROUP_MSG = 202003
CMD_SEND_PRIVATE_MSG = 205001
CMD_SET_MSG_READED = 205006

BLCP_SERVICE_LCM = 1
BLCP_SERVICE_IM = 2
BLCP_SERVICE_MCAST = 3
BLCP_SERVICE_CLOUD_CONTROL = 4

BLCP_METHOD_LOGIN = 1
BLCP_METHOD_HEARTBEAT = 3
BLCP_METHOD_LOGIN_BY_TOKEN = 50
BLCP_METHOD_SEND_MCAST_MSG = 185
BLCP_METHOD_JOIN_CAST = 201

GROUP_TYPE_PRIVATE_MSG = 6
MSG_TYPE_PRIVATE_MSG = 1
MSG_TYPE_READED = 22


class MessageProtocolError(RuntimeError):
    """消息协议数据无法解析。"""


def _encode_varint(value):
    if value < 0:
        value &= (1 << 64) - 1

    result = bytearray()
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _decode_varint(data, offset):
    value = 0
    shift = 0
    size = len(data)
    while offset < size:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            break
    raise MessageProtocolError('invalid protobuf varint')


def _varint_field(field_number, value):
    if not value:
        return b''
    return _encode_varint(field_number << 3) + _encode_varint(value)


def _raw_varint_field(field_number, value):
    return _encode_varint(field_number << 3) + _encode_varint(value)


def _bytes_field(field_number, value):
    if not value:
        return b''
    return (_encode_varint((field_number << 3) | 2)
            + _encode_varint(len(value))
            + value)


def _string_field(field_number, value):
    if not value:
        return b''
    return _bytes_field(field_number, str(value).encode('utf-8'))


def _message_field(field_number, value):
    return _bytes_field(field_number, value)


def _pack_fields(*fields):
    return b''.join(fields)


def _iter_fields(data):
    offset = 0
    size = len(data)
    while offset < size:
        key, offset = _decode_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 0x07

        if wire_type == 0:
            value, offset = _decode_varint(data, offset)
        elif wire_type == 1:
            value = data[offset:offset + 8]
            offset += 8
        elif wire_type == 2:
            length, offset = _decode_varint(data, offset)
            end = offset + length
            if end > size:
                raise MessageProtocolError('truncated protobuf field')
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            value = data[offset:offset + 4]
            offset += 4
        else:
            raise MessageProtocolError(f'unsupported protobuf wire type {wire_type}')

        if offset > size:
            raise MessageProtocolError('truncated protobuf data')
        yield field_number, wire_type, value


def _first_field(fields, field_number, default=None):
    for number, _, value in fields:
        if number == field_number:
            return value
    return default


def _all_fields(fields, field_number):
    return [value for number, _, value in fields if number == field_number]


def _parse_message(data):
    if not data:
        return []
    return list(_iter_fields(data))


def _to_text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return str(value)


def _parse_error(data):
    error_data = _first_field(_parse_message(data), 1)
    if not error_data:
        return 0, ''
    fields = _parse_message(error_data)
    return int(_first_field(fields, 1, 0)), _to_text(_first_field(fields, 2, ''))


def _raise_server_error(error_data):
    code, message = _parse_error(error_data)
    if code:
        raise aiotieba.exception.TiebaServerError(code, message)


def compute_sign(data, salt):
    """计算贴吧客户端参数签名。"""
    md5 = hashlib.md5()
    for key, value in sorted(data):
        md5.update(f'{key}={value}'.encode())
    md5.update(salt)
    return md5.hexdigest()


def sign_params(data, salt=APP_SALT):
    """为参数二元组列表追加贴吧签名。"""
    data.append(('sign', compute_sign(data, salt)))
    return data


def user_id2bduk(user_id):
    """将 user_id 转换为吧群报文使用的 baidu_uk。"""
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(str(user_id).encode()) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(b'AFD311832EDEEAEF'),
        modes.CBC(b'2011121211143000'),
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.urlsafe_b64encode(encrypted).rstrip(b'=').decode()


def bduk2user_id(bduk):
    """将吧群报文中的 baidu_uk 转换为 user_id。"""
    encrypted = base64.urlsafe_b64decode(bduk + '=' * (-len(bduk) % 4))
    decryptor = Cipher(
        algorithms.AES(b'AFD311832EDEEAEF'),
        modes.CBC(b'2011121211143000'),
    ).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return int(plain.decode())


def compute_msg_key(bduk):
    timestamp = int(time.time() * 1000) * 1000
    return bduk + str(timestamp) + str(random.randint(-LONG_MAX, LONG_MAX))


def new_correlation_id():
    return random.randint(0, LONG_MAX)


def _create_ws_cipher(ws_sec_key):
    kdf = PBKDF2HMAC(hashes.SHA1(), 32, WS_KDF_SALT, 5)
    secret_key = kdf.derive(ws_sec_key)
    return Cipher(algorithms.AES(secret_key), modes.ECB())


def pack_ws_bytes(ws_sec_key, data, cmd, req_id, compress=False, encrypt=True):
    """打包贴吧 WebSocket 消息。"""
    flag = 0x08

    if compress:
        flag |= 0x40
        data = gzip.compress(data, compresslevel=6, mtime=0)
    if encrypt:
        flag |= 0x80
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        data = padder.update(data) + padder.finalize()
        encryptor = _create_ws_cipher(ws_sec_key).encryptor()
        data = encryptor.update(data) + encryptor.finalize()

    return b''.join((
        flag.to_bytes(1, 'big'),
        cmd.to_bytes(4, 'big'),
        req_id.to_bytes(4, 'big'),
        data,
    ))


def parse_ws_bytes(ws_sec_key, data):
    """解包贴吧 WebSocket 消息，返回 (body, cmd, req_id)。"""
    if len(data) < 9:
        raise MessageProtocolError('truncated websocket message')

    view = memoryview(data)
    flag = view[0]
    cmd = int.from_bytes(view[1:5], 'big')
    req_id = int.from_bytes(view[5:9], 'big')
    body = view[9:].tobytes()

    if flag & 0x80:
        decryptor = _create_ws_cipher(ws_sec_key).decryptor()
        body = decryptor.update(body) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        body = unpadder.update(body) + unpadder.finalize()
    if flag & 0x40:
        body = gzip.decompress(body)
    return body, cmd, req_id


def pack_update_client_info_req(bduss, device, secret_key, stoken='', cuid=''):
    data = _pack_fields(
        _string_field(1, bduss),
        _string_field(2, json.dumps(device, ensure_ascii=False, separators=(',', ':'))),
        _bytes_field(3, secret_key),
        _string_field(12, stoken),
    )
    return _pack_fields(
        _string_field(1, cuid),
        _message_field(2, data),
    )


def parse_update_client_info_res(data):
    _raise_server_error(data)
    root = _parse_message(data)
    data_fields = _parse_message(_first_field(root, 2, b''))

    groups = []
    for item in _all_fields(data_fields, 1):
        fields = _parse_message(item)
        groups.append({
            'group_id': int(_first_field(fields, 1, 0)),
            'group_type': int(_first_field(fields, 20, 0)),
            'last_msg_id': int(_first_field(fields, 21, 0)),
        })

    user_fields = _parse_message(_first_field(data_fields, 2, b''))
    user = {
        'user_id': int(_first_field(user_fields, 1, 0)),
        'user_name': _to_text(_first_field(user_fields, 2, '')),
        'portrait': _to_text(_first_field(user_fields, 4, '')).split('?', 1)[0],
    }
    return {
        'groups': groups,
        'user': user,
        'is_user_available': int(_first_field(data_fields, 6, 0)),
    }


def pack_send_private_msg_req(user_id, content, local_msg_id):
    data = _pack_fields(
        _varint_field(2, user_id),
        _varint_field(3, MSG_TYPE_PRIVATE_MSG),
        _string_field(4, content),
        _varint_field(6, local_msg_id),
    )
    return _message_field(1, data)


def parse_send_private_msg_res(data):
    _raise_server_error(data)
    root = _parse_message(data)
    fields = _parse_message(_first_field(root, 2, b''))

    block_fields = _parse_message(_first_field(fields, 6, b''))
    block_code = int(_first_field(block_fields, 1, 0))
    if block_code:
        raise aiotieba.exception.TiebaServerError(
            block_code,
            _to_text(_first_field(block_fields, 2, '')),
        )

    result = {
        'msg_id': int(_first_field(fields, 1, 0)),
        'group_id': int(_first_field(fields, 2, 0)),
        'local_msg_id': int(_first_field(fields, 3, 0)),
        'to_user_id': int(_first_field(fields, 4, 0)),
        'to_user_type': int(_first_field(fields, 5, 0)),
    }
    if not result['msg_id']:
        raise aiotieba.exception.TiebaValueError('msgId is 0')
    return result


def pack_set_msg_readed_req(user_id, group_id, msg_id):
    data = _pack_fields(
        _varint_field(1, group_id),
        _varint_field(2, user_id),
        _varint_field(3, MSG_TYPE_READED),
        _varint_field(4, msg_id),
    )
    return _message_field(1, data)


def parse_set_msg_readed_res(data):
    _raise_server_error(data)
    root = _parse_message(data)
    fields = _parse_message(_first_field(root, 2, b''))
    return {
        'read_msg_id': int(_first_field(fields, 1, 0)),
        'group_id': int(_first_field(fields, 2, 0)),
        'to_user_id': int(_first_field(fields, 3, 0)),
        'to_user_type': int(_first_field(fields, 4, 0)),
    }


def pack_get_group_msg_req(group_ids, msg_ids, get_type, cuid=''):
    groups = []
    for group_id, msg_id in zip(group_ids, msg_ids):
        group = _pack_fields(
            _varint_field(1, int(group_id)),
            _varint_field(2, int(msg_id)),
        )
        groups.append(_message_field(6, group))

    data = _pack_fields(
        *groups,
        _string_field(7, str(get_type)),
    )
    return _pack_fields(
        _string_field(1, cuid),
        _message_field(2, data),
    )


def parse_get_group_msg_res(data):
    _raise_server_error(data)
    root = _parse_message(data)
    data_fields = _parse_message(_first_field(root, 2, b''))

    groups = []
    for group_item in _all_fields(data_fields, 1):
        group_fields = _parse_message(group_item)
        group_info = _parse_message(_first_field(group_fields, 1, b''))
        group_id = int(_first_field(group_info, 1, 0))
        if not group_id:
            continue

        messages = []
        for msg_item in _all_fields(group_fields, 2):
            msg_fields = _parse_message(msg_item)
            user_fields = _parse_message(_first_field(msg_fields, 10, b''))
            messages.append({
                'msg_id': int(_first_field(msg_fields, 1, 0)),
                'msg_type': int(_first_field(msg_fields, 3, 0)),
                'text': _to_text(_first_field(msg_fields, 5, '')),
                'create_time': int(_first_field(msg_fields, 8, 0)),
                'user': {
                    'user_id': int(_first_field(user_fields, 1, 0)),
                    'user_name': _to_text(_first_field(user_fields, 2, '')),
                    'portrait': _to_text(
                        _first_field(user_fields, 4, '')
                    ).split('?', 1)[0],
                },
            })

        groups.append({
            'group_id': group_id,
            'group_type': int(_first_field(group_info, 20, 0)),
            'messages': messages,
        })
    return groups


def pack_rpc_request(service_id, method_id, body=b'', correlation_id=None, event='CLCPReqBegin'):
    if correlation_id is None:
        correlation_id = new_correlation_id()

    events = b''
    if event:
        event_fields = _pack_fields(
            _string_field(1, event),
            _varint_field(2, int(time.time() * 1000)),
        )
        events = _message_field(5, event_fields)

    request_meta = _pack_fields(
        _varint_field(1, service_id),
        _varint_field(2, method_id),
        _varint_field(3, correlation_id),
        _varint_field(4, 1),
        events,
    )
    header = _pack_fields(
        _message_field(1, request_meta),
        _raw_varint_field(3, 0),
        _varint_field(4, correlation_id),
        _varint_field(9, 1),
    )
    return header, body, correlation_id


def encode_blcp_frame(header, body):
    total_len = len(header) + len(body)
    return b''.join((
        BLCP_FRAME_PREFIX,
        total_len.to_bytes(4, 'big'),
        len(header).to_bytes(4, 'big'),
        header,
        body,
    ))


def parse_rpc_meta(data):
    fields = _parse_message(data)
    if _first_field(fields, 2) is not None:
        response = _parse_message(_first_field(fields, 2, b''))
        return {
            'meta_type': 2,
            'service_id': int(_first_field(response, 1, 0)),
            'method_id': int(_first_field(response, 2, 0)),
            'log_id': int(_first_field(response, 3, 0)),
            'error_code': int(_first_field(response, 4, 0)),
            'error_text': _to_text(_first_field(response, 5, '')),
        }
    if _first_field(fields, 8) is not None:
        notify = _parse_message(_first_field(fields, 8, b''))
        return {
            'meta_type': 3,
            'service_id': int(_first_field(notify, 1, 0)),
            'method_id': int(_first_field(notify, 2, 0)),
            'log_id': int(_first_field(notify, 3, 0)),
        }
    request = _parse_message(_first_field(fields, 1, b''))
    return {
        'meta_type': 1,
        'service_id': int(_first_field(request, 1, 0)),
        'method_id': int(_first_field(request, 2, 0)),
        'log_id': int(_first_field(request, 3, 0)),
    }


def _extract_rpc_meta(data):
    fields = _parse_message(data)
    meta = parse_rpc_meta(data)
    meta['correlation_id'] = int(_first_field(fields, 4, 0))
    meta['compress_type'] = int(_first_field(fields, 3, 0))
    return meta


def pack_lcm_login_req(token, correlation_id, cuid, device='android'):
    common = _pack_fields(
        _string_field(1, cuid),
        _string_field(2, device),
        _string_field(6, str(CHAT_APPID)),
        _string_field(7, MESSAGE_CLIENT_VERSION),
        _string_field(8, BLCP_SDK_VERSION),
        _string_field(9, 'wifi'),
    )
    lcm_request = _pack_fields(
        _varint_field(1, correlation_id),
        _string_field(2, token),
        _message_field(3, common),
        _varint_field(4, int(time.time() * 1000)),
        _varint_field(6, -1),
        _varint_field(7, 1),
    )
    return _message_field(1, lcm_request)


def pack_lcm_heartbeat_req(correlation_id):
    lcm_request = _pack_fields(
        _varint_field(1, correlation_id),
        _varint_field(4, int(time.time() * 1000)),
    )
    return _message_field(1, lcm_request)


def parse_lcm_response(data):
    fields = _parse_message(data)
    response = _parse_message(_first_field(fields, 2, b''))
    return {
        'log_id': int(_first_field(response, 1, 0)),
        'error_code': int(_first_field(response, 2, 0)),
        'error_msg': _to_text(_first_field(response, 3, '')),
        'next_interval_ms': int(_first_field(response, 4, 0)),
        'server_info': _to_text(_first_field(response, 5, '')),
    }


def parse_json_body(data):
    if not data:
        return {}
    return json.loads(data.decode('utf-8'))


def encode_json_body(data):
    return json.dumps(data, ensure_ascii=False).encode('utf-8')
