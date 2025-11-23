"""本地配置文件管理器"""
import json
import time
import copy

import consts

local_config_model = {
    'thread_view_settings': {'hide_video': False,
                             'hide_ip': False,
                             'tb_emoticon_size': 1,
                             'default_sort': 0,
                             'enable_lz_only': False,
                             'play_gif': True},
    'forum_view_settings': {'default_sort': 0},
    'web_browser_settings': {'url_open_policy': 0},
    "notify_settings": {"enable_interact_notify": True}
}

video_webview_show_html = ''
local_config = {}
view_history = []

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


def fix_local_config():
    global local_config
    new_cfg = copy.deepcopy(local_config_model)  # 复制出一份新配置
    new_cfg.update(local_config)  # 把缺少索引的老配置更新到参数齐全的新配置上
    local_config = new_cfg

    save_local_config()


def save_local_config():
    global local_config
    with open(f'{consts.datapath}/config.json', 'wt') as file:
        file.write(json.dumps(local_config, indent=4))


def load_view_history() -> dict:
    global view_history
    with open(f'{consts.datapath}/view_history', 'rt') as file:
        view_history = json.loads(file.read())
        return view_history


def delete_history_item(data_dict: dict):
    """
    删除历史记录条目\n
    此函数相对于 clear_repeat_history() 时间复杂度更低
    """
    if data_dict:
        view_history.remove(data_dict)


def clear_repeat_history(data_dict: dict):
    """
    找出时间不同但数据相同的历史记录条目，并将其从历史记录中删除
    """

    # {"type": "int32 ^1 贴子,2 用户,3 吧,4 网页^",
    #  "time": 114514,
    #  "web_info": {"web_icon_md5": "xxxx", "web_title": "xx", "web_url": "xx"},
    #  "user_info": {"uid": -1, "portrait": "xx", "nickname": "xx"},
    #  "forum_info": {"icon_md5": "xx", "forum_id": -1, "forum_name": "xx"},
    #  "thread_info": {"thread_id": -1, "title": "xx"}}
    global view_history
    founded_data = None
    for h in view_history:
        if h['type'] == data_dict['type'] == 1:
            compare_data = h['thread_info']
            if compare_data == data_dict['thread_info']:
                founded_data = h
                break
        elif h['type'] == data_dict['type'] == 2:
            compare_data = h['user_info']
            if compare_data == data_dict['user_info']:
                founded_data = h
                break
        elif h['type'] == data_dict['type'] == 3:
            compare_data = h['forum_info']
            if compare_data == data_dict['forum_info']:
                founded_data = h
                break
        elif h['type'] == data_dict['type'] == 4:
            compare_data = h['web_info']
            if compare_data == data_dict['web_info']:
                founded_data = h
                break

    if founded_data:
        delete_history_item(founded_data)


def add_view_history(type_: int, data_dict: dict):
    """
    添加一个历史记录信息

    Notes:
        在type_字段中 1贴子 2用户 3吧 4网页
    """

    # {"type": "int32 ^1 贴子,2 用户,3 吧,4 网页^",
    #  "time": 114514,
    #  "web_info": {"web_icon_md5": "xxxx", "web_title": "xx", "web_url": "xx"},
    #  "user_info": {"uid": -1, "portrait": "xx", "nickname": "xx"},
    #  "forum_info": {"icon_md5": "xx", "forum_id": -1, "forum_name": "xx"},
    #  "thread_info": {"thread_id": -1, "title": "xx"}}
    global view_history
    history_data = {"type": type_,
                    "time": time.time(),
                    "web_info": {"web_icon_md5": "", "web_title": "", "web_url": ""},
                    "user_info": {"uid": -1, "portrait": "", "nickname": ""},
                    "forum_info": {"icon_md5": "", "forum_id": -1, "forum_name": ""},
                    "thread_info": {"thread_id": -1, "title": ""}}

    if type_ == 1:
        history_data['thread_info'].update(data_dict)
    elif type_ == 2:
        history_data['user_info'].update(data_dict)
    elif type_ == 3:
        history_data['forum_info'].update(data_dict)
    elif type_ == 4:
        history_data['web_info'].update(data_dict)

    clear_repeat_history(history_data)
    view_history.insert(0, history_data)  # 插入到列表最前面，确保浏览时间降序排序
    while len(view_history) > 300:  # 删除较早的历史记录
        view_history.pop()
    save_view_history()


def save_view_history():
    global view_history
    with open(f'{consts.datapath}/view_history', 'wt') as file:
        file.write(json.dumps(view_history, indent=4))


def init_all_datas():
    """从本地磁盘加载所有配置数据"""
    load_show_html()
    load_local_config()
    load_view_history()
