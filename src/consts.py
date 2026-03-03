"""程序内的全局常量"""
import os


def get_default_datapath():
    if os.name == 'nt':
        datapath = os.getenv('userprofile').replace('\\', '/') + '/AppData/Local/TiebaDesktop'
    else:
        datapath = './TiebaDesktop_UserData'

    return datapath


# 版本信息
APP_VERSION_STR = '1.3.0-release'
APP_VERSION_NUM = 9

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
