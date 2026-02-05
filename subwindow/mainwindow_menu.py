from PyQt5.QtGui import QPixmap

from subwindow.history_list import HistoryViewWindow
from subwindow.star_thread_list import StaredThreadsList
from subwindow.user_home_page import UserHomeWindow
from ui import mw_popup
from PyQt5.QtWidgets import QWidget, qApp, QMenu
from PyQt5.QtGui import QIcon, QResizeEvent
from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QEvent
from publics import request_mgr, profile_mgr, funcs, qt_window_mgr, qt_image, logging
import asyncio
import pyperclip


class MainPopupMenu(QWidget, mw_popup.Ui_Form):
    """主窗口右上角菜单中个人信息条目"""
    infoLoaded = pyqtSignal(dict)
    followForumClicked = pyqtSignal()
    tieba_id = -1

    def __init__(self, parent_menu: QMenu):
        super().__init__()
        self.setupUi(self)

        self.parent_menu = parent_menu
        self.toolButton_3.setIcon(QIcon('ui/content_copy.png'))

        self.infoLoaded.connect(self._ui_set_self_info)
        self.toolButton_3.clicked.connect(self.copy_tieba_id)
        self.portrait_icon = qt_image.MultipleImage()
        self.portrait_icon.currentImageChanged.connect(lambda: self.label.setPixmap(self.portrait_icon.currentPixmap()))
        self.portrait_icon.imageLoadSucceed.connect(self.resize_menu)
        self.destroyed.connect(self.portrait_icon.destroyImage)

        click_areas = [
            self.label,
            self.label_4,
            self.label_5,
            self.label_2,
            self.label_6,
            self.label_7,
            self.label_8,
            self.label_9,
            self.label_10,
            self.label_11,
            self.label_12,
            self.label_13,
            self.label_14,
            self.label_15
        ]
        for w in click_areas:
            w.installEventFilter(self)

    def showEvent(self, a0):
        self.get_self_info_async()

    def resizeEvent(self, a0):
        resizeEvent = QResizeEvent(self.size(), self.parent_menu.size())
        qApp.sendEvent(self.parent_menu, resizeEvent)  # 使菜单调整到正确大小

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if source in (self.label, self.label_2, self.label_8, self.label_9):
                self.open_user_homepage()
            elif source in (self.label_10, self.label_11):
                self.followForumClicked.emit()
            elif source in (self.label_4, self.label_5):
                self.open_user_homepage(3)
            elif source in (self.label_6, self.label_7):
                self.open_user_homepage(4)
            elif source in (self.label_12, self.label_13):
                self.open_history_window()
            elif source in (self.label_14, self.label_15):
                self.open_star_window()
        return super(type(self), self).eventFilter(source, event)  # 照常处理事件

    def copy_tieba_id(self):
        pyperclip.copy(str(self.tieba_id))
        self.toolButton_3.setIcon(QIcon('ui/checked.png'))
        QTimer.singleShot(2000, lambda: self.toolButton_3.setIcon(QIcon('ui/content_copy.png')))

    def open_history_window(self):
        history_window = HistoryViewWindow()
        qt_window_mgr.add_window(history_window)

    def open_user_homepage(self, tab=0):
        if profile_mgr.current_uid != 'default':
            user_home_page = UserHomeWindow(profile_mgr.current_bduss, profile_mgr.current_stoken,
                                            profile_mgr.current_uid,
                                            tab)
            qt_window_mgr.add_window(user_home_page)

    def open_star_window(self):
        user_stared_list = StaredThreadsList(profile_mgr.current_bduss, profile_mgr.current_stoken)
        qt_window_mgr.add_window(user_stared_list)

    def resize_menu(self):
        self.adjustSize()
        self.resizeEvent(None)

    def _ui_set_self_info(self, data):
        widgets = [self.toolButton_3, self.frame_1, self.frame_2, self.frame_3, self.frame_4, self.frame_6]

        self.label_12.setText(str(data['view_history_num']))
        if profile_mgr.current_bduss:
            for i in widgets:
                i.show()

            self.portrait_icon.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait, data['portrait'],
                                            qt_image.ImageCoverType.RoundCover, (50, 50))
            self.portrait_icon.reloadImage()
            self.label_2.setText(data['nickname'])
            self.label_3.setText('贴吧 ID: ' + str(data['tieba_id']))

            self.label_8.setText(str(data['agree_me_num']))
            self.label_10.setText(str(data['follow_forum_num']))
            self.label_4.setText(str(data['follow']))
            self.label_6.setText(str(data['fans']))
            self.label_14.setText(str(data['store_num']))
        else:
            for i in widgets:
                i.hide()

            self.label.setPixmap(data['portrait_pixmap'])
            self.label_2.setText('未登录')
            self.label_3.setText('登录后即可使用所有功能')

        self.resize_menu()

    def get_self_info(self):
        async def getinfo():
            try:
                emit_data = {'portrait': '',
                             'portrait_pixmap': None,
                             'nickname': '',
                             'tieba_id': 0,
                             'agree_me_num': 0,
                             'store_num': 0,
                             'fans': 0,
                             'follow': 0,
                             'view_history_num': len(profile_mgr.view_history),
                             'follow_forum_num': 0}

                if profile_mgr.current_bduss:
                    params = {
                        "_client_type": '2',
                        "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                        "BDUSS": profile_mgr.current_bduss,
                        "stoken": profile_mgr.current_stoken,
                        "uid": str(profile_mgr.current_uid),
                        "subapp_type": "hybrid"
                    }

                    resp = request_mgr.run_get_api('/c/u/user/profile', bduss=profile_mgr.current_bduss,
                                                   stoken=profile_mgr.current_stoken, use_mobile_header=True,
                                                   params=params)

                    emit_data['portrait'] = resp['user']['portraith'].split('?')[0]
                    emit_data['nickname'] = resp['user']['name_show']
                    self.tieba_id = emit_data['tieba_id'] = int(resp['user']['tieba_uid'])
                    emit_data['agree_me_num'] = int(resp['user']['total_agree_num'])
                    emit_data['store_num'] = int(resp['user']['favorite_num'])
                    emit_data['fans'] = int(resp['user']['fans_num'])
                    emit_data['follow'] = int(resp['user']['concern_num'])

                    emit_data['follow_forum_num'] = int(resp['user']['my_like_num'])
                else:
                    pixmap = QPixmap()
                    pixmap.load('ui/default_user_image.png')
                    pixmap = pixmap.scaled(50, 50, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
                    emit_data['portrait_pixmap'] = pixmap

                self.infoLoaded.emit(emit_data)
            except Exception as e:
                logging.log_exception(e)

        def start_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            asyncio.run(getinfo())

        start_async()

    def get_self_info_async(self):
        funcs.start_background_thread(self.get_self_info)
