from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ImageDesc:
    description: str
    tags: list[str]
    match_quality: float = 0.5
    emotion: str = ""
    sticker_description: str = ""


class ImageDescriber(ABC):
    async def describe(self, image_url: str) -> ImageDesc:
        fetched = await self._fetch(image_url)
        desc = await self._do_describe(fetched)
        return await self._finalize(desc)

    @abstractmethod
    async def _do_describe(self, image_url: str) -> ImageDesc:
        pass

    async def _fetch(self, image_url: str) -> str:
        return image_url

    async def _finalize(self, desc: ImageDesc) -> ImageDesc:
        desc.match_quality = max(0.0, min(1.0, float(desc.match_quality)))
        desc.description = str(desc.description or "").strip()
        desc.sticker_description = str(desc.sticker_description or "").strip()
        desc.tags = [str(tag).strip() for tag in desc.tags if str(tag).strip()]
        return desc
