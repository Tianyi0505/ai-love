from __future__ import annotations

import time

from shared.configuration.global_settings import MemorySettings, TimeoutSettings
from shared.contracts.memory import MemoryActivity
from shared.contracts.rpc.memory import (
    MemoryContextRequest,
    MemoryContextResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    PersonContextRequest,
    PersonContextResponse,
)
from shared.contracts.tools import ToolExecutionContext


# 封装记忆客户端调用
class MemoryClient:
    # 初始化当前实例
    def __init__(self, bus, ai_id: str, config: MemorySettings, timeouts: TimeoutSettings) -> None:
        self._bus = bus
        self._ai_id = ai_id
        self._config = config
        self._timeouts = timeouts

    # 检索匹配内容
    async def search(
        self,
        query: str,
        top_k: int | None = None,
        person_id: str = "",
    ) -> list[str]:
        limit = top_k if top_k is not None else self._config.search_top_k
        response = await self._bus.request_model(
            "memory.search.request",
            MemorySearchRequest(
                ai_id=self._ai_id,
                query=query,
                top_k=limit,
                person_id=person_id or None,
                session_id=None,
                active_session_actors=[],
            ),
            MemorySearchResponse,
            timeout=self._timeouts.memory_search_sec,
        )
        return [item.content for item in response.results]

    # 获取记忆上下文
    async def context(self, person_id: str = "", conversation_id: str = "") -> MemoryContextResponse:
        return await self._bus.request_model(
            "memory.context.request",
            MemoryContextRequest(
                ai_id=self._ai_id,
                person_id=person_id or None,
                conversation_id=conversation_id or None,
            ),
            MemoryContextResponse,
            timeout=self._timeouts.memory_context_sec,
        )

    # 获取经过场景隐私策略过滤的人物事实
    async def person_context(
        self,
        person_id: str,
        context: ToolExecutionContext,
    ) -> PersonContextResponse:
        return await self._bus.request_model(
            "memory.person-context.request",
            PersonContextRequest(context=context, person_id=person_id),
            PersonContextResponse,
            timeout=self._timeouts.memory_context_sec,
        )

    # 记录记忆活动
    async def activity(
        self,
        *,
        person_id: str,
        conversation_id: str,
        message_id: str,
    ) -> None:
        if not person_id or not conversation_id:
            return
        now = time.time()
        activity = MemoryActivity(
            ai_id=self._ai_id,
            person_id=person_id,
            conversation_id=conversation_id,
            message_id=message_id,
            sequence=time.time_ns(),
            active_at=now,
        )
        await self._bus.publish_durable_model("memory.activity", activity)
