"""贴子内的投票内容"""
from typing import Union

from PyQt5.QtCore import pyqtSignal, QRectF, Qt
from PyQt5.QtGui import QPaintEvent, QPainter, QBrush, QColor
from PyQt5.QtWidgets import QListWidgetItem

from publics import profile_mgr, request_mgr, app_logger, funcs
from publics.base_ui_elements import top_toast_widget, base_ui
from publics.funcs import get_exception_string
from publics.qt_image import get_pixmap_icon_from_file

from ui import thread_vote_info, thread_vote_option_item


class VoteItem(base_ui.InsideWidgetBaseQWidget, thread_vote_option_item.Ui_Form):
    voteSubmitted = pyqtSignal(int)

    def __init__(self, vop_id: int, is_multi_vote: bool):
        super().__init__()
        self.setupUi(self)
        self.reset_theme()

        self.vote_option_id = vop_id
        self.is_multi_vote = is_multi_vote
        self.total_vote_num = 0
        self.current_vote_num = 0
        self.is_voted = False
        self.is_self_option = False

        self.pushButton.clicked.connect(lambda: self.voteSubmitted.emit(self.vote_option_id))

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        self.paint_vote_percent_bg()

    def paint_vote_percent_bg(self):
        if not self.is_voted:
            return

        vote_percent = self.current_vote_num / self.total_vote_num
        percent_show_width = int(self.width() * vote_percent)

        color = QColor()
        if self.is_self_option:
            color.setRgb(93, 69, 229, 200)
        else:
            color.setRgb(63, 46, 153, 120)

        rect = QRectF(0, 5, percent_show_width, self.frame.height() + 5)
        brush = QBrush(color)
        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(brush)
        painter.drawRoundedRect(rect, 8, 8)

    def set_info(self, option_str: str,
                 total_vote_num: int,
                 current_vote_num: int,
                 is_voted: bool,
                 is_chose_current_option: bool):
        self.total_vote_num = total_vote_num
        self.current_vote_num = current_vote_num

        self.label_3.setText(option_str)
        self.pushButton.setVisible(not self.is_multi_vote)
        self.checkBox.setVisible(self.is_multi_vote)

        if is_voted:
            self.set_voted(is_chose_current_option, is_already_voted=True)
        else:
            self.label.hide()

    def show_vote_num(self):
        vote_percent = round((self.current_vote_num / self.total_vote_num) * 100, 1)
        self.label.setText(f'{self.current_vote_num} 票 | 占比 {vote_percent} %')
        self.label.show()

    def set_voted(self, is_chose_current_option: bool, is_already_voted: bool = False):
        self.is_voted = True
        self.is_self_option = is_chose_current_option

        if not self.is_multi_vote:
            self.pushButton.setEnabled(False)
            self.pushButton.setText('你的选项' if is_chose_current_option else '投票')
        else:
            self.checkBox.setChecked(is_chose_current_option)
            self.checkBox.setEnabled(False)

        self.current_vote_num += 1 if not is_already_voted and is_chose_current_option else 0
        self.total_vote_num += 1 if not is_already_voted else 0
        self.show_vote_num()

        self.paint_vote_percent_bg()


