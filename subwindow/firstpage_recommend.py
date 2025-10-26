import asyncio

import publics.logging as logging
import aiotieba
import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QListWidget, QListWidgetItem
from bs4 import BeautifulSoup

from publics import request_mgr, cache_mgr, profile_mgr
from publics.funcs import start_background_thread, format_second


class RecommandWindow(QListWidget):
    """首页推荐列表组件"""
    isloading = False
    offset = 0
    add_tie = pyqtSignal(dict)

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken
        self.setStyleSheet('QListWidget{outline:0px;}'
                           'QListWidget::item:hover {color:white; background-color:white;}'
                           'QListWidget::item:selected {color:white; background-color:white;}')
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSizeAdjustPolicy(QListWidget.SizeAdjustPolicy.AdjustToContents)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.verticalScrollBar().setSingleStep(20)
        self.add_tie.connect(self.add_thread)
        self.verticalScrollBar().valueChanged.connect(self.load_more)

    def load_more(self):
        if not self.isloading and self.verticalScrollBar().value() >= self.verticalScrollBar().maximum() - self.verticalScrollBar().maximum() / 5:
            self.get_recommand_async()

    def add_thread(self, infos):
        # {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
        # 'content': content, 'author_portrait': portrait, 'user_name': user_name,
        # 'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
        # 'forum_pixmap': forum_pixmap, 'view_pixmap': []}
        item = QListWidgetItem()
        from subwindow.thread_preview_item import ThreadView
        widget = ThreadView(self.bduss, infos['thread_id'], infos['forum_id'], self.stoken)
        widget.set_infos(infos['user_portrait_pixmap'], infos['user_name'], infos['title'], infos['content'],
                         infos['forum_pixmap'], infos['forum_name'])
        widget.set_picture(infos['view_pixmap'])
        widget.adjustSize()
        item.setSizeHint(widget.size())
        self.addItem(item)
        self.setItemWidget(item, widget)

    def get_recommand_async(self):
        if self.bduss:  # 登录了使用新接口
            start_background_thread(self.get_recommand_v2)
        else:
            start_background_thread(self.get_recommand_v1)

    def get_recommand_v1(self):
        """贴吧电脑网页版的推荐接口，不登录也能获取"""

        async def get_detail(element):
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                title = element.find_all(class_='title feed-item-link')[0].text  # 找出标题
                content = element.find_all(class_='n_txt')[0].text[0:-1]  # 找出正文
                portrait = \
                    element.find_all(class_='post_author')[0]['href'].split('/home/main?id=')[1].split(
                        '&fr=index')[
                        0]  # 找出portrait，方便获取用户数据
                thread_id = element['data-thread-id']  # 贴子id
                forum_id = element['fid']  # 吧id

                # 找出所有预览图
                preview_pixmap = []
                picture_elements = element.find_all(class_="m_pic")  # 找出所有图片
                for i in picture_elements:
                    pic_addr = i['original']
                    response = requests.get(pic_addr, headers=request_mgr.header)
                    if response.content:
                        pixmap = QPixmap()
                        pixmap.loadFromData(response.content)
                        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                               Qt.SmoothTransformation)
                        preview_pixmap.append(pixmap)

                # 进一步获取用户信息
                userinfo = await client.get_user_info(portrait)
                user_name = userinfo.nick_name_new
                user_head_pixmap = QPixmap()
                user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                # 进一步获取吧信息
                forum = await client.get_forum_detail(int(forum_id))
                forum_name = forum.fname
                forum_pixmap = QPixmap()
                response = requests.get(forum.origin_avatar, headers=request_mgr.header)
                if response.content:
                    forum_pixmap.loadFromData(response.content)
                    forum_pixmap = forum_pixmap.scaled(15, 15, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                tdata = {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
                         'content': content, 'author_portrait': portrait, 'user_name': user_name,
                         'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
                         'forum_pixmap': forum_pixmap, 'view_pixmap': preview_pixmap}
                self.add_tie.emit(tdata)

        def start_async(element):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(get_detail(element))

        def func():
            global datapath
            self.isloading = True
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

                for element in elements:
                    start_background_thread(start_async, (element,))
            except Exception as e:
                logging.log_exception(e)
            else:
                self.offset += 20
            finally:
                self.isloading = False
                logging.log_INFO('loading recommands from api /f/index/feedlist finished')

        func()

    def get_recommand_v2(self):
        """手机网页版贴吧的首页推荐接口"""

        async def get_detail(element):
            # 视频贴过滤检测
            if profile_mgr.local_config['thread_view_settings']['hide_video'] and element.get('video_info'):
                return

            title = element['title']  # 找出标题
            content = ''  # 贴子正文
            if element['abstract']:
                for i in element['abstract']:
                    if i['type'] == 0:
                        content += i['text']
            if element.get('video_info'):
                content = '[这是一条视频贴，时长 {vlen}，{view_num} 次浏览，进贴即可查看]'.format(
                    vlen=format_second(element['video_info']['video_duration']),
                    view_num=element['video_info']['play_count'])
            portrait = element['author']['portrait'].split('?')[0]
            thread_id = element['tid']  # 贴子id
            forum_id = element['forum']['forum_id']  # 吧id

            # 找出所有预览图
            preview_pixmap = []
            picture_elements = element['media']  # 找出所有媒体
            if picture_elements:
                for i in picture_elements:
                    if i['type'] == 3:  # 类型是图片
                        pic_addr = i['big_pic']
                        response = requests.get(pic_addr, headers=request_mgr.header)
                        if response.content:
                            pixmap = QPixmap()
                            pixmap.loadFromData(response.content)
                            pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)
                            preview_pixmap.append(pixmap)

            # 进一步获取用户信息
            user_name = element['author'].get('user_nickname_v2',
                                              element['author']['display_name'])  # 优先获取新版昵称，如果没有则使用旧版昵称或者用户名
            user_head_pixmap = QPixmap()
            user_head_pixmap.loadFromData(cache_mgr.get_portrait(portrait))
            user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # 进一步获取吧信息
            forum_name = element['forum']['forum_name']
            forum_pixmap = QPixmap()
            response = requests.get(element['forum']['forum_avatar'], headers=request_mgr.header)
            if response.content:
                forum_pixmap.loadFromData(response.content)
                forum_pixmap = forum_pixmap.scaled(15, 15, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            tdata = {'thread_id': thread_id, 'forum_id': forum_id, 'title': title,
                     'content': content, 'author_portrait': portrait, 'user_name': user_name,
                     'user_portrait_pixmap': user_head_pixmap, 'forum_name': forum_name,
                     'forum_pixmap': forum_pixmap, 'view_pixmap': preview_pixmap}
            self.add_tie.emit(tdata)

        def start_async(element):
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                asyncio.run(get_detail(element))
            except Exception as e:
                logging.log_exception(e)

        def func():
            global datapath
            self.isloading = True
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
                    for element in tlist:
                        start_background_thread(start_async, (element,))
                    logging.log_INFO('loading recommands from api /mg/o/getRecommPage finished')
            except Exception as e:
                logging.log_exception(e)
            finally:
                self.isloading = False

        func()

