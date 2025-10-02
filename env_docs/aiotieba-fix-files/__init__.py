"""
Asynchronous I/O Client/Reviewer for Baidu Tieba

@Author: starry.qvq@gmail.com
@License: Unlicense
@Documentation: https://aiotieba.cc/
"""

import os

from . import const, core, enums, exception, logging, typing
from .__version__ import __version__
from .client import Client
from .config import TimeoutConfig
from .core import Account
from .enums import *  # noqa: F403
from .logging import enable_filelog, get_logger
from .api import (
    add_bawu,
    add_bawu_blacklist,
    add_blacklist_old,
    add_post,
    agree,
    block,
    del_bawu,
    del_bawu_blacklist,
    del_blacklist_old,
    del_post,
    del_posts,
    del_thread,
    del_threads,
    dislike_forum,
    follow_forum,
    follow_user,
    get_ats,
    get_bawu_blacklist,
    get_bawu_info,
    get_bawu_perm,
    get_bawu_postlogs,
    get_bawu_userlogs,
    get_blacklist,
    get_blacklist_old,
    get_blocks,
    get_cid,
    get_comments,
    get_dislike_forums,
    get_fans,
    get_fid,
    get_follow_forums,
    get_follows,
    get_forum,
    get_forum_detail,
    get_forum_level,
    get_group_msg,
    get_images,
    get_member_users,
    get_posts,
    get_rank_forums,
    get_rank_users,
    get_recom_status,
    get_recovers,
    get_replys,
    get_roomlist_by_fid,
    get_self_follow_forums,
    get_selfinfo_initNickname,
    get_selfinfo_moindex,
    get_square_forums,
    get_statistics,
    get_tab_map,
    get_threads,
    get_uinfo_getuserinfo_app,
    get_uinfo_getUserInfo_web,
    get_uinfo_panel,
    get_uinfo_user_json,
    get_unblock_appeals,
    get_user_contents,
    good,
    handle_unblock_appeals,
    init_z_id,
    login,
    move,
    profile,
    recommend,
    recover,
    remove_fan,
    search_exact,
    send_chatroom_msg,
    send_msg,
    set_bawu_perm,
    set_blacklist,
    set_msg_readed,
    set_nickname_old,
    set_profile,
    set_thread_privacy,
    sign_forum,
    sign_growth,
    sync,
    tieba_uid2user_info,
    top,
    unblock,
    undislike_forum,
    unfollow_forum,
    unfollow_user,
    ungood,
)

if os.name == "posix":
    import signal


    def terminate(signal_number, frame):
        raise KeyboardInterrupt


    signal.signal(signal.SIGTERM, terminate)

    try:
        import asyncio

        import uvloop

        if not isinstance(asyncio.get_event_loop_policy(), uvloop.EventLoopPolicy):
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    except ImportError:
        pass
