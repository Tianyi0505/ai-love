
from __future__ import annotations

import asyncio

from services.gateway.channels.base import Channel, ChannelCapabilities, channel_registry


@channel_registry.register("bilibili")
class BilibiliChannel(Channel):
    name = "bilibili"

    async def start(self) -> None:
        # 将直播间 WebSocket 事件转换为统一互动事件
        await asyncio.Event().wait()

    async def stop(self) -> None:
        pass

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            channel=self.name,
            send_types=["text"],
            receive_types=["text", "gift", "guard", "super_chat"],
            supports_history=False,
            is_live_platform=True,
            supports_multi_ai=True,
        )
