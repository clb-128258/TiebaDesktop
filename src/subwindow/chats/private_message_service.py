"""当前激活账号的私信长连接服务。"""
import asyncio
import concurrent.futures
import threading
import time

from publics import app_logger
from publics.baidu_features.tieba_message_apis import TiebaMessageClient

from .models import ChatMessage


class PrivateMessageService:
    """在独立事件循环线程中维护当前账号的私信 WebSocket。"""

    def __init__(self, account, store, on_messages):
        self.account = account
        self.store = store
        self.on_messages = on_messages
        self._thread = None
        self._loop = None
        self._client = None
        self._main_task = None
        self._stop_event = threading.Event()
        self._latest_incoming = {}
        self._peer_to_group = {}
        self._start_synced_groups = set()
        self._initial_sync_done = False

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f'private-message-{getattr(self.account, "uid", 0)}',
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
                future.result(timeout=3)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=6)
        self._thread = None
        self._loop = None

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def send_message(self, peer_user_id, content):
        future = concurrent.futures.Future()
        loop = self._loop
        if loop is None or not loop.is_running() or self._client is None:
            future.set_exception(RuntimeError('私信连接尚未建立'))
            return future

        async def send():
            result = await self._client.send_msg(int(peer_user_id), str(content))
            timestamp = int(time.time())
            message = ChatMessage(
                session_key=f'private:{int(peer_user_id)}',
                message_id=int(result.msg_id),
                sender_id=self._client.user_id,
                sender_name=self._client.user_name,
                sender_portrait=self._client.portrait,
                direction='out',
                msg_type=1,
                text=str(content),
                timestamp=timestamp,
                is_read=True,
                notify=False,
            )
            if self.store.save_message(
                peer_user_id,
                '',
                '',
                message,
                group_id=result.group_id,
            ):
                if result.group_id:
                    self._peer_to_group[int(peer_user_id)] = result.group_id
                    self.store.set_group_peer(
                        result.group_id,
                        peer_user_id,
                    )
                self.on_messages([message])
            return result

        asyncio.run_coroutine_threadsafe(send(), loop).add_done_callback(
            lambda done: _forward_future(done, future)
        )
        return future

    def mark_read(self, peer_user_id):
        self.store.mark_read(peer_user_id)
        loop = self._loop
        message = self._latest_incoming.get(int(peer_user_id))
        if (
            loop is None
            or not loop.is_running()
            or self._client is None
            or message is None
        ):
            return

        async def report_read():
            await self._client.set_msg_readed(
                message,
                group_id=self._peer_to_group.get(int(peer_user_id)),
            )

        try:
            asyncio.run_coroutine_threadsafe(report_read(), loop)
        except RuntimeError:
            pass

    def _thread_main(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            self._main_task = loop.create_task(self._run())
            loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if not self._stop_event.is_set():
                app_logger.log_exception(error)
        finally:
            if self._client is not None:
                loop.run_until_complete(self._client.close())
                self._client = None
            self._main_task = None
            loop.close()

    async def _shutdown(self):
        self._stop_event.set()
        if self._main_task is not None and not self._main_task.done():
            self._main_task.cancel()

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                if self._client is None:
                    self._client = TiebaMessageClient(self.account.aiotieba_account)
                    await self._client.start(private=True, chatroom=False)

                await self._pull_messages(notify=self._initial_sync_done)
                self._initial_sync_done = True
                await self._wait_for_update()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self._stop_event.is_set():
                    break
                app_logger.log_exception(error)
                if self._client is not None:
                    await self._client.close()
                    self._client = None
                await asyncio.sleep(5)

    async def _wait_for_update(self):
        queue = self._client.get_private_notification_queue()
        try:
            notices = await asyncio.wait_for(queue.get(), timeout=12)
        except asyncio.TimeoutError:
            return
        group_ids = list(dict.fromkeys(
            int(notice['group_id'])
            for notice in notices
            if int(notice.get('group_type', 0)) == 6
        ))
        if not group_ids:
            return
        groups = await self._client.get_group_msg(group_ids)
        self._save_groups(groups, notify=True)

    async def _pull_messages(self, notify):
        group_ids = self._client.private_group_ids
        if not group_ids:
            return
        if not notify:
            groups = await self._client.get_group_msg(
                group_ids,
                from_start=True,
            )
            self._start_synced_groups.update(group_ids)
            self._save_groups(groups, notify=False)
            return

        peer_unknown_groups = [
            group_id for group_id in group_ids
            if (
                self.store.get_group_peer(group_id) is None
                and group_id not in self._start_synced_groups
            )
        ]
        if peer_unknown_groups:
            groups = await self._client.get_group_msg(
                peer_unknown_groups,
                from_start=True,
            )
            self._start_synced_groups.update(peer_unknown_groups)
            self._save_groups(groups, notify=True)
        groups = await self._client.get_group_msg(group_ids)
        self._save_groups(groups, notify=True)

    def _save_groups(self, groups, notify):
        newly_received = []
        for group in groups:
            group_id = int(group.group_id)
            peer_info = self.store.get_group_peer(group_id) or {}
            peer_user_id = int(peer_info.get('peer_user_id', 0) or 0)
            peer_name = str(peer_info.get('user_name', '') or '')
            peer_portrait = str(peer_info.get('portrait', '') or '')

            for message in group.messages:
                sender_id = int(message.user.user_id)
                if sender_id and sender_id != self._client.user_id:
                    peer_user_id = sender_id
                    peer_name = message.user.user_name or peer_name
                    peer_portrait = message.user.portrait or peer_portrait

            if peer_user_id:
                self._peer_to_group[peer_user_id] = group_id
                self.store.set_group_peer(
                    group_id,
                    peer_user_id,
                    peer_name,
                    peer_portrait,
                )

            for message in group.messages:
                if message.msg_type == 22:
                    continue
                if not peer_user_id:
                    continue

                sender_id = int(message.user.user_id)
                direction = 'out' if sender_id == self._client.user_id else 'in'
                sender_name = (
                    self._client.user_name
                    if direction == 'out'
                    else message.user.user_name
                )
                sender_portrait = (
                    self._client.portrait
                    if direction == 'out'
                    else message.user.portrait
                )
                chat_message = ChatMessage(
                    session_key=f'private:{peer_user_id}',
                    message_id=int(message.msg_id),
                    sender_id=sender_id,
                    sender_name=sender_name,
                    sender_portrait=sender_portrait,
                    direction=direction,
                    msg_type=int(message.msg_type),
                    text=message.text,
                    timestamp=int(message.create_time or time.time()),
                    is_read=direction == 'out',
                    payload={'raw': message.text},
                    notify=notify,
                )
                inserted = self.store.save_message(
                    peer_user_id,
                    peer_name,
                    peer_portrait,
                    chat_message,
                    group_id=group_id,
                )
                if direction == 'in':
                    self._latest_incoming[peer_user_id] = message
                if inserted:
                    newly_received.append(chat_message)

        if newly_received:
            self.on_messages(newly_received)


def _forward_future(source_future, target_future):
    try:
        target_future.set_result(source_future.result())
    except Exception as error:
        target_future.set_exception(error)
