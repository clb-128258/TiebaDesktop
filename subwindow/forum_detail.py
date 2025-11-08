import asyncio
import time

import aiotieba
import pyperclip
import requests
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QDialog, QListWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QListWidgetItem, \
    QTableWidgetItem

from publics import qt_window_mgr, request_mgr, cache_mgr
from publics.funcs import LoadingFlashWidget, start_background_thread, http_downloader, ExtTreeWidgetItem, \
    open_url_in_browser
import publics.logging as logging

from ui import forum_detail


class ForumDetailWindow(QDialog, forum_detail.Ui_Dialog):
    """吧详细信息窗口，可显示吧详细信息、吧务信息、等级排行榜"""
    set_main_info_signal = pyqtSignal(dict)
    action_ok_signal = pyqtSignal(dict)

    forum_bg_link = ''
    forum_name = ''
    forum_atavar_link = ''
    is_followed = False

    def __init__(self, bduss, stoken, forum_id, default_index=0):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken
        self.forum_id = forum_id

        self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.tableWidget.setEditTriggers(QListWidget.NoEditTriggers)
        self.tableWidget.verticalHeader().setVisible(False)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_load_flash()

        self.set_main_info_signal.connect(self.ui_set_main_info)
        self.action_ok_signal.connect(self.action_ok_slot)
        self.pushButton_5.clicked.connect(self.close)
        self.treeWidget.itemDoubleClicked[QTreeWidgetItem, int].connect(self.open_user_homepage)
        self.pushButton_4.clicked.connect(self.save_bg_image)
        self.pushButton_6.clicked.connect(lambda: pyperclip.copy(self.forum_bg_link))
        self.pushButton_7.clicked.connect(lambda: self.show_big_picture(self.forum_atavar_link))
        self.pushButton.clicked.connect(lambda: self.do_action_async('unfollow' if self.is_followed else 'follow'))
        self.pushButton_2.clicked.connect(lambda: self.do_action_async('sign'))
        self.pushButton_8.clicked.connect(self.refresh_main_data)
        self.label_15.linkActivated.connect(open_url_in_browser)

        self.tabWidget.setCurrentIndex(default_index)
        self.loading_widget.show()
        self.get_main_info_async()

    def closeEvent(self, a0):
        self.loading_widget.hide()
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_load_flash(self):
        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self)

    def refresh_main_data(self):
        self.loading_widget.set_caption(True, '正在重新加载数据...')
        self.loading_widget.show()
        self.get_main_info_async()

    def save_bg_image(self):
        if self.forum_bg_link:
            path, tpe = QFileDialog.getSaveFileName(self, '保存图片', '',
                                                    'JPG 图片文件 (*.jpg;*.jpeg)')
            if path:
                start_background_thread(http_downloader, (path, self.forum_bg_link))

    def open_user_homepage(self, item, column):
        if isinstance(item, ExtTreeWidgetItem):
            from subwindow.user_home_page import UserHomeWindow
            user_home_page = UserHomeWindow(self.bduss, self.stoken, item.user_portrait_id)
            qt_window_mgr.add_window(user_home_page)

    def show_big_picture(self, link):
        from subwindow.net_imageview import NetworkImageViewer
        opic_view = NetworkImageViewer(link)
        opic_view.closed.connect(lambda: qt_window_mgr.del_window(opic_view))
        qt_window_mgr.add_window(opic_view)

    def action_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
            self.refresh_main_data()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)

    def do_action_async(self, action_type=""):
        run_flag = True
        if action_type == 'unfollow':
            if QMessageBox.warning(self, '取关贴吧', f'确定不再关注 {self.forum_name}吧？',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                run_flag = False

        if run_flag:
            start_background_thread(self.do_action, (action_type,))

    def do_action(self, action_type=""):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                logging.log_INFO(f'do forum {self.forum_id} action type {action_type}')
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    if action_type == 'follow':
                        r = await client.follow_forum(self.forum_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '关注成功'
                            turn_data['text'] = f'已成功关注 {self.forum_name}吧。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'unfollow':
                        r = await client.unfollow_forum(self.forum_id)
                        if r:
                            turn_data['success'] = True
                            turn_data['title'] = '取消关注成功'
                            turn_data['text'] = f'已成功取消关注 {self.forum_name}吧。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '取消关注失败'
                            turn_data['text'] = f'{r.err}'
                    elif action_type == 'sign':
                        tsb_resp = request_mgr.run_post_api('/c/s/login', request_mgr.calc_sign(
                            {'_client_version': request_mgr.TIEBA_CLIENT_VERSION, 'bdusstoken': self.bduss}),
                                                            use_mobile_header=True,
                                                            host_type=2)
                        tbs = tsb_resp["anti"]["tbs"]

                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'fid': self.forum_id,
                            'kw': self.forum_name,
                            'stoken': self.stoken,
                            'tbs': tbs,
                        }
                        r = request_mgr.run_post_api('/c/c/forum/sign',
                                                     payloads=request_mgr.calc_sign(payload),
                                                     bduss=self.bduss, stoken=self.stoken,
                                                     use_mobile_header=True,
                                                     host_type=2)
                        if r['error_code'] == '0':
                            user_sign_rank = r['user_info']['user_sign_rank']
                            sign_bonus_point = r['user_info']['sign_bonus_point']

                            turn_data['success'] = True
                            turn_data['title'] = '签到成功'
                            turn_data[
                                'text'] = f'{self.forum_name}吧 已签到成功。\n本次签到经验 +{sign_bonus_point}，你是今天本吧第 {user_sign_rank} 个签到的用户。'
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '签到失败'
                            turn_data['text'] = f'{r["error_msg"]} (错误代码 {r["error_code"]})'
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

    def ui_set_main_info(self, datas):
        if not datas['err_info']:
            self.loading_widget.hide()
            self.forum_name = datas['forum_name']
            self.label_2.setText(datas['forum_name'] + '吧')
            self.label.setPixmap(datas['forum_pixmap'])
            self.label_11.setText(f'吧 ID：{self.forum_id}')
            self.label_3.setText('关注数：' + str(datas['follow_c']))
            self.label_4.setText('贴子数：' + str(datas['thread_c']))
            self.label_12.setText('吧分类：' + datas['forum_volume'])
            self.label_13.setText('主题贴数：{0}'.format(str(datas['main_thread_c'])))
            self.textBrowser.setHtml(datas['forum_rule_html'])
            self.label_15.setText(f'<html><body>'
                                  f'<p>很抱歉，出于加载时的性能问题，该功能已被停用。<br/>该页面将在将来的版本中删除。<br>'
                                  f'你可以到 <a href="https://tieba.baidu.com/f/like/furank?kw={self.forum_name}&ie=utf-8">牛人排行榜</a> '
                                  f'中查看{self.forum_name}吧的等级排行榜。</p>'
                                  f'</body></html>')

            forum_desp_text = ''
            if datas['forum_desp']:
                forum_desp_text += datas['forum_desp']
            if datas['forum_desp_ex']:
                forum_desp_text += '\n' + datas['forum_desp_ex']
            if not forum_desp_text:
                self.label_5.hide()
            else:
                self.label_5.setText(forum_desp_text)

            if self.bduss:
                self.is_followed = datas['follow_info']['isfollow']
                if datas['follow_info']['isfollow']:
                    self.pushButton.setText('取消关注')
                else:
                    self.pushButton.setText('关注')
                self.label_6.setText(f'你已经关注了本吧。' if datas['follow_info'][
                    'isfollow'] else f'你还没有关注{self.forum_name}吧，不妨考虑一下？')

                if datas['follow_info']['isfollow']:
                    ts = time.time() - datas["follow_info"]["follow_day"] * 86400
                    timeArray = time.localtime(ts)
                    follow_date_str = time.strftime("(大约是在 %Y年%m月%d日 那天关注的)", timeArray)
                else:
                    follow_date_str = ''
                self.label_7.setText('等级：' + str(datas['follow_info']['level']))
                self.label_8.setText('等级头衔：' + datas['follow_info']['level_flag'])
                self.label_25.setText(
                    f'关注天数：{datas["follow_info"]["follow_day"]} 天 {follow_date_str}')
                self.label_26.setText(f'总发贴数：{datas["follow_info"]["total_thread_num"]}')
                self.label_27.setText(f'今日发贴回贴数：{datas["follow_info"]["today_post_num"]}')

                if datas['follow_info']['isSign']:
                    self.pushButton_2.setEnabled(False)
                    self.pushButton_2.setText('已签到')
                self.label_9.setText(
                    f'{datas["follow_info"]["exp"]} / {datas["follow_info"]["next_exp"]}，距离下一等级还差 {datas["follow_info"]["next_exp"] - datas["follow_info"]["exp"]} 经验值')
                self.progressBar.setRange(0, datas["follow_info"]["next_exp"])
                self.progressBar.setValue(datas["follow_info"]["exp"])

                self.label_10.setText(f'共计签到天数：{datas["follow_info"]["total_sign_count"]}')
                self.label_17.setText(f'连签天数：{datas["follow_info"]["continuous_sign_count"]}')
                self.label_18.setText(f'漏签天数：{datas["follow_info"]["forget_sign_count"]}')
                self.label_28.setText(f'今日签到名次：第 {datas["follow_info"]["today_sign_rank"]} 个签到')
            else:
                self.pushButton.hide()
                self.label_6.setText('你还没有登录，登录后即可查看自己的信息。')
                self.groupBox.hide()

            if datas['bg_pic_info']['pixmap']:
                self.label_14.setPixmap(datas['bg_pic_info']['pixmap'])
            else:
                self.label_14.setText('本吧没有背景图片。')

            for i in datas['friend_forum_list']:
                from subwindow.forum_item import ForumItem
                item = QListWidgetItem()
                widget = ForumItem(i['forum_id'], True, self.bduss, self.stoken, i['forum_name'])
                widget.set_info(i['headpix'], i['forum_name'] + '吧', '')
                widget.pushButton_2.hide()
                widget.adjustSize()
                item.setSizeHint(widget.size())

                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, widget)

            bawu_types = {}
            for i in datas['bawu_info']:
                if not bawu_types.get(i['type']):
                    item = QTreeWidgetItem()
                    item.setText(0, i['type'])
                    self.treeWidget.addTopLevelItem(item)
                    bawu_types[i['type']] = item

                item = ExtTreeWidgetItem(self.bduss, self.stoken)
                item.user_portrait_id = i['portrait']
                item.setIcon(0, QIcon(i['portrait_pixmap']))
                item.setText(0, i['name'])
                item.setText(1, str(i['level']))
                item.setText(2, i['type'])
                bawu_types[i['type']].addChild(item)

            count = 0
            for i in datas['forum_level_value_index']:
                self.tableWidget.insertRow(count)
                self.tableWidget.setItem(count, 0, QTableWidgetItem(str(count + 1)))
                self.tableWidget.setItem(count, 1, QTableWidgetItem(i['name']))
                self.tableWidget.setItem(count, 2, QTableWidgetItem(str(i['score'])))
                count += 1
            self.tableWidget.setHorizontalHeaderLabels(('等级', '头衔', '所需经验值'))

        else:
            QMessageBox.critical(self, '吧信息加载异常', datas['err_info'], QMessageBox.Ok)
            self.close()

    def get_main_info_async(self):
        self.treeWidget.clear()
        self.listWidget.clear()
        self.tableWidget.clear()
        self.tableWidget.setRowCount(0)
        start_background_thread(self.get_main_info)

    def get_main_info(self):
        async def dosign():
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    # 初始化数据
                    data = {'forum_name': '', 'has_bawu': False, 'bawu_info': [], 'forum_pixmap': None,
                            'forum_desp': '', 'thread_c': 0, 'follow_c': 0, 'main_thread_c': 0,
                            'follow_info': {'isfollow': False, 'level': 0, 'exp': 0, 'level_flag': '', 'isSign': False,
                                            'next_exp': 0, 'total_sign_count': 0, 'continuous_sign_count': 0,
                                            'forget_sign_count': 0, 'follow_day': 0, 'today_sign_rank': 0,
                                            'total_thread_num': 0, 'today_post_num': 0},
                            'forum_volume': '', 'err_info': '', 'friend_forum_list': [],
                            'bg_pic_info': {'url': '', 'pixmap': None}, 'forum_desp_ex': '', 'forum_rule_html': '',
                            'forum_level_value_index': []}

                    async def get_forum_desp_ex():
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'forum_id': str(self.forum_id),
                            'is_newfrs': '1',
                            'stoken': self.stoken,
                        }
                        ex_forum_info = request_mgr.run_post_api('/c/f/forum/getforumdetail',
                                                                 request_mgr.calc_sign(payload), bduss=self.bduss,
                                                                 stoken=self.stoken, use_mobile_header=True,
                                                                 host_type=2)
                        if forum_content := ex_forum_info["forum_info"].get("content"):
                            data['forum_desp_ex'] = forum_content[0]['text']

                        data['follow_info']['isfollow'] = bool(int(ex_forum_info['forum_info']['is_like']))
                        data['follow_info']['exp'] = int(ex_forum_info['forum_info']["cur_score"])
                        data['follow_info']['level'] = int(ex_forum_info['forum_info']["level_id"])
                        data['follow_info']['level_flag'] = ex_forum_info['forum_info']["level_name"]
                        data['follow_info']['next_exp'] = int(ex_forum_info['forum_info']["levelup_score"])
                        self.forum_atavar_link = ex_forum_info['forum_info']["avatar_origin"]

                    async def get_forum_rule():
                        payload = {
                            'BDUSS': self.bduss,
                            '_client_type': "2",
                            '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                            'forum_id': str(self.forum_id),
                            'stoken': self.stoken,
                        }
                        ex_rule = request_mgr.run_post_api('/c/f/forum/forumRuleDetail',
                                                           request_mgr.calc_sign(payload), bduss=self.bduss,
                                                           stoken=self.stoken, use_mobile_header=True,
                                                           host_type=2)
                        html_code = '<html>'
                        if ex_rule['forum_rule_id']:
                            html_code += f'<h2>{ex_rule["title"]}</h2>'
                            html_code += f'<h3>{ex_rule["forum"]["forum_name"]}吧吧务于 {ex_rule["publish_time"]} 修订</h3>'
                            html_code += f'<h4>前言</h4><p>{ex_rule["preface"]}</p>'
                            r_count = 0  # 前缀下标

                            for rule in ex_rule.get('rules', []):  # 纯自定义吧规
                                title = rule['title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'

                                for single_sub_rule_item in rule['content']:
                                    if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                        content = single_sub_rule_item['text']
                                        if content != '\n':
                                            sub_html_code += f'<p>{content}</p>'
                                    elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                        sub_html_code += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'

                                html_code += sub_html_code

                            for rule in ex_rule.get('default_rules', []):  # 默认吧规内容
                                title = ex_rule['forum_rule_conf']['first_level_index_list'][r_count] + rule[
                                    'title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'
                                sub_prefix_count = 0  # 前缀下标
                                for sub_rule in rule['content_list']:  # 子条目
                                    pfix = ex_rule['forum_rule_conf']['second_level_index_list'][
                                        sub_prefix_count]  # 数字前缀
                                    content = ''  # 正文内容
                                    for single_sub_rule_item in sub_rule['content']:
                                        if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                            content += single_sub_rule_item['text']
                                        elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                            content += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'
                                    sub_html_code += f'<p>{pfix}{content}</p>'
                                    sub_prefix_count += 1
                                html_code += sub_html_code
                                r_count += 1

                            for rule in ex_rule.get('new_rules', []):  # 混合的自定义吧规
                                title = ex_rule['forum_rule_conf']['first_level_index_list'][r_count] + rule[
                                    'title']  # 标题
                                sub_html_code = f'<h4>{title}</h4>'
                                sub_prefix_count = 0  # 前缀下标
                                for sub_rule in rule['content_list']:  # 子条目
                                    pfix = ex_rule['forum_rule_conf']['second_level_index_list'][
                                        sub_prefix_count]  # 数字前缀
                                    content = ''  # 正文内容
                                    for single_sub_rule_item in sub_rule['content']:
                                        if single_sub_rule_item['type'] == '0':  # 是文本就添加
                                            content += single_sub_rule_item['text']
                                        elif single_sub_rule_item['type'] == '1':  # 是链接添加html代码
                                            content += f'<a href=\"{single_sub_rule_item["link"]}\">{single_sub_rule_item["text"]}</a>'
                                    sub_html_code += f'<p>{pfix}{content}</p>'
                                    sub_prefix_count += 1
                                html_code += sub_html_code
                                r_count += 1

                            html_code += '</html>'
                            data['forum_rule_html'] = html_code
                        else:
                            data['forum_rule_html'] = '<html><h2>很抱歉，本吧吧主并没有在此设置吧规。</h2></html>'

                    async def get_sign_info():
                        if self.bduss:
                            # 在登录情况下，获取签到信息
                            payload = {
                                'BDUSS': self.bduss,
                                '_client_type': "2",
                                '_client_version': request_mgr.TIEBA_CLIENT_VERSION,
                                'forum_ids': str(self.forum_id),
                                'from': "frs",
                                'stoken': self.stoken,
                            }
                            resp_sign_info = request_mgr.run_post_api('/c/f/forum/getUserSign',
                                                                      request_mgr.calc_sign(payload), bduss=self.bduss,
                                                                      stoken=self.stoken, use_mobile_header=True,
                                                                      host_type=2)

                            # 整理签到信息
                            data['follow_info']['isSign'] = bool(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["is_sign_in"])
                            data['follow_info']['total_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["cout_total_sign_num"])
                            data['follow_info']['continuous_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["cont_sign_num"])
                            data['follow_info']['forget_sign_count'] = int(
                                resp_sign_info["data"]['forum'][0]["sign_in_info"]["user_info"]["miss_sign_num"])

                    async def get_user_forum_level_info():
                        if self.bduss:
                            # 在登录情况下，获取新版我在本吧信息
                            params = {
                                "_client_type": "2",
                                "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                                "BDUSS": self.bduss,
                                "stoken": self.stoken,
                                "forum_id": str(self.forum_id),
                                "subapp_type": "hybrid"
                            }
                            resp_mytb_info = request_mgr.run_get_api('/c/f/forum/getUserForumLevelInfo',
                                                                     bduss=self.bduss,
                                                                     stoken=self.stoken, use_mobile_header=True,
                                                                     host_type=1, params=params)

                            # 整理我在本吧信息
                            data['follow_info']['follow_day'] = int(
                                resp_mytb_info["data"]['user_forum_info']["follow_days"])
                            data['follow_info']['today_sign_rank'] = int(
                                resp_mytb_info["data"]['user_forum_info']["day_sign_no"])
                            data['follow_info']['total_thread_num'] = int(
                                resp_mytb_info["data"]['user_forum_info']["thread_num"])
                            data['follow_info']['today_post_num'] = int(
                                resp_mytb_info["data"]['user_forum_info']["day_post_num"])
                            data['forum_level_value_index'] = resp_mytb_info["data"]['level_info']["list"]

                    async def get_forum_bg():
                        # 获取吧背景图片
                        self.forum_bg_link = url = forum_info.background_image_url
                        data['bg_pic_info']['url'] = url
                        if url:
                            forum_bg_pixmap = QPixmap()
                            response = requests.get(url, headers=request_mgr.header)
                            if response.content:
                                forum_bg_pixmap.loadFromData(response.content)
                                data['bg_pic_info']['pixmap'] = forum_bg_pixmap

                    async def get_forums_heads():
                        # 获取友情吧信息
                        if forum_info.friend_forums:
                            for i in forum_info.friend_forums:
                                single_ff_info = {'forum_name': i.fname, 'forum_id': i.fid, 'headpix': None}
                                pixmap = QPixmap()
                                response = requests.get(i.small_avatar, headers=request_mgr.header)
                                if response.content:
                                    pixmap.loadFromData(response.content)
                                    pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                                           Qt.SmoothTransformation)
                                    single_ff_info['headpix'] = pixmap
                                data['friend_forum_list'].append(single_ff_info)

                    async def get_self_forum_head():
                        # 获取吧头像
                        forum_pixmap = QPixmap()
                        response = requests.get(forum_info.small_avatar, headers=request_mgr.header)
                        if response.content:
                            forum_pixmap.loadFromData(response.content)
                            forum_pixmap = forum_pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            data['forum_pixmap'] = forum_pixmap

                    async def get_bawu_infos():
                        # 有吧务获取吧务信息
                        if forum_info.has_bawu:
                            bawu_info = await client.get_bawu_info(self.forum_id)
                            bawu_iter_index = {'大吧主': bawu_info.admin,
                                               '小吧主': bawu_info.manager,
                                               '语音小编': bawu_info.voice_editor,
                                               '图片小编': bawu_info.image_editor,
                                               '视频小编': bawu_info.video_editor,
                                               '广播小编': bawu_info.broadcast_editor,
                                               '吧刊主编': bawu_info.journal_chief_editor,
                                               '吧刊小编': bawu_info.journal_editor,
                                               '职业吧主': bawu_info.profess_admin,
                                               '第四吧主': bawu_info.fourth_admin}

                            for k, v in bawu_iter_index.items():
                                for bawu in v:
                                    pixmap = QPixmap()
                                    pixmap.loadFromData(cache_mgr.get_portrait(bawu.portrait))
                                    pixmap = pixmap.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                                    data['bawu_info'].append(
                                        {'name': bawu.nick_name_new, 'level': bawu.level, 'type': k,
                                         'portrait': bawu.portrait, 'portrait_pixmap': pixmap})

                    # 获取吧信息
                    forum_info = await client.get_forum(self.forum_id)

                    if forum_info.err:
                        if isinstance(forum_info.err, aiotieba.exception.TiebaServerError):
                            data['err_info'] = f'{forum_info.err.msg} (错误代码 {forum_info.err.code})'
                        else:
                            data['err_info'] = str(forum_info.err)
                    else:
                        # 整理吧信息
                        data['forum_name'] = forum_info.fname
                        data['has_bawu'] = forum_info.has_bawu
                        data['forum_desp'] = forum_info.slogan
                        data['thread_c'] = forum_info.post_num
                        data['follow_c'] = forum_info.member_num
                        data['main_thread_c'] = forum_info.thread_num
                        data['forum_volume'] = f'{forum_info.category} - {forum_info.subcategory}'

                        await asyncio.gather(get_forum_rule(),
                                             get_forum_desp_ex(),
                                             get_sign_info(),
                                             get_forum_bg(),
                                             get_forums_heads(),
                                             get_bawu_infos(),
                                             get_self_forum_head(),
                                             get_user_forum_level_info(),
                                             return_exceptions=True)

                    self.set_main_info_signal.emit(data)
            except Exception as e:
                logging.log_exception(e)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()
