from __future__ import annotations

from collections import OrderedDict
from ..logging import get_logger as LOG
import os
import sys
import json
import threading
import queue
import time

sys.path.append(os.getcwd())  # 添加程序所在路径，以便正确引入consts.py
import consts

_fname2fid = OrderedDict()
_fid2fname = OrderedDict()
_sync_queue = queue.Queue()


def load_caches():
    """
    从本地加载缓存信息
    """

    if os.path.isfile(f'{consts.datapath}/cache_index/fidfname_index.json'):
        with open(f'{consts.datapath}/cache_index/fidfname_index.json', 'rt', encoding='utf-8') as f:
            data = json.loads(f.read())
            for k, v in data.items():
                _fname2fid[v] = k
                _fid2fname[k] = v
            LOG().info('disk fid2fname cache loaded')


def clear_repeat_items():
    """
    对本地的缓存信息进行去重操作
    """

    if os.path.isfile(f'{consts.datapath}/cache_index/fidfname_index.json'):
        with open(f'{consts.datapath}/cache_index/fidfname_index.json', 'rt', encoding='utf-8') as f:
            data = json.loads(f.read())

        final_data = {}
        for k, v in tuple(data.items()):
            if k not in final_data.keys():
                final_data[k] = v

        with open(f'{consts.datapath}/cache_index/fidfname_index.json', 'wt', encoding='utf-8') as f:
            f.write(json.dumps(final_data, indent=4))

        LOG().info('disk fid2fname cache repeat cleared')


def save_caches():
    """
    保存缓存信息到本地
    """

    with open(f'{consts.datapath}/cache_index/fidfname_index.json', 'wt', encoding='utf-8') as f:
        f.write(json.dumps(_fid2fname, indent=4))
        LOG().info('disk fid2fname cache saved')


def __handle_add_event():
    load_caches()  # 在子线程加载，提高性能

    has_event = False
    while True:
        if not _sync_queue.empty():  # 队列非空说明有更改
            has_event = True  # 标记
            while not _sync_queue.empty():
                _sync_queue.get()  # 清空队列

        if has_event:  # 只在有更改时才执行保存
            save_caches()
            clear_repeat_items()
            has_event = False
        time.sleep(10)  # 每隔十秒检测一次


def init_local_cache():
    threading.Thread(target=__handle_add_event, daemon=True).start()


class ForumInfoCache:
    """
    吧信息缓存\n
    本文件经过修改，支持存储在本地的持久缓存
    """

    @classmethod
    def get_fid(cls, fname: str) -> int:
        """
        通过贴吧名获取forum_id

        Args:
            fname (str): 贴吧名

        Returns:
            int: 该贴吧的forum_id
        """

        return _fname2fid.get(fname, "")

    @classmethod
    def get_fname(cls, fid: int) -> str:
        """
        通过forum_id获取贴吧名

        Args:
            fid (int): forum_id

        Returns:
            str: 该贴吧的贴吧名
        """

        return _fid2fname.get(str(fid), "")

    @classmethod
    def add_forum(cls, fname: str, fid: int) -> None:
        """
        将贴吧名与forum_id的映射关系添加到缓存

        Args:
            fname (str): 贴吧名
            fid (int): 贴吧id
        """

        _fname2fid[fname] = fid
        _fid2fname[str(fid)] = fname

        _sync_queue.put(None)  # 提交一次更新事件


init_local_cache()
