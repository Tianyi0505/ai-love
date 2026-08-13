from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ChatMessage:
    role: str
    content: str
    name: str = ""


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class ChatRequest:
    ai_id: str
    messages: list[ChatMessage]
    tools: list[ToolSchema] = field(default_factory=list)
    options: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ChatStreamChunk:
    content: str = ""
    finish_reason: str = ""
    tool_call: ToolCall | None = None
    latency_ms: int = 0


class LLMProvider(ABC):
    @abstractmethod
    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        ...

    async def close(self) -> None:
        ...


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
