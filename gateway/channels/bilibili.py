
from __future__ import annotations

import asyncio

from gateway.channels.base import Channel, ChannelCapabilities, channel_registry


# 接入哔哩哔哩消息渠道
@channel_registry.register("bilibili")
class BilibiliChannel(Channel):
    name = "bilibili"

    # 启动服务
    async def start(self) -> None:
        # 将直播间 WebSocket 事件转换为统一互动事件
        await asyncio.Event().wait()

    # 停止服务
    async def stop(self) -> None:
        pass

    # 返回渠道能力
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
