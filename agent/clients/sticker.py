from __future__ import annotations

import hashlib


class StickerClient:
    def __init__(self, bus, ai_id: str, timeouts: dict) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._timeouts = timeouts

    async def search(self, query: str) -> dict | None:
        try:
            response = await self._bus.request_json(
                "sticker.search.request",
                {"ai_id": self._ai_id, "query": query},
                timeout=float(self._timeouts["memory_search_sec"]),
            )
        except Exception:
            return None
        return response.get("sticker")

    async def add(
        self,
        image_url: str,
        description: str,
        tags: list[str],
        match_quality: float,
    ) -> bool:
        sticker_id = f"stk_{hashlib.md5(image_url.encode()).hexdigest()[:12]}"
        response = await self._bus.request_json(
            "sticker.add.request",
            {
                "ai_id": self._ai_id,
                "id": sticker_id,
                "image_url": image_url,
                "description": description,
                "tags": tags,
                "match_quality": match_quality,
            },
            timeout=float(self._timeouts["sticker_add_sec"]),
        )
        return bool(response.get("ok"))
