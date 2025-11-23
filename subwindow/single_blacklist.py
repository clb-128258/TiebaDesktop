import asyncio

import aiotieba
from PyQt5.QtGui import QIcon, QPixmap

# 引入protobuf
from proto.GetUserBlackInfo import GetUserBlackInfoReqIdl_pb2, GetUserBlackInfoResIdl_pb2

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QMessageBox

from publics import qt_window_mgr, profile_mgr, cache_mgr, request_mgr
from publics.funcs import LoadingFlashWidget, start_background_thread
import publics.logging as logging
from ui import user_blacklist_setter


class SingleUserBlacklistWindow(QWidget, user_blacklist_setter.Ui_Form):
    """拉黑设置窗口"""
    get_black_status_ok_signal = pyqtSignal(dict)
    set_black_status_ok_signal = pyqtSignal(dict)

    def __init__(self, bduss, stoken, user_id_portrait):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.user_id_portrait = user_id_portrait

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_loading_flash()

        self.get_black_status_ok_signal.connect(self.get_black_status_ok_slot)
        self.set_black_status_ok_signal.connect(self.set_black_status_ok_slot)
        self.pushButton_2.clicked.connect(self.close)
        self.pushButton.clicked.connect(self.set_black_status_async)
        self.pushButton_3.clicked.connect(self.open_user_homepage)

        self.get_black_status_async()

    def closeEvent(self, a0):
        a0.accept()
        qt_window_mgr.del_window(self)

    def init_loading_flash(self):
        self.loading_widget = LoadingFlashWidget()
        self.loading_widget.cover_widget(self)

    def open_user_homepage(self):
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, self.user_id_portrait)
        qt_window_mgr.add_window(user_home_page)

    def set_black_status_ok_slot(self, data):
        if data['success']:
            QMessageBox.information(self, data['title'], data['text'], QMessageBox.Ok)
            self.close()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)
            self.loading_widget.hide()

    def set_black_status_async(self):
        self.loading_widget.set_caption(True, '正在应用拉黑设置，请稍等...')
        self.loading_widget.show()
        start_background_thread(self.set_black_status)

    def set_black_status(self):
        async def doaction():
            turn_data = {'success': False, 'title': '', 'text': ''}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    flag = aiotieba.enums.BlacklistType.NULL
                    if self.checkBox.isChecked():
                        flag |= aiotieba.enums.BlacklistType.INTERACT
                    if self.checkBox_3.isChecked():
                        flag |= aiotieba.enums.BlacklistType.CHAT
                    if self.checkBox_2.isChecked():
                        flag |= aiotieba.enums.BlacklistType.FOLLOW

                    r = await client.set_blacklist(self.user_id_portrait, btype=flag)
                    if r:
                        turn_data['success'] = True
                        turn_data['title'] = '拉黑成功'
                        turn_data['text'] = '已成功对此用户设置拉黑。'
                    else:
                        turn_data['success'] = False
                        turn_data['title'] = '拉黑失败'
                        turn_data['text'] = str(r.err)
            except Exception as e:
                logging.log_exception(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.set_black_status_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()

    def get_black_status_ok_slot(self, data):
        if data['success']:
            self.label.setPixmap(data['head'])
            self.label_2.setText(data['name'])
            self.checkBox.setChecked(data['black_state'][0])
            self.checkBox_2.setChecked(data['black_state'][2])
            self.checkBox_3.setChecked(data['black_state'][1])
            self.loading_widget.hide()
        else:
            QMessageBox.critical(self, data['title'], data['text'], QMessageBox.Ok)
            self.close()

    def get_black_status_async(self):
        self.loading_widget.show()
        start_background_thread(self.get_black_status)

    def get_black_status(self):
        async def doaction():
            # 互动、私信、关注
            turn_data = {'success': True, 'head': None, 'name': '', 'black_state': [False, False, False]}
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    user_info = await client.get_user_info(self.user_id_portrait,
                                                           aiotieba.enums.ReqUInfo.USER_ID | aiotieba.enums.ReqUInfo.NICK_NAME | aiotieba.enums.ReqUInfo.PORTRAIT)
                    if user_info.err:
                        turn_data['success'] = False
                        turn_data['title'] = '获取用户信息失败'
                        turn_data['text'] = f'{user_info.err}'
                    elif profile_mgr.current_uid == user_info.user_id:
                        turn_data['success'] = False
                        turn_data['title'] = '错误'
                        turn_data['text'] = '你不能拉黑自己。'
                    else:
                        user_head_pixmap = QPixmap()
                        user_head_pixmap.loadFromData(cache_mgr.get_portrait(user_info.portrait))
                        user_head_pixmap = user_head_pixmap.scaled(40, 40, Qt.KeepAspectRatio,
                                                                   Qt.SmoothTransformation)
                        turn_data['head'] = user_head_pixmap
                        turn_data['name'] = user_info.nick_name_new

                        payload = GetUserBlackInfoReqIdl_pb2.GetUserBlackInfoReqIdl()

                        payload.data.common._client_type = 2
                        payload.data.common._client_version = request_mgr.TIEBA_CLIENT_VERSION
                        payload.data.common.BDUSS = self.bduss
                        payload.data.common.stoken = self.stoken

                        payload.data.black_uid = user_info.user_id

                        response = request_mgr.run_protobuf_api('/c/u/user/getUserBlackInfo',
                                                                payloads=payload.SerializeToString(),
                                                                cmd_id=309698,
                                                                bduss=self.bduss, stoken=self.stoken,
                                                                host_type=2)
                        final_response = GetUserBlackInfoResIdl_pb2.GetUserBlackInfoResIdl()
                        final_response.ParseFromString(response)

                        if final_response.error.errorno == 0:
                            turn_data['black_state'][0] = bool(int(final_response.data.perm_list.interact))
                            turn_data['black_state'][1] = bool(int(final_response.data.perm_list.chat))
                            turn_data['black_state'][2] = bool(int(final_response.data.perm_list.follow))
                        else:
                            turn_data['success'] = False
                            turn_data['title'] = '获取拉黑状态失败'
                            turn_data[
                                'text'] = f'{final_response.error.errmsg} (错误代码 {final_response.error.errorno})'

            except Exception as e:
                logging.log_exception(e)
                turn_data['success'] = False
                turn_data['title'] = '程序内部错误'
                turn_data['text'] = str(e)
            finally:
                self.get_black_status_ok_signal.emit(turn_data)

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(doaction())

        start_async()
