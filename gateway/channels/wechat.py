
from __future__ import annotations

from gateway.channels.base import Channel, ChannelCapabilities, channel_registry


@channel_registry.register("wechat")
class WeChatChannel(Channel):
    name = "wechat"

    async def start(self) -> None:
        # 接入微信消息通道
        pass

    async def stop(self) -> None:
        pass

    async def send(self, req) -> dict:
        return {"ok": False, "message_id": "", "fallback_note": "微信渠道未实现"}

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            channel="wechat",
            send_types=["text", "image", "sticker"],
            receive_types=["text", "image", "voice", "sticker", "forward", "quote", "file", "at"],
            supports_history=False,
        )
