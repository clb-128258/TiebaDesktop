"""贴子内的投票内容"""
from PyQt5.QtWidgets import QWidget, QListWidgetItem
from publics import profile_mgr, request_mgr

from ui import thread_vote_info, thread_vote_option_item


class VoteItem(QWidget, thread_vote_option_item.Ui_Form):
    def __init__(self, vop_id: int):
        super().__init__()
        self.setupUi(self)
        self.vote_option_id = vop_id

    def set_info(self, option_str: str, total_vote_num: int, current_vote_num: int, is_voted: bool,
                 is_chose_current_option: bool):
        self.label_3.setText(option_str)
        self.label.setText(f'{current_vote_num} 票，占比 {round((current_vote_num / total_vote_num) * 100, 1)} %')
        if is_voted:
            self.set_voted(is_chose_current_option)

    def set_voted(self, is_chose_current_option: bool):
        self.pushButton.setEnabled(False)
        self.pushButton.setText('当前选项' if is_chose_current_option else '已投票')


class ThreadVoteItem(QWidget, thread_vote_info.Ui_Form):
    def __init__(self, is_multi: bool):
        super().__init__()
        self.setupUi(self)
        self.is_multi_vote = is_multi

    def set_info(self, title: str, vote_num: int, vote_user_num: int, vote_items: list[VoteItem]):
        self.label_2.setText(title)
        self.label_4.setText(f'已有 {vote_user_num} 人投票\n有效票数 {vote_num} 票')
        if self.is_multi_vote:
            self.label_3.setText('在下方为要投票的条目点按按钮即可投票。\n该投票可以多选，你可以为多个条目投票。')

        for widget in vote_items:
            item = QListWidgetItem()
            widget.adjustSize()
            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
