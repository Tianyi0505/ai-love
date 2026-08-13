
from __future__ import annotations

import logging

logger = logging.getLogger("ailove.ai-agent.retrieval")


class Retrieval:

    def __init__(self, service) -> None:
        self._service = service

    async def hybrid(self, chat_key: str, query: str) -> list[str]:
        svc = self._service
        vector_texts = await svc.memory.vector_search(query)
        chat_type, _, chat_id = chat_key.partition(":")
        bm25_texts = svc.conversation.bm25_search(chat_type, chat_id, query)
        return vector_texts[:3] + bm25_texts[:3]

    async def search_sticker(self, query: str) -> dict | None:
        svc = self._service
        try:
            resp = await svc.bus.request_json(
                "sticker.search.request",
                {"ai_id": svc.ai_id, "query": query},
                timeout=2.0,
            )
        except Exception:
            return None
        return resp.get("sticker")
