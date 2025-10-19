"""本地配置文件管理器"""
import json
import consts

video_webview_show_html = ''
local_config = {}
current_uid = 'default'
current_bduss = ''
current_stoken = ''


def load_show_html() -> str:
    """加载视频播放器所用的html框架"""
    global video_webview_show_html
    with open('ui/tb_video_webview.html', 'rt', encoding='utf-8') as f:
        video_webview_show_html = f.read()
        return video_webview_show_html


def load_local_config() -> dict:
    global local_config
    with open(f'{consts.datapath}/config.json', 'rt') as file:
        local_config = json.loads(file.read())
        return local_config


def save_local_config():
    global local_config
    with open(f'{consts.datapath}/config.json', 'wt') as file:
        file.write(json.dumps(local_config))


def init_all_datas():
    """从本地磁盘加载所有配置数据"""
    load_show_html()
    load_local_config()
