from __future__ import annotations

from gateway.application.grounding_request_handler import GroundingRequestHandler
from gateway.application.group_member_synchronizer import GroupMemberSynchronizer
from gateway.channels.channel import Channel
from gateway.social_router import SocialRouter
from shared.configuration.global_settings import LiveSettings
from shared.contracts.live import InteractionEvent, InteractionType, Viewer
from shared.contracts.social import SUBJ_SOCIAL_CHAT, ChatType, SocialMessage
from shared.contracts.turn import new_run_id
from shared.infrastructure.nats_bus import Bus
from shared.persistence.repositories.conversation_repository import ConversationRepository
from shared.persistence.repositories.identity_repository import IdentityRepository

SUBJ_LIVE_EVENTS = "live.events"


class GatewayMessageHandler:
    def __init__(
        self,
        *,
        channels: dict[str, Channel],
        identities: IdentityRepository,
        conversations: ConversationRepository,
        router: SocialRouter,
        group_members: GroupMemberSynchronizer,
        grounding: GroundingRequestHandler,
        bus: Bus,
        live_settings: LiveSettings,
        priority_user_ids: frozenset[str],
    ) -> None:
        self._channels = channels
        self._identities = identities
        self._conversations = conversations
        self._router = router
        self._group_members = group_members
        self._grounding = grounding
        self._bus = bus
        self._live_settings = live_settings
        self._priority_user_ids = priority_user_ids

    async def handle(self, message: SocialMessage) -> None:
        message.meta["run_id"] = new_run_id()
        if message.platform == "qq":
            message.meta["priority_contact"] = str(message.sender.user_id) in self._priority_user_ids
        if message.chat.chat_type == ChatType.GROUP and message.chat.chat_id.startswith("live:"):
            await self._publish_live_interaction(message)
            return

        message = await self._channels[message.account_id].hydrate_message(message)
        identity_id, person_id = await self._identities.resolve_or_create(
            message.platform,
            message.account_id,
            message.sender.user_id,
            message.sender.name,
        )
        message.meta["platform_identity_id"] = identity_id
        message.meta["person_id"] = person_id
        message.meta["conversation_id"] = await self._conversations.get_or_create(
            message.platform,
            message.account_id,
            message.chat.chat_id,
            message.chat.chat_type.value,
        )
        turn = await self._router.route(message)
        message.meta["ai_id"] = turn.ai_id
        if message.chat.chat_type == ChatType.GROUP:
            await self._group_members.sync(message)
            message.meta["entity_context"] = await self._grounding.ground_message(message, turn.ai_id)
        await self._conversations.record_inbound(message, turn.ai_id)
        await self._bus.publish_model(SUBJ_SOCIAL_CHAT.format(ai_id=turn.ai_id), message)

    async def _publish_live_interaction(self, message: SocialMessage) -> None:
        event = InteractionEvent(
            type=InteractionType(message.meta["bili_type"]),
            actor=Viewer(uid=int(message.sender.user_id), name=message.sender.name),
            importance=self._live_settings.default_importance,
            content=message.text,
            meta=message.meta,
            ai_target=message.at_user_id,
            context_metadata={"account_id": message.account_id},
        )
        await self._bus.publish_model(SUBJ_LIVE_EVENTS, event)
