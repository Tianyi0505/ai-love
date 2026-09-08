import json
from unittest.mock import AsyncMock, patch

import pytest

from gateway.qq_channel import QQChannel
from shared.contracts.social import ChatType


@pytest.mark.parametrize(
    ("segments", "expected_text"),
    [
        ([{"type": "face", "data": {"id": "14"}}], "[QQ表情：ID:14]"),
        (
            [
                {"type": "text", "data": {"text": "你好"}},
                {"type": "face", "data": {"id": "14", "text": "微笑"}},
                {"type": "text", "data": {"text": "呀"}},
                {"type": "face", "data": {"id": "66"}},
            ],
            "你好[QQ表情：微笑]呀[QQ表情：ID:66]",
        ),
        (
            [{"type": "image", "data": {"url": "https://example.com/sticker.gif", "summary": "[动画表情]"}}],
            "",
        ),
    ],
)
async def test_private_emoticons_reach_message_handler(segments, expected_text):
    """从 NapCat 接收入口验证表情作为聊天消息正常分发"""
    channel = QQChannel(
        {
            "ws_url": "ws://127.0.0.1",
            "http_url": "http://127.0.0.1",
            "uin": "10000",
            "account_id": "qq-main",
            "message_timeout_sec": 1,
            "forward_timeout_sec": 1,
            "content_strategies": ["quote", "forward", "voice", "image", "file", "at", "text"],
        },
        http_client=object(),
    )
    handler = AsyncMock()
    channel.set_message_handler(handler)

    async def messages():
        yield json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 20000,
                "message_id": 999,
                "time": 1,
                "sender": {"nickname": "联系人"},
                "message": segments,
            }
        )

    async def connections():
        yield messages()

    with patch("gateway.qq_channel.websockets.connect", return_value=connections()):
        await channel.start()

    handler.assert_awaited_once()
    message = handler.await_args.args[0]
    assert message.chat.chat_type == ChatType.PRIVATE
    assert message.text == expected_text
    if segments[0]["type"] == "image":
        assert message.all_media_urls() == ["https://example.com/sticker.gif"]
    else:
        assert message.text
