
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from services.ai_agent.llm.errors import LLMErrorMessage
from services.ai_agent.llm.model import ModelHealthStore, ModelSelector, ModelTarget
from services.ai_agent.llm.tier import Tier
from services.ai_agent.llm.types import ChatRequest, ChatStreamChunk, LLMProvider

logger = logging.getLogger("ailove.llm.routing")

class RoutingLLMService:

    def __init__(self, selector: ModelSelector, health_store: ModelHealthStore, provider_factory) -> None:
        self._selector = selector
        self._health = health_store
        self._provider_factory = provider_factory
        self._streams: dict[str, AsyncIterator[ChatStreamChunk]] = {}

    async def chat(self, req: ChatRequest, tier: Tier | None = None, preferred: str = "") -> AsyncIterator[ChatStreamChunk]:
        thinking = getattr(req, "thinking", False)
        targets = self._selector.select_chat_candidates(thinking, tier, preferred)
        if not targets:
            raise RuntimeError(LLMErrorMessage.NO_PROVIDER.value)

        last_error: Exception | None = None
        for target in targets:
            if not self._health.allow_call(target.candidate.id):
                continue
            provider = self._provider_factory(target.candidate.provider, target.candidate.id)
            if provider is None:
                continue

            first_chunk, stream = await self._try_first_packet(provider, req, target)
            if first_chunk is not None:
                self._health.mark_success(target.candidate.id)
                yield first_chunk
                async for chunk in stream:
                    yield chunk
                return

            self._health.mark_failure(target.candidate.id)
            logger.warning("[routing] 模型失败切换: %s", target.candidate.id)
            last_error = last_error or RuntimeError(LLMErrorMessage.START_FAILED.value)

        raise RuntimeError(LLMErrorMessage.ALL_FAILED.value) from last_error

    async def _try_first_packet(self, provider: LLMProvider, req: ChatRequest, target: ModelTarget) -> tuple[ChatStreamChunk | None, AsyncIterator]:
        try:
            stream = provider.chat_stream(req)
            async with asyncio.timeout(target.timeout_ms / 1000):
                first = await anext(stream, None)
            if first is None:
                return None, stream
            return first, stream
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("[routing] %s 启动失败: %s", target.candidate.id, str(e)[:80])
            return None, None
