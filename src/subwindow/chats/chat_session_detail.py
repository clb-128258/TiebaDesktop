"""统一私信、吧群和互动消息会话详情。"""
import math

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QTextDocument
from PyQt5.QtWidgets import (
    QAction,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QWidget,
)

from publics import account_mgr, profile_mgr, qt_image, qt_window_mgr
from publics.base_ui_elements import base_ui, top_toast_widget,loading_widget
from publics.base_ui_elements.message_box import MessageBox
from publics.funcs import (
    cleanup_listWidget,
    get_exception_string,
    show_label_pixmap_with_animation,
    start_background_thread,
)

from ui import chat_session_detail

from .chatroom_session import ChatRoomSessionWorker
from .interaction import InteractionSessionProvider
from .message_widget import ChatMessageWidget
from .models import ChatSessionType
from .storage import ChatStore


class ChatSessionDetail(base_ui.WindowBaseQWidget, chat_session_detail.Ui_Form):
    """单实例承载全部会话类型。"""

    toastRequested = pyqtSignal(object)
    detachRequested = pyqtSignal(object)
    unsubscribeRequested = pyqtSignal(int)
    sessionChanged = pyqtSignal(object)
    _interactionLoaded = pyqtSignal(object)
    _interactionFailed = pyqtSignal(str)
    _chatroomDetailLoaded = pyqtSignal(object, object)
    _chatroomMessagesLoaded = pyqtSignal(object, object)
    _sendFinished = pyqtSignal(object, object)

    def __init__(self, bduss='', stoken='', parent=None, independent=False, account=None):
        super().__init__()
        self.setupUi(self)
        if parent is not None:
            self.setParent(parent)

        self.bduss = bduss
        self.stoken = stoken
        self.account = account or account_mgr.GlobalAccountContainer.get_current_account()
        self.independent = independent
        self.current_session = None
        self._store = None
        self._chatroom_worker = None
        self._chatroom_messages = []
        self._interaction_entries = []
        self._interaction_category = ''
        self._interaction_page = 0
        self._interaction_has_more = True
        self._interaction_loading = False
        self._interaction_agree_cursor = 0
        self._interaction_scroll_ready = False
        self._load_version = 0
        self._cleaned = False

        self.setWindowIcon(QIcon('ui/tieba_logo_small.png'))
        self.init_ui_elements()
        self.reset_theme()

        if independent:
            self.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
            self.toolButton_2.hide()
            self.top_toaster = top_toast_widget.TopToaster()
            self.top_toaster.setCoverWidget(self)
            self.toastRequested.connect(self.top_toaster.showToast)

        self.listWidget.setStyleSheet(
            'QListWidget{outline:0px;background-color:transparent;}'
            'QListWidget::item{background-color:transparent;}'
        )
        self.listWidget.verticalScrollBar().setSingleStep(25)
        self.listWidget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.listWidget.verticalScrollBar().valueChanged.connect(self._load_visible_images)
        self.listWidget.verticalScrollBar().valueChanged.connect(self._on_message_scroll)

        self.portrait_image = qt_image.MultipleImage()
        self.portrait_image.currentPixmapChanged.connect(
            lambda pixmap: show_label_pixmap_with_animation(self.label, pixmap)
        )
        self.destroyed.connect(self.portrait_image.destroyImage)
        self.destroyed.connect(self._cleanup)

        self.pushButton_3.clicked.connect(self.send_current_message)
        self.textEdit.textChanged.connect(self._update_send_button)
        self.toolButton.clicked.connect(self.show_more_menu)
        self.toolButton_2.clicked.connect(self.open_independent_window)

        self._interactionLoaded.connect(self._render_interaction_messages)
        self._interactionFailed.connect(self._show_error)
        self._chatroomMessagesLoaded.connect(self._render_chatroom_messages)
        self._chatroomDetailLoaded.connect(self._render_chatroom_detail)
        self._sendFinished.connect(self._on_send_finished)

        if self.account:
            self.set_account(
                self.bduss,
                self.stoken,
                self.account.uid,
            )

    def closeEvent(self, event):
        self._cleanup()
        event.accept()
        if self.independent:
            qt_window_mgr.del_window(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for row in range(self.listWidget.count()):
            self._adjust_message_item_height(self.listWidget.item(row))

    def set_account(self, bduss, stoken, uid):
        self.close_session()
        self._load_version += 1
        self.current_session = None
        current_account = account_mgr.GlobalAccountContainer.get_current_account()
        if current_account and current_account.uid == int(uid or 0):
            self.account = current_account
        self.bduss = bduss
        self.stoken = stoken
        if self._store is not None:
            self._store.close()
        self._store = ChatStore(uid)

    def set_session(self, session, force=False):
        if session is None:
            self.clear_view()
            return
        if (
                not force
                and self.current_session is not None
                and self.current_session.key == session.key
        ):
            return

        self.close_session()
        self.current_session = session
        self._load_version += 1
        load_version = self._load_version
        self.clear_view()

        self.label_2.setText(session.title or '会话')
        self.label_3.setText(self._detail_text(session))
        self._set_header_avatar(session)
        self.frame.setVisible(session.session_type in (
            ChatSessionType.PRIVATE,
            ChatSessionType.CHATROOM,
        ))

        if session.session_type == ChatSessionType.PRIVATE:
            self._load_private_messages(session)
        elif session.session_type == ChatSessionType.CHATROOM:
            self._start_chatroom_worker(session, load_version)
        elif session.session_type == ChatSessionType.INTERACTION:
            self._interaction_category = session.extra.get('category', 'reply')
            self._interaction_page = 0
            self._interaction_has_more = True
            self._interaction_loading = False
            self._interaction_agree_cursor = 0
            self._interaction_scroll_ready = False
            self._start_interaction_load(load_version, load_more=False)

        self._update_send_button()

    def clear_view(self):
        cleanup_listWidget(self.listWidget)
        self.label_2.clear()
        self.label_3.clear()
        self.textEdit.clear()

    def clear_session(self):
        self._load_version += 1
        self.close_session()
        self.current_session = None
        self.clear_view()

    def close_session(self):
        if self._chatroom_worker is not None:
            self._chatroom_worker.stop()
            self._chatroom_worker = None
        self._chatroom_messages = []
        self._interaction_entries = []
        self._interaction_loading = False
        self._interaction_scroll_ready = False

    def suspend_chatroom(self):
        if self.current_session is not None and self.current_session.is_chatroom:
            self.close_session()

    def resume_chatroom(self):
        if (
                self.current_session is not None
                and self.current_session.is_chatroom
                and self._chatroom_worker is None
        ):
            self.set_session(self.current_session, force=True)

    def _cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        self.close_session()
        self.portrait_image.destroyImage()
        if self._store is not None:
            self._store.close()
            self._store = None

    def _detail_text(self, session):
        if session.session_type == ChatSessionType.PRIVATE:
            return '私信'
        if session.session_type == ChatSessionType.CHATROOM:
            forum_name = session.extra.get('forum_name', '')
            return f'{forum_name}吧' if forum_name else ''
        return {
            'reply': '回复我的',
            'at': '@我的',
            'agree': '赞过我的',
        }.get(session.extra.get('category'), '互动消息')

    def _load_private_messages(self, session):
        self._ensure_store()
        messages = self._store.get_messages(session.target_id)
        if not messages:
            self._add_placeholder('暂无聊天记录')
        else:
            self._render_chat_messages(messages, show_sender=False)
        account_mgr.GlobalAccountContainer.get_current_manager().mark_private_session_read(
            session.target_id
        )
        self.sessionChanged.emit(session)

    def _ensure_store(self):
        if self._store is None:
            uid = self.account.uid if self.account is not None else 0
            self._store = ChatStore(uid)

    def _start_interaction_load(self, load_version, load_more):
        if not self.bduss or not self.stoken:
            self._add_placeholder('登录后即可查看互动消息')
            return
        if self._interaction_loading or (load_more and not self._interaction_has_more):
            return

        if not load_more:
            self.loading_widget.show()

        self._interaction_loading = True
        self._interaction_scroll_ready = False
        bduss = self.bduss
        stoken = self.stoken
        category = self._interaction_category
        page = self._interaction_page + 1
        agree_cursor = self._interaction_agree_cursor

        def load():
            provider = InteractionSessionProvider(bduss, stoken)
            try:
                entries, has_more, next_cursor = provider.load_page(
                    category,
                    page,
                    agree_cursor,
                )
            except Exception as error:
                if load_version == self._load_version:
                    self._safe_emit('_interactionFailed', get_exception_string(error))
                    self._safe_emit(
                        '_interactionLoaded',
                        (load_version, category, [], False, page, load_more, agree_cursor),
                    )
            else:
                self._safe_emit(
                    '_interactionLoaded',
                    (load_version, category, entries, has_more, page, load_more, next_cursor),
                )

        start_background_thread(load)

    def _safe_emit(self, signal_name, *args):
        try:
            signal = getattr(self, signal_name)
            signal.emit(*args)
        except (RuntimeError, AttributeError):
            pass

    def _render_interaction_messages(self, result):
        (
            load_version,
            category,
            entries,
            has_more,
            page,
            load_more,
            agree_cursor,
        ) = result

        if load_version != self._load_version:
            return
        if category != self._interaction_category:
            return

        self._interaction_loading = False
        self._interaction_page = page
        self._interaction_has_more = has_more
        self._interaction_agree_cursor = agree_cursor
        if not load_more:
            self._interaction_entries = []
            cleanup_listWidget(self.listWidget)

        existing_keys = {
            (
                item.category,
                item.data.get('thread_id', 0),
                item.data.get('post_id', 0),
                item.timestamp,
            )
            for item in self._interaction_entries
        }
        new_entries = []
        for entry in entries:
            key = (
                entry.category,
                entry.data.get('thread_id', 0),
                entry.data.get('post_id', 0),
                entry.timestamp,
            )
            if key not in existing_keys:
                existing_keys.add(key)
                new_entries.append(entry)
        self._interaction_entries.extend(new_entries)

        if page == 1 and not new_entries:
            self._interaction_has_more = False
            self._add_placeholder('暂无互动消息')
            return
        if load_more and not new_entries:
            self._interaction_has_more = False
            self._interaction_scroll_ready = True
            return
        for entry in new_entries:
            self._append_interaction_entry(entry)
        if page == 1:
            self.listWidget.scrollToTop()

        QTimer.singleShot(180, self._enable_interaction_scroll)
        QTimer.singleShot(0, self._load_visible_images)

        self.loading_widget.hide()

    def _enable_interaction_scroll(self):
        if (
                self.current_session is not None
                and self.current_session.is_interaction
        ):
            self._interaction_scroll_ready = True

    def _on_message_scroll(self, value):
        if (
                not self._interaction_scroll_ready
                or self._interaction_loading
                or not self._interaction_has_more
                or self.current_session is None
                or not self.current_session.is_interaction
        ):
            return
        scrollbar = self.listWidget.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= scrollbar.maximum():
            self._start_interaction_load(self._load_version, load_more=True)

    def _append_interaction_entry(self, entry):
        from subwindow.thread_agreed_item import AgreedThreadItem
        from subwindow.thread_reply_item import ReplyItem

        data = entry.data
        if entry.category == 'agree':
            item_widget = AgreedThreadItem(self.bduss, self.stoken)
            item_widget.item_type = data['item_type']
            item_widget.portrait = data['portrait']
            item_widget.thread_id = data['thread_id']
            item_widget.post_id = data['post_id']
            item_widget.setdatas(
                data['portrait'],
                data['user_name'],
                data['content'],
                data['pic_link'],
                data['post_time_str'],
                '在 <a href="tieba_forum://{fid}">{fname}吧</a> '
                '的主题贴 <a href="tieba_thread://{tid}">{tname}</a> '
                '内为你发布的以下内容点了赞：'.format(
                    fname=data['forum_name'],
                    tname=data['thread_title'],
                    tid=data['thread_id'],
                    fid=data['forum_id'],
                ),
            )
        else:
            item_widget = ReplyItem(self.bduss, self.stoken)
            item_widget.messageAdded.connect(self.toastRequested.emit)
            item_widget.show_msg_outside = True
            item_widget.load_by_callback = True
            item_widget.is_comment = data['is_subfloor']
            item_widget.portrait = data['portrait']
            item_widget.thread_id = data['thread_id']
            item_widget.post_id = data['post_id']
            item_widget.forum_id = data['forum_id']
            item_widget.subcomment_show_thread_button = True
            item_widget.set_reply_text(
                '{sub_floor}在 <a href="tieba_forum://{fid}">{fname}吧</a> '
                '的主题贴 <a href="tieba_thread://{tid}">{tname}</a> '
                '中{ptype}了你：'.format(
                    fname=data['forum_name'],
                    tname=data['thread_title'],
                    tid=data['thread_id'],
                    fid=data['forum_id'],
                    sub_floor='[楼中楼] ' if data['is_subfloor'] else '[回复贴] ',
                    ptype='回复' if data['type'] == 'reply' else '@',
                )
            )
            item_widget.setdatas(
                data['portrait'],
                data['user_name'],
                False,
                data['content'],
                [],
                -1,
                data['post_time_str'],
                '',
                -2,
                -1,
                -1,
                False,
            )

        self._enable_wrapped_layout(item_widget)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        item_widget.setMaximumWidth(760)
        layout.addStretch(1)
        layout.addWidget(item_widget, 8)
        layout.addStretch(1)

        item = QListWidgetItem()
        item.setData(Qt.UserRole + 1, item_widget)
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, container)
        self._adjust_message_item_height(item)

    def _enable_wrapped_layout(self, widget):
        for name in ('label_6', 'label_10'):
            label = getattr(widget, name, None)
            if label is None:
                continue
            label.setWordWrap(True)
            label.setMaximumHeight(16777215)
            policy = label.sizePolicy()
            policy.setHeightForWidth(True)
            policy.setVerticalPolicy(QSizePolicy.MinimumExpanding)
            label.setSizePolicy(policy)

    def _start_chatroom_worker(self, session, load_version):
        self.loading_widget.show()
        worker = ChatRoomSessionWorker(
            self.account,
            session.target_id,
            session.extra.get('fid', 0),
            on_messages=lambda messages: self._safe_emit(
                '_chatroomMessagesLoaded',
                load_version,
                messages,
            ),
            on_error=lambda error: self._safe_emit(
                '_interactionFailed',
                get_exception_string(error),
            ),
            on_detail=lambda detail: self._safe_emit(
                '_chatroomDetailLoaded',
                load_version,
                detail,
            ),
        )
        self._chatroom_worker = worker
        worker.start()

    def _render_chatroom_detail(self, load_version, detail):
        if (
                load_version != self._load_version
                or self.current_session is None
                or not self.current_session.is_chatroom
        ):
            return
        self.current_session.title = detail.name or self.current_session.title
        self.current_session.avatar = detail.avatar or self.current_session.avatar
        self.current_session.extra['fid'] = detail.fid or self.current_session.extra.get('fid', 0)
        self.current_session.extra['forum_name'] = detail.fname
        self.current_session.extra['member_num'] = detail.member_num
        self.label_2.setText(self.current_session.title)
        self.label_3.setText(
            f'{detail.fname}吧 | 热度 {detail.member_num}'
            if detail.fname
            else f'热度 {detail.member_num}'
        )
        self._set_header_avatar(self.current_session)
        self.setWindowTitle(self.current_session.title)
        self.sessionChanged.emit(self.current_session)

    def _render_chatroom_messages(self, load_version, messages):
        if load_version != self._load_version:
            return

        signature = [(m.message_id, m.timestamp, m.text) for m in messages]
        old_signature = [
            (m.message_id, m.timestamp, m.text)
            for m in self._chatroom_messages
        ]
        if signature == old_signature:
            return

        self._chatroom_messages = messages

        cleanup_listWidget(self.listWidget)
        if not messages:
            self._add_placeholder('本群暂无消息')
            return

        self._render_chat_messages(messages, show_sender=True)
        self.listWidget.scrollToBottom()
        if self.current_session is not None and messages:
            last = messages[-1]
            self.current_session.subtitle = last.text
            self.current_session.timestamp = last.timestamp
            self.sessionChanged.emit(self.current_session)

        self.loading_widget.hide()

    def _render_chat_messages(self, messages, show_sender):
        cleanup_listWidget(self.listWidget)
        for message in messages:
            widget = ChatMessageWidget(message, show_sender=show_sender)
            item = QListWidgetItem()
            item.setData(Qt.UserRole + 1, widget)
            self.listWidget.addItem(item)
            self.listWidget.setItemWidget(item, widget)
            self._adjust_message_item_height(item)
        self.listWidget.scrollToBottom()

    def _adjust_message_item_height(self, item):
        if item is None:
            return
        width = max(80, self.listWidget.viewport().width())
        inner_widget = item.data(Qt.UserRole + 1)
        list_item_widget = self.listWidget.itemWidget(item)
        if (
                list_item_widget is not None
                and list_item_widget is not inner_widget
        ):
            list_item_widget.setFixedWidth(width)
        if isinstance(inner_widget, ChatMessageWidget):
            height = inner_widget.preferred_height(width)
        elif isinstance(inner_widget, QWidget):
            inner_width = max(140, min(760, width - 24))
            inner_widget.setFixedWidth(inner_width)
            self._resize_interaction_labels(inner_widget, inner_width)
            layout = inner_widget.layout()
            if layout is not None:
                layout.activate()
            height = inner_widget.sizeHint().height()
            if layout is not None and layout.hasHeightForWidth():
                height_for_width = layout.heightForWidth(inner_width)
                if height_for_width > 0:
                    height = height_for_width
        else:
            height = max(50, item.sizeHint().height())
        item.setSizeHint(QSize(width, max(50, height + 4)))

    def _resize_interaction_labels(self, widget, width):
        label_6 = getattr(widget, 'label_6', None)
        label_10 = getattr(widget, 'label_10', None)
        if label_6 is not None and not label_6.isHidden():
            image_width = 0
            label_2 = getattr(widget, 'label_2', None)
            if label_2 is not None and not label_2.isHidden():
                image_width = max(label_2.width(), 100)
            label_6.setFixedHeight(
                self._document_height(label_6, width - image_width - 18)
            )
        if label_10 is not None and not label_10.isHidden():
            label_10.setFixedHeight(
                max(26, self._document_height(label_10, width - 18))
            )

    @staticmethod
    def _document_height(label, width):
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(label.font())
        document.setHtml(label.text())
        document.setTextWidth(max(40, width))
        return max(18, int(math.ceil(document.size().height())) + 6)

    def _add_placeholder(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet('QLabel{color:grey;padding:30px;}')
        item = QListWidgetItem()
        item.setSizeHint(label.sizeHint())
        self.listWidget.addItem(item)
        self.listWidget.setItemWidget(item, label)

    def _set_header_avatar(self, session):
        if session.session_type == ChatSessionType.PRIVATE and session.avatar:
            self.portrait_image.destroyImage()
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.TiebaPortrait,
                session.avatar.split('?', 1)[0],
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        elif session.session_type == ChatSessionType.CHATROOM and session.avatar:
            self.portrait_image.destroyImage()
            self.portrait_image.setImageInfo(
                qt_image.ImageLoadSource.HttpLink,
                session.avatar,
                qt_image.ImageCoverType.RoundCover,
                (42, 42),
            )
            self.portrait_image.loadImage()
        else:
            self.portrait_image.destroyImage()
            policy = profile_mgr.get_theme_policy_string()[1]
            pixmap = QPixmap(f'ui/icon_{policy}/comment.png')
            pixmap.setDevicePixelRatio(qt_image.get_screen_ratio())
            self.label.setPixmap(pixmap.scaled(
                30,
                30,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            ))

    def _load_visible_images(self):
        rect = self.listWidget.viewport().contentsRect()
        start = self.listWidget.indexAt(rect.topLeft())
        end = self.listWidget.indexAt(rect.bottomLeft())
        if not start.isValid():
            return
        if not end.isValid():
            end = self.listWidget.model().index(self.listWidget.count() - 1)
        for row in range(start.row(), end.row() + 1):
            widget = self.listWidget.itemWidget(self.listWidget.item(row))
            if hasattr(widget, 'load_images'):
                widget.load_images()
            elif widget is not None:
                for child in widget.findChildren(QWidget):
                    if hasattr(child, 'load_images'):
                        child.load_images()

    def _update_send_button(self):
        has_text = bool(self.textEdit.toPlainText().strip())
        self.pushButton_3.setEnabled(
            has_text and self.current_session is not None and not self.current_session.is_interaction
        )

    def send_current_message(self):
        text = self.textEdit.toPlainText().strip()
        if not text or self.current_session is None:
            return
        self.pushButton_3.setEnabled(False)
        self.textEdit.setEnabled(False)

        if self.current_session.is_private:
            manager = account_mgr.GlobalAccountContainer.get_current_manager()
            future = manager.send_private_message(self.current_session.target_id, text)
        elif self.current_session.is_chatroom and self._chatroom_worker is not None:
            future = self._chatroom_worker.send_message(text)
        else:
            self.textEdit.setEnabled(True)
            self._update_send_button()
            return

        def wait_result():
            try:
                result = future.result()
            except Exception as error:
                self._sendFinished.emit(None, error)
            else:
                self._sendFinished.emit(result, None)

        start_background_thread(wait_result)

    def _on_send_finished(self, result, error):
        self.textEdit.setEnabled(True)
        if error is not None:
            self._show_error(get_exception_string(error))
            self._update_send_button()
            return

        self.textEdit.clear()
        if self.current_session is not None and self.current_session.is_private:
            self._render_chat_messages(
                self._store.get_messages(self.current_session.target_id),
                show_sender=False,
            )

    def on_private_messages(self, messages):
        if self.current_session is None or not self.current_session.is_private:
            return
        if not any(
                message.session_key == self.current_session.key
                for message in messages
        ):
            return

        self._render_chat_messages(
            self._store.get_messages(self.current_session.target_id),
            show_sender=False,
        )
        account_mgr.GlobalAccountContainer.get_current_manager().mark_private_session_read(
            self.current_session.target_id
        )

    def show_more_menu(self):
        menu = base_ui.BaseQMenu(self)
        refresh_action = QAction('刷新会话', menu)
        refresh_action.triggered.connect(
            lambda: self.set_session(self.current_session, force=True)
        )
        menu.addAction(refresh_action)

        if self.current_session is not None and not self.independent:
            separate_action = QAction('在独立窗口打开', menu)
            separate_action.triggered.connect(self.open_independent_window)
            menu.addAction(separate_action)

        if self.current_session is not None and self.current_session.is_chatroom:
            unsubscribe = QAction('取消订阅此吧群', menu)
            unsubscribe.triggered.connect(self._confirm_unsubscribe)
            menu.addAction(unsubscribe)

        menu.exec(self.toolButton.mapToGlobal(self.toolButton.rect().bottomLeft()))

    def _confirm_unsubscribe(self):
        if self.current_session is None:
            return
        if MessageBox.warning(
                self,
                '确认要取消订阅吧群吗',
                '取消后该吧群会从左侧会话列表移除，聊天记录仍保留在贴吧云端。',
                MessageBox.Yes | MessageBox.No,
        ) == MessageBox.Yes:
            self.unsubscribeRequested.emit(self.current_session.target_id)
            self.detachRequested.emit(None)

    def open_independent_window(self):
        if self.current_session is None:
            return
        window = ChatSessionDetail(
            self.bduss,
            self.stoken,
            independent=True,
            account=self.account,
        )
        window.set_session(self.current_session)
        qt_window_mgr.add_window(window)
        self.detachRequested.emit(self.current_session)

    def _show_error(self, text):
        toast = top_toast_widget.ToastMessage(
            f'[聊天会话] {text}',
            icon_type=top_toast_widget.ToastIconType.ERROR,
        )
        self.toastRequested.emit(toast)

    def reset_theme(self):
        super().reset_theme()
        self.label_2.setStyleSheet(
            f'QLabel{{color:{profile_mgr.get_theme_font_color_string()};}}'
        )
        self.label_3.setStyleSheet('QLabel{color:grey;}')
        for row in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(row))
            if widget is not None and hasattr(widget, 'reset_theme'):
                widget.reset_theme()
    def init_ui_elements(self):
        self.loading_widget=loading_widget.LoadingFlashWidget(caption='消息正在赶来的路上...')
        self.loading_widget.cover_widget(self)
        self.loading_widget.hide()
