"""本地配置文件管理器"""
import json
import time
import copy
from publics import proxytool
import consts

local_config_model = {
    'thread_view_settings': {
        'hide_video': False,
        'hide_ip': False,
        'tb_emoticon_size': 1,
        'default_sort': 0,
        'enable_lz_only': False,
        'play_gif': True
    },
    'forum_view_settings': {
        'default_sort': 0
    },
    'web_browser_settings': {
        'url_open_policy': 0
    },
    "notify_settings": {
        "enable_interact_notify": True,
        'offline_notify': True,
        'enable_clipboard_notify': True
    },
    "proxy_settings": {
        "proxy_switch": 0,
        "custom_proxy_server": {"ip": '', "port": -1},
        "enabled_scheme": {"http": True, "https": True}
    },
    "other_settings": {
        "show_msgbox_before_close": True,
        "context_menu_search_engine": {"preset": "bing", "custom_url": ""},
        "mw_default_page": 0,
    },
    "webview_settings": {
        "disable_font_cover": False,
        'view_frozen': False
    }
}

search_engine_presets = {
    "bing": "https://www.bing.com/search?q=[query]",
    "baidu": "https://www.baidu.com/s?wd=[query]",
    "google": 'https://www.google.com/search?q=[query]',
    "yandex": 'https://www.yandex.com/search/?text=[query]'
}
# display name -> flag name
sep_name_map = {
    'Bing': 'bing',
    '百度': 'baidu',
    'Google': 'google',
    'Yandex': 'yandex'
}
# flag name -> display name
sep_name_map_inverted = {v: k for k, v in sep_name_map.items()}

local_config = {}
view_history = []
post_drafts = {}
window_rects = {}
emoticons_list = {}  # tag -> id
emoticons_list_inverted = {}  # id -> tag

current_uid = 'default'
current_bduss = ''
current_stoken = ''


def add_window_rects(window_class, x, y, w, h, is_maxsize):
    """添加窗口位置信息"""
    global window_rects
    window_rects[window_class.__name__] = [x, y, w, h, is_maxsize]
    save_window_rects()


def get_window_rects(window_class):
    """获取窗口位置信息"""
    return window_rects.get(window_class.__name__)


def load_window_rects() -> dict:
    """加载窗口位置信息"""
    global window_rects
    with open(f'{consts.datapath}/window_rects.json', 'rt') as file:
        window_rects = json.loads(file.read())
        return window_rects


def save_window_rects():
    """保存窗口位置信息到文件"""
    global window_rects
    with open(f'{consts.datapath}/window_rects.json', 'wt') as file:
        file.write(json.dumps(window_rects, indent=4))


def add_post_draft(thread_id: int, text: str):
    """添加草稿信息"""
    global post_drafts

    post_drafts[str(thread_id)] = text  # 保证字典内能取到值
    if not text:
        del post_drafts[str(thread_id)]
    save_post_drafts()


def get_post_draft(thread_id: int) -> str:
    """获取已有的草稿信息"""
    return post_drafts.get(str(thread_id), '')


def load_post_drafts() -> dict:
    global post_drafts
    with open(f'{consts.datapath}/post_drafts', 'rt') as file:
        post_drafts = json.loads(file.read())
        return post_drafts


def save_post_drafts():
    global post_drafts
    with open(f'{consts.datapath}/post_drafts', 'wt') as file:
        file.write(json.dumps(post_drafts, indent=4))


def load_local_config() -> dict:
    global local_config
    with open(f'{consts.datapath}/config.json', 'rt') as file:
        local_config = json.loads(file.read())
        return local_config


def fix_local_config():
    global local_config
    local_config = copy.deepcopy(local_config_model)  # 复制出一份新配置
    save_local_config()


def save_local_config():
    global local_config
    with open(f'{consts.datapath}/config.json', 'wt') as file:
        file.write(json.dumps(local_config, indent=4))
    proxytool.set_proxy()  # 保存配置后重设代理


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


def load_emoticons_list():
    global emoticons_list, emoticons_list_inverted
    with open('./ui/emoticons_index.json', 'rt', encoding='utf-8') as file:
        emoticons_list = json.loads(file.read())
        emoticons_list_inverted = {v: k for k, v in emoticons_list.items()}


def init_all_datas():
    """从本地磁盘加载所有配置数据"""
    from publics.funcs import start_background_thread

    thread_list = [start_background_thread(load_local_config),
                   start_background_thread(load_view_history),
                   start_background_thread(load_post_drafts),
                   start_background_thread(load_window_rects),
                   start_background_thread(load_emoticons_list)]

    for i in thread_list:
        i.join()
