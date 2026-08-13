from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ai.llm.types import ChatRequest, ChatStreamChunk


class LLMProvider(ABC):
    @abstractmethod
    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        ...

    async def close(self) -> None:
        ...
