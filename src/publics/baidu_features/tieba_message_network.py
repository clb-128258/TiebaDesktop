"""私信 WebSocket 与吧群 BLCP 的连接管理。"""
import asyncio
import contextlib
import gzip
import socket
import ssl
import time

import aiohttp

from . import tieba_message_protocol as protocol


class MessageConnectionError(RuntimeError):
    """消息长连接不可用。"""


def _resolve_proxy(proxy):
    if proxy is True:
        proxy_info = aiohttp.helpers.proxies_from_env().get('http')
        if proxy_info is None:
            return None, None
        return str(proxy_info.proxy), proxy_info.proxy_auth
    if isinstance(proxy, str) and proxy:
        return proxy, None
    return None, None


class PrivateMessageConnection:
    """贴吧私信 WebSocket 连接。"""

    def __init__(self, ws_sec_key, proxy=True, read_timeout=8):
        self._ws_sec_key = ws_sec_key
        self._proxy = proxy
        self._read_timeout = read_timeout
        self._session = None
        self._websocket = None
        self._dispatcher = None
        self._pending = {}
        self._req_id = int(time.time())
        self.message_queue = asyncio.Queue()

    @property
    def is_open(self):
        return (
            self._websocket is not None
            and not self._websocket.closed
            and self._dispatcher is not None
            and not self._dispatcher.done()
        )

    async def connect(self):
        if self.is_open:
            return
        await self.close()

        proxy_url, proxy_auth = _resolve_proxy(self._proxy)
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=self._proxy is True,
        )

        proxy_headers = None
        if proxy_auth is not None:
            proxy_headers = {
                'Proxy-Authorization': aiohttp.encode_basic_auth(
                    proxy_auth.login,
                    proxy_auth.password,
                ),
            }

        try:
            self._websocket = await self._session.ws_connect(
                'ws://im.tieba.baidu.com:8000',
                headers={
                    aiohttp.hdrs.SEC_WEBSOCKET_EXTENSIONS: 'im_version=2.3',
                    aiohttp.hdrs.ACCEPT_ENCODING: 'gzip',
                    aiohttp.hdrs.USER_AGENT: 'aiotieba/4.8.4',
                },
                timeout=10,
                autoclose=True,
                autoping=True,
                heartbeat=180,
                ssl=False,
                compress=0,
                proxy=proxy_url,
                proxy_headers=proxy_headers,
            )
        except BaseException:
            await self.close()
            raise

        self._dispatcher = asyncio.create_task(self._dispatch())

    async def close(self):
        websocket, self._websocket = self._websocket, None
        dispatcher, self._dispatcher = self._dispatcher, None
        session, self._session = self._session, None

        error = MessageConnectionError('private message websocket closed')
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

        if websocket is not None:
            with contextlib.suppress(Exception):
                await websocket.close()
        if dispatcher is not None and not dispatcher.done():
            dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await dispatcher
        if session is not None:
            await session.close()

    async def _dispatch(self):
        error = MessageConnectionError('private message websocket disconnected')
        try:
            async for message in self._websocket:
                if message.type != aiohttp.WSMsgType.BINARY:
                    continue

                body, cmd, req_id = protocol.parse_ws_bytes(
                    self._ws_sec_key,
                    message.data,
                )
                future = self._pending.get(req_id)
                if future is not None and not future.done():
                    future.set_result(body)
                    continue

                if cmd == protocol.CMD_GET_GROUP_MSG:
                    try:
                        groups = protocol.parse_get_group_msg_res(body)
                    except Exception:
                        continue
                    await self.message_queue.put(groups)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def send(self, body, cmd, encrypt=True):
        websocket = self._websocket
        if websocket is None or websocket.closed:
            raise MessageConnectionError('private message websocket not connected')

        self._req_id += 1
        req_id = self._req_id
        future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        packet = protocol.pack_ws_bytes(
            self._ws_sec_key,
            body,
            cmd,
            req_id,
            encrypt=encrypt,
        )
        try:
            await asyncio.wait_for(websocket.send_bytes(packet), timeout=3)
            return await asyncio.wait_for(future, timeout=self._read_timeout)
        finally:
            self._pending.pop(req_id, None)


class BlcpNotification:
    """BLCP 服务端推送。"""

    def __init__(self, service_id, method_id, payload):
        self.service_id = service_id
        self.method_id = method_id
        self.payload = payload

    def __repr__(self):
        return f'BlcpNotification({self.service_id}/{self.method_id})'


class BlcpResponse:
    """BLCP 请求响应。"""

    def __init__(self, service_id, method_id, correlation_id, error_code, error_text, payload):
        self.service_id = service_id
        self.method_id = method_id
        self.correlation_id = correlation_id
        self.error_code = error_code
        self.error_text = error_text
        self.payload = payload

    @property
    def ok(self):
        return self.error_code == 0


