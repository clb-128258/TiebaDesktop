"""程序内的全局常量"""
import os


def get_default_datapath():
    if os.name == 'nt':
        datapath = os.getenv('userprofile').replace('\\', '/') + '/AppData/Local/TiebaDesktop'
    else:
        datapath = './TiebaDesktop_UserData'

    return datapath


enable_log_file = True
APP_VERSION_STR = '1.2.3-beta'
APP_VERSION_NUM = 8
WINDOWS_AUMID = 'CLB.TiebaDesktop'
encrypt_key = 'G6WxHyBcliRT5KqcaLkskO5SKB3JJ9dX'
datapath = get_default_datapath()
