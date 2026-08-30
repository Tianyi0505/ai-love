from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class FetchedImage:
    data: bytes
    media_type: str


class ImageFetcher:
    def __init__(self, client: httpx.AsyncClient, media_type: str) -> None:
        self._client = client
        self._media_type = media_type

    async def fetch(self, image_url: str) -> FetchedImage:
        response = await self._client.get(image_url)
        response.raise_for_status()
        return FetchedImage(data=response.content, media_type=self._media_type)