class BlcpConnection:
    """贴吧群聊使用的 BLCP TCP/TLS 长连接。"""

    def __init__(self, read_timeout=10, heartbeat_interval=60, message_queue=None):
        self._read_timeout = read_timeout
        self._heartbeat_interval = heartbeat_interval
        self._reader = None
        self._writer = None
        self._dispatcher = None
        self._heartbeater = None
        self._pending = {}
        self.message_queue = message_queue or asyncio.Queue(maxsize=100)

    @property
    def is_open(self):
        return (
            self._reader is not None
            and self._writer is not None
            and not self._writer.is_closing()
            and self._dispatcher is not None
            and not self._dispatcher.done()
        )

    async def connect(self):
        if self.is_open:
            return
        await self.close()

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(
                'common.lcs.baidu.com',
                443,
                ssl=ssl_context,
                family=socket.AF_INET,
            ),
            timeout=10,
        )
        self._dispatcher = asyncio.create_task(self._dispatch())

    async def close(self):
        self._reader = None
        writer, self._writer = self._writer, None
        dispatcher, self._dispatcher = self._dispatcher, None
        heartbeater, self._heartbeater = self._heartbeater, None

        for task in (heartbeater, dispatcher):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

        error = MessageConnectionError('BLCP connection closed')
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

        if writer is not None:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    async def _read_frame(self):
        await self._reader.readuntil(protocol.BLCP_FRAME_PREFIX)
        lengths = await self._reader.readexactly(8)
        total_len = int.from_bytes(lengths[:4], 'big')
        header_len = int.from_bytes(lengths[4:], 'big')
        header = await self._reader.readexactly(header_len)
        body = await self._reader.readexactly(total_len - header_len)
        return header, body

    async def _dispatch(self):
        error = MessageConnectionError('BLCP connection disconnected')
        try:
            while True:
                header_data, body = await self._read_frame()
                meta = protocol._extract_rpc_meta(header_data)
                if meta['compress_type'] == 1 and body:
                    body = gzip.decompress(body)

                if meta['meta_type'] == 2:
                    if (
                        meta['service_id'] == protocol.BLCP_SERVICE_LCM
                        and meta['method_id'] == protocol.BLCP_METHOD_HEARTBEAT
                    ):
                        payload = protocol.parse_lcm_response(body)
                        if payload['next_interval_ms'] > 0:
                            self.start_heartbeat(payload['next_interval_ms'])

                    future = self._pending.get(meta['correlation_id'])
                    if future is not None and not future.done():
                        future.set_result((meta, body))
                elif meta['meta_type'] == 3:
                    if meta['service_id'] == protocol.BLCP_SERVICE_LCM:
                        payload = protocol.parse_lcm_response(body)
                    else:
                        try:
                            payload = protocol.parse_json_body(body)
                        except Exception:
                            payload = body
                    notification = BlcpNotification(
                        meta['service_id'],
                        meta['method_id'],
                        payload,
                    )
                    if self.message_queue.full():
                        self.message_queue.get_nowait()
                    self.message_queue.put_nowait(notification)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def _heartbeat_loop(self):
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                await self.heartbeat()
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    def start_heartbeat(self, interval_ms=0):
        if self._heartbeater is not None:
            self._heartbeater.cancel()
            self._heartbeater = None

        interval = interval_ms / 1000 if interval_ms > 0 else self._heartbeat_interval
        if not interval or interval <= 0:
            return
        self._heartbeat_interval = interval
        self._heartbeater = asyncio.create_task(self._heartbeat_loop())

    async def heartbeat(self):
        correlation_id = protocol.new_correlation_id()
        body = protocol.pack_lcm_heartbeat_req(correlation_id)
        header, _, _ = protocol.pack_rpc_request(
            protocol.BLCP_SERVICE_LCM,
            protocol.BLCP_METHOD_HEARTBEAT,
            body,
            correlation_id,
        )
        self._writer.write(protocol.encode_blcp_frame(header, body))
        await self._writer.drain()

    async def request(self, service_id, method_id, payload, correlation_id=None):
        if not self.is_open:
            raise MessageConnectionError('BLCP connection not established')

        if isinstance(payload, (dict, list)):
            body = protocol.encode_json_body(payload)
        else:
            body = payload or b''

        header, body, correlation_id = protocol.pack_rpc_request(
            service_id,
            method_id,
            body,
            correlation_id,
        )
        future = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future

        try:
            self._writer.write(protocol.encode_blcp_frame(header, body))
            await self._writer.drain()
            meta, response_body = await asyncio.wait_for(
                future,
                timeout=self._read_timeout,
            )

            if service_id == protocol.BLCP_SERVICE_LCM:
                response_payload = protocol.parse_lcm_response(response_body)
            else:
                response_payload = protocol.parse_json_body(response_body)

            return BlcpResponse(
                meta['service_id'],
                meta['method_id'],
                meta['correlation_id'],
                meta['error_code'],
                meta['error_text'],
                response_payload,
            )
        finally:
            self._pending.pop(correlation_id, None)
