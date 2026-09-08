from __future__ import annotations

import asyncio
import logging

from agent.social.sticker_client import StickerClient
from agent.vision.image_describer import ImageDescriber

logger = logging.getLogger("ailove.ai-agent.sticker-collector")


class StickerCollector:
    def __init__(
        self,
        ai_id: str,
        vision: ImageDescriber,
        stickers: StickerClient,
        minimum_quality: float,
    ) -> None:
        self._ai_id = ai_id
        self._vision = vision
        self._stickers = stickers
        self._minimum_quality = minimum_quality

    async def collect(self, image_urls: list[str]) -> None:
        await asyncio.gather(*(self._collect(image_url) for image_url in image_urls))

    async def _collect(self, image_url: str) -> None:
        description = await self._vision.describe(image_url)
        if (
            description.image_type != "sticker"
            or description.match_quality < self._minimum_quality
            or not description.sticker_description
        ):
            return
        added = await self._stickers.add(
            image_url,
            description.sticker_description,
            description.tags,
            description.match_quality,
        )
        if added:
            logger.info("[ai-agent:%s] 收藏表情: %s", self._ai_id, description.description)
