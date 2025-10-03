"""本地缓存文件管理器"""
import json
import consts
import request_mgr
import requests

portrait_cache_dict = {}


def get_portrait(portrait: str) -> bytes:
    if not portrait_cache_dict.get(portrait):
        save_portrait(portrait)
    with open(portrait_cache_dict[portrait]['local_path'], 'rb') as file:
        bytesdata = file.read()
        return bytesdata


def is_portrait_changed(portrait: str) -> bool:
    """判断一个portrait是否需要修改"""
    global portrait_cache_dict

    if portrait_cache_dict.get(portrait):
        head_url = f'http://tb.himg.baidu.com/sys/portraith/item/{portrait}'
        response = requests.head(head_url, headers=request_mgr.header)
        if response.headers.get('Portrait_tag') == portrait_cache_dict[portrait]['tag']:  # 还没被修改
            return False
    return True


def save_portrait(portrait: str):
    global portrait_cache_dict
    if is_portrait_changed(portrait):
        head_url = f'http://tb.himg.baidu.com/sys/portraith/item/{portrait}'
        response = requests.get(head_url, headers=request_mgr.header)
        bytes_data = response.content
        if bytes_data and response.status_code == 200:
            local_path = f'{consts.datapath}/image_caches/portrait_{portrait}.jpg'
            with open(local_path, 'wb') as file:
                file.write(bytes_data)
            portrait_cache_dict[portrait] = {'tag': response.headers.get('Portrait_tag', ''), 'local_path': local_path}
            save_portrait_pf()

            return bytes_data


def save_portrait_pf():
    global portrait_cache_dict
    with open(f'{consts.datapath}/cache_index/user_portraits.json', 'wt', encoding='utf-8') as file:
        file.write(json.dumps(portrait_cache_dict, indent=4))


def load_portrait_pf():
    global portrait_cache_dict
    with open(f'{consts.datapath}/cache_index/user_portraits.json', 'rt', encoding='utf-8') as file:
        portrait_cache_dict = json.loads(file.read())


def init_all_datas():
    """从本地磁盘加载所有配置数据"""
    load_portrait_pf()
