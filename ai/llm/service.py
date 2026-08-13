from __future__ import annotations

from typing import AsyncIterator

from ai.llm.types import ChatRequest, ChatStreamChunk


class LLMService:
    def __init__(self, routing) -> None:
        self._routing = routing

    async def chat(
        self,
        req: ChatRequest,
        tier=None,
        preferred: str = "",
    ) -> AsyncIterator[ChatStreamChunk]:
        async for chunk in self._routing.chat(req, tier, preferred):
            yield chunk
