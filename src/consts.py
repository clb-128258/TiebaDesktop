"""程序内的全局常量"""
import os


def get_default_datapath():
    if os.name == 'nt':
        datapath = os.getenv('userprofile').replace('\\', '/') + '/AppData/Local/TiebaDesktop'
    else:
        datapath = './TiebaDesktop_UserData'

    return datapath


# 版本信息
APP_VERSION_STR = '1.3.2-release'
APP_VERSION_NUM = 11

# 网络请求信息
HTTP_TIMEOUT = 12

SCHEME_HTTP = 'http://'
SCHEME_HTTPS = 'https://'

TIEBA_APP_HOST = 'tiebac.baidu.com'
TIEBA_WEB_HOST = 'tieba.baidu.com'
TIEBA_CLIENT_VERSION = '22.1.1.0'

BAIDU_PASSPORT_HOST = 'passport.baidu.com'
BAIDU_SOFIRE_HOST = "sofire.baidu.com"

http_header = {
    'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 '
                  f'Safari/537.36 CLBTiebaDesktop/{APP_VERSION_STR}',
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
http_header_android = {
    'User-Agent': f"Mozilla/5.0 (Linux; Android 12; PFGM00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) "
                  f"Version/4.0 Chrome/101.0.4951.61 Safari/537.36 tieba/{TIEBA_CLIENT_VERSION} skin/default "
                  f"CLBTiebaDesktop/{APP_VERSION_STR}",
    'Accept': "application/json, text/plain, */*",
    'Accept-Encoding': "gzip, deflate",
    'x-requested-with': "XMLHttpRequest",
    'Subapp-Type': "hybrid",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}
http_header_protobuf = {
    'User-Agent': f"Mozilla/5.0 (Linux; Android 12; PFGM00 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) "
                  f"Version/4.0 Chrome/101.0.4951.61 Safari/537.36 tieba/{TIEBA_CLIENT_VERSION} skin/default "
                  f"CLBTiebaDesktop/{APP_VERSION_STR}",
    'Accept': "*/*",
    'Accept-Encoding': "gzip, deflate",
    'Sec-Fetch-Site': "same-origin",
    'Sec-Fetch-Mode': "cors",
    'Sec-Fetch-Dest': "empty",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "x_bd_data_type": "protobuf"
}

# 其它全局信息
enable_log_file = True
WINDOWS_AUMID = 'CLB.TiebaDesktop'
encrypt_key = 'G6WxHyBcliRT5KqcaLkskO5SKB3JJ9dX'
datapath = get_default_datapath()

# 主题色调信息
qss_dark_bg_color = 'rgb(20, 20, 20)'
qss_dark_font_color = 'rgb(245, 245, 245)'

qss_bright_bg_color = 'white'
qss_bright_font_color = 'black'
