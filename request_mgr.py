"""百度贴吧同步请求模块"""
import requests
import consts
from aiotieba.helper.crypto import _sign

header = {
    'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 CLBTiebaDesktop/{consts.APP_VERSION_STR}',
    'sec-ch-ua': "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\"",
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': "\"Windows\"",
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    'Accept-Encoding': "gzip, deflate, br, zstd",
    'Accept': '*/*',
    'Connection': 'close',
    'x-requested-with': 'XMLHttpRequest'
}
header_android = {
    'User-Agent': f"Mozilla/5.0 (Linux; Android 12; PFGM00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36 tieba/12.87.1.1 skin/default CLBTiebaDesktop/{consts.APP_VERSION_STR}",
    'Accept': "application/json, text/plain, */*",
    'Accept-Encoding': "gzip, deflate",
    'x-requested-with': "XMLHttpRequest",
    'Subapp-Type': "hybrid",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}
header_protobuf = {
    'User-Agent': f"Mozilla/5.0 (Linux; Android 12; PFGM00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36 tieba/12.87.1.1 skin/default CLBTiebaDesktop/{consts.APP_VERSION_STR}",
    'Accept': "*/*",
    'Accept-Encoding': "gzip, deflate",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "x_bd_data_type": "protobuf"
}
SCHEME_HTTP = 'http://'
SCHEME_HTTPS = 'https://'
TIEBA_APP_HOST = 'tiebac.baidu.com'
TIEBA_WEB_HOST = 'tieba.baidu.com'
TIEBA_CLIENT_VERSION = '12.91.1.0'


def calc_sign(str_dict: dict):
    """生成待提交数据的签名，并把签名添加到表单字典中"""
    sign_list_adp = []
    for k, v in str_dict.items():
        sign_list_adp.append((str(k), str(v)))
    sign = _sign(sign_list_adp)  # 贴吧签名的实现较为复杂，因此这里直接调用aiotieba的
    str_dict['sign'] = sign
    return str_dict


def get_sign(str_dict: dict):
    """计算并返回待提交数据的签名"""
    sign_list_adp = []
    for k, v in str_dict.items():
        sign_list_adp.append((str(k), str(v)))
    sign = _sign(sign_list_adp)  # 贴吧签名的实现较为复杂，因此这里直接调用aiotieba的
    return sign


def run_get_api(api: str, bduss='', encoding='', stoken: str = '', cookies: dict = None, return_json=True,
                params: dict = None, use_mobile_header=False, host_type: int = 1, use_https: bool = False):
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
        use_mobile_header (bool): 是否使用手机版header进行请求 (安卓版贴吧 12.87.1.1)
        host_type (int): 欲请求的接口类型 1为web端，2为手机端
        use_https (bool): 是否使用https请求
    """
    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}

    if use_mobile_header:
        final_header = header_android
    else:
        final_header = header
    session = requests.Session()
    session.trust_env = True
    host_name = ''
    if host_type == 1:
        host_name = TIEBA_WEB_HOST
    elif host_type == 2:
        host_name = TIEBA_APP_HOST
    if use_https:
        scheme = SCHEME_HTTPS
    else:
        scheme = SCHEME_HTTP
    response = session.get(f'{scheme}{host_name}{api}',
                           headers=final_header,
                           cookies=cookie, params=params)
    if encoding:
        response.encoding = encoding
    response.raise_for_status()
    session.close()
    if return_json:
        return response.json()
    else:
        return response.text


def run_post_api(api: str, payloads: dict, bduss='', encoding='', stoken: str = '', cookies: dict = None,
                 return_json=True,
                 params: dict = None, use_mobile_header=False, host_type: int = 1, use_https: bool = False):
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
        use_mobile_header (bool): 是否使用手机版header进行请求 (安卓版贴吧 12.87.1.1)
        host_type (int): 欲请求的接口类型 1为web端，2为手机端
        use_https (bool): 是否使用https请求
    """
    if cookies:
        cookie = cookies
    elif bduss:
        cookie = {'BDUSS': bduss, 'STOKEN': stoken}
    else:
        cookie = {}

    if use_mobile_header:
        final_header = header_android
    else:
        final_header = header
    session = requests.Session()
    session.trust_env = True
    host_name = ''
    if host_type == 1:
        host_name = TIEBA_WEB_HOST
    elif host_type == 2:
        host_name = TIEBA_APP_HOST
    if use_https:
        scheme = SCHEME_HTTPS
    else:
        scheme = SCHEME_HTTP

    response = session.post(f'{scheme}{host_name}{api}',
                            headers=final_header,
                            cookies=cookie, params=params, data=payloads)
    if encoding:
        response.encoding = encoding
    response.raise_for_status()
    session.close()
    if return_json:
        return response.json()
    else:
        return response.text


def run_protobuf_api(api: str, payloads: bytes, cmd_id: int, bduss='', stoken: str = '', cookies: dict = None,
                     host_type: int = 1, use_https: bool = False):
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

    if use_mobile_header:
        final_header = header_android
    else:
        final_header = header

    params = {'cmd': str(cmd_id), 'format': 'protobuf'}

    host_name = ''
    if host_type == 1:
        host_name = TIEBA_WEB_HOST
    elif host_type == 2:
        host_name = TIEBA_APP_HOST
    if use_https:
        scheme = SCHEME_HTTPS
    else:
        scheme = SCHEME_HTTP
    data = {
        'data': ('file', payloads)
    }

    session = requests.Session()
    session.trust_env = True
    response = session.post(f'{scheme}{host_name}{api}',
                            headers=final_header,
                            cookies=cookie,
                            params=params,
                            files=data)
    response.raise_for_status()
    session.close()

    return response.content
