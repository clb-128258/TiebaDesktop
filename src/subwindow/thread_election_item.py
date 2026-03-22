"""贴子内的吧主竞选信息"""
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

from publics import profile_mgr
from ui import manager_election_item
from subwindow import base_ui


def get_day_during_string(during):
    unit_list = [(86400, '天'), (3600, '小时'), (60, '分钟'), (0, '秒')]
    during_string = ''

    for unit in unit_list:
        if during >= unit[0]:
            during_string += f' {int(during / unit[0]) if unit[0] != 0 else int(during)} {unit[1]}'
            during = (during % unit[0]) if unit[0] != 0 else during

    return during_string[1:]


class ThreadManagerElectionItem(base_ui.WindowBaseQWidget, manager_election_item.Ui_Form):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.can_vote = False
        self.vote_start_time = -1
        self.vote_status = -1

        self.vote_timer = QTimer(self)
        self.destroyed.connect(self.vote_timer.stop)
        self.vote_timer.timeout.connect(self.update_vote_status)
        self.vote_timer.setInterval(200)

    def reset_theme(self):
        super().reset_theme()
        vote_icon = QPixmap(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/ballot.png')
        vote_icon = vote_icon.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label_3.setPixmap(vote_icon)

    def update_vote_status(self):
        if self.vote_start_time <= time.time() and self.vote_status != 6:
            self.can_vote = True
            self.vote_status = 1  # 表示正在投票期，该字段值尚不确定
            self.vote_timer.stop()

        if not self.can_vote:
            self.pushButton.setEnabled(False)
            self.pushButton.setText('不可投票')
        else:
            self.pushButton.setEnabled(True)
            self.pushButton.setText('暂不支持投票，敬请期待')

        if self.vote_status == 6:
            self.pushButton.setText('竞选已结束')
            self.label_7.hide()
            self.label_6.setText(f'你来晚了，该吧吧主竞选已结束，无法再投票。')
        elif self.vote_status == 2:
            self.pushButton.setText('竞选未开始')
            self.label_4.hide()

            until_vote_during = self.vote_start_time - time.time()
            self.label_7.setText(get_day_during_string(until_vote_during))

        elif self.vote_status == 1:
            self.label_7.hide()
            self.label_6.setText(f'投票已开始，你可以为心仪的用户投上一票了。\n'
                                 f'由于投票功能涉及回复操作（可能导致封号），请到贴吧手机 APP 进行投票。')

        if self.vote_status != 2:
            self.label_4.show()
            self.label_4.setText(f'该用户已有 0 人投票')

    def set_info(self, can_vote, status, vote_num, vote_start_time):
        self.can_vote = can_vote
        self.vote_start_time = vote_start_time
        self.vote_status = status

        self.update_vote_status()

        timeArray = time.localtime(self.vote_start_time)
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", timeArray)
        self.label_8.setText(f'投票正式开始时间：{timestr}')

        if status != 2:
            self.label_4.show()
            self.label_4.setText(f'该用户已有 {vote_num} 人投票')
        else:
            self.vote_timer.start()

        self.adjustSize()
