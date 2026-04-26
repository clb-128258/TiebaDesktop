import asyncio
import os
import sys

import aiotieba
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

from publics import top_toast_widget, tieba_apis, app_logger, profile_mgr
from publics.funcs import start_background_thread, get_exception_string
from subwindow import base_ui
from ui import sign

if os.name == 'nt':
    import win32api
    import win32con


class SignAllDialog(base_ui.WindowBaseQDialog, sign.Ui_Dialog):
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
        self.init_top_toaster()
        self.init_window_position()

        self.update_label_count.connect(lambda text: self.label_3.setText(text))
        self.sign_grow_ok.connect(self.show_grow_sign_msg)
        self.pushButton_2.clicked.connect(self.sign_grow_async)
        self.pushButton_3.clicked.connect(self.sign_all_forum_async)
        self.pushButton.clicked.connect(self.sign_all)

        self.bduss = bduss
        self.stoken = stoken

    def closeEvent(self, a0):
        self.save_window_position()

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

    def init_top_toaster(self):
        self.top_toaster = top_toast_widget.TopToaster()
        self.top_toaster.setCoverWidget(self)

    def sign_all(self):
        self.sign_grow_async()
        self.sign_all_forum_async()

    def show_grow_sign_msg(self, result):
        if not result:
            self.top_toaster.showToast(
                top_toast_widget.ToastMessage('成长等级签到成功', icon_type=top_toast_widget.ToastIconType.SUCCESS))
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
                        head = '\n' if err_msg else ''
                        err_msg += f'{head}成长等级签到：{get_exception_string(r1.err)}'
                    if not r2:
                        head = '\n' if err_msg else ''
                        err_msg += f'{head}成长等级分享任务：{get_exception_string(r2.err)}'

                    self.sign_grow_ok.emit(err_msg)

            self.is_signing_grows = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()

    def sign_all_forum_async(self):
        if not self.is_signing_forums:
            start_background_thread(self.sign_all_forum)

    def sign_all_forum(self):
        async def dosign():
            self.is_signing_forums = True
            signed_count = 0

            try:
                async with aiotieba.Client(self.bduss, self.stoken, proxy=True) as client:
                    self.update_label_count.emit('正在进行官方一键签到...')
                    await client.sign_forums()  # 先一键签到

                    self.update_label_count.emit('进入逐个签到模式，正在获取关注吧列表...')
                    bars = tieba_apis.newmoindex(self.bduss)['data']['like_forum']
                    bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

                    self.update_label_count.emit('吧列表获取完成，已签到的吧将会被跳过，签到即将开始...')
                    await asyncio.sleep(1)

                    for forum in bars:
                        if forum["is_sign"]:
                            # 已签到的直接跳过
                            signed_count += 1
                            continue

                        forum_name = forum['forum_name']
                        fid = forum['forum_id']

                        self.update_label_count.emit(f'正在签到 {forum_name}吧\n'
                                                     f'已签到 {signed_count} / 总吧数 {len(bars)}')
                        r = tieba_apis.sign_forum(self.bduss, self.stoken, fid, forum_name)

                        if r['error_code'] == '0':
                            user_sign_rank = r['user_info']['user_sign_rank']
                            sign_bonus_point = r['user_info']['sign_bonus_point']
                            sign_show_msg = f'√ 今日第 {user_sign_rank} 个签到 | 经验 +{sign_bonus_point}'

                            signed_count += 1  # 签到成功了加一
                        elif r['error_code'] == '160002':
                            sign_show_msg = f'* 已签到过此吧'
                            signed_count += 1  # 之前签到过了也加一
                        else:
                            sign_show_msg = f'× {r["error_msg"]} (错误代码 {r["error_code"]})'

                        self.update_label_count.emit(f'正在签到 {forum_name}吧\n'
                                                     f'{sign_show_msg}\n'
                                                     f'已签到 {signed_count} / 总吧数 {len(bars)}')

                        await asyncio.sleep(0.3)

                    self.update_label_count.emit(f'签到完成，已签到 {signed_count} 个吧，'
                                                 f'{len(bars) - signed_count} 个吧签到失败。')

            except Exception as e:
                app_logger.log_exception(e)
                self.update_label_count.emit(f'签到时发生如下错误：\n'
                                             f'{get_exception_string(e)}')
            finally:
                if os.name == 'nt':
                    win32api.MessageBeep(win32con.MB_ICONASTERISK)
                self.is_signing_forums = False

        def start_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(dosign())

        start_async()
