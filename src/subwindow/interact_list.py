"""消息页：只负责会话列表排序、选择和详情装配。"""
import asyncio

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import (
    QAction,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
)

from publics import account_mgr, app_logger
from publics.base_ui_elements import base_ui, top_toast_widget
from publics.baidu_features.tieba_message_apis import get_roomlist_by_fid
from publics.funcs import get_exception_string, start_background_thread
from publics.tb_syncer import UnreadMessageType

from ui import reply_at_me_page

from subwindow.chats.chat_session_detail import ChatSessionDetail
from subwindow.chats.chatroom_picker import ChatRoomPickerDialog
from subwindow.chats.models import ChatSession
from subwindow.chats.session_item import UserChatSessionItem
from subwindow.chats.storage import ChatRoomSubscriptionStore, ChatStore


class UserInteractionsList(base_ui.InsideWidgetBaseQWidget, reply_at_me_page.Ui_Form):
    """统一聊天会话列表。"""

    error_happened = pyqtSignal(top_toast_widget.ToastMessage)
    _roomsLoaded = pyqtSignal(object, int)
    _roomsLoadFailed = pyqtSignal(str)

    is_first_show = True

    def __init__(self, bduss, stoken, parent):
        super().__init__()
        self.setupUi(self)

        self.bduss = bduss
        self.stoken = stoken
        self.parent_window = parent
        self.account_manager = account_mgr.GlobalAccountContainer.get_current_manager()
        self._store = None
        self._chatroom_store = None
        self._sessions = []
        self._selected_key = None
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

        self._roomsLoaded.connect(self._show_room_selector)
        self._roomsLoadFailed.connect(
            lambda error: self.error_happened.emit(top_toast_widget.ToastMessage(
                f'[获取吧群] {error}',
                icon_type=top_toast_widget.ToastIconType.ERROR,
            ))
        )
        self.error_happened.connect(self.parent_window.toast_widget.showToast)
        self.destroyed.connect(self._cleanup)

        self.set_account(bduss, stoken)
        self.reset_theme()

    def _cleanup(self):
        if self._store is not None:
            self._store.close()
            self._store = None

    def set_account(self, bduss, stoken):
        if self.detail is not None:
            self.detail.close_session()
            self.detail.clear_session()
        if self._store is not None:
            self._store.close()
        uid = account_mgr.GlobalAccountContainer.get_current_account().uid
        self.bduss = bduss
        self.stoken = stoken
        self._store = ChatStore(uid)
        self._chatroom_store = ChatRoomSubscriptionStore(uid)
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

    def reset_theme(self):
        super().reset_theme()
        self.empty_placeholder.setStyleSheet(
            'QLabel{color:grey;font-size:17px;}'
        )
        if self.detail is not None:
            self.detail.reset_theme()
        for row in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(row))
            if widget is not None:
                widget.reset_theme()

    def refresh_list(self):
        self.refresh_sessions(reload_detail=True)

    def total_unread_count(self):
        interaction_count = sum(
            session.unread_count
            for session in self._build_interaction_sessions()
        )
        private_count = sum(
            session.unread_count
            for session in self._store.get_sessions()
        ) if self._store is not None else 0
        return interaction_count + private_count

    def refresh_sessions(self, reload_detail=False):
        if self._store is None:
            return

        sessions = self._build_interaction_sessions()
        sessions.extend(self._store.get_sessions())
        sessions.extend(
            ChatSession.chatroom_session(room)
            for room in self._chatroom_store.list_rooms()
        )
        sessions[3:] = sorted(
            sessions[3:],
            key=lambda session: session.timestamp,
            reverse=True,
        )
        self._sessions = sessions
        if not any(session.key == self._selected_key for session in sessions):
            self._selected_key = None
            if self.detail is not None:
                self.detail.clear_session()
                self.detail.hide()
            self.empty_placeholder.show()
        self._rebuild_list(reload_detail=reload_detail)
        if hasattr(self.parent_window, 'set_unread_count'):
            self.parent_window.set_unread_count()

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
        while self.listWidget.count():
            item = self.listWidget.item(0)
            widget = self.listWidget.itemWidget(item)
            self.listWidget.takeItem(0)
            if widget is not None:
                widget.deleteLater()
            del item

        target_row = 0
        for row, session in enumerate(self._sessions):
            widget = UserChatSessionItem(session)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, session.key)
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
            if session.key == self._selected_key:
                target_row = row

        if self._selected_key is None:
            self.listWidget.setCurrentItem(None)
            selection_model = self.listWidget.selectionModel()
            selection_model.clearCurrentIndex()
            selection_model.clearSelection()
        elif self._sessions:
            self.listWidget.setCurrentRow(target_row)
        if self._sessions and self._selected_key is not None and reload_detail:
            self._select_session(self._selected_key, force=True)
        QPixmapCache.clear()

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
        self._selected_key = key
        self._ensure_detail()
        self.empty_placeholder.hide()
        self.detail.show()
        self.detail.set_session(session, force=force)

    def _show_empty_state(self):
        self._selected_key = None
        if self.detail is not None:
            self.detail.clear_session()
            self.detail.hide()
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
            self.refresh_sessions()
            session = next((item for item in self._sessions if item.key == key), None)
        if session is None:
            return
        for row in range(self.listWidget.count()):
            item = self.listWidget.item(row)
            if item.data(Qt.UserRole) == key:
                self.listWidget.setCurrentItem(item)
                break
        self._select_session(key, force=True)

    def suspend_current_session(self):
        if self.detail is not None:
            self.detail.suspend_chatroom()

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
            self._chatroom_store.update_room(
                session.target_id,
                name=session.title,
                avatar=session.avatar,
                forum_name=session.extra.get('forum_name', ''),
                fid=session.extra.get('fid', 0),
                member_num=session.extra.get('member_num', 0),
                last_message=session.subtitle,
                last_time=session.timestamp,
            )
            self.refresh_sessions()
        elif session.is_private:
            self.refresh_sessions()
        elif session.is_interaction:
            self.parent_window.notice_syncer.run_msg_sync_immedently()
            self.refresh_sessions()

    def _on_detail_detached(self, session):
        self._show_empty_state()
        self.listWidget.setCurrentItem(None)

    def _unsubscribe_chatroom(self, room_id):
        self._chatroom_store.remove_room(room_id)
        self._show_empty_state()
        self.refresh_sessions(reload_detail=True)

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

        account = self.account_manager.current_account.aiotieba_account

        def load():
            try:
                rooms = asyncio.run(get_roomlist_by_fid(account, fid))
            except Exception as error:
                app_logger.log_exception(error)
                self._roomsLoadFailed.emit(get_exception_string(error))
            else:
                self._roomsLoaded.emit(rooms.room_list, fid)

        start_background_thread(load)

    def _show_room_selector(self, rooms, fid):
        if not rooms:
            self._roomsLoadFailed.emit('该吧没有可订阅的吧群')
            return
        normalized_rooms = [
            self._normalize_room(room, fid)
            for room in rooms
        ]
        normalized_rooms = [room for room in normalized_rooms if room['room_id']]
        if not normalized_rooms:
            self._roomsLoadFailed.emit('该吧没有可订阅的吧群')
            return
        picker = ChatRoomPickerDialog(normalized_rooms)
        if picker.exec() != picker.Accepted:
            return
        room = picker.selected_room()
        if room is None:
            return
        room_id = room['room_id']
        self._chatroom_store.add_room(room)
        self._selected_key = f'chatroom:{room_id}'
        self.refresh_sessions(reload_detail=True)

    @staticmethod
    def _normalize_room(raw, default_fid=0):
        room_info = raw.get('room_info')
        if not isinstance(room_info, dict):
            room_info = raw
        msg_info = raw.get('msg_info')
        if not isinstance(msg_info, dict):
            msg_info = {}

        room_id = int(
            raw.get('room_id')
            or room_info.get('room_id')
            or room_info.get('id')
            or 0
        )
        forum_id = int(
            room_info.get('forum_id')
            or raw.get('forum_id')
            or default_fid
            or 0
        )
        forum_name = str(
            room_info.get('forum_name')
            or raw.get('forum_name')
            or ''
        )
        room_name = str(
            room_info.get('name')
            or raw.get('name')
            or room_info.get('room_name')
            or f'吧群 {room_id}'
        )
        if forum_name and forum_name not in room_name:
            display_name = f'{room_name}（{forum_name}吧）'
        else:
            display_name = room_name

        return {
            'room_id': room_id,
            'fid': forum_id,
            'forum_name': forum_name,
            'name': display_name,
            'avatar': str(room_info.get('avatar') or raw.get('avatar') or ''),
            'last_message': str(msg_info.get('content') or ''),
            'last_time': int(msg_info.get('msg_time') or 0),
            'unread_count': int(room_info.get('unread_num') or 0),
        }
