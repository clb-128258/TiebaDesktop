import asyncio
import gc

import publics.logging as logging
import aiotieba
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from bs4 import BeautifulSoup

from publics import request_mgr, profile_mgr, top_toast_widget
from publics.funcs import start_background_thread, format_second, cut_string, LoadingFlashWidget, get_exception_string, \
    listWidget_get_visible_widgets, large_num_to_string


class RecommendWindow(QListWidget):
    """首页推荐列表组件"""
    isloading = False
    is_first_load = False
    offset = 0
    add_tie = pyqtSignal(dict)
    load_finish = pyqtSignal(top_toast_widget.ToastMessage)

    def __init__(self, bduss, stoken, parent):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken
        self.parent_window = parent
        self.init_cover_widgets()
        self.setStyleSheet('QListWidget{outline:0px;}'
                           'QListWidget::item:hover {color:white; background-color:white;}'
                           'QListWidget::item:selected {color:white; background-color:white;}')
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSizeAdjustPolicy(QListWidget.SizeAdjustPolicy.AdjustToContents)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.verticalScrollBar().setSingleStep(20)
        self.add_tie.connect(self.add_thread)
        self.load_finish.connect(self.on_load_finish)
        self.verticalScrollBar().valueChanged.connect(self.load_more)

    def init_cover_widgets(self):
        self.loading_widget = LoadingFlashWidget(caption='贴子正在赶来的路上...')
        self.loading_widget.cover_widget(self)
        self.loading_widget.hide()

    def on_load_finish(self, msg):
        if self.is_first_load:
            self.loading_widget.hide()
            self.parent_window.toast_widget.showToast(msg)
            self.load_list_images()
            self.is_first_load = False

    def load_list_images(self):
        lws = listWidget_get_visible_widgets(self)
        for widget in lws:
            widget.load_all_AsyncImage()

    def load_more(self):
        self.load_list_images()

        if not self.isloading:
            is_scroll_to_end = self.verticalScrollBar().value() >= self.verticalScrollBar().maximum() - self.verticalScrollBar().maximum() / 5
            if is_scroll_to_end:
                self.get_recommand_async()

    def add_thread(self, infos):
        # {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
        # 'content': content, 'author_portrait': portrait, 'user_name': user_name,
        # 'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
        # 'forum_pixmap': forum_pixmap, 'view_pixmap': []}
        item = QListWidgetItem()
        from subwindow.thread_preview_item import ThreadView
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
        widget.load_by_callback = True
        widget.set_infos(infos['author_portrait'],
                         infos['user_name'],
                         infos['title'],
                         infos['content'],
                         infos['forum_avatar'],
                         infos['forum_name'])
        widget.set_picture(infos['view_pixmap'])
        widget.adjustSize()
        item.setSizeHint(widget.size())
        self.addItem(item)
        self.setItemWidget(item, widget)

    def get_recommand_async(self, refresh=False):
        if not self.isloading:
            self.is_first_load = True if refresh else self.is_first_load
            if self.is_first_load:
                self.loading_widget.show()
                # 清理内存
                self.clear()
                QPixmapCache.clear()
                gc.collect()

            if self.bduss:  # 登录了使用新接口
                start_background_thread(self.get_recommand_v2)
            else:
                start_background_thread(self.get_recommand_v1)

    def get_recommand_v1(self):
        """贴吧电脑网页版的推荐接口，不登录也能获取"""
        from subwindow.thread_preview_item import AsyncLoadImage

        async def get_detail(element):
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                title = element.find_all(class_='title feed-item-link')[0].text  # 找出标题
                content = element.find_all(class_='n_txt')[0].text[0:-1]  # 找出正文
                content = cut_string(content, 50)
                portrait = \
                    element.find_all(class_='post_author')[0]['href'].split('/home/main?id=')[1].split(
                        '&fr=index')[
                        0]  # 找出portrait，方便获取用户数据
                thread_id = element['data-thread-id']  # 贴子id
                forum_id = element['fid']  # 吧id
                user_name = element.find_all(class_='post_author')[0].text

                # 找出所有预览图
                preview_pixmap = []
                picture_elements = element.find_all(class_="m_pic")  # 找出所有图片
                for i in picture_elements:
                    pic_addr = i['original']
                    preview_pixmap.append(AsyncLoadImage(pic_addr))

                # 进一步获取吧信息
                forum = await client.get_forum_detail(int(forum_id))
                forum_name = forum.fname
                forum_avatar = forum.small_avatar

                tdata = {'thread_id': thread_id,
                         'forum_id': forum_id,
                         'title': title,
                         'content': content,
                         'author_portrait': portrait,
                         'user_name': user_name,
                         'forum_name': forum_name,
                         'forum_avatar': forum_avatar,
                         'view_pixmap': preview_pixmap}
                self.add_tie.emit(tdata)

        def start_async(element):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(get_detail(element))

        def func():
            self.isloading = True
            toast_msg = top_toast_widget.ToastMessage()
            try:
                # 贴吧电脑网页版的推荐接口，不登录也能获取
                # 在登录情况下，需要传一组特定的cookie才能使推荐个性化（不只是bduss和stoken），否则是默认推荐
                logging.log_INFO('loading recommands from api /f/index/feedlist')
                response = request_mgr.run_get_api(f'/f/index/feedlist?tag_id=like&offset={self.offset}')
                html = response['data']['html']

                # 统一贴子列表内的class类型
                for i in range(1, 11):
                    html = html.replace(f'clearfix j_feed_li  {i}', 'clearfix j_feed_li')

                # 解析网页
                soup = BeautifulSoup(html, "html.parser")
                elements = soup.find_all(class_="clearfix j_feed_li")  # 找出所有贴子
                thread_list = []

                for element in elements:
                    thread = start_background_thread(start_async, (element,))
                    thread_list.append(thread)
                for t in thread_list:
                    t.join()

                toast_msg.title = f'已为你刷新 {len(thread_list)} 条贴子'
                toast_msg.icon_type = top_toast_widget.ToastIconType.SUCCESS
                self.offset += 20
                logging.log_INFO('loading recommands from api /f/index/feedlist finished')
            except Exception as e:
                logging.log_exception(e)
                toast_msg.title = get_exception_string(e)
                toast_msg.icon_type = top_toast_widget.ToastIconType.ERROR
            finally:
                self.isloading = False
                self.load_finish.emit(toast_msg)

        func()

    def get_recommand_v2(self):
        """手机网页版贴吧的首页推荐接口"""
        from subwindow.thread_preview_item import AsyncLoadImage
        def judge_filler(element):
            if profile_mgr.local_config['thread_view_settings']['hide_video'] and element.get('video_info'):
                # 视频贴过滤检测
                return False
            return True

        async def get_detail(element):
            title = element['title']  # 找出标题
            content = ''  # 贴子正文
            if element['abstract']:
                for i in element['abstract']:
                    if i['type'] == 0:
                        content += i['text']
            if element.get('video_info'):
                content = '[视频] 时长 {vlen} | {view_num}次浏览'.format(
                    vlen=format_second(element['video_info']['video_duration']),
                    view_num=large_num_to_string(element['video_info']['play_count'], endspace=True))
            content = cut_string(content, 50)
            portrait = element['author']['portrait'].split('?')[0]
            thread_id = element['tid']  # 贴子id
            forum_id = element['forum']['forum_id']  # 吧id

            # 找出所有预览图
            preview_pixmap = []
            picture_elements = element.get('media') if element.get('media') else []
            for i in picture_elements:
                if i['type'] == 3:  # 类型是图片
                    pic_addr = i['big_pic']
                    preview_pixmap.append(AsyncLoadImage(pic_addr))

            # 进一步获取用户信息
            user_name = element['author'].get('user_nickname_v2',
                                              element['author']['display_name'])  # 优先获取新版昵称，如果没有则使用旧版昵称或者用户名

            # 进一步获取吧信息
            forum_name = element['forum']['forum_name']
            forum_avatar = element['forum']['forum_avatar']

            tdata = {'thread_id': thread_id,
                     'forum_id': forum_id,
                     'title': title,
                     'content': content,
                     'author_portrait': portrait,
                     'user_name': user_name,
                     'forum_name': forum_name,
                     'forum_avatar': forum_avatar,
                     'view_pixmap': preview_pixmap}
            self.add_tie.emit(tdata)

        def start_async(element):
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                asyncio.run(get_detail(element))
            except Exception as e:
                logging.log_exception(e)

        def func():
            self.isloading = True
            toast_msg = top_toast_widget.ToastMessage()
            try:
                # 手机网页版贴吧的首页推荐接口
                # 该接口在未登录的情况下会获取不到数据，并报未知错误 (110003)
                # 在登录情况下，有bduss和stoken就可以实现个性化推荐
                # 该接口包含的信息较为全面，很多信息无需再另起请求，因此该方法获取贴子数据会比旧版的快
                # 该接口返回的视频贴较多，疑似是贴吧后端刻意为之
                logging.log_INFO('loading recommands from api /mg/o/getRecommPage')
                response = request_mgr.run_get_api('/mg/o/getRecommPage?load_type=1&eqid=&refer=tieba.baidu.com'
                                                   '&page_thread_count=10',
                                                   bduss=self.bduss, stoken=self.stoken)
                if response['errno'] == 110003:
                    start_background_thread(self.get_recommand_v1)
                else:
                    tlist = response['data']['thread_list']
                    thread_list = []
                    for element in tlist:
                        if judge_filler(element):
                            thread = start_background_thread(start_async, (element,))
                            thread_list.append(thread)
                    for t in thread_list:
                        t.join()

                    logging.log_INFO('loading recommands from api /mg/o/getRecommPage finished')
                    toast_msg.title = f'已为你刷新 {len(thread_list)} 条贴子'
                    toast_msg.icon_type = top_toast_widget.ToastIconType.SUCCESS
            except Exception as e:
                logging.log_exception(e)
                toast_msg.title = get_exception_string(e)
                toast_msg.icon_type = top_toast_widget.ToastIconType.ERROR
            finally:
                self.isloading = False
                self.load_finish.emit(toast_msg)

        func()
