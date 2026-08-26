from __future__ import annotations

from shared.contracts.rpc.sticker import (
    StickerAddRequest,
    StickerAddResponse,
    StickerSearchRequest,
    StickerSearchResponse,
)
from shared.global_settings import TimeoutSettings
from shared.snowflake_id_generator import snowflake_ids


# 封装表情客户端调用
class StickerClient:
    # 初始化当前实例
    def __init__(self, bus, ai_id: str, timeouts: TimeoutSettings) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._timeouts = timeouts

    # 检索匹配内容
    async def search(self, query: str) -> dict | None:
        response = await self._bus.request_model(
            "sticker.search.request",
            StickerSearchRequest(ai_id=self._ai_id, query=query),
            StickerSearchResponse,
            timeout=self._timeouts.memory_search_sec,
        )
        return response.sticker.model_dump(mode="json") if response.sticker else None

    # 添加数据
    async def add(
        self,
        image_url: str,
        description: str,
        tags: list[str],
        match_quality: float,
    ) -> bool:
        sticker_id = str(snowflake_ids().next_id())
        response = await self._bus.request_model(
            "sticker.add.request",
            StickerAddRequest(
                ai_id=self._ai_id,
                id=sticker_id,
                image_url=image_url,
                description=description,
                tags=tags,
                match_quality=match_quality,
            ),
            StickerAddResponse,
            timeout=self._timeouts.sticker_add_sec,
        )
        return response.ok
