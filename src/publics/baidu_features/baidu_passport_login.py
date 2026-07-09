"""百度账号登录相关类"""
import copy
import json
import os
import shutil
import sys
import time
import typing
import requests

from PyQt5.QtCore import pyqtSignal, Qt, QObject
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

import consts

from publics import qt_image, profile_mgr, request_mgr, account_mgr, app_logger, webview2
from publics.app_logger import log_exception, log_INFO
from publics.funcs import LoadingFlashWidget, start_background_thread, get_exception_string, get_dict_value_treely, \
    save_json

from subwindow import base_ui
from ui import qr_login, login_by_bduss


class QRLoginDialog(base_ui.WindowBaseQDialog, qr_login.Ui_Dialog):
    """扫码登录对话框"""
    qr_code_loaded = pyqtSignal(dict)
    qr_status_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))

        self.qr_sign = ''
        self.tangram_guid = ''
        self.is_qr_loading = False
        self.is_window_using = True
        self.is_login_succeed = False
        self.session = requests.Session()
        self.session.trust_env = True

        self.loading_widget = LoadingFlashWidget(caption='二维码加载中...')
        self.loading_widget.cover_widget(self.label_3)
        self.loading_widget.hide()
        self.qr_code_image = qt_image.MultipleImage()
        self.qr_code_image.currentPixmapChanged.connect(self.label_3.setPixmap)
        self.qr_code_image.imageLoadSucceed.connect(lambda: self.on_qrimg_loaded(True))
        self.qr_code_image.imageLoadFailed.connect(lambda: self.on_qrimg_loaded(False))

        self.qr_code_loaded.connect(self.load_qrcode_img)
        self.qr_status_changed.connect(self.on_login_state_changed)
        self.toolButton.clicked.connect(self.get_new_qr_code_async)

        self.start_looper()
        self.get_new_qr_code_async()

    def reset_theme(self):
        super().reset_theme()
        self.toolButton.setIcon(QIcon(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/refresh.png'))

    def closeEvent(self, a0):
        def do_close():
            self.is_window_using = False
            self.session.close()
            a0.accept()

        if self.is_login_succeed:
            do_close()
        else:
            if QMessageBox.information(self,
                                       '提示',
                                       '你确实要中止登录流程吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                do_close()
            else:
                a0.ignore()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def parse_response(self, text):
        text = text.replace(f'{self.tangram_guid}(', '')[0:-1]
        if text.endswith(')'):
            text = text[0:-1]
        return text

    def parse_response_qrbdusslogin(self, text):
        final_text = text.replace(f'bd__cbs__iou0dl(', '')[0:-1].replace(' ', '').replace(r'\&', '').replace('\'', '\"')
        return final_text

    def on_login_state_changed(self, data):
        if data['type'] == 1:
            self.label_3.setText('二维码已过期，请重新加载')
        elif data['type'] == 2:
            self.label_3.setText('扫码成功，请在手机上确认')
        elif data['type'] == 3:
            self.label_3.setText('你已取消扫码，二维码已失效，请重新加载')
        elif data['type'] == 4:
            self.label_3.setText('百度服务器要求短信验证，请使用网页登录')
        elif data['type'] == 5:
            QMessageBox.information(self, '登录成功',
                                    f'你已成功登录账号 {data["user"]}。\n可以在 设置-账号管理 中找到你的账号。',
                                    QMessageBox.Ok)
            self.close()

    def get_bduss_by_token(self, token):
        header = {
            'User-Agent': request_mgr.header['User-Agent'],
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'sec-ch-ua-platform': "\"Windows\"",
            'sec-ch-ua': "\"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
            'sec-ch-ua-mobile': "?0",
            'Sec-Fetch-Site': "same-site",
            'Sec-Fetch-Mode': "no-cors",
            'Sec-Fetch-Dest': "script",
            'Referer': "https://tieba.baidu.com/",
            'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Connection": "keep-alive",
        }

        timestamp = time.time()
        timestamp_second = int(timestamp)
        timestamp_ms = int(timestamp * 1000)
        params = {
            "v": str(timestamp_ms),
            "bduss": token,
            "u": "",
            "loginVersion": "v5",
            "qrcode": "1",
            "tpl": "tb",
            "maskId": "",
            "fileId": "",
            "apiver": "v3",
            "tt": str(timestamp_ms),
            "traceid": "",
            "time": str(timestamp_second),
            "alg": "v3",
            "elapsed": "10",
            "callback": "bd__cbs__iou0dl"
        }

        response = self.session.get(
            f'{request_mgr.SCHEME_HTTPS}{consts.BAIDU_PASSPORT_HOST}/v3/login/main/qrbdusslogin',
            headers=header, params=params)
        response.raise_for_status()
        json_text = self.parse_response_qrbdusslogin(response.text)
        jsonify_data = json.loads(json_text)
        response.close()

        return jsonify_data

    def handle_qr_status(self, resp):
        """处理扫码轮询逻辑"""
        if resp['errno'] == 1:
            # 没扫码，不操作
            pass
        elif resp['errno'] == 0:
            channel_v = resp['channel_v']
            channel_v_json = json.loads(channel_v)
            if channel_v_json['status'] == 1:
                # 已经扫码，等待手机确认
                self.qr_status_changed.emit({'type': 2})
            elif channel_v_json['status'] == 2:
                # 用户取消扫码登录
                self.qr_status_changed.emit({'type': 3})
            elif channel_v_json['status'] == 0:
                # 用户点击确定登录，登录成功
                login_token = channel_v_json['v']
                login_data = self.get_bduss_by_token(login_token)
                if int(login_data['data']['session']['needvcode']):
                    # 需要验证码
                    self.qr_status_changed.emit({'type': 4})
                else:
                    # 正常上号
                    bduss = login_data['data']['session']['bduss']
                    stoken = login_data['data']['session']['stokenList'].split('quot;')[1][3:]
                    result = self.write_user_info(bduss, stoken)
                    if result:
                        self.is_login_succeed = True
                        self.qr_status_changed.emit({'type': 5, 'user': result})
                    else:
                        self.qr_status_changed.emit({'type': 6})
        else:
            raise Exception(f'errno is {resp["errno"]}')

    def query_qr_status(self):
        header = {
            'User-Agent': request_mgr.header['User-Agent'],
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'sec-ch-ua-platform': "\"Windows\"",
            'sec-ch-ua': "\"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
            'sec-ch-ua-mobile': "?0",
            'Sec-Fetch-Site': "same-site",
            'Sec-Fetch-Mode': "no-cors",
            'Sec-Fetch-Dest': "script",
            'Referer': "https://tieba.baidu.com/",
            'Accept-Language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "Connection": "keep-alive",
        }

        timestamp = time.time()
        timestamp_ms = int(timestamp * 1000)
        params = {
            "channel_id": self.qr_sign,
            "tpl": "tb",
            "_sdkFrom": "1",
            "callback": self.tangram_guid,
            "apiver": "v3",
            "tt": str(timestamp_ms),
            '_': str(timestamp_ms),
        }

        response = self.session.get(f'{request_mgr.SCHEME_HTTPS}{consts.BAIDU_PASSPORT_HOST}/channel/unicast',
                                    headers=header, params=params)
        response.raise_for_status()
        json_text = self.parse_response(response.text)
        jsonify_data = json.loads(json_text)
        response.close()

        return jsonify_data

    def write_user_info(self, bduss, stoken):
        """向本地写入登录信息"""
        try:
            account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
            account = account_manager.add_account(bduss, stoken)
            return f"{account.nickname} ({account.uid})"
        except Exception as e:
            log_exception(e)
            return ''

    def start_looper(self):
        self.loop_thread = start_background_thread(self.status_looper)

    def status_looper(self):
        """二维码状态轮询器"""
        loop_count = 0
        current_sign = self.qr_sign

        while self.is_window_using:
            if current_sign != self.qr_sign:
                # 在二维码发生更改时，重新初始化数据
                loop_count = 0
                current_sign = self.qr_sign
                log_INFO(f'looping qr code {current_sign}')
            elif self.is_qr_loading or not current_sign:
                # 二维码在加载或没有初始化时不操作
                pass
            else:
                if loop_count >= 20:
                    # 在循环次数到上限时，通知二维码过期，重新初始化数据
                    self.qr_status_changed.emit({'type': 1})
                    loop_count = 0
                    current_sign = ''
                else:
                    # 执行轮询逻辑
                    try:
                        resp = self.query_qr_status()
                        log_INFO(f'time of loop qr code {current_sign} ok, json data {resp}')
                        self.handle_qr_status(resp)
                    except Exception as e:
                        app_logger.log_exception(e)
                    else:
                        loop_count += 1

            time.sleep(1)  # 休眠
        else:
            log_INFO(f'qr code loop thread will exit')

    def on_qrimg_loaded(self, success):
        if not success:
            self.label_3.setText('二维码图片加载失败')
        self.loading_widget.hide()
        self.is_qr_loading = False

    def load_qrcode_img(self, data):
        """已获取到token, 开始异步加载二维码图片"""
        if not data['success']:
            self.label_3.setText(data['info'])
            self.loading_widget.hide()
        else:
            self.qr_code_image.destroyImage()
            self.qr_code_image.setImageInfo(qt_image.ImageLoadSource.HttpLink,
                                            data['qr_code_url'])
            self.qr_code_image.loadImage()

    def get_new_qr_code_async(self):
        if not self.is_qr_loading:
            self.is_qr_loading = True
            self.loading_widget.show()
            start_background_thread(self.get_new_qr_code)

    def get_new_qr_code(self):
        emit_data = {'success': False, 'info': '', 'qr_code_url': ''}

        try:
            header = copy.deepcopy(request_mgr.header)
            del header['x-requested-with']
            header['Referer'] = 'https://tieba.baidu.com/'

            timestamp = time.time()
            timestamp_second = int(timestamp)
            timestamp_ms = int(timestamp * 1000)
            self.tangram_guid = f'tangram_guid_{timestamp_ms}'
            params = {
                "lp": "pc",
                "qrloginfrom": "pc",
                "apiver": "v3",
                "tt": str(timestamp_ms),
                "tpl": "tb",
                "logPage": f"traceId:pc_loginv5_{timestamp_second},logPage:loginv5",
                "callback": self.tangram_guid
            }

            response = self.session.get(f'{request_mgr.SCHEME_HTTPS}{consts.BAIDU_PASSPORT_HOST}/v2/api/getqrcode',
                                        headers=header, params=params)
            response.raise_for_status()
            json_text = self.parse_response(response.text)
            jsonify_data = json.loads(json_text)
            response.close()

            if jsonify_data['errno'] != 0:
                raise ValueError(f'Response status code is {jsonify_data["errno"]}')
            else:
                emit_data['qr_code_url'] = request_mgr.SCHEME_HTTP + jsonify_data['imgurl']
                self.qr_sign = jsonify_data['sign']
        except Exception as e:
            app_logger.log_exception(e)
            emit_data['success'] = False
            emit_data['info'] = get_exception_string(e)
            self.is_qr_loading = False
        else:
            emit_data['success'] = True
            emit_data['info'] = '获取成功'
        finally:
            self.qr_code_loaded.emit(emit_data)


class SeniorLoginDialog(base_ui.WindowBaseQDialog, login_by_bduss.Ui_Dialog):
    """高级登录对话框"""

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.pushButton_2.clicked.connect(self.close)
        self.pushButton.clicked.connect(self.save_account_info)

    def save_account_info(self):
        bduss = self.lineEdit.text()
        stoken = self.lineEdit_2.text()
        if len(bduss) == 192 and len(stoken) == 64:
            account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
            account_manager.add_account_async(bduss, stoken)
            self.close()
        else:
            QMessageBox.critical(self, '填写错误',
                                 '请正确填写 BDUSS 和 STOKEN 后再尝试登录。',
                                 QMessageBox.Ok)


class LoginWebView(base_ui.WindowBaseQDialog):
    """登录百度账号的webview"""

    class LoginRewriter(QObject, webview2.HttpDataRewriter):
        is_token_got = False
        tokenGot = pyqtSignal(dict)

        def onRequestCaught(self, url: str, method: str, header: typing.Dict[str, str],
                            content: typing.Optional[bytes]):
            if not self.is_token_got:
                tlist = [
                    'BDUSS',
                    'STOKEN']

                cookies_dic = self.parseCookieToDict(header['Cookie'])
                login_cookies = {}
                for k, v in cookies_dic.items():
                    if k in tlist:
                        login_cookies[k] = v

                if len(login_cookies.keys()) == len(tlist):
                    self.is_token_got = True
                    self.tokenGot.emit(login_cookies)

            return url, method, header, content

    islogin = False
    closeSignal = pyqtSignal()
    need_restart = False

    def __init__(self):
        super().__init__()
        self.setWindowTitle('登录百度账号')
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.closeSignal.connect(self.close)
        self.init_flash_widget()

        self.webview = webview2.QWebView2View()
        self.http_catcher = self.LoginRewriter()
        self.http_catcher.tokenGot.connect(self.start_login)
        self.webview.setParent(self)
        self.webview.newtabSignal.connect(self.open_in_current_page)
        self.profile = webview2.WebViewProfile(data_folder=f'{consts.datapath}/webview_data/default',
                                               user_agent=f'[default_ua] CLBTiebaDesktop/{consts.APP_VERSION_STR}',
                                               enable_link_hover_text=False,
                                               enable_zoom_factor=False,
                                               enable_error_page=False,
                                               enable_context_menu=False,
                                               enable_keyboard_keys=False,
                                               handle_newtab_byuser=False,
                                               http_rewriter={'*://tieba.baidu.com/*': self.http_catcher},
                                               enable_transparent_bg=get_dict_value_treely(
                                                   profile_mgr.local_config,
                                                   ['webview_settings', 'transparent_bg_color'], False))
        self.webview.setProfile(self.profile)
        self.webview.loadAfterRender('https://passport.baidu.com/v2/?login&u=https%3A%2F%2Ftieba.baidu.com')
        self.webview.initRender()

    def keyPressEvent(self, a0):
        if a0.key() == Qt.Key.Key_Escape:
            a0.ignore()
            self.close()

    def closeEvent(self, a0):
        if not self.islogin:
            if QMessageBox.information(self, '提示', '你确实要中止登录流程吗？',
                                       QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.webview.destroyWebviewUntilComplete()
                a0.accept()
            else:
                a0.ignore()
        else:
            if self.need_restart:
                QMessageBox.information(self, '提示',
                                        '账号已登录成功，为保证本地数据完全加载，你需要重启本软件。点击确定键关闭本软件，软件将在下次重新打开时自动应用你的设置。',
                                        QMessageBox.Ok)
                sys.exit(0)

            self.webview.destroyWebviewUntilComplete()
            self.flash_widget.hide()
            a0.accept()

    def resizeEvent(self, a0):
        self.webview.setGeometry(0, 0, self.width(), self.height())
        self.flash_widget.sync_parent_widget_size()

    def init_flash_widget(self):
        self.flash_widget = LoadingFlashWidget(caption='登录成功，即将跳转...')
        self.flash_widget.cover_widget(self, enable_filler=False)
        self.flash_widget.hide()

    def open_in_current_page(self, link):
        self.webview.load(link)

    def start_login(self, infos):
        self.webview.hide()
        self.flash_widget.show()
        start_background_thread(self.do_login, (infos,))

    def do_login(self, infos):
        self.webview.destroyWebviewUntilComplete()  # 先销毁webview
        time.sleep(5)

        account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
        account = account_manager.add_account(infos['BDUSS'], infos['STOKEN'], need_process_webview_udf=False)

        try:
            if os.path.isdir(f'{consts.datapath}/webview_data/{account.uid}'):  # 把旧的数据删掉
                shutil.rmtree(f'{consts.datapath}/webview_data/{account.uid}')
            os.rename(f'{consts.datapath}/webview_data/default', f'{consts.datapath}/webview_data/{account.uid}')
            os.mkdir(f'{consts.datapath}/webview_data/default')
        except PermissionError:
            self.need_restart = True
            save_json({'uid': str(account.uid)}, f'{consts.datapath}/d2id_flag')

        self.islogin = True
        self.closeSignal.emit()
