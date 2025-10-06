"""程序内的全局常量"""
import os

enable_log_file = True
APP_VERSION_STR = '1.1.1-beta'
APP_VERSION_NUM = 3
encrypt_key = 'G6WxHyBcliRT5KqcaLkskO5SKB3JJ9dX'
datapath = './tiebadesktop_userdata'
if os.name == 'nt':
    datapath = os.getenv('userprofile').replace('\\', '/') + '/AppData/Local/TiebaDesktop'
