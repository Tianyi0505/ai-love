from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from ai.llm.types import ChatRequest, ChatStreamChunk


# 定义大模型调用接口
class LLMProvider(ABC):
    # 流式生成聊天内容
    @abstractmethod
    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        ...

    # 关闭资源
    async def close(self) -> None:
        ...
