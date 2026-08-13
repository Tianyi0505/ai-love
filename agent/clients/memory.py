from __future__ import annotations


class MemoryClient:
    def __init__(self, bus, ai_id: str, config: dict, timeouts: dict) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._config = config
        self._timeouts = timeouts

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        person_id: str = "",
    ) -> list[str]:
        limit = int(top_k if top_k is not None else self._config["search_top_k"])
        try:
            response = await self._bus.request_json(
                "memory.search.request",
                {
                    "ai_id": self._ai_id,
                    "query": query,
                    "top_k": limit,
                    "person_id": person_id,
                },
                timeout=float(self._timeouts["memory_search_sec"]),
            )
            return [
                item.get("content", "")
                for item in response.get("results", [])
                if item.get("content")
            ]
        except Exception:
            return []

    async def write(self, entries: list[dict]) -> None:
        await self._bus.request_json(
            "memory.write.request",
            {"ai_id": self._ai_id, "entries": entries},
            timeout=float(self._timeouts["memory_write_sec"]),
        )
