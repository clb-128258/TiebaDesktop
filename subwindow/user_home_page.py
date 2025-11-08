import asyncio

import aiotieba
import requests
import pyperclip
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QWidget, QAction, QMenu, QMessageBox, QListWidgetItem

from publics import profile_mgr, qt_window_mgr, cache_mgr, request_mgr
from publics.funcs import LoadingFlashWidget, ExtListWidgetItem, start_background_thread, cut_string, \
    make_thread_content, timestamp_to_string, open_url_in_browser
import publics.logging as logging

from ui import user_home_page


class UserHomeWindow(QWidget, user_home_page.Ui_Form):
    """用户个人主页窗口"""
    set_head_info_signal = pyqtSignal(dict)
    set_list_info_signal = pyqtSignal(tuple)
    action_ok_signal = pyqtSignal(dict)

    nick_name = ''
    real_user_id = -1
    real_tieba_id = -1
    real_portrait = ''
    real_baidu_user_name = ''

    def __init__(self, bduss, stoken, user_id_portrait, tab_index=0):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.user_id_portrait = user_id_portrait

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.label_11.setPixmap(QPixmap('ui/user_ban_new.png').scaled(15, 15, transformMode=Qt.SmoothTransformation))
        self.label_7.setPixmap(QPixmap('ui/tb_dashen.png').scaled(15, 15, transformMode=Qt.SmoothTransformation))
        self.init_user_action_menu()

        # 隐藏组件
        self.frame_8.hide()
        self.frame_2.hide()
        self.frame_3.hide()
        self.frame_5.hide()
        self.frame_4.hide()

        self.page = {'thread': {'loading': False, 'page': 1},
                     'reply': {'loading': False, 'page': 1},
                     'follow_forum': {'loading': False, 'page': 1},
                     'follow': {'loading': False, 'page': 1},
                     'fans': {'loading': False, 'page': 1}}
        self.listwidgets = {'follow_forum': self.listWidget, 'reply': self.listWidget_2, 'follow': self.listWidget_3,
                            'thread': self.listWidget_4, 'fans': self.listWidget_5}
        for v in self.listwidgets.values():
            v.verticalScrollBar().setSingleStep(20)

        # 必须手动链接所有信号，在上面的循环里进行会有奇怪的bug
        self.listWidget.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('follow_forum'))
        self.listWidget_2.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('reply'))
        self.listWidget_3.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('follow'))
        self.listWidget_4.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('thread'))
        self.listWidget_5.verticalScrollBar().valueChanged.connect(lambda: self.scroll_load_list_info('fans'))

        self.listWidget_4.setStyleSheet('QListWidget{outline:0px;}'
                                        'QListWidget::item:hover {color:white; background-color:white;}'
                                        'QListWidget::item:selected {color:white; background-color:white;}')
        self.listWidget_2.setStyleSheet('QListWidget{outline:0px;}'
                                        'QListWidget::item:hover {color:white; background-color:white;}'
                                        'QListWidget::item:selected {color:white; background-color:white;}')

        # 隐藏ip属地
        if profile_mgr.local_config['thread_view_settings']['hide_ip']:
            self.label_5.hide()

        self.action_ok_signal.connect(self.action_ok_slot)
        self.set_head_info_signal.connect(self.set_head_info_ui)
        self.set_list_info_signal.connect(self.set_list_info_ui)
        self.listWidget_3.itemDoubleClicked.connect(self.open_user_homepage)
        self.listWidget_5.itemDoubleClicked.connect(self.open_user_homepage)

        self.tabWidget.setCurrentIndex(tab_index)
        self.init_load_flash()
        self.get_head_info_async()

    def closeEvent(self, a0):
        self.flash_shower.hide()
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.flash_shower = LoadingFlashWidget()
        self.flash_shower.cover_widget(self)
        self.flash_shower.show()

    def init_user_action_menu(self):
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        follow = QAction('关注', self)
        follow.triggered.connect(lambda: self.do_action_async('follow'))
        menu.addAction(follow)

        unfollow = QAction('取消关注', self)
        unfollow.triggered.connect(lambda: self.do_action_async('unfollow'))
        menu.addAction(unfollow)

        menu.addSeparator()

        blacklist = QAction('拉黑', self)
        blacklist.setToolTip('禁止该用户与你互动（转评赞等），以及禁止该用户关注你和给你发私信。')
        blacklist.triggered.connect(self.open_user_blacklister)
        menu.addAction(blacklist)

        old_mute = QAction('禁言', self)
        old_mute.triggered.connect(lambda: self.do_action_async('mute'))
        old_mute.setToolTip('禁止该用户回复你的贴子。\n'
                            'PS：该功能存在于旧版本贴吧中，已被新版本的拉黑功能取代，不推荐使用。')
        menu.addAction(old_mute)

        cancel_old_mute = QAction('取消禁言', self)
        cancel_old_mute.triggered.connect(lambda: self.do_action_async('unmute'))
        menu.addAction(cancel_old_mute)

        menu.addSeparator()

        copy_datas = QMenu(self)
        copy_datas.setToolTipsVisible(True)
        copy_datas.setTitle('复制...')

        copy_nickname = QAction('复制昵称', self)
        copy_nickname.setToolTip('复制该用户的昵称。')
        copy_nickname.triggered.connect(lambda: pyperclip.copy(self.nick_name))
        copy_datas.addAction(copy_nickname)

        copy_user_name = QAction('复制用户名', self)
        copy_user_name.setToolTip(
            '复制该用户使用的用户名。\n'
            '用户名在所有百度系产品是通用的，不同于昵称，具有唯一性。该字段可能为空。')
        copy_user_name.triggered.connect(lambda: pyperclip.copy(self.real_baidu_user_name))
        copy_datas.addAction(copy_user_name)

        copy_tieba_id = QAction('复制贴吧 ID', self)
        copy_tieba_id.setToolTip('复制贴吧 APP 个人主页内显示的贴吧 ID。该字段可能为空。')
        copy_tieba_id.triggered.connect(lambda: pyperclip.copy(self.real_tieba_id))
        copy_datas.addAction(copy_tieba_id)

        copy_user_id = QAction('复制用户 ID', self)
        copy_user_id.setToolTip(
            '复制贴吧内部使用的用户 ID。\n'
            '请注意，用户 ID 不是贴吧 ID，两者是有区别的。\n'
            '该字段一定不为空，且具有唯一性，可用于标识用户身份。')
        copy_user_id.triggered.connect(lambda: pyperclip.copy(self.real_user_id))
        copy_datas.addAction(copy_user_id)

        copy_portrait = QAction('复制 Portrait 字段', self)
        copy_portrait.setToolTip(
            '复制贴吧内部使用的 Portrait。\n'
            '该字段一定不为空，且具有唯一性，可用于标识用户身份，或直接用于获取用户头像图片。')
        copy_portrait.triggered.connect(lambda: pyperclip.copy(self.real_portrait))
        copy_datas.addAction(copy_portrait)

        menu.addMenu(copy_datas)

        open_in_browser = QAction('在浏览器内打开', self)
        open_in_browser.triggered.connect(
            lambda: open_url_in_browser(f'https://tieba.baidu.com/home/main?id={self.real_portrait}'))
        menu.addAction(open_in_browser)

        show_follow_forum_strongly_menu = QMenu(self)
        show_follow_forum_strongly_menu.setTitle('查询该用户关注的吧')

        chengqing = QAction('澄清·工具箱', self)
        chengqing.triggered.connect(lambda: open_url_in_browser(f'http://chengqing.cc/'))
        show_follow_forum_strongly_menu.addAction(chengqing)

        buer = QAction('不二的贴吧工具箱', self)
        buer.triggered.connect(
            lambda: open_url_in_browser(f'https://www.82cat.com/tieba/forum/{self.real_baidu_user_name}/1'))
        show_follow_forum_strongly_menu.addAction(buer)

        ouotool = QAction('ouo 工具箱', self)
        ouotool.triggered.connect(
            lambda: open_url_in_browser(f'https://ouotool.com/tb?un={self.real_baidu_user_name}'))
        show_follow_forum_strongly_menu.addAction(ouotool)

        menu.addMenu(show_follow_forum_strongly_menu)

        self.pushButton.setMenu(menu)

    def open_user_homepage(self, item):
        if isinstance(item, ExtListWidgetItem):
            user_home_page = UserHomeWindow(self.bduss, self.stoken, item.user_portrait_id)
            qt_window_mgr.add_window(user_home_page)

    def open_user_blacklister(self):
        from subwindow.single_blacklist import SingleUserBlacklistWindow
        blacklister = SingleUserBlacklistWindow(self.bduss, self.stoken, self.user_id_portrait)
        qt_window_mgr.add_window(blacklister)

    def action_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'unfollow':
            if QMessageBox.warning(self, '取关用户', f'确定要取消关注用户 {self.nick_name} 吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        elif action_type == 'mute':
            if QMessageBox.warning(self, '禁言用户', f'禁言后，该用户将无法回复你。确定要禁言用户 {self.nick_name} 吗？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False
        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                logging.log_INFO(f'do user {self.user_id_portrait} action type {action_type}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'follow':
                        r = await client.follow_user(self.user_id_portrait)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '关注成功'
                            turn_data['text'] = f'已成功关注该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unfollow':
                        r = await client.unfollow_user(self.user_id_portrait)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消关注成功'
                            turn_data['text'] = f'已成功取消关注该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'mute':
                        r = await client.add_blacklist_old(self.real_user_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '禁言成功'
                            turn_data['text'] = f'已成功禁言该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '禁言失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unmute':
                        r = await client.del_blacklist_old(self.real_user_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消禁言成功'
                            turn_data['text'] = f'已成功取消禁言该用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消禁言失败'
                            turn_data['text'] = f'{r.err}'
            except Exception as e:
                logging.log_exception(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.action_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def set_head_info_ui(self, data):
        if data['error']:
            QMessageBox.critical(self, '用户信息加载失败', data['error'], QMessageBox.Ok)
            self.close()
        else:
            self.setWindowTitle(data['name'] + ' - 个人主页')
            self.setWindowIcon(QIcon(data['portrait_pixmap']))

            self.label.setPixmap(data['portrait_pixmap'])
            self.label_2.setText(data['name'])
            self.label_2.setToolTip('用户名：' + data['bd_user_name'])
            self.label_9.setText('Lv.' + str(data['level']))
            self.label_8.setText('获赞数 ' + str(data['agree_c']))
            self.label_3.setText('贴吧 ID：' + str(data['tieba_id']))
            self.label_4.setText('吧龄 {age} 年'.format(age=data['account_age']))
            self.label_5.setText('IP 属地：' + data['ip'])
            self.label_14.setText('发贴数 ' + str(data['post_c']))
            self.tabWidget.setTabText(2, '关注的吧 ({c})'.format(c=data['follow_forum_count']))
            self.tabWidget.setTabText(3, '关注的人 ({c})'.format(c=data['follow']))
            self.tabWidget.setTabText(4, '粉丝列表 ({c})'.format(c=data['fans']))

            if not data['desp']:
                self.frame_6.hide()
            else:
                self.label_6.setText(cut_string(data['desp'], 50))

            sex_icon_path = ''
            sex_icon_desp = ''
            if data['sex'] == 1:
                sex_icon_path = 'ui/sex_male.png'
                sex_icon_desp = '男性'
            elif data['sex'] == 2:
                sex_icon_path = 'ui/sex_female.png'
                sex_icon_desp = '女性'
            if sex_icon_path:
                self.label_13.setToolTip(sex_icon_desp)
                self.label_13.setPixmap(QPixmap(sex_icon_path).scaled(20, 20, transformMode=Qt.SmoothTransformation))
            else:
                self.label_13.hide()

            have_flag_showed = False
            if data['is_banned']:
                self.frame_3.show()
                have_flag_showed = True
            if data['is_dashen']:
                self.frame_2.show()
                have_flag_showed = True
            if data['thread_reply_permission'] != 1:
                self.frame_5.show()
                have_flag_showed = True
                if data['thread_reply_permission'] == 5:
                    self.label_16.setText('由于隐私设置，只有粉丝可以评论该用户的贴子。')
                elif data['thread_reply_permission'] == 6:
                    self.label_16.setText('由于隐私设置，只有该用户关注的人可以评论该用户的贴子。')
            if data['follow_forums_show_permission'] != 1 or not self.bduss:
                self.frame_4.show()
                have_flag_showed = True
                if data['follow_forums_show_permission'] == 2:
                    self.label_15.setText('该用户设置关注吧列表仅好友可见。')
                elif data['follow_forums_show_permission'] == 3:
                    self.label_15.setText('该用户隐藏了关注吧列表。')
                elif not self.bduss:
                    self.label_15.setText('你还没有登录账号，无法获取关注吧列表，请先登录。')
            if have_flag_showed:
                self.frame_8.hide()

            # 隐藏动画，显示内容
            self.frame.show()
            self.tabWidget.show()
            self.frame_8.show()
            self.flash_shower.hide()

            # 查看当前用户主页或未登录时不显示操作按钮
            if profile_mgr.current_uid == self.real_user_id or not self.bduss:
                self.pushButton.hide()

            # 主信息加载完之后再加载
            for i in self.page.keys():
                self.get_list_info_async(i)

    def get_head_info_async(self):
        start_background_thread(self.get_head_info)

    def get_head_info(self):
        async def run_func():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    # 初始化数据
                    data = {'error': '',
                            'name': '',
                            'sex': 0,
                            'level': 0,
                            'portrait_pixmap': None,
                            'agree_c': 0,
                            'tieba_id': 0,
                            'post_c': 0,
                            'account_age': 0.0,
                            'ip': '',
                            'follow_forum_count': 0,
                            'follow': 0,
                            'fans': 0,
                            'is_dashen': False,
                            'is_banned': False,
                            'thread_reply_permission': 0,
                            'follow_forums_show_permission': 0,
                            'desp': '',
                            'bd_user_name': ''}

                    if self.user_id_portrait in ('00000000', 0):
                        data['error'] = '无法加载匿名用户的个人主页信息。'
                    else:
                        # 获取用户信息
                        user_info = await client.get_user_info(self.user_id_portrait, aiotieba.ReqUInfo.ALL)

                        # 判断是否出错
                        if user_info.err:
                            data['error'] = str(user_info.err)
                        else:
                            self.real_user_id = user_info.user_id
                            self.nick_name = data['name'] = user_info.nick_name_new
                            self.real_portrait = user_info.portrait
                            data['sex'] = user_info.gender
                            data['level'] = user_info.glevel
                            data['agree_c'] = user_info.agree_num
                            self.real_tieba_id = data['tieba_id'] = user_info.tieba_uid
                            data['account_age'] = user_info.age
                            data['ip'] = user_info.ip
                            data['follow_forum_count'] = user_info.forum_num
                            data['follow'] = user_info.follow_num
                            data['fans'] = user_info.fan_num
                            data['is_dashen'] = bool(user_info.is_god)
                            data['is_banned'] = bool(user_info.is_blocked)
                            data['thread_reply_permission'] = user_info.priv_reply
                            data['follow_forums_show_permission'] = user_info.priv_like
                            data['desp'] = user_info.sign
                            data['post_c'] = user_info.post_num
                            self.real_baidu_user_name = data['bd_user_name'] = user_info.user_name

                            pixmap = QPixmap()
                            pixmap.loadFromData(cache_mgr.get_portrait(user_info.portrait))
                            pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)
                            data['portrait_pixmap'] = pixmap

                            profile_mgr.add_view_history(2, {"uid": self.real_user_id, "portrait": self.real_portrait,
                                                             "nickname": self.nick_name})

                    self.set_head_info_signal.emit(data)

            except Exception as e:
                logging.log_exception(e)
                self.set_head_info_signal.emit({'error': '程序内部出错，请重试。'})

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()

    def scroll_load_list_info(self, tpe):
        if (tpe in self.listwidgets.keys() and
                self.listwidgets[tpe].verticalScrollBar().value() == self.listwidgets[
                    tpe].verticalScrollBar().maximum() and
                not self.page.get(tpe).get('loading')):
            self.get_list_info_async(tpe)

    def set_list_info_ui(self, data):
        from subwindow.thread_preview_item import ThreadView
        from subwindow.thread_reply_item import ReplyItem
        from subwindow.forum_item import ForumItem
        datas = data[1]
        if data[0] == 'thread':
            item = QListWidgetItem()
            widget = ThreadView(self.bduss, datas['thread_id'], datas['forum_id'], self.stoken)
            widget.set_thread_values(datas['view_count'], datas['agree_count'], datas['reply_count'],
                                     datas['repost_count'], datas['post_time'])
            widget.set_infos(datas['user_portrait_pixmap'], datas['user_name'], datas['title'], datas['content'],
                             None, datas['forum_name'])
            widget.set_picture(datas['view_pixmap'])
            widget.label.hide()
            widget.adjustSize()
            item.setSizeHint(widget.size())
            self.listWidget_4.addItem(item)
            self.listWidget_4.setItemWidget(item, widget)
        elif data[0] == 'reply':
            item = QListWidgetItem()
            widget = ReplyItem(self.bduss, self.stoken)

            widget.portrait = datas['portrait']
            widget.thread_id = datas['thread_id']
            widget.post_id = datas['post_id']
            widget.allow_home_page = False
            widget.subcomment_show_thread_button = True
            forum_link_html = '<a href=\"tieba_forum://{fid}\">{fname}吧</a>'.format(fname=datas['forum_name'],
                                                                                     fid=datas['forum_id'])
            forum_link_html = forum_link_html if datas['forum_name'] else '贴吧动态'
            widget.set_reply_text(
                '{sub_floor}在 {forum_link} 的主题贴 <a href=\"tieba_thread://{tid}\">{tname}</a> 下回复：'.format(
                    tname=datas['thread_title'],
                    tid=datas['thread_id'],
                    sub_floor='[楼中楼] ' if datas['is_subfloor'] else '[回复贴] ',
                    forum_link=forum_link_html))
            widget.setdatas(datas['user_portrait_pixmap'], datas['user_name'], False, datas['content'],
                            [], -1, datas['post_time_str'], '', -2, -1, -1, False)

            item.setSizeHint(widget.size())
            self.listWidget_2.addItem(item)
            self.listWidget_2.setItemWidget(item, widget)
        elif data[0] == 'follow_forum':
            item = QListWidgetItem()
            widget = ForumItem(datas['forum_id'], True, self.bduss, self.stoken, datas['forum_name'])
            widget.pushButton_2.hide()
            widget.set_info(datas['forum_pixmap'],
                            datas['forum_name'] + '吧',
                            datas['forum_desp'],
                            '{common_follow_flag}Lv.{level} | 经验值 {exp}'.format(
                                common_follow_flag='共同关注 | ' if datas['is_common_follow'] else '',
                                level=datas['level'],
                                exp=datas['exp']),
                            )
            widget.set_level_color(datas['level'])
            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        elif data[0] in ('follow', 'fans'):
            item = ExtListWidgetItem(self.bduss, self.stoken)
            item.user_portrait_id = datas['user_id']
            item.set_show_datas(datas['user_pixmap'], datas['user_name'])
            if data[0] == 'follow':
                self.listWidget_3.addItem(item)
            else:
                self.listWidget_5.addItem(item)

    def get_list_info_async(self, type_):
        if not self.page[type_]['loading'] and self.page[type_]['page'] != -1:
            start_background_thread(self.get_list_info, (type_,))

    def get_list_info(self, type_):
        async def run_func():
            self.page[type_]['loading'] = True
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if type_ == 'thread':
                        # 获取用户头像
                        user_head_pixmap = QPixmap()
                        thread_datas = await client.get_user_threads(self.user_id_portrait, self.page[type_]['page'])
                        for thread in thread_datas.objs:
                            # 初始化数据
                            if user_head_pixmap.isNull():  # 头像为空
                                user_head_pixmap.loadFromData(cache_mgr.get_portrait(thread.user.portrait))
                                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                           Qt.SmoothTransformation)
                            data = {'thread_id': thread.tid, 'forum_id': thread.fid, 'title': thread.title,
                                    'content': cut_string(make_thread_content(thread.contents.objs, True), 50),
                                    'author_portrait': thread.user.portrait, 'user_name': thread.user.nick_name_new,
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'forum_name': thread.fname if thread.fname else "贴吧动态",
                                    'view_pixmap': [], 'view_count': thread.view_num, 'agree_count': thread.agree,
                                    'reply_count': thread.reply_num, 'repost_count': thread.share_num,
                                    'post_time': thread.create_time}

                            # 找出所有预览图
                            preview_pixmap = []
                            for pic in thread.contents.imgs:
                                pic_hash = pic.hash
                                pixmap = QPixmap()
                                pixmap.loadFromData(cache_mgr.get_bd_hash_img(pic_hash))
                                pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio,
                                                       Qt.SmoothTransformation)
                                preview_pixmap.append(pixmap)
                            data['view_pixmap'] = preview_pixmap

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'reply':
                        # 获取新版昵称
                        nick_name = self.nick_name

                        # 初始化数据
                        user_head_pixmap = QPixmap()
                        post_list = []

                        post_datas = await client.get_user_posts(self.user_id_portrait, self.page[type_]['page'])
                        for t in post_datas.objs:
                            for st in t:
                                post_list.append(st)
                        post_list.sort(key=lambda k: k.create_time, reverse=True)  # 按发贴时间排序

                        for thread in post_list:
                            # 初始化数据
                            if user_head_pixmap.isNull():  # 头像为空
                                user_head_pixmap.loadFromData(cache_mgr.get_portrait(thread.user.portrait))
                                user_head_pixmap = user_head_pixmap.scaled(20, 20, Qt.KeepAspectRatio,
                                                                           Qt.SmoothTransformation)

                            # 获取吧名称
                            if thread.fid != 0:
                                forum_name = await client.get_fname(thread.fid)
                            else:
                                forum_name = ''

                            # 获取贴子标题
                            thread_info = await client.get_posts(thread.tid, pn=1, rn=0, comment_rn=0)
                            thread_title = thread_info.thread.title if thread_info.thread.title else "无法获取贴子标题，可能已被删除"

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
                            data = {'thread_id': thread.tid,
                                    'real_post_id': thread.pid,
                                    'post_id': pid,
                                    'is_subfloor': thread.is_comment,
                                    'forum_id': thread.fid,
                                    'forum_name': forum_name,
                                    'thread_title': thread_title,
                                    'content': cut_string(make_thread_content(thread.contents.objs, True), 50),
                                    'user_portrait_pixmap': user_head_pixmap,
                                    'portrait': thread.user.portrait,
                                    'user_name': nick_name,
                                    'post_time_str': timestr}
                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'follow_forum':
                        forum_list = await client.get_follow_forums(self.user_id_portrait, self.page[type_]['page'])
                        for f in forum_list.objs:
                            pixmap = QPixmap()
                            if f.avatar:
                                response = requests.get(f.avatar, headers=request_mgr.header)
                                if response.content:
                                    pixmap.loadFromData(response.content)
                                    pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                            data = {'forum_name': f.fname,
                                    'forum_id': f.fid,
                                    'forum_pixmap': pixmap,
                                    'forum_desp': f.slogan,
                                    'level': f.level,
                                    'exp': f.exp,
                                    'is_common_follow': f.is_common_follow}

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'follow':
                        follow_list = await client.get_follows(self.user_id_portrait, pn=self.page[type_]['page'])
                        for user in follow_list:
                            name = user.nick_name_new
                            if user.forum_admin_info:
                                name += f' ({user.forum_admin_info})'

                            data = {'user_name': name,
                                    'user_pixmap': None,
                                    'user_id': user.user_id}

                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(user.portrait))
                            user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)

                            data['user_pixmap'] = user_head_pixmap

                            self.set_list_info_signal.emit((type_, data))
                    elif type_ == 'fans':
                        fan_list = await client.get_fans(self.user_id_portrait, pn=self.page[type_]['page'])
                        for user in fan_list:
                            data = {'user_name': user.nick_name_new,
                                    'user_pixmap': None,
                                    'user_id': user.user_id}

                            user_head_pixmap = QPixmap()
                            user_head_pixmap.loadFromData(cache_mgr.get_portrait(user.portrait))
                            user_head_pixmap = user_head_pixmap.scaled(25, 25, Qt.KeepAspectRatio,
                                                                       Qt.SmoothTransformation)
                            data['user_pixmap'] = user_head_pixmap

                            self.set_list_info_signal.emit((type_, data))
            except Exception as e:
                logging.log_exception(e)
            else:
                self.page[type_]['page'] += 1
            finally:
                self.page[type_]['loading'] = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(run_func())

        start_async()
