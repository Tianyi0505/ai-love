from __future__ import annotations

from shared.configuration.global_settings import GlobalSettings
from shared.contracts.relationship import RelationshipCeilings, RelationshipPolicy
from shared.contracts.rpc.relationship import (
    GroupRelationshipRequest,
    GroupRelationshipResponse,
    RelationshipChatRequest,
    RelationshipListRequest,
    RelationshipListResponse,
    RelationshipSummaryRequest,
    RelationshipSummaryResponse,
)
from shared.infrastructure.nacos_agent_definition_store import NacosAgentDefinitionStore
from shared.persistence.repositories.relationship_repository import RelationshipRepository


class RelationshipHandler:
    def __init__(
        self,
        repository: RelationshipRepository,
        definitions: NacosAgentDefinitionStore,
        settings: GlobalSettings,
    ) -> None:
        self._repository = repository
        self._definitions = definitions
        self._settings = settings

    async def chat(self, request: RelationshipChatRequest) -> RelationshipSummaryResponse:
        policy = await self._policy(request.ai_id)
        current = await self._repository.get_person(request.ai_id, request.person_id)
        updated = policy.on_conversation(request.platform_user_id, current, request.quality)
        ceiling_policy = "whitelist" if self._is_priority_user(request.platform_user_id) else "default"
        await self._repository.save_person(request.ai_id, request.person_id, updated, ceiling_policy)
        if request.chat_type == "group":
            group = await self._repository.get_group(request.ai_id, request.account_id, request.group_id)
            group = policy.on_group_conversation(request.group_id, group, request.quality)
            await self._repository.save_group(request.ai_id, request.account_id, request.group_id, group)
        return RelationshipSummaryResponse(summary=policy.summarize_person(updated))

    async def summary(self, request: RelationshipSummaryRequest) -> RelationshipSummaryResponse:
        relationship = await self._repository.get_person(request.ai_id, request.person_id)
        summary = (await self._policy(request.ai_id)).summarize_person(relationship)
        return RelationshipSummaryResponse(summary=summary)

    async def list_people(self, request: RelationshipListRequest) -> RelationshipListResponse:
        relationships = await self._repository.list_people(request.ai_id)
        priority_user_ids = {str(item) for item in self._settings.qq.whitelist}
        for relationship in relationships:
            relationship["priority_contact"] = relationship["user_id"] in priority_user_ids
        return RelationshipListResponse.model_validate({"relationships": relationships})

    async def group(self, request: GroupRelationshipRequest) -> GroupRelationshipResponse:
        relationship = await self._repository.get_group(
            request.ai_id,
            request.account_id,
            request.group_id,
        )
        return GroupRelationshipResponse.model_validate({"relationship": relationship.__dict__})

    async def _policy(self, ai_id: str) -> RelationshipPolicy:
        raw = (await self._definitions.load(ai_id)).relationship_policy
        person_whitelist = {str(item) for item in raw.person_ceiling_whitelist}
        if raw.inherit_qq_whitelist_ceiling:
            person_whitelist.update(str(item) for item in self._settings.qq.whitelist)
        ceilings = RelationshipCeilings(
            default=raw.default_ceiling,
            whitelist=raw.whitelist_ceiling,
            person_whitelist=frozenset(person_whitelist),
            group_whitelist=frozenset(str(item) for item in raw.group_ceiling_whitelist),
        )
        return RelationshipPolicy(ceilings, raw)

    def _is_priority_user(self, platform_user_id: str) -> bool:
        return platform_user_id in {str(item) for item in self._settings.qq.whitelist}
