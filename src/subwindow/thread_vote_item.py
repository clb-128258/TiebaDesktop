"""贴子内的投票内容"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QListWidgetItem
from publics import profile_mgr, request_mgr, top_toast_widget, logging, funcs
from publics.funcs import get_exception_string

from ui import thread_vote_info, thread_vote_option_item


class VoteItem(QWidget, thread_vote_option_item.Ui_Form):
    voteSubmitted = pyqtSignal(int)

    def __init__(self, vop_id: int):
        super().__init__()
        self.setupUi(self)
        self.vote_option_id = vop_id

        self.pushButton.clicked.connect(lambda: self.voteSubmitted.emit(self.vote_option_id))

    def set_info(self, option_str: str, total_vote_num: int, current_vote_num: int, is_voted: bool,
                 is_chose_current_option: bool):
        self.label_3.setText(option_str)
        self.label.setText(f'{current_vote_num} 票，占比 {round((current_vote_num / total_vote_num) * 100, 1)} %')
        if is_voted:
            self.set_voted(is_chose_current_option)
        else:
            self.label.hide()

    def set_voted(self, is_chose_current_option: bool):
        self.pushButton.setEnabled(False)
        self.pushButton.setText('你的选项' if is_chose_current_option else '已投票')
        self.label.show()


class ThreadVoteItem(QWidget, thread_vote_info.Ui_Form):
    msgPopped = pyqtSignal(top_toast_widget.ToastMessage)
    voteok = pyqtSignal(dict)

    def __init__(self, is_multi: bool, thread_id: int, forum_id: int):
        super().__init__()
        self.setupUi(self)
        self.total_height = 0
        self.is_multi_vote = is_multi
        self.thread_id = thread_id
        self.forum_id = forum_id
        self.vote_item: list[VoteItem] = []

        self.label.setPixmap(QPixmap('ui/vote.png').scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.voteok.connect(self._on_poll_finish)
        self.destroyed.connect(self.listWidget.clear)

    def _on_poll_finish(self, datas):
        for widget in self.vote_item:
            widget.pushButton.setEnabled(True)
            if datas['success']:
                widget.set_voted(widget.vote_option_id == datas['option'])
            else:
                widget.pushButton.setText('投票')

    def run_poll(self, option: int):
        bduss = profile_mgr.current_bduss
        stoken = profile_mgr.current_stoken
        msg = top_toast_widget.ToastMessage()
        datas = {'success': False, 'option': option}

        try:
            if bduss and stoken:
                params = {
                    "_client_type": "2",
                    "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                    "BDUSS": bduss,
                    "stoken": stoken,
                    "thread_id": str(self.thread_id),
                    "forum_id": str(self.forum_id),
                    "options": str(option),
                    "subapp_type": "hybrid"
                }

                response = request_mgr.run_get_api('/c/c/post/addPollPost',
                                                   bduss=bduss, stoken=stoken,
                                                   use_mobile_header=True,
                                                   host_type=1,
                                                   params=params)

                if response['error_code'] == '0':
                    msg.title = '投票成功'
                    datas['success'] = True
                    msg.icon_type = top_toast_widget.ToastIconType.SUCCESS
                elif response['error_code'] == "320030":
                    msg.title = '你已经投过票了，无需再次投票'
                    datas['success'] = True
                    msg.icon_type = top_toast_widget.ToastIconType.INFORMATION
                else:
                    msg.title = f'投票失败，发生错误 {response["error_msg"]} ({response[{"error_code"}]})'
                    msg.icon_type = top_toast_widget.ToastIconType.ERROR
            else:
                msg.title = '登录账号后即可进行投票'
                msg.icon_type = top_toast_widget.ToastIconType.INFORMATION
        except Exception as e:
            logging.log_exception(e)
            msg.title = '投票失败 ' + get_exception_string(e)
            msg.icon_type = top_toast_widget.ToastIconType.ERROR
        finally:
            self.msgPopped.emit(msg)
            self.voteok.emit(datas)

    def run_poll_async(self, option: int):
        for widget in self.vote_item:
            widget.pushButton.setEnabled(False)
            widget.pushButton.setText('正在投票...')
        funcs.start_background_thread(self.run_poll, (option,))

    def set_info(self, title: str, vote_num: int, vote_user_num: int, vote_items: list[VoteItem]):
        self.label_2.setText(f'投票 - {title}')
        if vote_user_num == vote_num:
            self.label_4.setText(f'已有 {vote_user_num} 人投票')
        else:
            self.label_4.setText(f'已有 {vote_user_num} 人投票\n有效票数 {vote_num} 票')
        if self.is_multi_vote:
            self.label_3.setText('在下方为要投票的条目点按按钮即可投票。\n该投票可以多选，你可以为多个条目投票。')

        self.vote_item = vote_items
        for widget in self.vote_item:
            widget.voteSubmitted.connect(self.run_poll_async)
            item = QListWidgetItem()
            widget.adjustSize()
            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
            self.total_height += widget.height()
        self.listWidget.setFixedHeight(self.total_height)
