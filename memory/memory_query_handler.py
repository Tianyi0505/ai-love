from __future__ import annotations

from memory.episode_memory_repository import EpisodeMemoryRepository
from memory.postgres_memory_repository import PostgresMemoryRepository
from shared.contracts.rpc.memory import (
    MemoryContextRequest,
    MemoryContextResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    PersonContextRequest,
    PersonContextResponse,
)
from shared.global_settings import GroundingSettings


class MemoryQueryHandler:
    def __init__(
        self,
        memories: PostgresMemoryRepository,
        episodes: EpisodeMemoryRepository,
        grounding: GroundingSettings,
    ) -> None:
        self._memories = memories
        self._episodes = episodes
        self._grounding = grounding

    async def search(self, request: MemorySearchRequest) -> MemorySearchResponse:
        results = await self._memories.search(
            request.ai_id,
            request.query,
            request.top_k,
            person_id=request.person_id,
            session_id=request.session_id,
            active_session_actors=request.active_session_actors,
        )
        return MemorySearchResponse.model_validate({"results": results})

    async def context(self, request: MemoryContextRequest) -> MemoryContextResponse:
        result = await self._episodes.context(
            request.ai_id,
            request.person_id,
            request.conversation_id,
        )
        return MemoryContextResponse.model_validate(result)

    async def person_context(self, request: PersonContextRequest) -> PersonContextResponse:
        result = await self._episodes.person_context(
            request.context,
            request.person_id,
            self._grounding.person_context_fact_limit,
        )
        if result is None:
            raise PermissionError("当前场景无权读取该人物背景")
        return PersonContextResponse.model_validate(result)
