"""
互动消息会话适配器。
"""
import aiotieba
import asyncio

from publics import app_logger, request_mgr
from publics.funcs import timestamp_to_string

from .models import InteractionEntry


def _first_scalar(value, default=''):
    """把响应中偶发的列表、字典字段归一化为单值。"""
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _first_scalar(item, None)
            if result is not None and result != '':
                return result
        return default
    if isinstance(value, dict):
        for key in ('fname', 'name', 'kw', 'text', 'id', 'fid'):
            if key in value:
                result = _first_scalar(value[key], None)
                if result is not None and result != '':
                    return result
        return default
    return value if value is not None else default


def _to_text(value, default=''):
    result = _first_scalar(value, default)
    return str(result) if result is not None else default


def _to_int(value, default=0):
    try:
        return int(_first_scalar(value, default))
    except (TypeError, ValueError):
        return default


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _page_payload(page=1):
    return {
        'BDUSS': '',
        '_client_type': '2',
        '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
        'pn': str(int(page)),
        'stoken': '',
    }


class InteractionSessionProvider:
    """把回复、@ 与点赞转换为统一的互动消息列表。"""

    def __init__(self, bduss, stoken):
        self.bduss = bduss
        self.stoken = stoken

    def load_messages(self):
        entries = []
        for category in ('reply', 'at', 'agree'):
            page_entries, _, _ = self.load_page(category)
            entries.extend(page_entries)
        entries.sort(key=lambda item: item.timestamp, reverse=True)
        return entries

    def load_page(self, category, page=1, agree_cursor=0):
        try:
            if category == 'reply':
                entries, has_more = self._load_replies(page)
            elif category == 'at':
                entries, has_more = self._load_ats(page)
            elif category == 'agree':
                entries, has_more, agree_cursor = self._load_agrees(
                    page,
                    agree_cursor,
                )
            else:
                return [], False, agree_cursor
        except Exception as error:
            app_logger.log_exception(error)
            app_logger.log_WARN(f'[chats] failed to load interaction {category}')
            return [], False, agree_cursor

        entries.sort(key=lambda item: item.timestamp, reverse=True)
        return entries, has_more, agree_cursor

    def _post_feed(self, path, page=1, agree_cursor=0):
        payload = _page_payload(page)
        payload['BDUSS'] = self.bduss
        payload['stoken'] = self.stoken
        if agree_cursor:
            payload['id'] = str(int(agree_cursor))
        result = request_mgr.run_post_api(
            path,
            payloads=request_mgr.calc_sign(payload),
            use_mobile_header=True,
            host_type=2,
        )
        return result if isinstance(result, dict) else {}

    def _resolve_fid(self, fname, fid):
        async def get_fid():
            try:
                async with aiotieba.Client(proxy=True) as client:
                    fid = await client.get_fid(fname)
                    return fid
            except:
                return 0

        fid = _to_int(fid)
        if fid:
            return fid

        fname = _to_text(fname)
        if not fname:
            return 0

        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            fid = asyncio.run(get_fid())

            return _to_int(fid)
        except Exception as error:
            app_logger.log_exception(error)
            return 0

    def _load_replies(self, page=1):
        result = self._post_feed('/c/u/feed/replyme', page=page)
        reply_list = result.get('reply_list') or []
        if not isinstance(reply_list, list):
            return [], False

        entries = []
        for thread in reply_list:
            if not isinstance(thread, dict):
                continue
            try:
                forum_name = _to_text(thread.get('fname'))
                forum_id = self._resolve_fid(forum_name, thread.get('fid'))
                timestamp = _to_int(thread.get('time'))
                replyer = _as_dict(thread.get('replyer'))
                entries.append(InteractionEntry('reply', timestamp, {
                    'type': 'reply',
                    'thread_id': _to_int(thread.get('thread_id')),
                    'post_id': _to_int(thread.get('post_id')),
                    'is_subfloor': bool(_to_int(thread.get('is_floor'))),
                    'forum_id': forum_id,
                    'forum_name': forum_name,
                    'thread_title': _to_text(thread.get('title')),
                    'content': _to_text(thread.get('content')),
                    'portrait': _to_text(
                        replyer.get('portrait')
                    ).split('?', 1)[0],
                    'user_name': _to_text(replyer.get('name_show')),
                    'post_time_str': timestamp_to_string(timestamp),
                }))
            except Exception as error:
                app_logger.log_exception(error)
        page_info = _as_dict(result.get('page'))
        return entries, bool(_to_int(page_info.get('has_more')))

    def _load_ats(self, page=1):
        result = self._post_feed('/c/u/feed/atme', page=page)
        at_list = result.get('at_list') or []
        if not isinstance(at_list, list):
            return [], False

        entries = []
        for thread in at_list:
            if not isinstance(thread, dict):
                continue
            try:
                timestamp = _to_int(thread.get('time'))
                title = _to_text(thread.get('title'))
                if len(title) >= 3:
                    title = title[3:]
                replyer = _as_dict(thread.get('replyer'))
                entries.append(InteractionEntry('at', timestamp, {
                    'type': 'at',
                    'thread_id': _to_int(thread.get('thread_id')),
                    'post_id': _to_int(thread.get('post_id')),
                    'is_subfloor': bool(_to_int(thread.get('is_floor'))),
                    'forum_id': _to_int(thread.get('fid')),
                    'forum_name': _to_text(thread.get('fname')),
                    'thread_title': title or '无法获取帖子标题，可能已被删除',
                    'content': _to_text(thread.get('content')),
                    'portrait': _to_text(
                        replyer.get('portrait')
                    ).split('?', 1)[0],
                    'user_name': _to_text(replyer.get('name_show')),
                    'post_time_str': timestamp_to_string(timestamp),
                }))
            except Exception as error:
                app_logger.log_exception(error)
        page_info = _as_dict(result.get('page'))
        return entries, bool(_to_int(page_info.get('has_more')))

    def _load_agrees(self, page=1, latest_agree_id=0):
        result = self._post_feed(
            '/c/u/feed/agreeme',
            page=page,
            agree_cursor=latest_agree_id,
        )
        agree_list = result.get('agree_list') or []
        if not isinstance(agree_list, list):
            return [], False, latest_agree_id

        entries = []
        for thread in agree_list:
            if not isinstance(thread, dict):
                continue
            try:
                thread_id = _to_int(thread.get('id'))
                if thread_id:
                    latest_agree_id = thread_id
                timestamp = _to_int(thread.get('op_time'))
                thread_info = _as_dict(thread.get('thread_info'))
                title = _to_text(thread_info.get('title'))
                content = f'主题贴：{title}'
                item_type = _to_int(thread.get('type'))
                post_info = _as_dict(thread.get('post_info'))
                if item_type != 3:
                    content_values = post_info.get('content') or []
                    if (
                            isinstance(content_values, list)
                            and content_values
                            and isinstance(content_values[0], dict)
                    ):
                        post_text = _to_text(content_values[0].get('text'))
                    else:
                        post_text = _to_text(content_values)
                    author = _to_text(
                        _as_dict(post_info.get('author')).get('name_show')
                    )
                    content += f'\n  - {author} 发表的回复：{post_text}'

                picture = ''
                media_list = thread_info.get('media') or []
                if isinstance(media_list, dict):
                    media_list = [media_list]
                for media in media_list:
                    if not isinstance(media, dict):
                        continue
                    if _to_int(media.get('type')) == 3:
                        picture = _to_text(media.get('small_pic'))
                        break

                if item_type == 2:
                    post_id = _to_int(post_info.get('id'))
                else:
                    post_id = _to_int(thread.get('post_id'))

                agreeer = _as_dict(thread.get('agreeer'))
                entries.append(InteractionEntry('agree', timestamp, {
                    'type': 'agree',
                    'thread_id': _to_int(thread.get('thread_id')),
                    'post_id': post_id,
                    'item_type': item_type,
                    'forum_id': _to_int(thread_info.get('fid')),
                    'forum_name': _to_text(thread_info.get('fname')),
                    'thread_title': title,
                    'content': content,
                    'portrait': _to_text(
                        agreeer.get('portrait')
                    ).split('?', 1)[0],
                    'user_name': _to_text(agreeer.get('name_show')),
                    'post_time_str': timestamp_to_string(timestamp),
                    'pic_link': picture,
                }))
            except Exception as error:
                app_logger.log_exception(error)
        return entries, bool(_to_int(result.get('has_more'))), latest_agree_id