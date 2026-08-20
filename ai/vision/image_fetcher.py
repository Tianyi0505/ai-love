from __future__ import annotations

import httpx
from pydantic_ai import BinaryContent


class ImageFetcher:
    def __init__(self, client: httpx.AsyncClient, media_type: str) -> None:
        self._client = client
        self._media_type = media_type

    async def fetch(self, image_url: str) -> BinaryContent:
        response = await self._client.get(image_url)
        response.raise_for_status()
        return BinaryContent(data=response.content, media_type=self._media_type)
