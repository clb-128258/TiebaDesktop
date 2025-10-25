import asyncio

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QMessageBox

from publics import request_mgr, qt_window_mgr
from publics.funcs import start_background_thread
from ui import ba_item


class ForumItem(QWidget, ba_item.Ui_Form):
    """列表内嵌入的吧组件"""
    signok = pyqtSignal(tuple)

    def __init__(self, fid, issign, bduss, stoken, fname):
        super().__init__()
        self.setupUi(self)
        self.forum_id = fid
        self.is_sign = issign
        self.bduss = bduss
        self.stoken = stoken
        self.forum_name = fname

        self.signok.connect(self.update_sign_ui)
        self.pushButton.clicked.connect(self.open_ba_detail)
        self.pushButton_2.clicked.connect(self.sign_async)

        if issign:
            self.pushButton_2.setEnabled(False)
            self.pushButton_2.setText('已签到')

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.open_ba_detail()

    def update_sign_ui(self, isok):
        if isok[0]:
            QMessageBox.information(self, isok[1], isok[2])
            self.pushButton_2.setEnabled(False)
            self.pushButton_2.setText('已签到')
        else:
            QMessageBox.critical(self, isok[1], isok[2])
            self.pushButton_2.setEnabled(True)

    def sign_async(self):
        if not self.is_sign:
            self.pushButton_2.setEnabled(False)
            start_background_thread(self.sign)

    def sign(self):
        async def dosign():
            turn_data = [False, '签到完成', '']

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

                turn_data[0] = True
                turn_data[1] = '签到成功'
                turn_data[
                    2] = f'{self.forum_name}吧 已签到成功。\n本次签到经验 +{sign_bonus_point}，你是今天本吧第 {user_sign_rank} 个签到的用户。'
            elif r['error_code'] == '160002':
                turn_data[0] = True
                turn_data[1] = '已经签到过了'
                turn_data[2] = f'你已签到过 {self.forum_name}吧，无需再签到。'
            else:
                turn_data[0] = False
                turn_data[1] = '签到失败'
                turn_data[2] = f'{r["error_msg"]} (错误代码 {r["error_code"]})'

            self.signok.emit(tuple(turn_data))

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def open_ba_detail(self):
        from subwindow.forum_show_window import ForumShowWindow
        forum_window = ForumShowWindow(self.bduss, self.stoken, self.forum_id)
        qt_window_mgr.add_window(forum_window)
        forum_window.load_info_async()
        forum_window.get_threads_async()

    def set_info(self, headpixmap, name, desp):
        self.label.setPixmap(headpixmap)
        self.label_2.setText(name)
        self.label_3.setText(desp)

    def set_level_color(self, level):
        qss = 'QLabel{color: [color];font-weight: [is_high_level];}'
        if level >= 10:  # 10级以上粗体显示
            qss = qss.replace('[is_high_level]', 'bold')
        else:
            qss = qss.replace('[is_high_level]', 'normal')
        if 1 <= level <= 3:  # 绿牌
            qss = qss.replace('[color]', 'rgb(101, 211, 171)')
        elif 4 <= level <= 9:  # 蓝牌
            qss = qss.replace('[color]', 'rgb(101, 161, 255)')
        elif 10 <= level <= 15:  # 黄牌
            qss = qss.replace('[color]', 'rgb(253, 194, 53)')
        elif level >= 16:  # 橙牌老东西
            qss = qss.replace('[color]', 'rgb(247, 126, 48)')

        self.label_3.setStyleSheet(qss)  # 为不同等级设置qss
