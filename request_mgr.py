"""百度贴吧同步请求模块"""
import requests
import hashlib

requests.session().trust_env = True
requests.session().verify = False
header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
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
    'User-Agent': "Mozilla/5.0 (Linux; Android 12; PFGM00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36 tieba/12.87.1.1 skin/default",
    'Accept': "application/json, text/plain, */*",
    'Accept-Encoding': "gzip, deflate",
    'x-requested-with': "XMLHttpRequest",
    'Subapp-Type': "hybrid",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}
MD5_KEY = 'tiebaclient!!!'


def calc_sign(str_dict):
    """生成待提交数据的签名"""

    md5 = hashlib.md5()
    md5.update(('&'.join('%s=%s' % (k, v) for k, v in str_dict.items()) + MD5_KEY).encode('utf-8'))
    return md5.hexdigest().upper()


def calc_sign_str(string):
    """生成待提交数据的签名"""

    md5 = hashlib.md5()
    md5.update((string + MD5_KEY).encode('utf-8'))
    return md5.hexdigest().upper()


def run_get_api(api: str, bduss='', encoding='', stoken: str = '', cookies: dict = None, return_json=True,
                params: dict = None, use_mobile_header=False, host_type: int = 1):
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
    host_name = ''
    if host_type == 1:
        host_name = 'tieba.baidu.com'
    elif host_type == 2:
        host_name = 'tiebac.baidu.com'
    response = session.get(f'https://{host_name}{api}',
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
                 params: dict = None, use_mobile_header=False, host_type: int = 1, ):
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
    host_name = ''
    if host_type == 1:
        host_name = 'tieba.baidu.com'
    elif host_type == 2:
        host_name = 'tiebac.baidu.com'
    response = session.post(f'https://{host_name}{api}',
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
