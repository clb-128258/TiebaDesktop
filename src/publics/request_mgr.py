"""
HTTP 同步请求模块，主要用于贴吧 API
"""
import requests
import consts
import hashlib
import enum
import json
import time
import datetime

from publics import profile_mgr, funcs

# 保留变量以便向下兼容
SCHEME_HTTP = consts.SCHEME_HTTP
SCHEME_HTTPS = consts.SCHEME_HTTPS
TIEBA_APP_HOST = consts.TIEBA_APP_HOST
TIEBA_WEB_HOST = consts.TIEBA_WEB_HOST
TIEBA_CLIENT_VERSION = consts.TIEBA_CLIENT_VERSION

header = consts.http_header
header_android = consts.http_header_android
header_protobuf = consts.http_header_protobuf


class TiebaClientType(enum.IntEnum):
    """贴吧客户端类型"""
    IPHONE = 1  # ios版客户端
    ANDROID = 2  # 安卓客户端

    def __str__(self):
        return str(self.value)


def is_ssl_required():
    """是否需要使用 SSL 验证"""
    need_verify = funcs.get_dict_value_treely(profile_mgr.local_config,
                                              ['other_settings', 'disable_ssl_verify'],
                                              False)
    return not need_verify


def generate_sign_key(str_dict: dict, key: str = 'tiebaclient!!!'):
    """计算贴吧表单签名"""
    form_content = ''
    for k, v in str_dict.items():
        form_content += f'{k}={v}'
    form_content += key
    md5_key = hashlib.md5(form_content.encode()).hexdigest().upper()

    return md5_key


def calc_sign(str_dict: dict):
    """生成待提交数据的手机端签名，并把签名添加到表单字典中"""
    signkey = generate_sign_key(str_dict, 'tiebaclient!!!')
    str_dict['sign'] = signkey
    return str_dict


def get_chat_common_params(account):
    """
    构造手机客户端公共请求字段

    Args:
        account (account_mgr.TiebaAccount): 账号实例
    """
    aiotieba_account = account.aiotieba_account
    timestamp = int(time.time() * 1000)
    event_day = datetime.datetime.now().strftime('%Y%m%d')

    return {
        '_client_id': str(aiotieba_account.client_id or ''),
        'subapp_type': 'hybrid',
        'from': '1008550l',
        'net_type': '1',
        'cuid': str(aiotieba_account.cuid or ''),
        'cuid_galaxy2': str(aiotieba_account.cuid_galaxy2 or ''),
        'c3_aid': str(aiotieba_account.c3_aid or ''),
        'cuid_gid': '',
        'timestamp': str(timestamp),
        'z_id': str(aiotieba_account.z_id or ''),
        'sample_id': str(aiotieba_account.sample_id or ''),
        'android_id': str(aiotieba_account.android_id or ''),
        'cmode': '1',
        'is_teenager': '0',
        'start_type': '1',
        'start_scheme': '',
        'scr_w': '900',
        'scr_h': '1600',
        'scr_dip': '1.5',
        'q_type': '0',
        'event_day': event_day,
    }


def run_get_api(api: str,
                bduss='',
                encoding='',
                stoken: str = '',
                cookies: dict = None,
                return_json=True,
                params: dict = None,
                use_mobile_header=False,
                host_type: int = 1,
                use_https: bool = True,
                host_name: str = ''):
    """
    执行GET请求

    Args:
        api (str): 欲请求的接口地址
        bduss (str): BDUSS，该字段可以为空
        encoding (str): 报文编码类型
        stoken (str): STOKEN，该字段可以为空
        cookies (dict): 要传入请求的cookies字典，该参数会覆盖前面的bduss和stoken参数
        return_json (bool): 是否将报文作为json文本解析，当此项为True时返回解析后的json字典，为False时返回编码后的报文文本
        params (dict): url参数字典
        use_mobile_header (bool): 是否使用手机版header进行请求
        host_type (int): 欲请求的接口类型 1为web端，2为手机端
        use_https (bool): 是否使用https请求
        host_name (str): 可选的请求域名，留空时按 host_type 选择
    """
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = host_name or (TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST)
    final_header = header_android if use_mobile_header else header
    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}

    session = requests.Session()
    session.trust_env = True
    session.verify = is_ssl_required()

    response = session.get(f'{scheme}{host_name}{api}',
                           headers=final_header,
                           cookies=cookie,
                           params=params,
                           timeout=consts.HTTP_TIMEOUT)

    if encoding:
        response.encoding = encoding
    response.raise_for_status()
    content = response.content
    text = response.text
    response.close()
    session.close()

    if return_json:
        return json.loads(content)
    else:
        return text