class ThreadVoteItem(base_ui.InsideWidgetBaseQWidget, thread_vote_info.Ui_Form):
    msgPopped = pyqtSignal(top_toast_widget.ToastMessage)
    voteok = pyqtSignal(dict)

    def __init__(self, is_multi: bool, thread_id: int, forum_id: int):
        super().__init__()
        self.setupUi(self)
        self.reset_theme()

        self.total_height = 0
        self.is_multi_vote = is_multi
        self.thread_id = thread_id
        self.forum_id = forum_id
        self.vote_item: list[VoteItem] = []
        self.vote_num = 0
        self.vote_user_num = 0

        self.pushButton.setVisible(self.is_multi_vote)

        self.pushButton.clicked.connect(self.run_multi_poll)
        self.voteok.connect(self._on_poll_finish)
        self.destroyed.connect(self.listWidget.clear)

    def reset_theme(self):
        super().reset_theme()
        self.label.setPixmap(
            get_pixmap_icon_from_file(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/vote.png', 30))

        # 设置列表内容的样式
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            widget.reset_theme()

    def _on_poll_finish(self, datas):
        if self.is_multi_vote and datas['success']:
            self.pushButton.setEnabled(False)
            self.pushButton.setText('已投票')
        elif self.is_multi_vote:
            self.pushButton.setEnabled(True)
            self.pushButton.setText('投票')

        for widget in self.vote_item:
            if datas['success']:
                widget.set_voted(widget.vote_option_id in datas['option'])
            else:
                if not widget.is_multi_vote:
                    widget.pushButton.setEnabled(True)
                    widget.pushButton.setText('投票')
                else:
                    widget.checkBox.setEnabled(True)

        if datas['success']:
            self.vote_num += len(datas['option'])
            self.vote_user_num += 1
            self.update_vote_num()

    def run_poll(self, option: str):
        bduss = profile_mgr.current_bduss
        stoken = profile_mgr.current_stoken
        msg = top_toast_widget.ToastMessage()
        datas = {'success': False, 'option': [int(i) for i in option.split(',')] if option else []}

        try:
            if bduss and stoken:
                params = {
                    "_client_type": "2",
                    "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                    "BDUSS": bduss,
                    "stoken": stoken,
                    "thread_id": str(self.thread_id),
                    "forum_id": str(self.forum_id),
                    "options": option,
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
                    datas['success'] = False
                    msg.icon_type = top_toast_widget.ToastIconType.INFORMATION
                else:
                    msg.title = f'投票失败，{response["error_msg"]} ({response["error_code"]})'
                    msg.icon_type = top_toast_widget.ToastIconType.ERROR
            else:
                msg.title = '登录账号后即可进行投票'
                msg.icon_type = top_toast_widget.ToastIconType.INFORMATION
        except Exception as e:
            app_logger.log_exception(e)
            msg.title = '投票失败，' + get_exception_string(e)
            msg.icon_type = top_toast_widget.ToastIconType.ERROR
        finally:
            self.msgPopped.emit(msg)
            self.voteok.emit(datas)

    def run_poll_async(self, option: Union[list[int], int]):
        if self.is_multi_vote:
            self.pushButton.setEnabled(False)
            self.pushButton.setText('正在投票...')

        for widget in self.vote_item:
            if not self.is_multi_vote:
                widget.pushButton.setEnabled(False)
                widget.pushButton.setText('正在投票...')
            else:
                widget.checkBox.setEnabled(False)

        if isinstance(option, int):
            option = str(option)
        elif isinstance(option, list):
            option = ','.join([str(i) for i in option])
        funcs.start_background_thread(self.run_poll, (option,))

    def run_multi_poll(self):
        options = []
        for widget in self.vote_item:
            if widget.is_multi_vote and widget.checkBox.isChecked():
                options.append(widget.vote_option_id)

        self.run_poll_async(options)

    def update_vote_num(self):
        if self.vote_user_num == self.vote_num:
            self.label_4.setText(f'投票人数 {self.vote_user_num}')
        else:
            self.label_4.setText(f'投票人数 {self.vote_user_num}\n有效票数 {self.vote_num}')

    def set_info(self, title: str, vote_num: int, vote_user_num: int, vote_items: list[VoteItem], is_voted: bool):
        self.vote_num = vote_num
        self.vote_user_num = vote_user_num

        self.label_2.setText(f'投票 | {title}')
        self.update_vote_num()

        if is_voted and self.is_multi_vote:
            self.pushButton.setEnabled(False)
            self.pushButton.setText('已投票')

        if is_voted:
            self.label_3.setText('你已进行过投票，不可再次投票')
        elif self.is_multi_vote:
            self.label_3.setText('该投票可以多选，你可以为多个条目投票。\n'
                                 '请勾选所有要投票的项目，再点击“提交投票”完成投票。')

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
