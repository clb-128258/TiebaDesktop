import pyperclip

from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QListWidgetItem, QTreeWidgetItem

from publics import qt_image, profile_mgr, qt_window_mgr
from publics.base_ui_elements import base_ui
from publics.funcs import show_label_pixmap_with_animation
from ui import user_item


class ExtListWidgetItem(QListWidgetItem):
    """可以标识用户id的QListWidgetItem，用于在列表内添加用户并找出item对应的用户id"""
    user_portrait_id = ''

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken

    def set_show_datas(self, uicon, name):
        self.setIcon(QIcon(uicon))
        self.setText(name)


class ExtTreeWidgetItem(QTreeWidgetItem):
    """可以标识用户id的QTreeWidgetItem，用于在列表内添加用户并找出item对应的用户id"""
    user_portrait_id = ''

    def __init__(self, bduss, stoken):
        super().__init__()
        self.bduss = bduss
        self.stoken = stoken


class UserItem(base_ui.InsideWidgetBaseQWidget, user_item.Ui_Form):
    """嵌入在列表内的用户组件"""
    user_portrait_id = ''
    __user_real_portrait = ''
    __user_avatar_loaded = False
    show_homepage_by_click = False
    switchRequested = pyqtSignal(tuple)
    deleteRequested = pyqtSignal(tuple)
    doubleClicked = pyqtSignal()
    load_by_callback = False

    def __init__(self, bduss, stoken):
        super().__init__()
        self.setupUi(self)
        self.bduss = bduss
        self.stoken = stoken

        self.toolButton.clicked.connect(self.show_toolbutton_icon)
        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label, pixmap))
        self.destroyed.connect(self.portrait_image.destroyImage)

        self.reset_theme()

    def reset_theme(self):
        super().reset_theme()
        self.toolButton.setIcon(QIcon(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/content_copy.png'))

    def mouseDoubleClickEvent(self, a0):
        a0.accept()
        self.doubleClicked.emit()
        if self.show_homepage_by_click:
            self.open_user_homepage(self.user_portrait_id)

    def show_toolbutton_icon(self):
        self.toolButton.setIcon(QIcon(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/checked.png'))
        QTimer.singleShot(2000, lambda: self.toolButton.setIcon(
            QIcon(f'ui/icon_{profile_mgr.get_theme_policy_string()[1]}/content_copy.png')))

    def open_user_homepage(self, uid):
        from subwindow.user_home_page import UserHomeWindow
        user_home_page = UserHomeWindow(self.bduss, self.stoken, uid)
        qt_window_mgr.add_window(user_home_page)

    def get_portrait(self):
        if not self.__user_avatar_loaded:
            self.portrait_image.setImageInfo(qt_image.ImageLoadSource.TiebaPortrait,
                                             self.__user_real_portrait,
                                             qt_image.ImageCoverType.RoundCover,
                                             (50, 50))
            self.portrait_image.loadImage()
            self.__user_avatar_loaded = True

    def setdatas(self, uicon, uname, uid=-1, show_switch=False, is_current_user=False, is_tieba_uid=False,
                 custom_desp_str=''):
        if uicon:
            if isinstance(uicon, QPixmap):
                self.label.setPixmap(uicon)
            elif isinstance(uicon, str):
                self.__user_real_portrait = uicon
                if not self.load_by_callback:
                    self.get_portrait()
        else:
            self.label.hide()
        self.label_2.setText(uname)

        if custom_desp_str:
            self.label_3.setText(custom_desp_str)
            self.label_3.setToolTip('')
            self.toolButton.hide()
        elif uid != -1:
            self.label_3.setText(f'{"贴吧 ID" if is_tieba_uid else "用户 ID"}: {uid}')
            self.toolButton.clicked.connect(lambda: pyperclip.copy(uid))
        else:
            self.label_3.hide()

        if not show_switch:
            self.pushButton.hide()
            self.pushButton_2.hide()
        else:
            if is_current_user:
                self.pushButton.setEnabled(False)
                self.pushButton.setText('当前账号')
            self.pushButton.clicked.connect(lambda: self.switchRequested.emit((uid, uname)))
            self.pushButton_2.clicked.connect(lambda: self.deleteRequested.emit((uid, uname)))
