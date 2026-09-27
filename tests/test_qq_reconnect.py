import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from gateway.qq_channel import QQChannel


@pytest.mark.parametrize("abrupt", [True, False])
async def test_socket_disconnect_reconnects_without_cancelling_inflight_message(abrupt):
    """真实 WebSocket 断开后，接收入口继续处理旧消息及重连后的私聊。"""
    first_started = asyncio.Event()
    reconnected = asyncio.Event()
    release_first = asyncio.Event()
    received = asyncio.Queue()
    connections = 0

    async def napcat(ws):
        nonlocal connections
        connections += 1
        current = connections
        if current > 1:
            reconnected.set()
        await ws.send(json.dumps({
            "post_type": "message", "message_type": "private",
            "user_id": 20000, "message_id": current, "time": 1,
            "sender": {"nickname": "测试联系人"},
            "message": [{"type": "text", "data": {"text": "good"}}],
        }))
        if current == 1:
            await first_started.wait()
            if abrupt:
                ws.transport.abort()
            else:
                await ws.close(code=1001, reason="服务重启")
        await ws.wait_closed()

    async def handle(message):
        if message.message_id == "1":
            first_started.set()
            await release_first.wait()
        await received.put((message.message_id, message.text))

    async with serve(napcat, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        channel = QQChannel({
            "ws_url": f"ws://127.0.0.1:{port}", "http_url": "http://127.0.0.1",
            "uin": "10000", "account_id": "qq-main", "message_timeout_sec": 15,
            "forward_timeout_sec": 1, "content_strategies": ["text"],
        }, http_client=object())
        channel.set_message_handler(handle)
        receiver = asyncio.create_task(channel.start())
        try:
            await asyncio.wait_for(reconnected.wait(), timeout=5)
            release_first.set()
            assert await asyncio.wait_for(received.get(), timeout=2) == ("1", "good")
            assert await asyncio.wait_for(received.get(), timeout=2) == ("2", "good")
            assert not receiver.done()
            assert connections == 2
        finally:
            release_first.set()
            receiver.cancel()
            result = (await asyncio.gather(receiver, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)
        assert channel._ws is None
