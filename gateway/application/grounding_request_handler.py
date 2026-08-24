from __future__ import annotations

from gateway.social_router import SocialRouter
from shared.configuration.global_settings import GroundingSettings
from shared.contracts.rpc.grounding import (
    ResolvePeopleRequest,
    ResolvePeopleResponse,
    SearchGroupHistoryRequest,
    SearchGroupHistoryResponse,
)
from shared.contracts.social import SocialMessage
from shared.contracts.tools import ToolExecutionContext
from shared.domain.entity_grounding_facade import EntityGroundingFacade


class GroundingRequestHandler:
    def __init__(
        self,
        grounding: EntityGroundingFacade,
        router: SocialRouter,
        settings: GroundingSettings,
    ) -> None:
        self._grounding = grounding
        self._router = router
        self._settings = settings

    def message_context(self, message: SocialMessage, ai_id: str) -> ToolExecutionContext:
        return ToolExecutionContext(
            ai_id=ai_id,
            account_id=message.account_id,
            conversation_id=str(message.meta["conversation_id"]),
            platform=message.platform,
            chat_type=message.chat.chat_type.value,
            chat_id=message.chat.chat_id,
            sender_person_id=str(message.meta["person_id"]),
        )

    async def ground_message(self, message: SocialMessage, ai_id: str) -> dict:
        context = self.message_context(message, ai_id)
        entity_context = await self._grounding.fast_ground(
            context,
            message,
            recent_participants_limit=self._settings.recent_participants_limit,
            recent_lookback_sec=self._settings.recent_participants_lookback_sec,
        )
        await self._record_explicit_mentions(message, context)
        return entity_context.model_dump(mode="json")

    async def resolve_people(self, request: ResolvePeopleRequest) -> ResolvePeopleResponse:
        await self._require_valid_group_context(request.context)
        return await self._grounding.resolve_people(
            request.context,
            request.mention,
            self._settings.candidate_limit,
        )

    async def search_group_history(
        self,
        request: SearchGroupHistoryRequest,
    ) -> SearchGroupHistoryResponse:
        await self._require_valid_group_context(request.context)
        limit = request.limit if request.limit is not None else self._settings.history_default_limit
        if limit > self._settings.history_max_limit:
            raise ValueError("群聊历史检索数量超过配置上限")
        messages = await self._grounding.search_group_history(
            request.context,
            request.query,
            limit,
            self._settings.history_lookback_sec,
        )
        return SearchGroupHistoryResponse(messages=messages)

    async def _record_explicit_mentions(
        self,
        message: SocialMessage,
        context: ToolExecutionContext,
    ) -> None:
        for target in message.meta.get("at_user_ids", []):
            user_id = str(target)
            if message.to_ai and user_id == message.at_user_id:
                continue
            result = await self._grounding.resolve_people(
                context,
                user_id,
                self._settings.primary_candidate_limit,
            )
            if not result.candidates:
                continue
            name = result.candidates[0].display_name.strip()
            if not name or name in self._settings.ignored_mention_names:
                continue
            await self._grounding.record_mention_evidence(
                mention_text=name,
                person_id=result.candidates[0].person_id,
                scope_type="group",
                scope_id=context.chat_id,
                conversation_id=context.conversation_id,
                source_message_id=message.message_id,
                evidence_type="explicit_at",
                confidence=self._settings.explicit_mention_confidence,
            )

    async def _require_valid_group_context(self, context: ToolExecutionContext) -> None:
        owner = await self._router.owner_for(context.account_id)
        valid = context.is_group and owner == context.ai_id and await self._grounding.context_matches(context)
        if not valid:
            raise PermissionError("当前工具不具备有效群聊作用域")
