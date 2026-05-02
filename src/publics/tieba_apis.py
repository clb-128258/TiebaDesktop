"""部分贴吧常用 API 的封装"""
import asyncio
import datetime
import json
import time
import aiotieba
import enum

from proto.AddPost import AddPostReqIdl_pb2, AddPostResIdl_pb2
from proto.PbPage import PbPageReqIdl_pb2, PbPageResIdl_pb2
from publics import request_mgr, app_logger, profile_mgr
from publics.funcs import get_dict_value_treely
from proto.Profile import ProfileReqIdl_pb2, ProfileResIdl_pb2
from proto.GetLevelInfo import GetLevelInfoReqIdl_pb2, GetLevelInfoResIdl_pb2
from proto.GetUserBlackInfo import GetUserBlackInfoReqIdl_pb2, GetUserBlackInfoResIdl_pb2


class OpAgreeObjectType(enum.IntEnum):
    """
    接口 agree_thread_or_post 的点赞条目类型

    Attributes:
        FloorPost: 主题下的楼层回复贴
        SubComment: 楼中楼回复
        Thread: 主题帖
    """
    FloorPost = 1
    SubComment = 2
    Thread = 3


def login(bduss):
    tsb_resp = request_mgr.run_post_api('/c/s/login',
                                        request_mgr.calc_sign({'_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                                                               'bdusstoken': bduss}),
                                        use_mobile_header=True,
                                        host_type=2)
    return tsb_resp


def get_forum_level_info(bduss, stoken, forum_id):
    payload = GetLevelInfoReqIdl_pb2.GetLevelInfoReqIdl()

    payload.data.common._client_type = 2
    payload.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
    payload.data.common.BDUSS = bduss
    payload.data.common.stoken = stoken

    payload.data.forum_id = forum_id

    resp_binary = request_mgr.run_protobuf_api('/c/f/forum/getLevelInfo',
                                               payloads=payload.SerializeToString(),
                                               cmd_id=301005,
                                               bduss=bduss, stoken=stoken,
                                               host_type=2)

    final_response = GetLevelInfoResIdl_pb2.GetLevelInfoResIdl()
    final_response.ParseFromString(resp_binary)

    return final_response


def get_user_black_info(bduss, stoken, user_id):
    payload = GetUserBlackInfoReqIdl_pb2.GetUserBlackInfoReqIdl()

    payload.data.common._client_type = 2
    payload.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
    payload.data.common.BDUSS = bduss
    payload.data.common.stoken = stoken

    payload.data.black_uid = user_id

    response = request_mgr.run_protobuf_api('/c/u/user/getUserBlackInfo',
                                            payloads=payload.SerializeToString(),
                                            cmd_id=309698,
                                            bduss=bduss, stoken=stoken,
                                            host_type=2)
    final_response = GetUserBlackInfoResIdl_pb2.GetUserBlackInfoResIdl()
    final_response.ParseFromString(response)

    return final_response


def get_user_profile(bduss, stoken, user_id_portrait):
    request_body_proto = ProfileReqIdl_pb2.ProfileReqIdl()

    request_body_proto.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
    request_body_proto.data.common._client_type = 2
    request_body_proto.data.common.BDUSS = bduss
    request_body_proto.data.common.stoken = stoken

    request_body_proto.data.need_post_count = 1
    request_body_proto.data.page = 1
    request_body_proto.data.is_from_usercenter = 1
    if isinstance(user_id_portrait, int):
        request_body_proto.data.uid = user_id_portrait
    else:
        request_body_proto.data.friend_uid_portrait = user_id_portrait

    response_origin = request_mgr.run_protobuf_api('/c/u/user/profile',
                                                   payloads=request_body_proto.SerializeToString(),
                                                   cmd_id=303012,
                                                   host_type=2)

    response_proto = ProfileResIdl_pb2.ProfileResIdl()
    response_proto.ParseFromString(response_origin)
    return response_proto


def add_post(bduss, stoken, forum_id, thread_id, text, captcha_md5, captcha_json_info):
    async def get_tbs():
        return login(bduss)['anti']['tbs']

    async def get_access_info(aiotieba_client) -> tuple[str, str, str, str, str]:
        """
        获取贴吧风控信息

        Return:
            以下风控字段值，均为字符串类型：z_id, client_id, sample_id, show_name, tbs
        """
        aiotieba_http_core = aiotieba_client._http_core

        # 并发执行，提高性能
        result = await asyncio.gather(aiotieba.init_z_id.request(aiotieba_http_core),
                                      aiotieba.sync.request(aiotieba_http_core),
                                      aiotieba_client.get_self_info(),
                                      get_tbs()
                                      )
        z_id = result[0]
        client_id, sample_id = result[1][0], result[1][1]
        show_name = result[2].show_name
        tbs = result[3]

        return z_id, client_id, sample_id, show_name, tbs

    async def run():
        app_logger.log_INFO(f'add post in thread {thread_id}')
        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            access_info = await get_access_info(client)
            z_id, client_id, sample_id, show_name, tbs = access_info[0], access_info[1], access_info[2], access_info[3], \
                access_info[4]

            # aiotieba.api.add_post.pack_proto function
            request_body_proto = AddPostReqIdl_pb2.AddPostReqIdl()
            request_body_proto.data.common.BDUSS = bduss
            request_body_proto.data.common._client_type = 2
            request_body_proto.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
            request_body_proto.data.common._client_id = client_id
            request_body_proto.data.common._phone_imei = "000000000000000"
            request_body_proto.data.common._from = "ad_wandoujia"
            request_body_proto.data.common.cuid = client.account.cuid_galaxy2
            current_ts = time.time()
            current_tsms = int(current_ts * 1000)
            current_dt = datetime.datetime.fromtimestamp(current_ts)
            request_body_proto.data.common._timestamp = current_tsms
            request_body_proto.data.common.model = "PFGM00"
            request_body_proto.data.common.tbs = tbs
            request_body_proto.data.common.net_type = 1
            request_body_proto.data.common.pversion = "1.0.3"
            request_body_proto.data.common._os_version = '12'
            request_body_proto.data.common.brand = "oppo"
            request_body_proto.data.common.lego_lib_version = "3.0.0"
            request_body_proto.data.common.applist = ""
            request_body_proto.data.common.stoken = stoken
            request_body_proto.data.common.z_id = z_id
            request_body_proto.data.common.cuid_galaxy2 = client.account.cuid_galaxy2
            request_body_proto.data.common.cuid_gid = ""
            request_body_proto.data.common.c3_aid = client.account.c3_aid
            request_body_proto.data.common.sample_id = sample_id
            request_body_proto.data.common.scr_w = 900
            request_body_proto.data.common.scr_h = 1600
            request_body_proto.data.common.scr_dip = 1.5
            request_body_proto.data.common.q_type = 0
            request_body_proto.data.common.is_teenager = 0
            request_body_proto.data.common.sdk_ver = "3.36.0"
            request_body_proto.data.common.framework_ver = "3340042"
            request_body_proto.data.common.naws_game_ver = "1030000"
            request_body_proto.data.common.active_timestamp = current_tsms - 86400 * 30
            request_body_proto.data.common.first_install_time = current_tsms - 86400 * 30
            request_body_proto.data.common.last_update_time = current_tsms - 86400 * 30
            request_body_proto.data.common.event_day = f"{current_dt.year}{current_dt.month}{current_dt.day}"
            request_body_proto.data.common.android_id = client.account.android_id
            request_body_proto.data.common.cmode = 1
            request_body_proto.data.common.start_scheme = ""
            request_body_proto.data.common.start_type = 1
            request_body_proto.data.common.idfv = "0"
            request_body_proto.data.common.extra = ""
            request_body_proto.data.common.user_agent = request_mgr.header_protobuf['User-Agent']
            request_body_proto.data.common.personalized_rec_switch = 1
            request_body_proto.data.common.device_score = "0.4"

            request_body_proto.data.anonymous = "1"
            request_body_proto.data.can_no_forum = "0"
            request_body_proto.data.is_feedback = "0"
            request_body_proto.data.takephoto_num = "0"
            request_body_proto.data.entrance_type = "0"
            request_body_proto.data.vcode_tag = "12"
            request_body_proto.data.new_vcode = "1"
            request_body_proto.data.content = text
            request_body_proto.data.fid = str(forum_id)
            request_body_proto.data.v_fid = ""
            request_body_proto.data.v_fname = ""
            request_body_proto.data.kw = str(await client.get_fname(forum_id))
            request_body_proto.data.is_barrage = "0"
            request_body_proto.data.from_fourm_id = str(forum_id)
            request_body_proto.data.tid = str(thread_id)
            request_body_proto.data.is_ad = "0"
            request_body_proto.data.post_from = "3"
            request_body_proto.data.name_show = show_name
            request_body_proto.data.is_pictxt = "0"
            request_body_proto.data.show_custom_figure = 0
            request_body_proto.data.is_show_bless = 0
            request_body_proto.data.with_tail = 1
            request_body_proto.data.score_id = 0
            request_body_proto.data.score = 0

            # 验证码特判
            if captcha_json_info and captcha_md5:
                vcode_stringify = json.dumps(captcha_json_info, separators=(',', ':'))
                request_body_proto.data.vcode_type = "6"
                request_body_proto.data.vcode_md5 = captcha_md5
                request_body_proto.data.vcode = vcode_stringify

            response_bin = request_mgr.run_protobuf_api('/c/c/post/add',
                                                        payloads=request_body_proto.SerializeToString(),
                                                        cmd_id=309731,
                                                        bduss=bduss,
                                                        stoken=stoken,
                                                        host_type=2
                                                        )

            response_proto = AddPostResIdl_pb2.AddPostResIdl()
            response_proto.ParseFromString(response_bin)

            return response_proto

    def start_async():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        return asyncio.run(run())

    return start_async()


def sign_forum(bduss, stoken, forum_id, forum_name):
    tbs = login(bduss)["anti"]["tbs"]

    from_widget = '1' if get_dict_value_treely(profile_mgr.local_config,
                                               ['sign_settings', 'use_widget_sign_flag'],
                                               False) else '0'
    payload = {
        'BDUSS': bduss,
        '_client_type': "2",
        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
        'fid': forum_id,
        'kw': forum_name,
        'stoken': stoken,
        'tbs': tbs,
        'from': 'frs',
        'from_widget': from_widget,
        'subapp_type': 'hybrid',
    }
    r = request_mgr.run_post_api('/c/c/forum/sign',
                                 payloads=request_mgr.calc_sign(payload),
                                 bduss=bduss, stoken=stoken,
                                 use_mobile_header=True,
                                 host_type=1)
    return r


def agree_thread_or_post(bduss: str,
                         stoken: str,
                         thread_id: int,
                         post_id: int,
                         is_cancel: bool,
                         content_type: OpAgreeObjectType):
    account = aiotieba.Account()  # 实例化account以便计算一些数据

    tbs = login(bduss)["anti"]["tbs"]  # 拿tbs

    payload = {
        'BDUSS': bduss,
        '_client_type': "2",
        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
        'agree_type': "5" if is_cancel else "2",  # 2点赞 5取消点赞
        'cuid': account.cuid_galaxy2,
        'obj_type': int(content_type),  # 1回复贴 2楼中楼 3主题贴
        'op_type': "1" if is_cancel else "0",  # 0点赞 1取消点赞
        'post_id': str(post_id),
        'stoken': stoken,
        'tbs': tbs,
        'thread_id': str(thread_id),
    }

    response = request_mgr.run_post_api('/c/c/agree/opAgree',
                                        payloads=request_mgr.calc_sign(payload),
                                        use_mobile_header=True,
                                        bduss=bduss,
                                        stoken=stoken,
                                        host_type=2)

    return response


def store_thread(bduss, stoken, thread_id, post_id):
    # 客户端收藏接口
    data = json.dumps([{'tid': str(thread_id), 'pid': str(post_id), 'status': 1}], separators=(',', ':'))
    payload = {
        'BDUSS': bduss,
        '_client_type': "2",
        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
        'data': data,
        'stoken': stoken,
    }

    result = request_mgr.run_post_api('/c/c/post/addstore',
                                      request_mgr.calc_sign(payload),
                                      bduss=bduss,
                                      stoken=stoken,
                                      use_mobile_header=True,
                                      host_type=2)
    return result


def cancel_store_thread(bduss, stoken, thread_id, post_id):
    # wap版取消收藏接口
    payload = {
        '_client_type': "2",
        '_client_version': "12.64.0",
        'subapp_type': "newwise",
        'tid': str(thread_id),
        'pid': str(post_id)
    }

    result = request_mgr.run_post_api('/mo/q/post_rmstore',
                                      request_mgr.calc_sign(payload),
                                      bduss=bduss,
                                      stoken=stoken,
                                      use_mobile_header=True)

    return result


def fetch_frs_bottom(bduss, stoken, forum_name):
    payload = {
        'BDUSS': bduss,
        '_client_type': "2",
        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
        'kw': forum_name,
        'stoken': stoken
    }

    resp = request_mgr.run_post_api('/c/f/frs/frsBottom',
                                    request_mgr.calc_sign(payload),
                                    bduss=bduss,
                                    stoken=stoken,
                                    host_type=2,
                                    use_mobile_header=True)

    return resp


def newmoindex(bduss):
    return request_mgr.run_get_api('/mo/q/newmoindex', bduss)


def pb_page(bduss, stoken, thread_id, pn=1, rn=30, sort_type=0, only_see_lz=False, pos_pid=0):
    proto_request = PbPageReqIdl_pb2.PbPageReqIdl()
    proto_request.data.common._client_type = 2
    proto_request.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
    proto_request.data.common.BDUSS = bduss
    proto_request.data.common.stoken = stoken

    proto_request.data.kz = int(thread_id)  # 贴子id
    proto_request.data.r = sort_type  # 排序类型
    proto_request.data.lz = 1 if only_see_lz else 0  # 只看楼主
    proto_request.data.rn = rn  # 条目数

    # 页数
    if pos_pid:
        proto_request.data.mark = 1
        proto_request.data.pid = pos_pid
    else:
        proto_request.data.pn = pn

    byte_response = request_mgr.run_protobuf_api('/c/f/pb/page',
                                                 payloads=proto_request.SerializeToString(),
                                                 cmd_id=302001,
                                                 bduss=bduss,
                                                 stoken=stoken,
                                                 host_type=2)

    proto_response = PbPageResIdl_pb2.PbPageResIdl()
    proto_response.ParseFromString(byte_response)

    return proto_response
