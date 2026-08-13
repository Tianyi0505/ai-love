from __future__ import annotations

from typing import AsyncIterator

from ai.llm.types import ChatRequest, ChatStreamChunk


# 提供大模型服务能力
class LLMService:
    # 初始化当前实例
    def __init__(self, routing) -> None:
        self._routing = routing

    # 执行大模型聊天
    async def chat(
        self,
        req: ChatRequest,
        tier=None,
        preferred: str = "",
    ) -> AsyncIterator[ChatStreamChunk]:
        async for chunk in self._routing.chat(req, tier, preferred):
            yield chunk
