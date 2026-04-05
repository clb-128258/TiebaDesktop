"""贴吧用户选择器"""
import gc
import time

from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtWidgets import QWidgetAction

from publics import profile_mgr, funcs, app_logger, request_mgr
from subwindow.base_ui import WindowBaseQWidget, BaseQMenu
from ui import tb_user_selector

import aiotieba
import asyncio


def search_user(query_word):
    """全局搜索贴吧用户"""

    result_list = []
    params = {
        'word': query_word
    }
    response = request_mgr.run_get_api('/mo/q/search/user',
                                       bduss=profile_mgr.current_bduss,
                                       stoken=profile_mgr.current_stoken,
                                       params=params,
                                       use_mobile_header=True)
    if response['no'] == 0:
        if response['data']['exactMatch']:
            # 准确用户结果
            data = {'user_id': response['data']['exactMatch']['id'],
                    'name': response['data']['exactMatch']['show_nickname'],
                    'portrait': response['data']['exactMatch']['encry_uid'],
                    'tieba_id': response['data']['exactMatch']['tieba_uid']}
            result_list.append(data)

        for user in response['data']['fuzzyMatch']:  # 相似结果
            data = {'user_id': user['id'],
                    'name': user['show_nickname'],
                    'portrait': user['encry_uid'],
                    'tieba_id': user['tieba_uid']}
            result_list.append(data)

    return result_list


def get_user_list():
    """获取当前用户关注与粉丝的整合列表"""

    async def run_get():
        async with aiotieba.Client(BDUSS=profile_mgr.current_bduss, STOKEN=profile_mgr.current_stoken) as client:
            follow_list = await client.get_follows()
            fans_list = await client.get_fans()

            # 整合关注/粉丝列表
            user_list = list(follow_list.objs)
            for i in fans_list.objs:
                if i not in user_list: user_list.append(i)

            return follow_list

    def start_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return asyncio.run(run_get())

    return start_async()


class TiebaUserSelector(WindowBaseQWidget, tb_user_selector.Ui_Form):
    """在 QMenu 中弹出的用户选择器"""

    add_user = pyqtSignal(object)  # emit Follow object or dict-like
    finished_loading = pyqtSignal()

    user_selector_instance = None
    user_selector_menu_instance = None

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.loading_widget = funcs.LoadingFlashWidget()
        self.loading_widget.cover_widget(self.listWidget)

        # 文本输入插值 QTimer
        self.search_input_interpolation_timer = QTimer(self)
        self.search_input_interpolation_timer.setInterval(1000)
        self.search_input_interpolation_timer.timeout.connect(self.update_last_timestamp)
        self.search_input_interpolation_timer.start()

        # visual tuning
        self.listWidget.verticalScrollBar().setSingleStep(20)
        self.listWidget.verticalScrollBar().valueChanged.connect(self.scroll_load_images)

        self.add_user.connect(self._ui_add_user)
        self.finished_loading.connect(self._on_load_finished)

        self.selected_user = None
        self.is_loading = False
        self.last_search_keyword = ''

    def reset_theme(self):
        super().reset_theme()

        self.loading_widget.reset_theme()

        # apply theme to listWidget
        color = profile_mgr.get_theme_color_string()
        self.listWidget.setStyleSheet(f'QListWidget{{outline:0px; background-color:{color};}}')

        # reset theme for existing widgets
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            widget.reset_theme()

    def showEvent(self, a0):
        super().showEvent(a0)
        self.activateWindow()
        # when shown, start async loading of user list in background thread
        self.selected_user = None
        self.load_user_list_async()

    def update_last_timestamp(self):
        kw = self.lineEdit.text()
        if kw != self.last_search_keyword:
            self.load_user_list_async()
            self.last_search_keyword = kw

    def clear_list(self):
        funcs.cleanup_listWidget(self.listWidget)

    def load_user_list_async(self):
        if not self.is_loading:
            self.clear_list()
            self.loading_widget.show()
            funcs.start_background_thread(self.load_user_list)

    def load_user_list(self):
        try:
            self.is_loading = True

            search_keyword = self.lineEdit.text()
            if search_keyword:
                user_list = search_user(search_keyword)
                for f in user_list:
                    # emit each follow object to UI thread
                    user = {'uid': f["user_id"], 'portrait': f['portrait'], 'name': f['name']}
                    self.add_user.emit(user)
            else:
                user_list = get_user_list()
                for f in user_list:
                    # emit each follow object to UI thread
                    user = {'uid': f.user_id, 'portrait': f.portrait, 'name': f.nick_name_new}
                    self.add_user.emit(user)
        except Exception as e:
            app_logger.log_exception(e)
        finally:
            self.is_loading = False
            self.finished_loading.emit()

    def _on_load_finished(self):
        self.loading_widget.hide()
        self.scroll_load_images()

    def _ui_add_user(self, user):
        # follow is aiotieba Follow object with attributes user_id, portrait, show_name
        try:
            item = funcs.ExtListWidgetItem(profile_mgr.current_bduss, profile_mgr.current_stoken)
            widget = funcs.UserItem(profile_mgr.current_bduss, profile_mgr.current_stoken)
            widget.load_by_callback = True
            portrait = user['portrait']
            name = user['name']
            uid = user['uid']

            widget.setdatas(portrait, name, uid, is_tieba_uid=False)
            widget.adjustSize()

            # when user double-clicks the user item, choose it
            def on_double():
                # store minimal info to return
                self.selected_user = {'user_id': uid, 'portrait': portrait, 'user_name': name}
                self.user_selector_menu_instance.close()

            widget.doubleClicked.connect(on_double)

            item.setSizeHint(widget.size())
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
        except Exception as e:
            app_logger.log_exception(e)

    def scroll_load_images(self):
        # lazy load avatars for visible items
        widgets = funcs.listWidget_get_visible_widgets(self.listWidget)
        for w in widgets:
            # UserItem defines get_portrait
            w.get_portrait()

    def pop_selector(self, pos):
        """Show the selector as a modal menu at position `pos` and return the selected user info dict or None."""
        self.selected_user = None

        # execute the menu modally
        self.user_selector_menu_instance.exec(pos)

        self.lineEdit.clear()
        return self.selected_user

    @classmethod
    def get_instance(cls):
        if not cls.user_selector_instance:
            cls.user_selector_instance = TiebaUserSelector()
            cls.user_selector_menu_instance = BaseQMenu(cls.user_selector_instance)

            action = QWidgetAction(cls.user_selector_instance)
            action.setDefaultWidget(cls.user_selector_instance)
            cls.user_selector_menu_instance.addAction(action)

        # lazy theme update
        cls.user_selector_instance.reset_theme()
        cls.user_selector_menu_instance.reset_theme()

        return cls.user_selector_instance
