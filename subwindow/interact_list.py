import asyncio
import gc

import aiotieba
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QWidget, QListWidgetItem

from publics import request_mgr, top_toast_widget
from publics.funcs import start_background_thread, timestamp_to_string, listWidget_get_visible_widgets, \
    get_exception_string
import publics.logging as logging

from ui import reply_at_me_page


class UserInteractionsList(QWidget, reply_at_me_page.Ui_Form):
    """点赞、回复和@当前用户的列表"""
    add_post_data = pyqtSignal(dict)
    error_happened = pyqtSignal(top_toast_widget.ToastMessage)
    reply_page = 1
    at_page = 1
    agree_page = 1
    is_reply_loading = False
    is_at_loading = False
    is_agree_loading = False
    latest_agree_id = 0
    is_first_show = True

    def __init__(self, bduss, stoken, parent):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.parent_window = parent

        self.label.hide()
        self.listwidgets = [self.listWidget_3, self.listWidget_2, self.listWidget]
        for lw in self.listwidgets:
            lw.verticalScrollBar().setSingleStep(25)
            lw.setStyleSheet('QListWidget{outline:0px;}'
                             'QListWidget::item:hover {color:white; background-color:white;}'
                             'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('reply'))
        self.listWidget_2.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('at'))
        self.listWidget_3.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('agree'))
        self.pushButton.clicked.connect(self.refresh_list)
        self.tabWidget.currentChanged.connect(self.load_item_images)

        self.add_post_data.connect(self.set_inter_data_ui)
        self.error_happened.connect(self.parent_window.toast_widget.showToast)

    def refresh_list(self):
        if not self.is_at_loading and not self.is_reply_loading:
            self.listWidget.clear()
            self.listWidget_2.clear()
            self.listWidget_3.clear()
            QPixmapCache.clear()
            gc.collect()
            self.reply_page = 1
            self.at_page = 1
            self.agree_page = 1
            self.latest_agree_id = 0

        self.load_inter_data_async('all')

    def load_item_images(self):
        current_widget = self.tabWidget.currentWidget()
        for lw in self.listwidgets:
            if lw.parent() == current_widget:
                visible_lw = listWidget_get_visible_widgets(lw)
                for i in visible_lw:
                    i.load_images()

    def scroll_load_list_info(self, type_):
        self.load_item_images()

        flag_reply = (
                type_ == "reply" and not self.is_reply_loading and self.listWidget.verticalScrollBar().maximum() == self.listWidget.verticalScrollBar().value() and not self.reply_page == -1)
        flag_at = (
                type_ == "at" and not self.is_at_loading and self.listWidget_2.verticalScrollBar().maximum() == self.listWidget_2.verticalScrollBar().value() and not self.at_page == -1)
        flag_agree = (
                type_ == "agree" and not self.is_agree_loading and self.listWidget_3.verticalScrollBar().maximum() == self.listWidget_3.verticalScrollBar().value() and not self.agree_page == -1)
        if flag_reply or flag_at or flag_agree:
            start_background_thread(self.load_inter_data, (type_,))

    def set_inter_data_ui(self, data):
        item = QListWidgetItem()
        if data['type'] != 'agree':
            from subwindow.thread_reply_item import ReplyItem
            widget = ReplyItem(self.bduss, self.stoken)

            widget.load_by_callback = True
            widget.is_comment = data['is_subfloor']
            widget.portrait = data['portrait']
            widget.thread_id = data['thread_id']
            widget.post_id = data['post_id']
            widget.subcomment_show_thread_button = True
            widget.set_reply_text(
                '{sub_floor}在 <a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下{ptype}了你：'.format(
                    fname=data['forum_name'],
                    tname=data['thread_title'],
                    tid=data['thread_id'],
                    fid=data['forum_id'],
                    sub_floor='[楼中楼] ' if data['is_subfloor'] else '[回复贴] ',
                    ptype='回复' if data['type'] == 'reply' else '@')
            )
            widget.setdatas(data['portrait'], data['user_name'], False, data['content'],
                            [], -1, data['post_time_str'], '', -2, -1, -1, False)
        else:
            from subwindow.thread_agreed_item import AgreedThreadItem
            widget = AgreedThreadItem(self.bduss, self.stoken)

            widget.is_post = False
            widget.portrait = data['portrait']
            widget.thread_id = data['thread_id']
            widget.post_id = data['post_id']
            widget.setdatas(data['portrait'], data['user_name'], data['content'],
                            data['pic_link'], data['post_time_str'],
                            '在 <a href=\"tieba_forum://{fid}\">{fname}吧</a> 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 内为你发布的以下内容点了赞：'.format(
                                fname=data['forum_name'],
                                tname=data['thread_title'],
                                tid=data['thread_id'],
                                fid=data['forum_id'])
                            )
        item.setSizeHint(widget.size())

        if data['type'] == 'reply':
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif data['type'] == 'at':
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
        elif data['type'] == 'agree':
            self.listWidget_3.addItem(item)
            self.listWidget_3.setItemWidget(item, widget)

        self.load_item_images()

    def load_inter_data_async(self, type_):
        if self.bduss:
            self.label.hide()
            self.tabWidget.show()
            if ((type_ == "reply" and not self.is_reply_loading)
                    or (type_ == "at" and not self.is_at_loading)
                    or (type_ == "agree" and not self.is_agree_loading)):
                start_background_thread(self.load_inter_data, (type_,))
            elif type_ == "all" and not self.is_reply_loading and not self.is_at_loading and not self.is_agree_loading:
                start_background_thread(self.load_inter_data, ('reply',))
                start_background_thread(self.load_inter_data, ('at',))
                start_background_thread(self.load_inter_data, ('agree',))
        else:
            self.label.show()
            self.tabWidget.hide()

    def load_inter_data(self, type_):
        async def run_func():
            try:
                logging.log_INFO(
                    f'loading userInteractionsList {type_}, page (reply {self.reply_page} at {self.at_page} agree {self.agree_page})')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if type_ == "reply":
                        self.is_reply_loading = True
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': '2',
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'pn': str(self.reply_page),
                            'stoken': self.stoken,
                        }
                        datas = request_mgr.run_post_api('/c/u/feed/replyme', payloads=request_mgr.calc_sign(payload),
                                                         use_mobile_header=True, host_type=2)

                        for thread in datas['reply_list']:
                            # 用户头像
                            portrait = thread["replyer"]["portrait"].split("?")[0]

                            # 用户昵称
                            nick_name = thread["replyer"]["name_show"]

                            # 获取吧id
                            forum_id = await client.get_fid(thread["fname"])

                            # 获取贴子标题
                            thread_title = thread['title']

                            # 发布时间字符串
                            timestr = timestamp_to_string(int(thread['time']))

                            # 是楼中楼获取对应的pid
                            if bool(int(thread['is_floor'])):
                                pid = int(thread['quote_pid'])
                            else:
                                pid = int(thread["post_id"])

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': int(thread["thread_id"]),
                                    'real_post_id': int(thread["post_id"]),
                                    'post_id': pid,
                                    'is_subfloor': bool(int(thread['is_floor'])),
                                    'forum_id': forum_id,
                                    'forum_name': thread["fname"],
                                    'thread_title': thread_title,
                                    'content': thread["content"],
                                    'portrait': portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.add_post_data.emit(data)
                    elif type_ == "at":
                        self.is_at_loading = True
                        datas = await client.get_ats(self.at_page)
                        if datas.err:
                            raise datas.err

                        for thread in datas.objs:
                            # 用户昵称
                            nick_name = thread.user.nick_name_new

                            # 获取吧id
                            forum_id = thread.fid

                            # 获取贴子标题
                            thread_title = thread.thread_title if thread.thread_title else "无法获取贴子标题，可能已被删除"

                            # 发布时间字符串
                            timestr = timestamp_to_string(thread.create_time)

                            # 是楼中楼获取对应的pid
                            if thread.is_comment:
                                thread_info = await client.get_comments(thread.tid, thread.pid, pn=1, is_comment=True)
                                pid = thread_info.post.pid
                            else:
                                pid = thread.pid

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': thread.tid,
                                    'real_post_id': thread.pid,
                                    'post_id': pid,
                                    'is_subfloor': thread.is_comment,
                                    'forum_id': forum_id,
                                    'forum_name': thread.fname,
                                    'thread_title': thread_title,
                                    'content': thread.text,
                                    'portrait': thread.user.portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.add_post_data.emit(data)
                    elif type_ == "agree":
                        self.is_agree_loading = True
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': '2',
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'id': str(self.latest_agree_id),
                            'rn': '20',
                            'stoken': self.stoken,
                        }
                        if not self.latest_agree_id:
                            del payload['id']
                        datas = request_mgr.run_post_api('/c/u/feed/agreeme', payloads=request_mgr.calc_sign(payload),
                                                         use_mobile_header=True, host_type=2)

                        for thread in datas['agree_list']:
                            # 更新点赞id
                            self.latest_agree_id = int(thread['id'])

                            # 用户头像
                            portrait = thread["agreeer"]["portrait"].split("?")[0]

                            # 用户昵称
                            nick_name = thread["agreeer"]["name_show"]

                            # 获取吧id
                            forum_id = thread["thread_info"]['fid']

                            # 获取贴子标题
                            thread_title = thread['thread_info']['title']

                            # 发布时间字符串
                            timestr = timestamp_to_string(int(thread['op_time']))

                            # 被点赞的内容
                            content = f'主题贴：{thread_title}'
                            if int(thread['type']) != 3:
                                content += '\n  - '
                                content += f"{thread['post_info']['author']['name_show']} 发表的回复：{thread['post_info']['content'][0]['text']}"

                            # 贴子图片链接
                            pic_link = ''
                            if pic_list := thread['thread_info'].get('media'):
                                for p in pic_list:
                                    if int(p['type']) == 3:
                                        pic_link = p['small_pic']
                                        break

                            # 是楼中楼获取对应的pid
                            if int(thread['type']) == 2:
                                pid = int(thread['post_info']['id'])
                            else:
                                pid = int(thread["post_id"])

                            # post_id 一定不是楼中楼，real_post_id 视情况而定，可能会指向楼中楼
                            # 如果 real_post_id 不是楼中楼，那么 post_id = real_post_id
                            # 如果 real_post_id 是楼中楼，则 post_id 指向这个楼中楼所在的回复贴
                            data = {'type': type_,
                                    'thread_id': int(thread["thread_id"]),
                                    'post_id': pid,
                                    'item_type': int(thread['type']),  # 1回复 2楼中楼 3主题
                                    'forum_id': forum_id,
                                    'forum_name': thread['thread_info']["fname"],
                                    'thread_title': thread_title,
                                    'content': content,
                                    'portrait': portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr,
                                    'pic_link': pic_link}
                            self.add_post_data.emit(data)
            except Exception as e:
                logging.log_exception(e)
                self.error_happened.emit(
                    top_toast_widget.ToastMessage(f'[GetInteractMsg {type_} Error] ' + get_exception_string(e),
                                                  icon_type=top_toast_widget.ToastIconType.ERROR
                                                  )
                )
            else:
                if type_ == "reply":
                    if bool(int(datas["page"]["has_more"])):
                        self.reply_page += 1
                    else:
                        self.reply_page = -1
                elif type_ == "at":
                    if datas.has_more:
                        self.at_page += 1
                    else:
                        self.at_page = -1
                elif type_ == "agree":
                    if bool(int(datas["has_more"])):
                        self.agree_page += 1
                    else:
                        self.agree_page = -1
            finally:
                if type_ == "reply":
                    self.is_reply_loading = False
                elif type_ == "at":
                    self.is_at_loading = False
                elif type_ == "agree":
                    self.is_agree_loading = False

                logging.log_INFO(
                    f'load userInteractionsList {type_}, '
                    f'page (reply {self.reply_page} '
                    f'at {self.at_page} '
                    f'agree {self.agree_page}) finished')

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()