def run_post_api(api: str,
                 payloads: dict = None,
                 bduss='',
                 encoding='',
                 stoken: str = '',
                 cookies: dict = None,
                 return_json=True,
                 params: dict = None,
                 use_mobile_header=False,
                 host_type: int = 1,
                 use_https: bool = True,
                 host_name: str = '',
                 json_payload: dict = None):
    """
    执行POST请求

    Args:
        api (str): 欲请求的接口地址
        payloads (dict): post请求提交的表单数据字典
        bduss (str): BDUSS，该字段可以为空
        encoding (str): 报文编码类型
        stoken (str): STOKEN，该字段可以为空
        cookies (dict): 要传入请求的cookies字典，该参数会覆盖前面的bduss和stoken参数
        return_json (bool): 是否将报文作为json文本解析，当此项为True时返回解析后的json字典，为False时返回编码后的报文文本
        params (dict): url参数字典
        use_mobile_header (bool): 是否使用手机版header进行请求
        host_type (int): 欲请求的接口类型 1为web端，2为手机端
        use_https (bool): 是否使用https请求
        host_name (str): 可选的请求域名，留空时按 host_type 选择
        json_payload (dict): 需要发送JSON请求体时传入，此时忽略payloads
    """
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = host_name or (TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST)
    final_header = header_android if use_mobile_header else header
    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}

    session = requests.Session()
    session.trust_env = True
    session.verify = is_ssl_required()

    if json_payload is not None:
        request_data = json.dumps(
            json_payload,
            ensure_ascii=False,
            separators=(',', ':'),
        ).encode('utf-8')
        final_header = dict(final_header)
        final_header['Content-Type'] = 'application/json'
    else:
        request_data = payloads
    response = session.post(f'{scheme}{host_name}{api}',
                            headers=final_header,
                            cookies=cookie,
                            params=params,
                            data=request_data,
                            timeout=consts.HTTP_TIMEOUT)

    if encoding:
        response.encoding = encoding
    response.raise_for_status()
    content = response.content
    text = response.text
    response.close()
    session.close()

    if return_json:
        return json.loads(content)
    else:
        return text


def run_post_api_capture_cookies(api: str,
                                 payloads: dict,
                                 bduss='',
                                 encoding='',
                                 stoken: str = '',
                                 cookies: dict = None,
                                 return_json=True,
                                 params: dict = None,
                                 use_mobile_header=False,
                                 host_type: int = 1,
                                 use_https: bool = True,
                                 host_name: str = ''):
    """
    执行POST请求\n
    并同时返回响应 Cookie

    Notes:
        用法同 run_post_api()
    """
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = host_name or (TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST)
    final_header = header_android if use_mobile_header else header
    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}

    session = requests.Session()
    session.trust_env = True
    session.verify = is_ssl_required()

    response = session.post(f'{scheme}{host_name}{api}',
                            headers=final_header,
                            cookies=cookie,
                            params=params,
                            data=payloads,
                            timeout=consts.HTTP_TIMEOUT)

    if encoding:
        response.encoding = encoding
    response.raise_for_status()
    content = response.content
    response_cookies = session.cookies.get_dict()
    response_cookies.update(response.cookies.get_dict())
    response.close()
    session.close()

    result = json.loads(content) if return_json else content.decode(
        encoding or 'utf-8'
    )
    return result, response_cookies


def run_protobuf_api(api: str,
                     payloads: bytes,
                     cmd_id: int,
                     bduss='',
                     stoken: str = '',
                     cookies: dict = None,
                     host_type: int = 1,
                     use_https: bool = True):
    """
    执行protobuf格式的POST请求

    Args:
        api (str): 欲请求的接口地址
        payloads (bytes): 已序列化的protobuf二进制数据
        cmd_id (int): websocket指令号码
        bduss (str): BDUSS，该字段可以为空
        stoken (str): STOKEN，该字段可以为空
        cookies (dict): 要传入请求的cookies字典，该参数会覆盖前面的bduss和stoken参数
        host_type (int): 欲请求的接口类型 1为web端，2为手机端
        use_https (bool): 是否使用https请求
    Return:
        已序列化的protobuf二进制数据
    """

    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST
    final_header = header_protobuf
    params = {'cmd': str(cmd_id), 'format': 'protobuf'}
    data = {
        'data': ('file', payloads)
    }

    session = requests.Session()
    session.trust_env = True
    session.verify = is_ssl_required()

    response = session.post(f'{scheme}{host_name}{api}',
                            headers=final_header,
                            cookies=cookie,
                            params=params,
                            files=data,
                            timeout=consts.HTTP_TIMEOUT)

    response.raise_for_status()
    response.close()
    session.close()

    return response.content
