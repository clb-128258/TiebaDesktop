"""
单个吧群会话的 BLCP 临时连接
"""
import asyncio
import concurrent.futures
import json
import threading

from publics import app_logger

from publics.baidu_features.chats.structs.chatroom_data_parser import (
    parse_message_content,
    CHATROOM_INVALID_MSG_TYPES
)
from publics.baidu_features.chats.tieba_message_apis import (
    ChatroomMsg,
    TiebaMessageClient
)
from publics.baidu_features.chats.network import tieba_message_protocol as protocol
from publics.baidu_features.chats.structs.models import ChatMessage


class ChatRoomSessionWorker:
    """按会话创建、关闭的条吧群连接"""

    def __init__(
            self,
            account,
            chatroom_id,
            fid,
            on_messages,
            on_error=None,
            on_detail=None,
    ):
        self.account = account
        self.chatroom_id = int(chatroom_id)
        self.fid = int(fid)
        self.on_messages = on_messages
        self.on_error = on_error
        self.on_detail = on_detail
        self._thread = None
        self._loop = None
        self._client = None
        self._main_task = None
        self._push_task = None
        self._message_cache = {}
        self._stop_event = threading.Event()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f'chatroom-{self.chatroom_id}',
            daemon=True,
        )
        self._thread.start()

    def request_stop(self):
        self._stop_event.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            except Exception:
                pass

    def stop(self, wait=True, timeout=3):
        self.request_stop()
        if not wait:
            return False
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                return False
        self._thread = None
        self._loop = None
        return True

    def send_message(self, text):
        future = concurrent.futures.Future()
        loop = self._loop
        if loop is None or not loop.is_running() or self._client is None:
            future.set_exception(RuntimeError('BLCP connection was not established'))
            return future

        async def send():
            await self._client.send_chatroom_msg(
                self.chatroom_id,
                self.fid,
                str(text),
            )
            await self._load_messages()

        asyncio.run_coroutine_threadsafe(send(), loop).add_done_callback(
            lambda done: _forward_future(done, future)
        )
        return future

    def load_older_messages(self, anchor_msg_id, count=30):
        future = concurrent.futures.Future()
        loop = self._loop
        if loop is None or not loop.is_running() or self._client is None:
            future.set_exception(RuntimeError('BLCP connection was not established'))
            return future

        async def load():
            cloud_messages = await self._client.get_chatroom_msgs(
                self.chatroom_id,
                count=-abs(int(count)),
                msgid_end=int(anchor_msg_id),
            )
            valid_messages = [
                message
                for message in cloud_messages.messages
                if int(message.msg_type or 0) not in CHATROOM_INVALID_MSG_TYPES
            ]
            if valid_messages:
                self._merge_messages(valid_messages)
            return {
                'count': len(valid_messages),
                'has_more': len(valid_messages) >= abs(int(count)),
            }

        asyncio.run_coroutine_threadsafe(load(), loop).add_done_callback(
            lambda done: _forward_future(done, future)
        )
        return future

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
                if self.on_error is not None:
                    self.on_error(error)
        finally:
            # 关闭会话
            if self._push_task is not None:
                self._push_task.cancel()
                try:
                    loop.run_until_complete(self._push_task)
                except:
                    pass
                self._push_task = None

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
        if self._stop_event.is_set():
            return

        self._client = TiebaMessageClient(self.account.aiotieba_account)

        try:
            detail = await self._client.get_chatroom_detail(self.chatroom_id)
        except Exception as error:
            app_logger.log_exception(error)
        else:
            if self.on_detail is not None:
                self.on_detail(detail)

        await self._client.start(private=False, chatroom=True)
        self._push_task = asyncio.create_task(
            self._consume_push_messages()
        )

        await self._client.join_chatroom(self.chatroom_id)
        await self._load_messages()

        while not self._stop_event.is_set():
            await asyncio.sleep(2)
            if self._stop_event.is_set():
                break
            if self._client.is_chatroom_connected:
                continue
            try:
                await self._client.join_chatroom(self.chatroom_id)
                await self._load_messages()
            except Exception as error:
                app_logger.log_exception(error)
                await asyncio.sleep(3)

    async def _load_messages(self):
        cloud_messages = await self._client.get_chatroom_msgs(self.chatroom_id)
        self._merge_messages(cloud_messages.messages)

    async def _consume_push_messages(self):
        queue = self._client.get_chat_message_queue()
        while not self._stop_event.is_set():
            try:
                notification = await queue.get()
                if notification.service_id != protocol.BLCP_SERVICE_MCAST:
                    continue

                payload = notification.payload
                if isinstance(payload, bytes):
                    payload = json.loads(payload.decode('utf-8'))
                if not isinstance(payload, dict):
                    continue

                mcast_id = int(payload.get('mcast_id', 0) or 0)
                if mcast_id and mcast_id != self.chatroom_id:
                    continue

                raw_messages = payload.get('messages', [])
                parsed_messages = []

                if not isinstance(raw_messages, list):
                    continue

                for raw_message in raw_messages:
                    try:
                        parsed_messages.append(
                            ChatroomMsg.from_json(raw_message)
                        )
                    except Exception as error:
                        app_logger.log_exception(error)

                if parsed_messages:
                    self._merge_messages(parsed_messages)
                else:
                    await self._load_messages()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                app_logger.log_exception(error)

    def _merge_messages(self, cloud_messages):
        for item in cloud_messages:
            if int(item.msg_type) in CHATROOM_INVALID_MSG_TYPES:
                continue

            message = item.to_normal_msg()
            key = (
                message.message_id
                if message.message_id
                else (
                    message.timestamp,
                    message.sender_id,
                    message.msg_type,
                    message.text,
                )
            )
            self._message_cache[key] = message

        messages = sorted(
            self._message_cache.values(),
            key=lambda message: (
                message.timestamp,
                message.message_id,
            ),
        )
        self.on_messages(messages)

def _forward_future(source_future, target_future):
    try:
        target_future.set_result(source_future.result())
    except Exception as error:
        target_future.set_exception(error)
