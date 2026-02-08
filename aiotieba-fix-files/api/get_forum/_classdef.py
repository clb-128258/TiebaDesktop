# 该版本文件经过 CLB 的扩充，并非原版代码
from __future__ import annotations

import dataclasses as dcs
from typing import TYPE_CHECKING

from ...exception import TbErrorExt

if TYPE_CHECKING:
    from collections.abc import Mapping


@dcs.dataclass
class FriendForum(TbErrorExt):
    """
    友情吧信息

    Attributes:
        fid (int): 贴吧id
        fname (str): 贴吧名
        small_avatar (str): 吧头像(小)
    """

    fid: int = 0
    fname: str = ""
    small_avatar: str = ""

    @staticmethod
    def from_tbdata(data_map: Mapping) -> FriendForum:
        fid = data_map["forum_id"]
        fname = data_map["forum_name"]
        small_avatar = data_map["avatar"]
        return FriendForum(
            fid, fname, small_avatar
        )


@dcs.dataclass
class Forum(TbErrorExt):
    """
    贴吧信息

    Attributes:
        err (Exception | None): 捕获的异常

        fid (int): 贴吧id
        fname (str): 贴吧名

        category (str): 一级分类
        subcategory (str): 二级分类

        background_image_url (str): 吧背景图片链接
        small_avatar (str): 吧头像(小)
        slogan (str): 吧标语
        member_num (int): 吧会员数
        post_num (int): 发帖量
        thread_num (int): 主题帖数
        friend_forums (tuple[FriendForum]): 友情吧信息

        has_bawu (bool): 是否有吧务
    """

    fid: int = 0
    fname: str = ""

    category: str = ""
    subcategory: str = ""

    background_image_url: str = ''
    small_avatar: str = ""
    slogan: str = ""
    member_num: int = 0
    post_num: int = 0
    thread_num: int = 0
    friend_forums: tuple = ()

    has_bawu: bool = False

    @staticmethod
    def from_tbdata(data_map: Mapping, activityhead_data_map: Mapping, ff_data_map: Mapping) -> Forum:
        fid = data_map["id"]
        fname = data_map["name"]
        category = data_map["first_class"]
        subcategory = data_map["second_class"]
        background_image_url = activityhead_data_map['head_imgs'][0]['img_url']
        small_avatar = data_map["avatar"]
        slogan = data_map["slogan"]
        member_num = data_map["member_num"]
        post_num = data_map["post_num"]
        thread_num = data_map["thread_num"]
        has_bawu = "managers" in data_map
        friend_forums = []
        if ff_data_map:
            for f in ff_data_map:
                friend_forums.append(FriendForum.from_tbdata(f))
        return Forum(
            fid, fname, category, subcategory, background_image_url, small_avatar, slogan, member_num, post_num,
            thread_num, tuple(friend_forums), has_bawu
        )
