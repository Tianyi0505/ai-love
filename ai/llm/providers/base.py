from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ai.llm.types import ChatRequest, ChatStreamChunk


# 定义流式聊天提供器的通用调用骨架
class StreamingChatProvider(ABC):
    # 流式生成聊天内容，并记录首个有效输出片段的延迟
    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        started_at = time.perf_counter()
        first_chunk = True
        async for chunk in self._chat_stream(req):
            if first_chunk:
                chunk.latency_ms = int((time.perf_counter() - started_at) * 1000)
                first_chunk = False
            yield chunk

    # 按具体协议生成统一的聊天片段
    @abstractmethod
    async def _chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        ...
