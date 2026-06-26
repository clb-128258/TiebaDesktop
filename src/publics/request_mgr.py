"""百度贴吧同步请求模块"""
import requests
import consts
import hashlib
import enum

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


def run_get_api(api: str,
                bduss='',
                encoding='',
                stoken: str = '',
                cookies: dict = None,
                return_json=True,
                params: dict = None,
                use_mobile_header=False,
                host_type: int = 1,
                use_https: bool = True):
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
    """
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST
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
    response.close()
    session.close()

    if return_json:
        return response.json()
    else:
        return response.text


def run_post_api(api: str,
                 payloads: dict,
                 bduss='',
                 encoding='',
                 stoken: str = '',
                 cookies: dict = None,
                 return_json=True,
                 params: dict = None,
                 use_mobile_header=False,
                 host_type: int = 1,
                 use_https: bool = True):
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
    """
    scheme = SCHEME_HTTPS if use_https else SCHEME_HTTP
    host_name = TIEBA_WEB_HOST if host_type == 1 else TIEBA_APP_HOST
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
    response.close()
    session.close()

    if return_json:
        return response.json()
    else:
        return response.text


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
