"""
单个吧群会话的 BLCP 临时连接
"""
import asyncio
import concurrent.futures
import json
import threading
import time

from publics import app_logger
from publics.baidu_features.chats.tieba_message_apis import (
    ChatroomMsg,
    TiebaMessageClient,
)

from . import tieba_message_protocol as protocol
from .models import ChatMessage


def _parse_content(content):
    if not isinstance(content, dict):
        return {}, {}
    text_data = content.get('text', {})
    if isinstance(text_data, str):
        try:
            text_data = json.loads(text_data)
        except ValueError:
            text_data = {}
    if not isinstance(text_data, dict):
        return {}, {}
    ext = text_data.get('ext', {})
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except ValueError:
            ext = {}
    return text_data, ext if isinstance(ext, dict) else {}


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
            future.set_exception(RuntimeError('吧群连接尚未建立'))
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
            future.set_exception(RuntimeError('群聊连接尚未建立'))
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
                if int(message.content_type or 0) != 101
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
            if self._push_task is not None:
                self._push_task.cancel()
                try:
                    loop.run_until_complete(self._push_task)
                except (asyncio.CancelledError, Exception):
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
        await self._client.start(private=False, chatroom=True)
        self._push_task = asyncio.create_task(
            self._consume_push_messages()
        )

        try:
            detail = await self._client.get_chatroom_detail(self.chatroom_id)
        except Exception as error:
            app_logger.log_exception(error)
        else:
            if self.on_detail is not None:
                self.on_detail(detail)
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

                raw_messages = payload.get('messages') or []
                if not isinstance(raw_messages, list):
                    continue
                parsed_messages = []
                for raw_message in raw_messages:
                    if not isinstance(raw_message, dict):
                        continue
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
            if int(item.content_type or 0) == 101:
                continue
            message = self._to_chat_message(item)
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

    def _to_chat_message(self, item):
        text_data, ext = _parse_content(item.content)
        sender_portrait = str(
            text_data.get('portrait')
            or ext.get('portrait')
            or ''
        ).split('?', 1)[0]
        sender_name = str(
            text_data.get('name')
            or ext.get('user_name')
            or item.user_id
        )
        return ChatMessage(
            session_key=f'chatroom:{self.chatroom_id}',
            message_id=int(item.msg_id),
            sender_id=int(item.user_id),
            sender_name=sender_name,
            sender_portrait=sender_portrait,
            msg_type=int(item.msg_type),
            text=item.text,
            image_urls=[item.image_url] if item.image_url else [],
            image_thumbnail_urls=(
                [item.image_thumbnail_url]
                if item.image_thumbnail_url
                else []
            ),
            image_width=int(item.image_width or 0),
            image_height=int(item.image_height or 0),
            timestamp=int(item.create_time or time.time()),
            payload=item.content,
            is_read=True,
            is_system=bool(item.is_sys_msg),
            reply_content=(
                item.reply_content.to_dict()
                if item.reply_content is not None
                else {}
            ),
            at_users=[
                user.to_dict()
                for user in item.at_users
            ],
        )


def _forward_future(source_future, target_future):
    try:
        target_future.set_result(source_future.result())
    except Exception as error:
        target_future.set_exception(error)
