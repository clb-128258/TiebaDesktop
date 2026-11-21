"""
消息页：负责会话列表排序、选择和详情装配
"""

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
)

from publics import account_mgr, app_logger, request_mgr
from publics.base_ui_elements import base_ui, top_toast_widget
from publics.baidu_features.tieba_apis import (
    get_chat_subscription_list,
    get_roomlist_by_fid,
    op_subscribe_chatroom,
)
from publics.funcs import get_exception_string, start_background_thread
from publics.tb_syncer import UnreadMessageType
from publics.baidu_features.chats.structs import chatroom_data_parser as chat_http_parsers
from publics.baidu_features.chats.structs.models import ChatSession
from publics.baidu_features.chats.storage import ChatStore

from ui import reply_at_me_page

from subwindow.chats.chat_session_detail import ChatSessionDetail
from subwindow.chats.chatroom_picker import ChatRoomPickerDialog
from subwindow.chats.session_item import UserChatSessionItem


class UserInteractionsList(base_ui.InsideWidgetBaseQWidget, reply_at_me_page.Ui_Form):
    """
    聊天会话列表，支持显示互动消息、吧群聊、私信等
    """

    error_happened = pyqtSignal(top_toast_widget.ToastMessage)
    _roomsLoaded = pyqtSignal(object, int, int)
    _roomsLoadFailed = pyqtSignal(str, int)
    _subscriptionsLoaded = pyqtSignal(object, int)
    _subscriptionsLoadFailed = pyqtSignal(str, int)
    _subscriptionOperationFinished = pyqtSignal(
        bool,
        object,
        str,
        bool,
        int,
    )
    _sessionsLoaded = pyqtSignal(object, int, bool)
    _sessionsLoadFailed = pyqtSignal(int)

    is_first_show = True

    def __init__(self, bduss, stoken, parent):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.parent_window = parent
        self.account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
        self._store = None
        self._chatroom_sessions = []
        self._sessions = []
        self._selected_key = None
        self._chatroom_uid = 0
        self._subscriptions_loading = False
        self._pending_chatroom_selection = None
        self._account_generation = 0
        self._subscription_generation = 0
        self._session_generation = 0
        self._session_refresh_running = False
        self._session_refresh_pending = False
        self._pending_reload_detail = False
        self._pending_open_session_key = None
        self.detail = None

        self.listWidget.setStyleSheet(
            'QListWidget{outline:0px;background-color:transparent;}'
            'QListWidget::item{background-color:transparent;border-radius:6px;}'
            'QListWidget::item:hover{background-color:rgba(127,127,127,30);}'
            'QListWidget::item:selected{background-color:rgba(79,131,204,45);}'
        )
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.listWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget.itemClicked.connect(self._on_session_clicked)
        self.listWidget.itemActivated.connect(self._on_session_clicked)
        self.listWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listWidget.customContextMenuRequested.connect(self._show_list_menu)

        self.detail_layout = QVBoxLayout(self.sessionDetailWidget)
        self.detail_layout.setContentsMargins(12, 0, 0, 0)
        self.empty_placeholder = QLabel('选择一个会话以开始聊天')
        self.empty_placeholder.setAlignment(Qt.AlignCenter)
        self.empty_placeholder.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.detail_layout.addWidget(self.empty_placeholder)

        self._roomsLoaded.connect(self.show_room_selector)
        self._roomsLoadFailed.connect(self._on_rooms_load_failed)
        self._subscriptionsLoaded.connect(self._on_subscriptions_loaded)
        self._subscriptionsLoadFailed.connect(self._on_subscriptions_load_failed)
        self._subscriptionOperationFinished.connect(
            self._on_subscription_operation_finished
        )
        self._sessionsLoaded.connect(
            self._on_sessions_loaded,
            Qt.QueuedConnection,
        )
        self._sessionsLoadFailed.connect(self._on_sessions_load_failed)
        self.error_happened.connect(self.parent_window.toast_widget.showToast)
        self.destroyed.connect(self._cleanup)

        self.set_account(bduss, stoken)
        self.reset_theme()

    def _cleanup(self):
        self._account_generation += 1
        self._subscription_generation += 1
        self._session_generation += 1
        self._session_refresh_running = False
        self._session_refresh_pending = False
        if self._store is not None:
            self._store.close()
            self._store = None

    def set_account(self, bduss, stoken):
        was_initialized = self._store is not None
        if self.detail is not None:
            self.detail.close_session()
            self.detail.clear_session()
        if self._store is not None:
            self._store.close()
        uid = account_mgr.GlobalAccountContainer.get_current_account().uid
        self.bduss = bduss
        self.stoken = stoken
        self._store = ChatStore(uid)
        self._chatroom_uid = uid
        self._chatroom_sessions = []
        self._pending_chatroom_selection = None
        self._account_generation += 1
        self._subscription_generation += 1
        self._session_generation += 1
        self._session_refresh_running = False
        self._session_refresh_pending = False
        self._pending_reload_detail = False
        self._subscriptions_loading = False
        self._pending_open_session_key = None
        if self.detail is not None:
            self.detail.set_account(bduss, stoken, uid)
            self.detail.hide()
        self.empty_placeholder.show()
        self._selected_key = None
        self._sessions = []
        self.listWidget.blockSignals(True)
        self.listWidget.clear()
        self.listWidget.blockSignals(False)
        self.is_first_show = True
        if was_initialized:
            self._load_chatroom_subscriptions()

    def reset_theme(self):
        super().reset_theme()
        self.empty_placeholder.setStyleSheet(
            'QLabel{color:grey;font-size:20px;}'
        )
        if self.detail is not None:
            self.detail.reset_theme()
        for row in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(row))
            if widget is not None:
                widget.reset_theme()

    def refresh_list(self):
        self.refresh_sessions(reload_detail=True)
        self._load_chatroom_subscriptions()

    def total_unread_count(self):
        interaction_count = sum(
            session.unread_count
            for session in self._build_interaction_sessions()
        )
        private_count = sum(
            session.unread_count
            for session in self._sessions
            if session.is_private
        )
        return interaction_count + private_count

    def refresh_sessions(self, reload_detail=False):
        if self._store is None:
            return
        if self._session_refresh_running:
            self._session_refresh_pending = True
            self._pending_reload_detail = (
                    self._pending_reload_detail or reload_detail
            )
            return

        self._session_refresh_running = True
        self._session_generation += 1
        generation = self._session_generation
        store = self._store

        def load():
            try:
                private_sessions = store.get_sessions()
            except Exception as error:
                app_logger.log_exception(error)
                self._sessionsLoadFailed.emit(generation)
            else:
                self._sessionsLoaded.emit(
                    private_sessions,
                    generation,
                    reload_detail,
                )

        start_background_thread(load)

    def _on_sessions_loaded(
            self,
            private_sessions,
            generation,
            reload_detail,
    ):
        if generation != self._session_generation or self._store is None:
            return
        self._session_refresh_running = False

        interaction_sessions = self._build_interaction_sessions()
        chat_sessions = list(private_sessions)
        chat_sessions.extend(self._chatroom_sessions)
        chat_sessions.sort(
            key=lambda session: session.timestamp,
            reverse=True,
        )
        self._sessions = interaction_sessions + chat_sessions
        if not any(
                session.key == self._selected_key
                for session in self._sessions
        ):
            self._selected_key = None
            if self.detail is not None:
                self.detail.clear_session()
                self.detail.hide()
            self.empty_placeholder.show()
        self._rebuild_list(reload_detail=reload_detail)
        self._select_pending_session()
        self.parent_window.set_unread_count()
        self._run_pending_session_refresh()

    def _on_sessions_load_failed(self, generation):
        if generation != self._session_generation:
            return
        self._session_refresh_running = False
        self._run_pending_session_refresh()

    def _run_pending_session_refresh(self):
        if not self._session_refresh_pending:
            return
        reload_detail = self._pending_reload_detail
        self._session_refresh_pending = False
        self._pending_reload_detail = False
        self.refresh_sessions(reload_detail=reload_detail)

    def _select_pending_session(self):
        pending_key = self._pending_open_session_key
        self._pending_open_session_key = None
        if not pending_key:
            pending_room_id = self._pending_chatroom_selection
            self._pending_chatroom_selection = None
            if pending_room_id:
                pending_key = f'chatroom:{int(pending_room_id)}'
        if not pending_key:
            return
        if any(session.key == pending_key for session in self._sessions):
            self._select_session(pending_key, force=True)

    def _load_chatroom_subscriptions(self, force=False):
        if not self._chatroom_uid or not self.bduss:
            return
        if self._subscriptions_loading and not force:
            return
        self._subscription_generation += 1
        generation = self._subscription_generation
        self._subscriptions_loading = True
        bduss = self.bduss
        stoken = self.stoken

        def load():
            try:
                content = get_chat_subscription_list(bduss, stoken)
                rooms = chat_http_parsers.parse_chat_subscription_list(content)
            except Exception as error:
                app_logger.log_exception(error)
                self._subscriptionsLoadFailed.emit(
                    get_exception_string(error),
                    generation,
                )
            else:
                self._subscriptionsLoaded.emit(rooms.room_list, generation)

        start_background_thread(load)

    def _on_subscriptions_loaded(self, rooms, generation):
        if generation != self._subscription_generation:
            return
        self._subscriptions_loading = False
        self._chatroom_sessions = [
            ChatSession.chatroom_session(room)
            for room in rooms
        ]
        self.refresh_sessions()

    def _on_subscriptions_load_failed(self, error, generation):
        if generation != self._subscription_generation:
            return
        self._subscriptions_loading = False
        self._pending_chatroom_selection = None
        self.error_happened.emit(top_toast_widget.ToastMessage(
            f'[获取订阅吧群] {error}',
            icon_type=top_toast_widget.ToastIconType.ERROR,
        ))

    def _on_rooms_load_failed(self, error, generation):
        if generation != self._account_generation:
            return
        self.error_happened.emit(top_toast_widget.ToastMessage(
            f'[获取吧群] {error}',
            icon_type=top_toast_widget.ToastIconType.ERROR,
        ))

    def _build_interaction_sessions(self):
        syncer = self.parent_window.notice_syncer
        categories = (
            ('agree', UnreadMessageType.AGREE, '赞过我的'),
            ('reply', UnreadMessageType.REPLY, '回复我的'),
            ('at', UnreadMessageType.AT, '@我的'),
        )
        return [
            ChatSession.interaction_session(
                category,
                unread_count=syncer.get_unread_notice_count(kind),
                title=title,
            )
            for category, kind, title in categories
        ]

    def _rebuild_list(self, reload_detail=False):
        desired_keys = {session.key for session in self._sessions}
        item_by_key = {}
        for row in range(self.listWidget.count()):
            item = self.listWidget.item(row)
            key = item.data(Qt.UserRole)
            if key:
                item_by_key[key] = item

        for row in range(self.listWidget.count() - 1, -1, -1):
            item = self.listWidget.item(row)
            key = item.data(Qt.UserRole)
            if key in desired_keys:
                continue
            item_by_key.pop(key, None)
            widget = self.listWidget.itemWidget(item)
            if widget is not None:
                self.listWidget.removeItemWidget(item)
                widget.hide()
                widget.deleteLater()
            stale_item = self.listWidget.takeItem(row)
            stale_item.setData(Qt.UserRole, None)
            del stale_item

        for row, session in enumerate(self._sessions):
            item = item_by_key.get(session.key)
            widget = self.listWidget.itemWidget(item) if item is not None else None
            if item is None:
                widget = UserChatSessionItem(session)
                item = QListWidgetItem()
                item.setData(Qt.UserRole, session.key)
                item.setSizeHint(widget.sizeHint())
                self.listWidget.insertItem(row, item)
                self.listWidget.setItemWidget(item, widget)
            else:
                current_row = self.listWidget.row(item)
                if current_row != row:
                    self.listWidget.removeItemWidget(item)
                    moved_item = self.listWidget.takeItem(current_row)
                    self.listWidget.insertItem(row, moved_item)
                    if widget is not None:
                        self.listWidget.setItemWidget(moved_item, widget)
                    item = moved_item
                if widget is None:
                    widget = UserChatSessionItem(session)
                    self.listWidget.setItemWidget(item, widget)
                else:
                    widget.set_session(session)
                size_hint = widget.sizeHint()
                if item.sizeHint() != size_hint:
                    item.setSizeHint(size_hint)
            item_by_key[session.key] = item

        if self._selected_key is None:
            self.listWidget.setCurrentItem(None)
            selection_model = self.listWidget.selectionModel()
            selection_model.clearCurrentIndex()
            selection_model.clearSelection()
        else:
            selected_item = item_by_key.get(self._selected_key)
            if selected_item is not None:
                self.listWidget.setCurrentItem(selected_item)
        if self._sessions and self._selected_key is not None and reload_detail:
            self._select_session(self._selected_key, force=True)

    def _on_session_clicked(self, item):
        if item is None:
            self._show_empty_state()
            return
        key = item.data(Qt.UserRole)
        session = next((session for session in self._sessions if session.key == key), None)
        self._select_session(
            key,
            force=bool(session and session.is_chatroom),
        )

    def _select_session(self, key, force=False):
        session = next((item for item in self._sessions if item.key == key), None)
        if session is None:
            return
        if self._selected_key == key:
            return

        self._selected_key = key
        self._ensure_detail()
        self.empty_placeholder.hide()
        self.detail.show()
        self.detail.set_session(session, force=force)

    def _show_empty_state(self, destroy=True):
        self._selected_key = None
        if self.detail is not None and destroy:
            self.detail.clear_session()
            self.detail.hide()

        self.detail = None
        self.empty_placeholder.show()

    def _ensure_detail(self):
        if self.detail is not None:
            return
        self.detail = ChatSessionDetail(
            self.bduss,
            self.stoken,
            parent=self.sessionDetailWidget,
            account=self.account_manager.current_account,
        )
        self.detail.hide()
        self.detail_layout.addWidget(self.detail)
        self.detail.toastRequested.connect(self.parent_window.toast_widget.showToast)
        self.detail.detachRequested.connect(self._on_detail_detached)
        self.detail.unsubscribeRequested.connect(self._unsubscribe_chatroom)
        self.detail.sessionChanged.connect(
            self._on_detail_session_changed,
            Qt.QueuedConnection,
        )

    def open_private_session(self, peer_user_id):
        key = f'private:{int(peer_user_id)}'
        session = next((item for item in self._sessions if item.key == key), None)
        if session is None:
            self._pending_open_session_key = key
            self.refresh_sessions()
            return
        for row in range(self.listWidget.count()):
            item = self.listWidget.item(row)
            if item.data(Qt.UserRole) == key:
                self.listWidget.setCurrentItem(item)
                break
        self._select_session(key, force=True)

    def suspend_current_session(self, wait=True):
        if self.detail is not None:
            self.detail.suspend_chatroom(wait=wait)

    def resume_current_session(self):
        if self.detail is not None:
            self.detail.resume_chatroom()

    def on_private_messages(self, messages):
        if self.detail is not None:
            self.detail.on_private_messages(messages)
        self.refresh_sessions()

    def _on_detail_session_changed(self, session):
        if session is None:
            return
        if session.is_chatroom:
            for index, current in enumerate(self._chatroom_sessions):
                if current.key == session.key:
                    self._chatroom_sessions[index] = session
                    break
            self.refresh_sessions()
        elif session.is_private:
            self.refresh_sessions()
        elif session.is_interaction:
            self.parent_window.notice_syncer.run_msg_sync_immedently()
            self.refresh_sessions()

    def _on_detail_detached(self, need_destroy):
        self._show_empty_state(need_destroy)
        self.listWidget.setCurrentItem(None)

    def _unsubscribe_chatroom(self, room_id):
        self._set_chatroom_subscription(room_id, subscribe=False)

    def _set_chatroom_subscription(self, room_id, subscribe):
        bduss = self.bduss
        stoken = self.stoken
        account = self.account_manager.current_account
        uid = int(account.uid or self._chatroom_uid)
        generation = self._account_generation

        def update():
            try:
                baidu_id, tbs = account.baidu_id, account.aiotieba_account.tbs
                response = op_subscribe_chatroom(
                    bduss,
                    stoken,
                    room_id,
                    subscribe=subscribe,
                    uid=uid,
                    baidu_id=baidu_id,
                    tbs=tbs,
                    common_params=request_mgr.get_chat_common_params(account),
                )

                chat_http_parsers.parse_chatroom_subscription_operation(response)
            except Exception as error:
                app_logger.log_exception(error)
                self._subscriptionOperationFinished.emit(
                    subscribe,
                    int(room_id),
                    get_exception_string(error),
                    False,
                    generation,
                )
            else:
                self._subscriptionOperationFinished.emit(
                    subscribe,
                    int(room_id),
                    '',
                    True,
                    generation,
                )

        start_background_thread(update)

    def _on_subscription_operation_finished(
            self,
            subscribe,
            room_id,
            error,
            success,
            generation,
    ):
        if generation != self._account_generation:
            return
        if not success:
            action = '订阅' if subscribe else '取消订阅'
            self.error_happened.emit(top_toast_widget.ToastMessage(
                f'[{action}吧群] {error}',
                icon_type=top_toast_widget.ToastIconType.ERROR,
            ))
            return
        if not subscribe and self._selected_key == f'chatroom:{room_id}':
            self._show_empty_state()
        self._load_chatroom_subscriptions(force=True)

    def _show_list_menu(self, position: QPoint):
        menu = base_ui.BaseQMenu(self)
        refresh_action = QAction('刷新会话', menu)
        refresh_action.triggered.connect(self.refresh_list)
        menu.addAction(refresh_action)

        add_room_action = QAction('添加吧群订阅', menu)
        add_room_action.triggered.connect(self.add_chatroom)
        menu.addAction(add_room_action)

        item = self.listWidget.itemAt(position)
        if item is not None:
            key = item.data(Qt.UserRole)
            session = next((s for s in self._sessions if s.key == key), None)
            if session is not None and session.is_chatroom:
                remove_action = QAction('取消订阅', menu)
                remove_action.triggered.connect(
                    lambda: self._unsubscribe_chatroom(session.target_id)
                )
                menu.addAction(remove_action)

        menu.exec(self.listWidget.viewport().mapToGlobal(position))

    def add_chatroom(self):
        fid, ok = QInputDialog.getInt(
            self.parent_window,
            '添加吧群订阅',
            '请输入吧 ID：',
            0,
            1,
            2147483647,
        )
        if not ok or not fid:
            return
        generation = self._account_generation

        def load():
            try:
                content = get_roomlist_by_fid(self.bduss, self.stoken, fid)
                rooms = chat_http_parsers.parse_roomlist_by_fid(
                    content,
                    default_fid=fid,
                )
            except Exception as error:
                app_logger.log_exception(error)
                self._roomsLoadFailed.emit(
                    get_exception_string(error),
                    generation,
                )
            else:
                self._roomsLoaded.emit(rooms.room_list, fid, generation)

        start_background_thread(load)

    def show_room_selector(self, rooms, fid, generation):
        if generation != self._account_generation:
            return
        if not rooms:
            self._roomsLoadFailed.emit('该吧没有可订阅的吧群', generation)
            return
        normalized_rooms = rooms
        normalized_rooms = [room for room in normalized_rooms if room['room_id']]
        if not normalized_rooms:
            self._roomsLoadFailed.emit('该吧没有可订阅的吧群', generation)
            return
        picker = ChatRoomPickerDialog(normalized_rooms)
        if picker.exec() != picker.Accepted:
            return
        room = picker.selected_room()
        if room is None:
            return
        room_id = room['room_id']
        self._pending_chatroom_selection = room_id
        self._set_chatroom_subscription(room_id, subscribe=True)
