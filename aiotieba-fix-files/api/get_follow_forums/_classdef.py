from __future__ import annotations

import dataclasses as dcs
from typing import TYPE_CHECKING

from ...exception import TbErrorExt
from .._classdef import Containers

if TYPE_CHECKING:
    from collections.abc import Mapping


@dcs.dataclass
class FollowForum:
    """
    关注吧信息

    Attributes:
        fid (int): 贴吧id
        fname (str): 贴吧名

        level (int): 用户等级
        exp (int): 经验值

        avatar (str): 吧头像
        slogan (str): 吧标语
        member_count (int): 吧成员数 有时获取不到恒为0
        is_common_follow (bool): 当前账号是否也关注了这个吧 该项仅在登录的情况下有效
    """

    fid: int = 0
    fname: str = ""
    level: int = 0
    exp: int = 0
    avatar: str = ""
    slogan: str = ""
    member_count: int = 0
    is_common_follow: bool = False

    @staticmethod
    def from_tbdata(data_map: Mapping, common_data_list: list) -> FollowForum:
        fid = int(data_map["id"])
        fname = data_map["name"]
        level = int(data_map["level_id"])
        exp = int(data_map["cur_score"])
        avatar = data_map["avatar"]
        slogan = data_map["slogan"]
        member_count = int(data_map.get('member_count', 0))
        is_common_follow = fid in common_data_list
        return FollowForum(fid, fname, level, exp, avatar, slogan, member_count, is_common_follow)

    def __eq__(self, obj: FollowForum) -> bool:
        return self.fid == obj.fid

    def __hash__(self) -> int:
        return self.fid


@dcs.dataclass
class FollowForums(TbErrorExt, Containers[FollowForum]):
    """
    用户关注贴吧列表

    Attributes:
        objs (list[Forum]): 用户关注贴吧列表
        err (Exception | None): 捕获的异常

        has_more (bool): 是否还有下一页
    """

    has_more: bool = False

    @staticmethod
    def from_tbdata(data_map: Mapping) -> FollowForums:
        if forum_list := data_map.get("forum_list", {}):
            if c_forum_list := data_map.get("common_forum_list", {}):
                # 共同关注列表
                forum_dicts = c_forum_list.get("non-gconforum", [])
                common_forum_list = [int(m["id"]) for m in forum_dicts]
                forum_dicts = c_forum_list.get("gconforum", [])
                common_forum_list += [int(m["id"]) for m in forum_dicts]
            else:
                common_forum_list = []

            forum_dicts = forum_list.get("non-gconforum", [])
            objs = [FollowForum.from_tbdata(m, common_forum_list) for m in forum_dicts]
            forum_dicts = forum_list.get("gconforum", [])
            objs += [FollowForum.from_tbdata(m, common_forum_list) for m in forum_dicts]
            has_more = bool(int(data_map["has_more"]))
        else:
            objs = []
            has_more = False

        return FollowForums(objs, has_more)
