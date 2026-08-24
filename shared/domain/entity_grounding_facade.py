from __future__ import annotations

from shared.configuration.global_settings import GroundingSettings
from shared.contracts.entity import EntityContext
from shared.contracts.rpc.grounding import HistoryMessage, ResolvePeopleResponse
from shared.contracts.tools import ToolExecutionContext
from shared.domain.entity_grounder import EntityGrounder
from shared.domain.person_resolver import PersonResolver
from shared.infrastructure.database import Database
from shared.persistence.repositories.conversation_context_repository import ConversationContextRepository
from shared.persistence.repositories.group_member_repository import GroupMemberRepository
from shared.utils.lfu import LazyLFU


class EntityGroundingFacade:
    def __init__(
        self,
        db: Database,
        settings: GroundingSettings,
        evidence_lfu: LazyLFU,
    ) -> None:
        self._resolver = PersonResolver(db, settings, evidence_lfu)
        self._group_members = GroupMemberRepository(db, settings)
        self._conversations = ConversationContextRepository(db)
        self._grounder = EntityGrounder(
            self._resolver,
            self._group_members,
            self._conversations,
            settings,
        )

    async def context_matches(self, context: ToolExecutionContext) -> bool:
        return await self._conversations.matches(context)

    async def sync_group_members(
        self,
        platform: str,
        account_id: str,
        chat_id: str,
        members: list[dict],
    ) -> None:
        await self._group_members.replace_snapshot(platform, account_id, chat_id, members)

    async def record_mention_evidence(self, **evidence) -> None:
        await self._resolver.record_evidence(**evidence)

    async def resolve_people(
        self,
        context: ToolExecutionContext,
        mention: str,
        limit: int,
    ) -> ResolvePeopleResponse:
        return await self._resolver.resolve(context, mention, limit)

    async def fast_ground(
        self,
        context: ToolExecutionContext,
        message,
        recent_participants_limit: int,
        recent_lookback_sec: float,
    ) -> EntityContext:
        return await self._grounder.ground(
            context,
            message,
            recent_participants_limit,
            recent_lookback_sec,
        )

    async def search_group_history(
        self,
        context: ToolExecutionContext,
        query: str,
        limit: int,
        lookback_sec: float,
    ) -> list[HistoryMessage]:
        return await self._conversations.search_group_history(context, query, limit, lookback_sec)
