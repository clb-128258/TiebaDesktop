"""程序内的全局常量"""
import os

enable_log_file = True
APP_VERSION_STR = '1.2.0-release'
APP_VERSION_NUM = 5
WINDOWS_AUMID = 'CLB.TiebaDesktop'
encrypt_key = 'G6WxHyBcliRT5KqcaLkskO5SKB3JJ9dX'
datapath = './tiebadesktop_userdata'
if os.name == 'nt':
    datapath = os.getenv('userprofile').replace('\\', '/') + '/AppData/Local/TiebaDesktop'
