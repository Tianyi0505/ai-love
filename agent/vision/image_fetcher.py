from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
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

    async def data_url(self, image_url: str) -> str:
        image = await self.fetch(image_url)
        encoded = base64.b64encode(image.data).decode("ascii")
        return f"data:{image.media_type};base64,{encoded}"

    async def data_urls(self, image_urls: Sequence[str]) -> tuple[str, ...]:
        return tuple(await asyncio.gather(*(self.data_url(url) for url in image_urls)))
