"""贴吧发贴相关类"""
import asyncio
import json
import time
import typing

import aiotieba

from PyQt5.QtCore import pyqtSignal, Qt, QEvent, QPoint, QObject
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

import consts
from publics import profile_mgr, top_toast_widget, app_logger, webview2
from publics.funcs import start_background_thread, get_exception_string, LoadingFlashWidget, get_dict_value_treely, \
    open_url_in_browser
from publics.baidu_features.tieba_apis import getRecomForumList, add_thread
from subwindow import base_ui, tieba_user_selector, tieba_emoji_selector
from subwindow.tieba_image_uploader import TiebaImageUploader
from ui import thread_publisher


class AddPostCaptchaWebView(base_ui.WindowBaseQDialog):
    """发贴遇到验证码时，显示验证码网页的webview"""

    class CaptchaDataGetter(QObject, webview2.HttpDataRewriter):
        is_captcha_token_got = False
        captchaTokenGot = pyqtSignal(dict)

        def onResponseCaught(self, url: str, statusCode: int, header: typing.Dict[str, str],
                             content: typing.Optional[bytes]):
            if statusCode == 200 and not self.is_captcha_token_got:
                json_data = json.loads(content.decode())
                if json_data['code'] == 0:
                    self.is_captcha_token_got = True
                    time.sleep(1)  # 休眠一秒，保证ui显示效果
                    self.captchaTokenGot.emit(json_data['data'])
                else:
                    app_logger.log_WARN(f'tieba add post captcha failed with json info {json_data}')
            else:
                app_logger.log_WARN(f'tieba add post captcha failed with HTTP status code {statusCode}')

            return statusCode, header, content

    def __init__(self, captcha_md5, h5_link):
        super().__init__()

        self.captcha_md5 = captcha_md5
        self.h5_link = h5_link
        self.captcha_success_json_info = None

        self.setWindowTitle('交互式发贴验证码')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.resize(800, 600)

        self.webview = webview2.QWebView2View()
        self.http_catcher = self.CaptchaDataGetter()
        self.http_catcher.captchaTokenGot.connect(self.on_captcha_succeed)
        self.webview.setParent(self)
        self.profile = webview2.WebViewProfile(data_folder=f'{consts.datapath}/webview_data/{profile_mgr.current_uid}',
                                               user_agent=f'[default_ua] CLBTiebaDesktop/{consts.APP_VERSION_STR}',
                                               enable_link_hover_text=False,
                                               enable_zoom_factor=False,
                                               enable_error_page=True,
                                               enable_context_menu=True,
                                               enable_keyboard_keys=True,
                                               handle_newtab_byuser=False,
                                               http_rewriter={
                                                   '*://seccaptcha.baidu.com/v1/webapi/verint/verify/*': self.http_catcher},
                                               enable_transparent_bg=get_dict_value_treely(
                                                   profile_mgr.local_config,
                                                   ['webview_settings', 'transparent_bg_color'], False))
        self.webview.setProfile(self.profile)
        self.webview.loadAfterRender(h5_link)
        self.webview.initRender()

    def resizeEvent(self, a0):
        self.webview.setGeometry(0, 0, self.width(), self.height())

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def closeEvent(self, a0):
        if not self.http_catcher.is_captcha_token_got:
            if QMessageBox.warning(self, '提示', '确认要取消本次验证码校验吗？如果取消验证，那么本次发贴操作将被取消。',
                                   QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.webview.destroyWebviewUntilComplete()
                a0.accept()
            else:
                a0.ignore()
        else:
            self.webview.destroyWebviewUntilComplete()
            a0.accept()

    def exec_window(self):
        self.exec()
        return self.captcha_md5, self.captcha_success_json_info

    def on_captcha_succeed(self, data):
        self.captcha_success_json_info = data
        self.close()


class ThreadPublisherWindow(base_ui.WindowBaseQDialog, thread_publisher.Ui_Dialog):
    """主题贴发布器"""
    forumInfoLoaded = pyqtSignal(dict)
    add_thread_signal = pyqtSignal(dict)
    forum_tab_exclude_list = ['热门', '最新', '视频', '吧主推荐', '吧友互助', '合辑', '精华', '吧友好物']

    def __init__(self, bduss, stoken, forum_name="", forum_id=0):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken

        self.forum_name = forum_name
        self.forum_id = forum_id
        self.forum_tab_index = {}
        self.latest_change_fname_ts = -1

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_elements()
        self.init_window_position()

        self.forumInfoLoaded.connect(self.on_forum_inited)
        self.comboBox.installEventFilter(self)
        self.toolButton.clicked.connect(self.reset_current_fname)
        self.pushButton_5.clicked.connect(self.show_image_switcher)
        self.pushButton_10.clicked.connect(self.show_emoji_selector)
        self.pushButton_6.clicked.connect(self.show_atuser_selector)
        self.add_thread_signal.connect(self.add_thread_ok_action)
        self.pushButton.clicked.connect(lambda: self.add_thread_async())

        self.init_forum_info_async()

    def closeEvent(self, a0):
        self.save_window_position()
        a0.accept()

    def showEvent(self, a0):
        super().showEvent(a0)

        # 未登录检测
        if not self.bduss:
            QMessageBox.critical(self, '尚未登录', '你还没有登录账号，不能使用发贴功能，请登录后再试。', QMessageBox.Ok)
            self.close()

    def eventFilter(self, source, event):
        if (event.type() == QEvent.KeyRelease and
                source is self.comboBox and
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):  # combobox 按下回车键
            self.reset_current_fname()  # 查询吧分区
        return super(type(self), self).eventFilter(source, event)  # 照常处理事件

    def reset_theme(self):
        super().reset_theme()
        self.flash_shower.reset_theme()

        bg_policy, font_policy = profile_mgr.get_theme_policy_string()
        self.toolButton.setIcon(QIcon(f'ui/icon_{font_policy}/forward.png'))

    def init_window_position(self):
        window_rect = profile_mgr.get_window_rects(type(self))
        if window_rect:
            self.setGeometry(window_rect[0],
                             window_rect[1],
                             window_rect[2],
                             window_rect[3])

    def save_window_position(self):
        profile_mgr.add_window_rects(type(self),
                                     self.x() + 1, self.y() + 31,
                                     self.width(), self.height(),
                                     False)

    def on_forum_inited(self, data):
        self.frame_2.setEnabled(True)
        self.label.setText('选择吧')
        self.label_2.setText('选择吧内分区')

        if data['error']:
            toast = top_toast_widget.ToastMessage('获取吧分区信息失败: ' + data['error'],
                                                  icon_type=top_toast_widget.ToastIconType.ERROR)
            self.toast_widget.showToast(toast)
        else:
            if data['call_type'] == 1:
                self.comboBox.clear()
                self.comboBox.addItems(data['preset_forum_list'])

                # 加载默认吧列表后立刻加载第一个吧的数据
                self.comboBox.setCurrentIndex(0)
                self.reset_current_fname()
            elif data['call_type'] == 2:
                self.comboBox.setCurrentText(self.forum_name)
                self.comboBox_2.clear()
                self.comboBox_2.addItems(self.forum_tab_index.keys())

    def reset_current_fname(self):
        self.forum_name = self.comboBox.currentText()
        self.init_forum_info_async()

    def init_forum_info_async(self):
        self.comboBox_2.clear()
        self.frame_2.setEnabled(False)

        if self.forum_name:
            self.label_2.setText('吧内分区加载中...')
        else:
            self.label.setText('默认吧列表加载中...')
        start_background_thread(self.init_forum_info)

    def init_forum_info(self):
        emit_data = {'error': '', 'call_type': 0, 'preset_forum_list': []}

        async def get_forum_page():
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                frs_info = await client.get_threads(self.forum_name)
                if frs_info.err:
                    raise frs_info.err

                self.forum_tab_index.clear()
                self.forum_tab_index['不选择分区'] = 0
                self.forum_tab_index.update(frs_info.tab_map)
                for k, v in tuple(self.forum_tab_index.items()):
                    if k in self.forum_tab_exclude_list and v != 0:
                        del self.forum_tab_index[k]

                self.forum_name = frs_info.forum.fname
                self.forum_id = frs_info.forum.fid

        def get_forum_list():
            resp = getRecomForumList(self.bduss, self.stoken)
            if resp['no'] != 0:
                raise ValueError(f"{resp['error']} (错误代码 {resp['no']})")
            else:
                emit_data['preset_forum_list'] = list(f['name'] for f in resp['data']['forum_list'])

        def start_async(func):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(func())

        try:
            if self.forum_name:
                emit_data['call_type'] = 2
                start_async(get_forum_page)
            else:
                emit_data['call_type'] = 1
                get_forum_list()
        except Exception as e:
            app_logger.log_exception(e)
            emit_data['error'] = get_exception_string(e)
        finally:
            self.forumInfoLoaded.emit(emit_data)

    def init_elements(self):
        self.flash_shower = LoadingFlashWidget(True, '正在发贴中，请稍等...')
        self.flash_shower.cover_widget(self)
        self.flash_shower.hide()

        self.toast_widget = top_toast_widget.TopToaster()
        self.toast_widget.setCoverWidget(self)

    def show_image_switcher(self):
        dialog = TiebaImageUploader()
        image_list = dialog.exec_window()
        if image_list:
            insert_text = '\n'.join(f'#(pic,{i.image_id},{i.origin_width},{i.origin_height})' for i in image_list)
            self.textEdit.insertPlainText(insert_text)

        dialog.deleteLater()

    def show_atuser_selector(self):
        selector = tieba_user_selector.TiebaUserSelector.get_instance()

        btn = self.pushButton_5
        bt_pos = btn.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x(), bt_pos.y() + btn.height() + 8)
        selected_user = selector.pop_selector(show_pos)
        if selected_user:
            self.textEdit.insertPlainText(f"#(at, {selected_user['portrait']}, {selected_user['user_name']})")

    def show_emoji_selector(self):
        selector = tieba_emoji_selector.TiebaEmojiSelector.get_instance()

        btn = self.pushButton_5
        bt_pos = btn.mapToGlobal(QPoint(0, 0))
        show_pos = QPoint(bt_pos.x(), bt_pos.y() + btn.height() + 8)

        emoji_id, emoji_text = selector.pop_selector(show_pos)
        if emoji_text:
            self.textEdit.insertPlainText(emoji_text)

    def add_thread_ok_action(self, msg):
        if msg['success']:
            QMessageBox.information(self, '发贴成功',
                                    '恭喜你，这条主题贴已发布成功！\n点击确定键将打开贴子窗口，你可以立即查看刚才发布的贴子。',
                                    QMessageBox.Ok)
            open_url_in_browser(f'tieba_thread://{msg["thread_info"]["thread_id"]}')
            self.close()
        else:
            self.flash_shower.hide()

            toast = top_toast_widget.ToastMessage()
            toast.title = msg['text']
            toast.icon_type = top_toast_widget.ToastIconType.ERROR

            self.toast_widget.showToast(toast)

            # 验证码模式特判
            if msg['is_captcha']:
                md5 = msg['captcha_info']['md5']
                h5_link = msg['captcha_info']['link']

                dialog = AddPostCaptchaWebView(md5, h5_link)
                md5, json_info = dialog.exec_window()
                if json_info:
                    self.add_thread_async(md5, json_info)
                else:
                    self.toast_widget.showToast(top_toast_widget.ToastMessage('用户已取消交互验证',
                                                                              icon_type=top_toast_widget.ToastIconType.INFORMATION))

    def add_thread_async(self, captcha_md5=None, captcha_json_info=None):
        if not self.textEdit.toPlainText() and not self.lineEdit.text():
            self.toast_widget.showToast(top_toast_widget.ToastMessage(title='请输入正文内容后再发布贴子',
                                                                      icon_type=top_toast_widget.ToastIconType.INFORMATION))
        elif not self.forum_name:
            self.toast_widget.showToast(top_toast_widget.ToastMessage(title='请先选择要发贴的吧',
                                                                      icon_type=top_toast_widget.ToastIconType.INFORMATION))
        elif not self.bduss:
            self.toast_widget.showToast(top_toast_widget.ToastMessage(title='请登录后再发贴',
                                                                      icon_type=top_toast_widget.ToastIconType.INFORMATION))
        else:
            if not (captcha_md5 and captcha_json_info):
                show_string = ('发布主题贴功能目前还处于测试阶段。\n'
                               '使用本软件发贴可能会遇到发贴失败、反复弹验证码等情况，甚至可能导致你的账号被全吧封禁，造成不必要损失。\n'
                               '目前我们不建议使用此方法进行发贴，我们建议你使用官方网页版进行发贴。\n确认要继续吗？')
                msgbox = QMessageBox(QMessageBox.Warning, '发贴风险提示', show_string, parent=self)
                msgbox.setStandardButtons(QMessageBox.Help | QMessageBox.Yes | QMessageBox.No)
                msgbox.button(QMessageBox.Help).setText("去网页发贴")
                msgbox.button(QMessageBox.Yes).setText("无视风险，继续发贴")
                msgbox.button(QMessageBox.No).setText("取消发贴")
                r = msgbox.exec()
                flag = r == QMessageBox.Yes
                if r == QMessageBox.Help:
                    url = f'https://tieba.baidu.com/f?kw={self.forum_name}'
                    open_url_in_browser(url)
            else:
                flag = True

            if flag:
                self.flash_shower.show()
                start_background_thread(self.add_thread, args=(captcha_md5, captcha_json_info))

    def add_thread(self, captcha_md5, captcha_json_info):
        emit_data = {'success': False,
                     'text': '',
                     'is_captcha': False,
                     'captcha_info': {'md5': '', 'link': ''},
                     "thread_info": {"thread_id": 0,
                                     "forum_id": 0,
                                     "first_post_id": 0}
                     }
        try:
            tab_name = self.comboBox_2.currentText()
            tab_id = self.forum_tab_index.get(tab_name, 0)
            tab_name = '' if tab_id == 0 else tab_name

            content_statement = self.comboBox_3.currentText()
            content_statement = '' if self.comboBox_3.currentIndex() == 0 else content_statement

            hide_thread = self.checkBox.isChecked()
            is_help = self.checkBox_2.isChecked()

            result = add_thread(self.bduss, self.stoken,
                                self.forum_id, self.lineEdit.text(), self.textEdit.toPlainText(),
                                tab_name, tab_id,
                                hide_thread, content_statement, is_help,
                                captcha_md5, captcha_json_info)

            if result.error.errorno == 0:
                emit_data['success'] = True

                emit_data['thread_info']['thread_id'] = result.data.tid
                emit_data['thread_info']['forum_id'] = result.data.forum_id
                emit_data['thread_info']['first_post_id'] = result.data.pid
            elif result.data.info.need_vcode == '1':
                emit_data['success'] = False
                emit_data['is_captcha'] = True
                emit_data['captcha_info']['md5'] = result.data.info.vcode_md5
                emit_data['captcha_info']['link'] = result.data.info.vcode_pic_url
                emit_data['text'] = '服务器要求安全风控验证，请在弹出的验证网页中完成验证。如多次弹出验证，建议使用官方客户端发贴'
            else:
                emit_data['success'] = False
                emit_data['text'] = f'{result.error.errmsg} (错误代码 {result.error.errorno})'
        except Exception as e:
            app_logger.log_exception(e)
            emit_data['success'] = False
            emit_data['text'] = get_exception_string(e)
        finally:
            self.add_thread_signal.emit(emit_data)
