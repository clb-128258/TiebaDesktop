import asyncio
import os
import sys

import aiotieba
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QMessageBox

from publics import request_mgr
from publics.funcs import start_background_thread
from ui import sign

if os.name == 'nt':
    import win32api
    import win32con


class SignAllDialog(QDialog, sign.Ui_Dialog):
    """一键签到窗口，可以实现全吧和成长等级签到"""
    update_label_count = pyqtSignal(str)
    sign_grow_ok = pyqtSignal(str)
    is_signing_forums = False
    is_signing_grows = False

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.lineEdit.setText(f'\"{sys.executable}\" --sign-all-forums --sign-grows')

        self.update_label_count.connect(lambda text: self.label_3.setText(text))
        self.sign_grow_ok.connect(self.show_grow_sign_msg)
        self.pushButton_2.clicked.connect(self.sign_grow_async)
        self.pushButton_3.clicked.connect(self.sign_all_forum_async)
        self.pushButton.clicked.connect(self.sign_all)

        self.bduss = bduss
        self.stoken = stoken

    def sign_all(self):
        self.sign_grow_async()
        self.sign_all_forum_async()

    def show_grow_sign_msg(self, result):
        if not result:
            QMessageBox.information(self, '签到成功', '成长等级签到成功。')
        else:
            QMessageBox.critical(self, '签到失败', result)

        self.pushButton_2.setEnabled(True)

    def sign_grow_async(self):
        if not self.is_signing_grows:
            self.pushButton_2.setEnabled(False)
            start_background_thread(self.sign_grow)

    def sign_grow(self):
        async def dosign():
            self.is_signing_grows = True
            async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                r1 = await client.sign_growth()
                r2 = await client.sign_growth_share()

                if r1 and r2:
                    self.sign_grow_ok.emit('')
                else:
                    err_msg = ''
                    if not r1:
                        head = ''
                        if err_msg:
                            head = '\n'
                        err_msg += f'{head}成长等级签到：{r1.err.msg}'
                    if not r2:
                        head = ''
                        if err_msg:
                            head = '\n'
                        err_msg += f'{head}成长等级分享任务：{r2.err.msg}'

                    self.sign_grow_ok.emit(err_msg)

            self.is_signing_grows = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def sign_all_forum_async(self):
        if not self.is_signing_forums:
            self.update_label_count.emit('正在开始签到...')
            start_background_thread(self.sign_all_forum)

    def sign_all_forum(self):
        async def dosign():
            self.is_signing_forums = True
            signed_count = 0
            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    bars = request_mgr.run_get_api('/mo/q/newmoindex', self.bduss)['data']['like_forum']
                    bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

                    for forum in bars:
                        if forum["is_sign"] != 1:
                            forum_name = forum['forum_name']
                            self.update_label_count.emit(
                                f'正在签到 {forum_name}吧\n已签到 {signed_count + 1} / 总吧数 {len(bars)}')

                            fid = forum['forum_id']
                            r = await client.sign_forum(fid)
                            if r:
                                signed_count += 1  # 签到成功了加一
                            elif r.err.code == 160002:
                                signed_count += 1  # 之前签到过了也加一
                            await asyncio.sleep(0.3)  # 休眠0.3秒，防止贴吧服务器抽风
                        else:
                            # 已签到的直接跳过
                            signed_count += 1

                self.update_label_count.emit(
                    f'签到完成，已签到 {signed_count} 个吧，{len(bars) - signed_count} 个吧签到失败。')

            except Exception as e:
                self.update_label_count.emit('签到时发生异常错误，请再试一次。')
                print(type(e))
                print(e)
            finally:
                if os.name == 'nt':
                    win32api.MessageBeep(win32con.MB_ICONASTERISK)
                self.is_signing_forums = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()
